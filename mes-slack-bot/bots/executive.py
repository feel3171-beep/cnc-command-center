"""경영진 봇 — 일일/주간 경영 브리핑, 원페이지 요약"""

from datetime import datetime, timedelta
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct, status_emoji, change_arrow,
    divider, header_block, section_block, context_block,
)


def get_daily_kpi(plan_date):
    """일일 KPI 전체 요약"""
    sql = """
        SELECT
            SUM(ORD_QTY) as PLAN_QTY,
            SUM(ORD_OUT_QTY) as PROD_QTY,
            SUM(RCV_GOOD_QTY) as GOOD_QTY,
            SUM(RCV_LOSS_QTY) as LOSS_QTY,
            COUNT(*) as ORD_COUNT,
            COUNT(DISTINCT FACTORY_CODE) as FAC_COUNT,
            COUNT(DISTINCT LINE_CODE) as LINE_COUNT
        FROM MWIPORDSTS
        WHERE PLAN_DATE = %s
    """
    return db.query_one(sql, (plan_date,))


def get_factory_kpi(plan_date):
    """공장별 KPI"""
    sql = """
        SELECT
            FACTORY_CODE,
            SUM(ORD_QTY) as PLAN_QTY,
            SUM(ORD_OUT_QTY) as PROD_QTY,
            SUM(RCV_GOOD_QTY) as GOOD_QTY,
            SUM(RCV_LOSS_QTY) as LOSS_QTY,
            CASE WHEN SUM(ORD_QTY) > 0
                 THEN CAST(100.0 * SUM(ORD_OUT_QTY) / SUM(ORD_QTY) AS decimal(5,2))
                 ELSE 0 END as ACHIEVEMENT,
            CASE WHEN SUM(RCV_GOOD_QTY + RCV_LOSS_QTY) > 0
                 THEN CAST(100.0 * SUM(RCV_GOOD_QTY) / SUM(RCV_GOOD_QTY + RCV_LOSS_QTY) AS decimal(5,2))
                 ELSE 100 END as YIELD_RATE
        FROM MWIPORDSTS
        WHERE PLAN_DATE = %s
        GROUP BY FACTORY_CODE
        ORDER BY FACTORY_CODE
    """
    return db.query(sql, (plan_date,))


def get_defect_top3(plan_date):
    """불량률 Top 3 품목"""
    sql = """
        SELECT TOP 3
            o.MAT_CODE, m.MAT_DESC,
            SUM(o.RCV_LOSS_QTY) as LOSS_QTY,
            CASE WHEN SUM(o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) > 0
                 THEN CAST(100.0 * SUM(o.RCV_LOSS_QTY) / SUM(o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) AS decimal(5,2))
                 ELSE 0 END as DEFECT_RATE
        FROM MWIPORDSTS o
        LEFT JOIN MWIPMATDEF m ON o.FACTORY_CODE = m.FACTORY_CODE AND o.MAT_CODE = m.MAT_CODE
        WHERE o.PLAN_DATE = %s
          AND (o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) > 100
        GROUP BY o.MAT_CODE, m.MAT_DESC
        HAVING SUM(o.RCV_LOSS_QTY) > 0
        ORDER BY DEFECT_RATE DESC
    """
    return db.query(sql, (plan_date,))


def count_issues(plan_date):
    """이슈 카운트"""
    unstarted = db.query_one("""
        SELECT COUNT(*) as CNT FROM MWIPORDSTS
        WHERE ORD_STATUS = 'CONFIRM' AND ORD_OUT_QTY = 0
          AND PLAN_DATE < %s AND LEN(PLAN_DATE) = 8
    """, (plan_date,))

    alarms = db.query_one("""
        SELECT COUNT(*) as CNT FROM MADMALMHIS
        WHERE ACK_FLAG = 0 AND ALARM_LEVEL IN ('WARNING', 'CRITICAL')
    """)

    expiring = db.query_one("""
        SELECT COUNT(*) as CNT FROM CINVBASDAT
        WHERE USE_TERM IS NOT NULL AND LEN(USE_TERM) = 8
          AND STATUS = 'S' AND QTY > 0
          AND DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112)) BETWEEN 0 AND 30
    """)

    return {
        "unstarted": (unstarted or {}).get("CNT", 0),
        "alarms": (alarms or {}).get("CNT", 0),
        "expiring": (expiring or {}).get("CNT", 0),
    }


