"""Production Agent — 생산/품질/납기 분석"""

from datetime import datetime, timedelta
from app.agents.base import BaseAgent
from app.agents.tools.mssql_tools import TOOL_QUERY_PRODUCTION_DB, handle_query_db
from app.agents.tools.slack_tools import TOOL_SEND_SLACK, handle_send_slack
from app.agents.tools.report_tools import TOOL_SAVE_REPORT, handle_save_report
from app.config import FACTORY_NAMES


class ProductionAgent(BaseAgent):
    agent_type = "PRODUCTION"

    @property
    def system_prompt(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        today_db = today.replace("-", "")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        return f"""당신은 화장품 제조 공장의 자율 생산 분석 에이전트입니다.
MES 데이터베이스를 실시간으로 조회하여 생산 현황을 분석하고 인사이트를 제공합니다.

오늘: {today} (DB형식: {today_db})
어제: {yesterday}

[공장 코드]
{chr(10).join(f'- {k} = {v}' for k, v in FACTORY_NAMES.items())}

[주요 테이블]
MWIPORDSTS: 작업지시 (ORD_DATE, FACTORY_CODE, LINE_CODE, ORD_QTY=계획, ORD_OUT_QTY=실적, RCV_GOOD_QTY=양품, RCV_LOSS_QTY=불량, ORD_STATUS)
MWIPLOTSTS: Lot 현황 (HOLD_FLAG, RWK_FLAG)
MWIPLOTMVH: Lot 이동이력 (PROC_TIME, QUEUE_TIME)
MWIPMATDEF: 자재정보 (MAT_CODE, MAT_DESC)
MWIPBOMCMP: BOM (BOM_SET_CODE, CHILD_MAT_CODE, COMPONENT_QTY)
CINVBASDAT: 재고 (MAT_CODE, QTY, STATUS, USE_TERM)

[분석 기준]
- 달성률 = 실적/계획 × 100 (%)
- 위험: 달성률 80% 미만 → 경보, 60% 미만 → 긴급
- 불량: 0.5% 초과 → 주의, 1% 초과 → 경보
- 항상 ORD_STATUS NOT IN ('DELETE') 조건 포함
- 숫자는 천단위 구분기호(,) 포함"""

    @property
    def tools(self) -> list[dict]:
        return [TOOL_QUERY_PRODUCTION_DB, TOOL_SEND_SLACK, TOOL_SAVE_REPORT]

    def handle_tool(self, name: str, tool_input: dict) -> str:
        if name == "query_production_db":
            return handle_query_db(tool_input)
        elif name == "send_slack_notification":
            return handle_send_slack(tool_input)
        elif name == "save_report":
            return handle_save_report(tool_input)
        return f"알 수 없는 도구: {name}"
