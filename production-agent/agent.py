"""
생산 분석 에이전트 (자율 실행 버전)
──────────────────────────────────────────────────────────────────────────────
[챗봇 vs 에이전트 차이]

챗봇 (main.py /api/chat):
  사람 질문 → Claude 답변
  사람이 없으면 아무것도 안 함

에이전트 (이 파일):
  스케줄 → Claude가 스스로 판단 → SQL 실행 → Slack 발송
  사람 없이도 매일 자동 실행
  Claude가 무엇을 조회할지, 어떻게 분석할지, 언제 끝낼지 스스로 결정

──────────────────────────────────────────────────────────────────────────────
실행 방법:
  python agent.py                     # 즉시 실행 (테스트)
  python agent.py --date 2026-03-28   # 특정 날짜 분석
"""

import argparse
import decimal
import io
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Windows 콘솔 UTF-8 출력
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import anthropic
import pyodbc
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── 설정 ────────────────────────────────────────────────────────────────────
CLAUDE_MODEL    = "claude-opus-4-6"
SLACK_WEBHOOK   = os.getenv("SLACK_WEBHOOK_URL", "")
REPORTS_DIR     = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

ODBC_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server",
]

FACTORY_NAMES = {"1100": "퍼플", "1200": "그린", "1300": "제3공장"}


# ── DB 헬퍼 ──────────────────────────────────────────────────────────────────
def get_conn_str() -> str:
    for drv in ODBC_DRIVERS:
        if drv in pyodbc.drivers():
            return (
                f"DRIVER={{{drv}}};"
                "SERVER=192.161.0.16,1433;DATABASE=MES;"
                "UID=mestmp;PWD=cncmgr123!;"
                "Encrypt=no;TrustServerCertificate=yes;"
            )
    raise RuntimeError("ODBC Driver를 찾을 수 없습니다.")


def run_query(sql: str, params=None) -> list[dict]:
    conn = pyodbc.connect(get_conn_str())
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            row = {}
            for c, v in zip(cols, r):
                if isinstance(v, decimal.Decimal):
                    v = float(v)
                elif isinstance(v, datetime):
                    v = str(v)
                row[c] = v
            rows.append(row)
        return rows
    finally:
        conn.close()


# ── 툴 실행 핸들러 ────────────────────────────────────────────────────────────
def handle_tool(name: str, tool_input: dict) -> str:
    """Claude가 요청한 툴을 실행하고 결과를 반환"""

    if name == "query_production_db":
        sql  = tool_input["sql"]
        desc = tool_input.get("description", "")
        print(f"  🔍 SQL 실행: {desc or sql[:60]}...")
        try:
            rows = run_query(sql)
            result = json.dumps(rows[:300], ensure_ascii=False, default=str)
            print(f"     → {len(rows)}행 반환")
            return result
        except Exception as e:
            err = f"SQL 오류: {e}"
            print(f"     ❌ {err}")
            return err

    elif name == "send_slack_notification":
        message = tool_input["message"]
        level   = tool_input.get("level", "info")   # info | warning | critical
        print(f"  📨 Slack 발송 ({level})...")

        # 이모지 설정
        emoji = {"info": "📊", "warning": "⚠️", "critical": "🚨"}.get(level, "📊")
        payload = {
            "text": f"{emoji} *생산 분석 에이전트*\n{message}",
            "mrkdwn": True,
        }

        if SLACK_WEBHOOK:
            try:
                resp = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
                if resp.status_code == 200:
                    print("     ✅ Slack 발송 성공")
                    return "Slack 발송 완료"
                else:
                    return f"Slack 오류: HTTP {resp.status_code}"
            except Exception as e:
                return f"Slack 연결 실패: {e}"
        else:
            # Webhook 미설정 시 콘솔 출력 (개발/테스트용)
            print(f"\n{'='*60}")
            print(f"[Slack 미전송 - SLACK_WEBHOOK_URL 미설정]\n{message}")
            print(f"{'='*60}\n")
            return "Slack 미발송 (웹훅 미설정) - 콘솔 출력으로 대체"

    elif name == "save_report":
        content  = tool_input["content"]
        date_str = tool_input.get("date", datetime.now().strftime("%Y%m%d"))
        path     = REPORTS_DIR / f"report_{date_str}.txt"
        path.write_text(content, encoding="utf-8")
        print(f"  💾 리포트 저장: {path}")
        return f"리포트 저장 완료: {path}"

    return f"알 수 없는 툴: {name}"