def get_forecast_summary():
    """미래 예측 종합 요약"""
    parts = []

    # 미완료 작업지시 잔량
    backlog = db.query_one("""
        SELECT COUNT(*) as CNT, SUM(ORD_QTY - ORD_OUT_QTY) as REMAIN_QTY
        FROM MWIPORDSTS
        WHERE ORD_STATUS = 'CONFIRM' AND ORD_OUT_QTY < ORD_QTY AND ORD_QTY > 0
          AND FACTORY_CODE IN ('1100','1200','1300')
    """)
    if backlog and backlog["CNT"]:
        parts.append(f"\U0001f4cb 미완료 작업지시: {backlog['CNT']}건 (잔여 {fmt_num(backlog['REMAIN_QTY'])}개)")

    # 자재 부족 예측
    shortage = db.query_one("""
        SELECT COUNT(*) as CNT
        FROM (
            SELECT b.CHILD_MAT_CODE,
                SUM(o.ORD_QTY * b.COMPONENT_QTY / 1000.0) as NEED,
                ISNULL(inv.STK, 0) as STK
            FROM MWIPORDSTS o
            INNER JOIN MWIPBOMCMP b ON o.MAT_CODE = b.BOM_SET_CODE
            LEFT JOIN (SELECT MAT_CODE, SUM(QTY) as STK FROM CINVBASDAT WHERE STATUS='S' AND QTY>0 GROUP BY MAT_CODE) inv
                ON b.CHILD_MAT_CODE = inv.MAT_CODE
            WHERE o.ORD_STATUS = 'CONFIRM' AND o.ORD_OUT_QTY = 0
              AND o.PLAN_DATE BETWEEN CONVERT(char(8), GETDATE(), 112) AND CONVERT(char(8), DATEADD(day,7,GETDATE()), 112)
            GROUP BY b.CHILD_MAT_CODE, inv.STK
            HAVING ISNULL(inv.STK, 0) < SUM(o.ORD_QTY * b.COMPONENT_QTY / 1000.0)
        ) t
    """)
    if shortage and shortage["CNT"]:
        parts.append(f"\U0001f4e6 7일내 자재 부족 예상: {shortage['CNT']}건")

    # 미출하 건
    unshipped = db.query_one("""
        SELECT COUNT(*) as CNT
        FROM MINVSHPMST
        WHERE SHIP_STATUS IN ('REQUEST', 'RESV', 'CONFIRM')
    """)
    if unshipped and unshipped["CNT"]:
        parts.append(f"\U0001f69a 미출하 건: {unshipped['CNT']}건")

    if parts:
        return "*\U0001f52e 미래 예측*\n  " + "\n  ".join(parts)
    return None


def run_daily(target_date=None):
    """일일 경영 브리핑"""
    today = target_date or datetime.now().strftime("%Y%m%d")
    yesterday = (datetime.strptime(today, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    date_str = f"{today[:4]}-{today[4:6]}-{today[6:]}"

    kpi = get_daily_kpi(today)
    prev_kpi = get_daily_kpi(yesterday)
    factories = get_factory_kpi(today)
    defects = get_defect_top3(today)
    issues = count_issues(today)

    if not kpi or not kpi["PLAN_QTY"]:
        send_message(f"\U0001f4ca 경영 브리핑 ({date_str}): 금일 생산 데이터 없음")
        return

    plan = kpi["PLAN_QTY"] or 0
    prod = kpi["PROD_QTY"] or 0
    good = kpi["GOOD_QTY"] or 0
    loss = kpi["LOSS_QTY"] or 0
    ach_pct = (prod / plan * 100) if plan > 0 else 0
    yield_pct = (good / (good + loss) * 100) if (good + loss) > 0 else 100
    prev_prod = prev_kpi["PROD_QTY"] if prev_kpi else None

    blocks = [
        header_block(f"\U0001f4ca 일일 경영 브리핑 ({date_str})"),
        section_block(
            f"*\U0001f3ed 생산*\n"
            f"  달성률: *{fmt_pct(ach_pct)}* {status_emoji(ach_pct)} | "
            f"{fmt_num(prod)} / {fmt_num(plan)} {change_arrow(prod, prev_prod)}\n"
            f"  수율: *{fmt_pct(yield_pct)}* | 양품 {fmt_num(good)} | 불량 {fmt_num(loss)}\n"
            f"  가동: {kpi['FAC_COUNT']}공장 {kpi['LINE_COUNT']}라인 {kpi['ORD_COUNT']}건"
        ),
        divider(),
    ]

    # 공장별 한줄 요약
    if factories:
        fac_lines = ["*공장별 요약*"]
        for f in factories:
            fc = config.FACTORY_NAMES.get(f["FACTORY_CODE"], f["FACTORY_CODE"])
            fac_lines.append(
                f"  {status_emoji(f['ACHIEVEMENT'])} {fc} | "
                f"달성 {fmt_pct(f['ACHIEVEMENT'])} | 수율 {fmt_pct(f['YIELD_RATE'])} | "
                f"생산 {fmt_num(f['PROD_QTY'])}"
            )
        blocks.append(section_block("\n".join(fac_lines)))
        blocks.append(divider())

    # 불량 Top 3
    if defects:
        def_lines = ["*\U0001f534 불량 Top 3*"]
        for i, d in enumerate(defects, 1):
            mat = (d["MAT_DESC"] or d["MAT_CODE"])[:25]
            def_lines.append(f"  {i}. {mat} — {fmt_pct(d['DEFECT_RATE'])} ({fmt_num(d['LOSS_QTY'])}개)")
        blocks.append(section_block("\n".join(def_lines)))
        blocks.append(divider())

    # 이슈 요약
    issue_parts = []
    if issues["unstarted"] > 0:
        issue_parts.append(f"\u26a0\ufe0f 미착수 작업지시 {issues['unstarted']}건")
    if issues["alarms"] > 0:
        issue_parts.append(f"\U0001f514 미확인 알람 {issues['alarms']}건")
    if issues["expiring"] > 0:
        issue_parts.append(f"\u23f0 유통기한 임박 자재 {issues['expiring']}건")
    if issue_parts:
        blocks.append(section_block("*\u26a1 이슈*\n  " + "\n  ".join(issue_parts)))
    else:
        blocks.append(section_block("*\u26a1 이슈*\n  \u2705 특이사항 없음"))
    blocks.append(divider())

    # 예측 요약
    forecast = get_forecast_summary()
    if forecast:
        blocks.append(section_block(forecast))

    send_message(f"경영 브리핑 ({date_str})", blocks=blocks)
    print(f"[OK] 경영진 일일 브리핑 전송 ({date_str})")


def run(target_date=None):
    run_daily(target_date)


if __name__ == "__main__":
    run()
