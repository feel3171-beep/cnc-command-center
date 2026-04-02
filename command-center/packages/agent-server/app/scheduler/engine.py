"""
스케줄러 엔진 — APScheduler 기반 24/7 자동 실행
기존 mes-slack-bot/setup_scheduler.bat 의 10개 크론 작업 마이그레이션
"""

import asyncio
import json
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.agents.production_agent import ProductionAgent
from app.agents.hr_agent import HRAgent
from app.agents.finance_agent import FinanceAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scheduler")

# Agent instances
production_agent = ProductionAgent()
hr_agent = HRAgent()
finance_agent = FinanceAgent()


def run_production_briefing():
    """생산 브리핑 (08:00, 12:00, 17:00)"""
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"[Production] 생산 브리핑 시작 ({today})")
    result = production_agent.run(
        f"[자율 실행] {today} 생산 현황 브리핑을 수행하세요.\n"
        f"1. 공장별 생산 실적 (계획/실적/달성률/불량률)\n"
        f"2. 전일 대비 변화\n"
        f"3. 이상 항목 감지\n"
        f"4. Slack 리포트 발송"
    )
    logger.info(f"[Production] 완료 ({result['turns']}턴, {result['tokens']}토큰)")


def run_anomaly_alert():
    """이상 알림 (2시간마다)"""
    logger.info("[Production] 이상 알림 체크")
    result = production_agent.run(
        "달성률 80% 미만 라인, 불량률 0.5% 초과 품목, Hold/재작업 Lot을 조회하세요.\n"
        "이상 있으면 Slack에 warning 레벨로 발송. 없으면 조용히 종료."
    )
    logger.info(f"[Production] 이상 알림 완료 ({result['turns']}턴)")


def run_delivery_watch():
    """납기 감시 (07:30, 13:30)"""
    logger.info("[Production] 납기 감시")
    result = production_agent.run(
        "납기일 3일 이내 미완료 주문, 납기 변경 건, 미출하 건을 조회하세요.\n"
        "리스크 있으면 Slack warning 발송."
    )
    logger.info(f"[Production] 납기 감시 완료 ({result['turns']}턴)")


def run_executive_briefing():
    """경영진 브리핑 (18:00)"""
    logger.info("[Finance] 경영진 브리핑")
    result = finance_agent.run(
        "오늘의 경영진 브리핑을 작성하세요.\n"
        "1. 전체 생산 KPI (달성률, 수율)\n"
        "2. 공장별 요약\n"
        "3. 불량 Top 3\n"
        "4. 미완료 작업지시, 미확인 알람, 유통기한 임박 자재\n"
        "5. Slack에 info 레벨로 발송, 리포트 저장"
    )
    logger.info(f"[Finance] 경영진 브리핑 완료 ({result['turns']}턴)")


def run_weekly_report():
    """주간 리포트 (월요일 09:00)"""
    logger.info("[Production] 주간 리포트")
    result = production_agent.run(
        "지난 7일간 생산 추이를 분석하세요.\n"
        "일별/공장별 달성률 트렌드, 불량률 추이, 주요 이슈 요약.\n"
        "Slack에 상세 리포트 발송, 파일 저장."
    )
    logger.info(f"[Production] 주간 리포트 완료 ({result['turns']}턴)")


def run_hr_daily_briefing():
    """인사팀 일일 브리핑 (매일 10:00)"""
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"[HR] 인사팀 일일 브리핑 시작 ({today})")
    result = hr_agent.run(
        f"[자율 실행] {today} 기준 인사팀 일일 브리핑을 생성하세요.\n\n"
        f"반드시 아래 4개 섹션을 모두 포함해야 합니다:\n"
        f"[1] 전사 인원 현황 (본부 단위) — TO, 현원, 정규, 도급, 충원율, 충원필요\n"
        f"[2] 채용 현황 (본부 단위) — 채용요청(정/도), 입사예정(정/도), 미충원\n"
        f"[3] 입퇴사 현황 — 월별 순증감, 공장 퇴사 유형 추이 (정규/도급 분리)\n"
        f"[4] 인건비 현황 — 누적/월별, 정규직/도급직 분리\n\n"
        f"Google Sheets에서 인사 데이터를 읽어서 분석하세요.\n"
        f"MES DB에서 공장별 인원 데이터를 보완하세요.\n"
        f"완성된 리포트를 save_report로 저장하고 Slack으로 핵심 요약을 발송하세요."
    )
    logger.info(f"[HR] 인사팀 일일 브리핑 완료 ({result['turns']}턴)")


def run_recruitment_pipeline():
    """채용 파이프라인 (월요일 10:30)"""
    logger.info("[HR] 채용 파이프라인 체크")
    result = hr_agent.run(
        "현재 채용 파이프라인 현황을 확인하세요.\n"
        "본부별 채용요청/입사예정/미충원 현황을 정리하여 Slack 발송."
    )
    logger.info(f"[HR] 채용 파이프라인 완료 ({result['turns']}턴)")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # 생산 브리핑: 평일 08, 12, 17시
    scheduler.add_job(run_production_briefing, CronTrigger(hour="8,12,17", day_of_week="mon-fri"), id="prod_briefing")

    # 이상 알림: 평일 07~21시, 2시간마다
    scheduler.add_job(run_anomaly_alert, CronTrigger(hour="7-21/2", day_of_week="mon-fri"), id="anomaly_alert")

    # 납기 감시: 평일 07:30, 13:30
    scheduler.add_job(run_delivery_watch, CronTrigger(hour="7,13", minute="30", day_of_week="mon-fri"), id="delivery_watch")

    # 경영진 브리핑: 평일 18시
    scheduler.add_job(run_executive_briefing, CronTrigger(hour="18", day_of_week="mon-fri"), id="exec_briefing")

    # 주간 리포트: 월요일 09시
    scheduler.add_job(run_weekly_report, CronTrigger(hour="9", day_of_week="mon"), id="weekly_report")

    # 인사팀 일일 브리핑: 매일 평일 10시
    scheduler.add_job(run_hr_daily_briefing, CronTrigger(hour="10", day_of_week="mon-fri"), id="hr_daily_briefing")

    # 채용 파이프라인: 월요일 10:30
    scheduler.add_job(run_recruitment_pipeline, CronTrigger(hour="10", minute="30", day_of_week="mon"), id="recruitment_pipeline")

    return scheduler


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("C&C Command Center — 스케줄러 시작")
    logger.info("=" * 50)

    scheduler = create_scheduler()
    scheduler.start()

    jobs = scheduler.get_jobs()
    for job in jobs:
        logger.info(f"  {job.id}: 다음 실행 {job.next_run_time}")

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("스케줄러 종료")