# ── 에이전트 실행 ─────────────────────────────────────────────────────────────
def run_agent(target_date: str | None = None) -> str:
    """
    에이전트의 핵심 – 사람의 질문 없이 스스로 미션을 수행.

    [챗봇과의 결정적 차이]
    챗봇: messages = [{"role": "user", "content": 사람_질문}]
    에이전트: messages = [{"role": "user", "content": 자동_생성된_미션}]
              → Claude가 무엇을 할지 스스로 결정하고 루프를 반복
    """
    today = target_date or datetime.now().strftime("%Y-%m-%d")
    today_db = today.replace("-", "")
    yesterday_db = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y%m%d")

    print(f"\n🤖 생산 분석 에이전트 시작 [{today}]")
    print(f"   모델: {CLAUDE_MODEL} (adaptive thinking)")
    print("-" * 50)

    from dotenv import dotenv_values
    env = dotenv_values(Path(__file__).parent / ".env")
    api_key = env.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    # ── 툴 정의 ──────────────────────────────────────────────────────────────
    tools = [
        {
            "name": "query_production_db",
            "description": (
                "MES 데이터베이스에서 생산 데이터를 조회합니다. "
                "MWIPORDSTS(작업지시: ORD_DATE='YYYYMMDD', FACTORY_CODE, LINE_CODE, "
                "ORD_QTY=계획, ORD_OUT_QTY=실적, RCV_GOOD_QTY=양품, RCV_LOSS_QTY=불량, "
                "ORD_STATUS NOT IN('DELETE')), "
                "MWIPLOTSTS(Lot현황: HOLD_FLAG, RWK_FLAG), "
                "MWIPLOTMVH(이력: PROC_TIME초, QUEUE_TIME초) 사용 가능."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "sql":         {"type": "string", "description": "실행할 T-SQL 쿼리"},
                    "description": {"type": "string", "description": "이 쿼리의 목적"},
                },
                "required": ["sql"],
            },
        },
        {
            "name": "send_slack_notification",
            "description": "분석 결과를 Slack 채널에 발송합니다. 일반 리포트는 info, 주의 필요 시 warning, 즉각 대응 필요 시 critical 사용.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "발송할 메시지 (마크다운 사용 가능)"},
                    "level":   {"type": "string", "enum": ["info", "warning", "critical"], "description": "알림 레벨"},
                },
                "required": ["message", "level"],
            },
        },
        {
            "name": "save_report",
            "description": "분석 리포트를 파일로 저장합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "저장할 리포트 내용"},
                    "date":    {"type": "string", "description": "날짜 (YYYYMMDD)"},
                },
                "required": ["content"],
            },
        },
    ]

    # ── 시스템 프롬프트 ───────────────────────────────────────────────────────
    system = f"""당신은 화장품 제조 공장의 자율 생산 분석 에이전트입니다.
매일 스케줄에 따라 자동 실행되며, 사람의 지시 없이 스스로 데이터를 분석하고 결과를 발송합니다.

오늘 날짜: {today}
어제 날짜: {yesterday_db[:4]}-{yesterday_db[4:6]}-{yesterday_db[6:]}

[분석 기준]
- 공장: 1100=퍼플, 1200=그린, 1300=제3공장
- 달성률 = 실적/계획 × 100 (%)
- 위험 기준: 달성률 80% 미만 → 경보, 60% 미만 → 긴급
- 불량률 기준: 0.5% 초과 → 주의, 1% 초과 → 경보

[수행 방식]
1. 필요한 SQL을 스스로 작성하여 query_production_db로 조회
2. 어제 대비 비교 분석 수행
3. 이상 항목 자동 감지
4. Slack 리포트 발송 (이상 없으면 info, 있으면 warning 또는 critical)
5. save_report로 파일 저장

숫자는 항상 천단위 구분기호(,) 포함."""

    # ── 미션 (핵심 차이: 사람이 아닌 스케줄이 트리거) ─────────────────────────
    mission = f"""[자율 실행 미션] {today} 생산 분석

다음을 자율적으로 수행하세요:

1. {today} 공장별 생산 실적 조회 (계획/실적/달성률/불량률)
2. {yesterday_db[:4]}-{yesterday_db[4:6]}-{yesterday_db[6:]} 대비 변화 분석
3. 이상 항목 자동 감지:
   - 달성률 80% 미만 라인
   - 전일 대비 달성률 20%p 이상 하락
   - 불량률 급증 (0.5% 초과)
   - Hold 또는 재작업 Lot 급증
4. 핵심 인사이트 도출
5. Slack 리포트 발송 (이상 여부에 따라 레벨 결정)
6. 리포트 파일 저장

스스로 필요한 SQL을 결정하고 실행하여 미션을 완료하세요."""

    messages = [{"role": "user", "content": mission}]

    # ── 에이전트 루프 (Claude가 스스로 반복 결정) ────────────────────────────
    turn = 0
    max_turns = 15

    while turn < max_turns:
        turn += 1
        print(f"\n[턴 {turn}] Claude 실행 중...")

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8096,
            thinking={"type": "adaptive"},   # Claude가 스스로 얼마나 생각할지 결정
            system=system,
            tools=tools,
            messages=messages,
        )

        # 응답 내용 출력
        for block in response.content:
            if hasattr(block, "thinking") and block.thinking:
                print(f"  💭 [사고] {block.thinking[:100]}...")
            elif hasattr(block, "text") and block.text:
                print(f"  💬 {block.text[:200]}")

        # 종료 조건: Claude가 더 이상 툴 호출 없이 완료
        if response.stop_reason == "end_turn":
            final_text = next(
                (b.text for b in response.content if hasattr(b, "text") and b.text),
                "미션 완료"
            )
            print(f"\n✅ 에이전트 완료 ({turn}턴)")
            return final_text

        # 툴 호출 처리
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    result = handle_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

            messages.append({"role": "user", "content": tool_results})

    print(f"\n⚠️ 최대 턴 수({max_turns}) 도달")
    return "최대 턴 수 초과로 미션 중단"


# ── 진입점 ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="생산 분석 에이전트")
    parser.add_argument("--date", help="분석 날짜 (YYYY-MM-DD), 기본값: 오늘")
    args = parser.parse_args()

    result = run_agent(args.date)
    print(f"\n{'='*50}")
    print("최종 결과:")
    print(result)
    print(f"{'='*50}")
