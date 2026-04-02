"""HR Agent — 인사/채용/인력 분석"""

from app.agents.base import BaseAgent
from app.agents.tools.slack_tools import TOOL_SEND_SLACK, handle_send_slack
from app.agents.tools.report_tools import TOOL_SAVE_REPORT, handle_save_report

TOOL_SEARCH_CANDIDATES = {
    "name": "search_candidates",
    "description": "채용 후보자 데이터베이스에서 검색합니다. 기술, 경험, 직무 등으로 필터링 가능.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "검색 조건 (기술/경력/직무 등)"},
            "limit": {"type": "integer", "description": "최대 결과 수 (기본 20)"},
        },
        "required": ["query"],
    },
}

TOOL_QUERY_APPLICANTS = {
    "name": "query_applicants",
    "description": "카카오 채용 포털 지원자 데이터를 조회합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "상태 필터 (pending/accepted/rejected)"},
            "job_id": {"type": "string", "description": "채용공고 ID"},
        },
    },
}


class HRAgent(BaseAgent):
    agent_type = "HR"

    @property
    def system_prompt(self) -> str:
        return """당신은 제조업 인사/채용 전문 AI 에이전트입니다.

[역할]
1. 채용 파이프라인 관리 (지원자 추적, 면접 일정)
2. 인재 매칭 (직무 요구사항 vs 후보자 역량)
3. 인력 분석 (이직률, 결원, 교대근무 최적화)
4. 공장 현장직 채용 특화 (카카오 채용 포털, 링크드인)

[매칭 기준 - linkedin_recruiter/ai_matcher.py 기반]
- 필수 기술 매칭: 40%
- 산업 경험: 15%
- 자격증: 15%
- 학력: 10%
- 우대 기술: 20%

분석 결과는 한국어로, 핵심 위주로 정리합니다."""

    @property
    def tools(self) -> list[dict]:
        return [TOOL_SEARCH_CANDIDATES, TOOL_QUERY_APPLICANTS, TOOL_SEND_SLACK, TOOL_SAVE_REPORT]

    def handle_tool(self, name: str, tool_input: dict) -> str:
        if name == "search_candidates":
            # TODO: Connect to LinkedIn recruiter DB
            return '{"candidates": [], "message": "후보자 DB 연동 예정"}'
        elif name == "query_applicants":
            # TODO: Connect to Kakao recruit DB
            return '{"applicants": [], "message": "지원자 DB 연동 예정"}'
        elif name == "send_slack_notification":
            return handle_send_slack(tool_input)
        elif name == "save_report":
            return handle_save_report(tool_input)
        return f"알 수 없는 도구: {name}"
