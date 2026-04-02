"""Finance Agent — 매출/수주/재무 분석"""

from datetime import datetime
from app.agents.base import BaseAgent
from app.agents.tools.mssql_tools import TOOL_QUERY_SALES_DB, handle_query_db
from app.agents.tools.slack_tools import TOOL_SEND_SLACK, handle_send_slack
from app.agents.tools.report_tools import TOOL_SAVE_REPORT, handle_save_report


class FinanceAgent(BaseAgent):
    agent_type = "FINANCE"

    @property
    def system_prompt(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""당신은 제조업 재무/매출 분석 전문 AI 에이전트입니다.

오늘: {today}

[역할]
1. 수주/매출 현황 분석 (고객별, 제품별, 기간별)
2. 납기 리스크 식별 (지연 건, 미출하 건)
3. KPI 추적 (매출 달성률, 수주잔고, 재고회전율)
4. 경영진 브리핑 자료 생성

[주요 테이블]
IWIPORDSTS: 수주 (SO_NO, CUSTOMER_CODE, MAT_CODE, SO_QTY, DELIVERY_DATE, SO_STATUS)
IINVSHPMST: 출하 (SHIP_NO, SHIP_STATUS, SHIP_DATE, CUSTOMER_CODE)
CINVBASDAT: 재고 (MAT_CODE, QTY, STATUS, USE_TERM, LOT_NO)
MWIPORDSTS: 작업지시 (생산 실적 참조)
MWIPMATDEF: 자재마스터 (MAT_CODE, MAT_DESC, UNIT)

[규칙]
- 금액은 원 단위, 천단위 구분기호 포함
- 수량은 개 단위
- 달성률 = 실적/계획 × 100 (%)
- 답변은 한국어, 핵심 위주 정리
- 표나 목록으로 시각화"""

    @property
    def tools(self) -> list[dict]:
        return [TOOL_QUERY_SALES_DB, TOOL_SEND_SLACK, TOOL_SAVE_REPORT]

    def handle_tool(self, name: str, tool_input: dict) -> str:
        if name == "query_sales_db":
            return handle_query_db(tool_input)
        elif name == "send_slack_notification":
            return handle_send_slack(tool_input)
        elif name == "save_report":
            return handle_save_report(tool_input)
        return f"알 수 없는 도구: {name}"
