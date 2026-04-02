"""
BaseAgent — 자율 에이전트 루프 (production-agent/agent.py 패턴)

모든 에이전트는 이 패턴을 공유:
1. 미션 프롬프트 수신
2. 시스템 프롬프트 + 도구 정의
3. Claude 호출 루프 (tool_use → handle → 반복 → end_turn)
4. 결과 반환 + 로그 저장
"""

import json
from datetime import datetime
from typing import Optional

import anthropic
from app.config import ANTHROPIC_API_KEY, OPUS_MODEL, SONNET_MODEL


class BaseAgent:
    """Override: agent_type, system_prompt, tools, handle_tool"""

    agent_type: str = "base"
    max_turns: int = 15
    model: str = OPUS_MODEL

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.tool_log: list[dict] = []
        self.total_tokens: int = 0

    @property
    def system_prompt(self) -> str:
        raise NotImplementedError

    @property
    def tools(self) -> list[dict]:
        raise NotImplementedError

    def handle_tool(self, name: str, tool_input: dict) -> str:
        raise NotImplementedError

    def run(self, mission: str) -> dict:
        """Execute the autonomous agent loop. Returns {result, turns, tool_log, tokens}."""
        messages = [{"role": "user", "content": mission}]
        self.tool_log = []
        self.total_tokens = 0

        for turn in range(1, self.max_turns + 1):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8096,
                thinking={"type": "adaptive"},
                system=self.system_prompt,
                tools=self.tools,
                messages=messages,
            )

            self.total_tokens += (response.usage.input_tokens + response.usage.output_tokens)

            if response.stop_reason == "end_turn":
                final_text = next(
                    (b.text for b in response.content if hasattr(b, "text") and b.text),
                    "미션 완료",
                )
                return {
                    "result": final_text,
                    "turns": turn,
                    "tool_log": self.tool_log,
                    "tokens": self.total_tokens,
                }

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        result = self.handle_tool(block.name, block.input)
                        self.tool_log.append({
                            "turn": turn,
                            "tool": block.name,
                            "input": block.input,
                            "output_preview": result[:500] if result else "",
                            "timestamp": datetime.now().isoformat(),
                        })
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})

        return {
            "result": f"최대 턴 수({self.max_turns}) 초과로 미션 중단",
            "turns": self.max_turns,
            "tool_log": self.tool_log,
            "tokens": self.total_tokens,
        }

    def chat(self, message: str, context: Optional[dict] = None):
        """Interactive chat mode — yields SSE events. Uses Sonnet for speed."""
        system = self.system_prompt
        if context:
            system += f"\n\n[현재 태스크 컨텍스트]\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        messages = []
        if context and context.get("chat_history"):
            for m in context["chat_history"]:
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": message})

        for turn in range(6):
            response = self.client.messages.create(
                model=SONNET_MODEL,
                max_tokens=4096,
                system=system,
                tools=self.tools,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text") and block.text:
                        yield {"type": "text", "content": block.text}
                return

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        yield {
                            "type": "tool_use",
                            "name": block.name,
                            "description": block.input.get("description", ""),
                        }
                        result = self.handle_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})

        yield {"type": "text", "content": "분석을 완료했습니다."}
