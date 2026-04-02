"""HR Agent — 인사팀 일일 브리핑 + 인력 분석"""

from datetime import datetime, timedelta
from app.agents.base import BaseAgent
from app.agents.tools.mssql_tools import TOOL_QUERY_PRODUCTION_DB, handle_query_db
from app.agents.tools.gsheet_tools import TOOL_READ_GSHEET, handle_read_gsheet
from app.agents.tools.slack_tools import TOOL_SEND_SLACK, handle_send_slack
from app.agents.tools.report_tools import TOOL_SAVE_REPORT, handle_save_report


class HRAgent(BaseAgent):
    agent_type = "HR"

    @property
    def system_prompt(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        year = datetime.now().year

        return f"""당신은 C&C 화장품 제조업의 인사 분석 AI 에이전트입니다.
매일 "인사팀 일일 브리핑"을 생성하여 경영진에게 전달합니다.

오늘: {today}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[인사팀 일일 브리핑 보고서 구조]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] 전사 인원 현황 (본부 단위)
본부 | TO(정원) | 현원 | 정규 | 도급 | 충원율 | 충원필요

본부 목록:
- 경영기획본부
- 생산기획부
- 생산본부(퍼플) — 1100 공장
- 생산본부(그린) — 1200 공장
- 생산본부(3공장) — 1300 공장
- 제품개발본부
- 연구소
- 전사 합계

계산: 충원율 = 현원/TO × 100, 충원필요 = TO - 현원

[2] 채용 현황 (본부 단위)
본부 | 채용요청(정) | 채용요청(도) | 입사예정(정) | 입사예정(도) | 미충원

[3] 입퇴사 현황
- {year}년 전사 순증감, 연간 총 입사, 연간 총 퇴사
- 월별 순증감 × 본부별 테이블
- 공장 퇴사 유형 추이 (정규직): 입사, 조기퇴사(3개월미만), 일반퇴사(3개월이상), 전체퇴사, 조기퇴사율
- 공장 퇴사 유형 추이 (도급직): 동일 구조

[4] {year}년 인건비 현황 (월별)
- 누적 인건비, 정규직 누적, 도급직 누적
- 월별 합계/정규직/도급직
- 전월 대비 변동

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[데이터 소스]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Google Sheets (ID: 1U5x5obWAd2FRFJX5ks4mJivl0bFXzBEbhqoR1rAtIeI)
   - 시트 "인사_인사팀": 공장별 일일 출근인원/근무시간
   - 시트 "인사_데이터": 통합 인원 데이터
   - 시트 "인사_MES": MES 연동 인원 데이터

2. MES DB (MSSQL) — 생산 인원 관련 추가 참조
   - MWIPORDSTS: 작업지시 (라인별 인원 배치)

3. 이전 브리핑 이메일 패턴을 참고하여 동일 형식으로 생성

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[작업 지침]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Google Sheets에서 최신 인사 데이터를 조회합니다
2. MES DB에서 공장별 작업지시 인원 데이터를 보완합니다
3. 4개 섹션 모두 포함된 인사팀 일일 브리핑을 생성합니다
4. 핵심 변동사항/리스크를 별도로 강조합니다
5. 충원율이 90% 미만인 본부는 ⚠️ 경고 표시합니다
6. 조기퇴사율이 50% 이상이면 🔴 위험 표시합니다
7. 숫자는 천단위 구분기호(,) 포함
8. Slack 발송 시 채널에 맞는 간결한 요약 + 전체 리포트 파일 저장"""

    @property
    def tools(self) -> list[dict]:
        return [
            TOOL_READ_GSHEET,
            TOOL_QUERY_PRODUCTION_DB,
            TOOL_SEND_SLACK,
            TOOL_SAVE_REPORT,
        ]

    def handle_tool(self, name: str, tool_input: dict) -> str:
        if name == "read_google_sheet":
            return handle_read_gsheet(tool_input)
        elif name == "query_production_db":
            return handle_query_db(tool_input)
        elif name == "send_slack_notification":
            return handle_send_slack(tool_input)
        elif name == "save_report":
            return handle_save_report(tool_input)
        return f"알 수 없는 도구: {name}"
