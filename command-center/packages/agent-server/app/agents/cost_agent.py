"""Cost Agent — 원가 분석 (데이터 연동 준비 중)"""

from app.agents.base import BaseAgent
from app.agents.tools.mssql_tools import TOOL_QUERY_PRODUCTION_DB, handle_query_db
from app.agents.tools.slack_tools import TOOL_SEND_SLACK, handle_send_slack
from app.agents.tools.report_tools import TOOL_SAVE_REPORT, handle_save_report

TOOL_QUERY_COST_DB = {
    "name": "query_cost_db",
    "description": (
        "원가 관련 데이터를 조회합니다. "
        "현재 MES에서 추출 가능한 원가 관련 데이터: "
        "MWIPBOMCMP(BOM: BOM_SET_CODE, CHILD_MAT_CODE, COMPONENT_QTY — 자재 소요량), "
        "CINVBASDAT(재고: MAT_CODE, QTY, STATUS — 재고 현황), "
        "MWIPORDSTS(생산실적: ORD_QTY, ORD_OUT_QTY, RCV_LOSS_QTY — 투입 대비 산출), "
        "MWIPLOTMVH(공정이력: PROC_TIME, QUEUE_TIME — 공정 시간=인건비 추정). "
        "직접 원가 테이블은 아직 없으므로 간접 추정 기반으로 분석합니다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "실행할 T-SQL SELECT 쿼리"},
            "description": {"type": "string", "description": "쿼리 목적"},
        },
        "required": ["sql"],
    },
}


class CostAgent(BaseAgent):
    agent_type = "COST"

    @property
    def system_prompt(self) -> str:
        return """당신은 제조업 원가 분석 전문 AI 에이전트입니다.

[역할]
1. 제품별 원가 구조 분석 (자재비, 가공비, 인건비 추정)
2. BOM 기반 자재 소요량 분석
3. 불량/로스 비용 산출
4. 공정 시간 기반 가공비 추정
5. 제품별 수익성 분석

[현재 사용 가능 데이터]
- MWIPBOMCMP: BOM 구성 (자재 소요량 계산)
- CINVBASDAT: 재고 현황 (자재 단가 추정 기준)
- MWIPORDSTS: 생산 실적 (투입 대비 산출, 불량 비용)
- MWIPLOTMVH: 공정 이력 (시간 × 시급 = 인건비 추정)
- MWIPMATDEF: 자재 마스터

[주의사항]
- 직접 원가 테이블이 아직 없으므로 간접 추정임을 명시
- BOM COMPONENT_QTY는 천분율(‰)이므로 /1000 필요
- 금액 추정 시 가정 사항을 명확히 기재
- 분석 결과는 한국어, 표 형식 선호"""

    @property
    def tools(self) -> list[dict]:
        return [TOOL_QUERY_COST_DB, TOOL_SEND_SLACK, TOOL_SAVE_REPORT]

    def handle_tool(self, name: str, tool_input: dict) -> str:
        if name == "query_cost_db":
            return handle_query_db(tool_input)
        elif name == "send_slack_notification":
            return handle_send_slack(tool_input)
        elif name == "save_report":
            return handle_save_report(tool_input)
        return f"알 수 없는 도구: {name}"
