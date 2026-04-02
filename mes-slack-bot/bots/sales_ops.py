"""영업 담당자 봇 — 고객사별 진척, 납기 위험, 출하 현황, 검사 적체"""

from datetime import datetime, timedelta
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct, status_emoji,
    divider, header_block, section_block, context_block,
)


def get_customer_progress(plan_date):
    """고객사별 생산 달성률"""
    sql = """
        SELECT TOP 15
            o.CUSTOMER_CODE,
            c.CUSTOMER_DESC,
            COUNT(*) as ORD_COUNT,
            SUM(o.ORD_QTY) as PLAN_QTY,
            SUM(o.ORD_OUT_QTY) as PROD_QTY,
            SUM(o.RCV_GOOD_QTY) as GOOD_QTY,
            SUM(o.RCV_LOSS_QTY) as LOSS_QTY,
            CASE WHEN SUM(o.ORD_QTY) > 0
                 THEN CAST(100.0 * SUM(o.ORD_OUT_QTY) / SUM(o.ORD_QTY) AS decimal(5,2))
                 ELSE 0 END as ACHIEVEMENT
        FROM MWIPORDSTS o
        LEFT JOIN MWIPCUSDEF c ON o.FACTORY_CODE = c.FACTORY_CODE AND o.CUSTOMER_CODE = c.CUSTOMER_CODE
        WHERE o.PLAN_DATE >= %s
          AND o.CUSTOMER_CODE IS NOT NULL AND o.CUSTOMER_CODE != ''
        GROUP BY o.CUSTOMER_CODE, c.CUSTOMER_DESC
        HAVING SUM(o.ORD_QTY) > 0
        ORDER BY PLAN_QTY DESC
    """
    week_start = (datetime.strptime(plan_date, "%Y%m%d") - timedelta(days=6)).strftime("%Y%m%d")
    return db.query(sql, (week_start,))


def check_delivery_risk():
    """납기 위험 — 출하 계획 대비 미완료 건"""
    sql = """
        SELECT TOP 10
            s.SHIP_ORD_NO, s.SHIP_PLAN_DATE,
            s.SHIP_PLAN_QTY, s.SHIP_QTY,
            s.SHIP_STATUS, s.CUSTOMER_CODE,
            c.CUSTOMER_DESC,
            DATEDIFF(day, GETDATE(), CONVERT(datetime, s.SHIP_PLAN_DATE, 112)) as DAYS_LEFT
        FROM MINVSHPMST s
        LEFT JOIN MWIPCUSDEF c ON s.FACTORY_CODE = c.FACTORY_CODE AND s.CUSTOMER_CODE = c.CUSTOMER_CODE
        WHERE s.SHIP_STATUS != 'CLOSE'
          AND LEN(s.SHIP_PLAN_DATE) = 8
          AND DATEDIFF(day, GETDATE(), CONVERT(datetime, s.SHIP_PLAN_DATE, 112)) BETWEEN -7 AND 7
        ORDER BY DAYS_LEFT ASC
    """
    return db.query(sql)


def get_finished_goods_status():
    """완제품 출하 현황 (최근 7일)"""
    sql = """
        SELECT
            o.FACTORY_CODE,
            COUNT(*) as TOTAL_LOTS,
            SUM(o.TRAN_QTY) as TOTAL_QTY,
            COUNT(DISTINCT o.ORDER_NO) as ORDER_COUNT
        FROM OWIPLOTSTS o
        WHERE o.TRAN_DATE >= CONVERT(char(8), DATEADD(day, -7, GETDATE()), 112)
          AND o.IF_PROCESS_STATUS = 'S'
        GROUP BY o.FACTORY_CODE
        ORDER BY o.FACTORY_CODE
    """
    return db.query(sql)


def check_inspection_backlog():
    """품질 검사 적체 — 2일 이상 대기"""
    sql = """
        SELECT TOP 10
            r.FACTORY_CODE, r.INSP_NO, r.MAT_CODE,
            r.INSP_REQ_QTY,
            r.INSP_STATUS,
            r.INSP_REQ_TIME,
            DATEDIFF(hour, r.INSP_REQ_TIME, GETDATE()) as WAIT_HOURS
        FROM MQCMREQSTS r
        WHERE r.INSP_STATUS NOT IN ('CLOSE', 'CANCEL')
          AND r.INSP_TIME IS NULL
          AND DATEDIFF(hour, r.INSP_REQ_TIME, GETDATE()) >= 48
        ORDER BY WAIT_HOURS DESC
    """
    return db.query(sql)


def get_tight_schedule_orders():
    """납기일 대비 생산일정이 촉박한 수주 — 선제 커뮤니케이션 필요"""
    sql = """
        SELECT
            s.SHIP_ORD_NO,
            s.SHIP_PLAN_DATE as DUE_DATE,
            s.CUSTOMER_CODE,
            c.CUSTOMER_DESC,
            sd.MAT_CODE,
            m.MAT_DESC,
            sd.SHIP_PLAN_QTY,
            o.ORDER_NO,
            o.PLAN_DATE as PROD_DATE,
            o.ORD_QTY,
            o.ORD_OUT_QTY,
            CASE WHEN o.ORD_OUT_QTY = 0 THEN 'NOT_STARTED'
                 WHEN o.ORD_OUT_QTY < o.ORD_QTY THEN 'WIP'
                 ELSE 'DONE' END as PROD_STATUS,
            DATEDIFF(day,
                CONVERT(datetime, o.PLAN_DATE, 112),
                CONVERT(datetime, s.SHIP_PLAN_DATE, 112)) as BUFFER_DAYS
        FROM MINVSHPMST s
        INNER JOIN MINVSHPDTL sd ON s.FACTORY_CODE = sd.FACTORY_CODE AND s.SHIP_ORD_NO = sd.SHIP_ORD_NO
        INNER JOIN MWIPORDSTS o ON sd.FACTORY_CODE = o.FACTORY_CODE AND sd.MAT_CODE = o.MAT_CODE
            AND o.ORD_STATUS = 'CONFIRM' AND o.ORD_OUT_QTY < o.ORD_QTY AND o.ORD_QTY > 0
        LEFT JOIN MWIPCUSDEF c ON s.FACTORY_CODE = c.FACTORY_CODE AND s.CUSTOMER_CODE = c.CUSTOMER_CODE
        LEFT JOIN MWIPMATDEF m ON sd.FACTORY_CODE = m.FACTORY_CODE AND sd.MAT_CODE = m.MAT_CODE
        WHERE s.SHIP_STATUS NOT IN ('CLOSE', 'COMPLETE')
          AND LEN(s.SHIP_PLAN_DATE) = 8 AND ISDATE(s.SHIP_PLAN_DATE) = 1
          AND LEN(o.PLAN_DATE) = 8 AND ISDATE(o.PLAN_DATE) = 1 AND o.PLAN_DATE != '00000000'
          AND DATEDIFF(day, CONVERT(datetime, o.PLAN_DATE, 112), CONVERT(datetime, s.SHIP_PLAN_DATE, 112)) <= 7
        ORDER BY BUFFER_DAYS ASC, s.SHIP_PLAN_DATE ASC
    """
    return db.query(sql)


def predict_delivery_risk():
    """미완료 작업지시의 예상 완료일 vs 출하 납기 비교 → 납기 위험 감지"""
    sql = """
        SELECT TOP 10
            o.ORDER_NO, o.FACTORY_CODE, o.MAT_CODE, m.MAT_DESC,
            o.ORD_QTY, o.ORD_OUT_QTY,
            (o.ORD_QTY - o.ORD_OUT_QTY) as REMAIN_QTY,
            o.PLAN_DATE,
            AVG_UPH.DAILY_AVG,
            CASE WHEN AVG_UPH.DAILY_AVG > 0
                 THEN CEILING((o.ORD_QTY - o.ORD_OUT_QTY) * 1.0 / AVG_UPH.DAILY_AVG)
                 ELSE 99 END as EST_REMAINING_DAYS,
            CASE WHEN AVG_UPH.DAILY_AVG > 0
                 THEN CONVERT(char(10), DATEADD(day,
                    CEILING((o.ORD_QTY - o.ORD_OUT_QTY) * 1.0 / AVG_UPH.DAILY_AVG),
                    GETDATE()), 23)
                 ELSE '산출불가' END as EST_COMPLETE_DATE
        FROM MWIPORDSTS o
        LEFT JOIN MWIPMATDEF m ON o.FACTORY_CODE = m.FACTORY_CODE AND o.MAT_CODE = m.MAT_CODE
        LEFT JOIN (
            SELECT FACTORY_CODE, LINE_CODE,
                CAST(SUM(ORD_OUT_QTY) / NULLIF(COUNT(DISTINCT PLAN_DATE), 0) AS decimal(10,0)) as DAILY_AVG
            FROM MWIPORDSTS
            WHERE ORD_OUT_QTY > 0 AND PLAN_DATE >= CONVERT(char(8), DATEADD(day, -30, GETDATE()), 112)
            GROUP BY FACTORY_CODE, LINE_CODE
        ) AVG_UPH ON o.FACTORY_CODE = AVG_UPH.FACTORY_CODE AND o.LINE_CODE = AVG_UPH.LINE_CODE
        WHERE o.ORD_STATUS = 'CONFIRM'
          AND o.ORD_OUT_QTY < o.ORD_QTY AND o.ORD_QTY > 1000
          AND o.FACTORY_CODE IN ('1100','1200','1300')
        ORDER BY REMAIN_QTY DESC
    """
    return db.query(sql)


def get_weekly_schedule():
    """주별 생산 스케줄 (미완료 작업지시 기준)"""
    sql = """
        SELECT
            o.FACTORY_CODE,
            o.PLAN_DATE,
            COUNT(*) as ORD_COUNT,
            SUM(o.ORD_QTY) as PLAN_QTY,
            SUM(o.ORD_OUT_QTY) as PROD_QTY,
            SUM(o.ORD_QTY - o.ORD_OUT_QTY) as REMAIN_QTY
        FROM MWIPORDSTS o
        WHERE o.ORD_STATUS = 'CONFIRM'
          AND o.PLAN_DATE IS NOT NULL AND o.PLAN_DATE != '' AND o.PLAN_DATE != '00000000'
          AND LEN(o.PLAN_DATE) = 8 AND ISDATE(o.PLAN_DATE) = 1
          AND o.FACTORY_CODE IN ('1100','1200','1300')
          AND CONVERT(datetime, o.PLAN_DATE, 112) BETWEEN DATEADD(day, -7, GETDATE()) AND DATEADD(day, 14, GETDATE())
        GROUP BY o.FACTORY_CODE, o.PLAN_DATE
        ORDER BY o.PLAN_DATE, o.FACTORY_CODE
    """
    return db.query(sql)


def run(target_date=None):
    today = target_date or datetime.now().strftime("%Y%m%d")
    date_str = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    blocks = [header_block(f"\U0001f4bc 영업 담당자 알림 ({date_str})")]

    # 0. 납기 촉박 수주 — 선제 커뮤니케이션 필요
    tight = get_tight_schedule_orders()
    if tight:
        # 중복 제거 (SHIP_ORD_NO + CUSTOMER 기준)
        seen = set()
        overdue = []  # 생산계획 > 납기 (이미 늦음)
        risky = []    # 여유 0~7일
        for t in tight:
            key = (t["SHIP_ORD_NO"], t["CUSTOMER_CODE"], t["ORDER_NO"])
            if key in seen:
                continue
            seen.add(key)
            if (t["BUFFER_DAYS"] or 0) < 0:
                overdue.append(t)
            else:
                risky.append(t)

        if overdue:
            lines = [f"\U0001f6a8 *생산일정 납기 초과 — 즉시 고객 소통 필요 ({len(overdue)}건)*"]
            for o in overdue[:5]:
                cust = (o["CUSTOMER_DESC"] or o["CUSTOMER_CODE"] or "-")[:15]
                mat = (o["MAT_DESC"] or o["MAT_CODE"])[:18]
                due = o["DUE_DATE"]
                prod = o["PROD_DATE"]
                due_str = f"{due[:4]}-{due[4:6]}-{due[6:]}"
                prod_str = f"{prod[:4]}-{prod[4:6]}-{prod[6:]}"
                lines.append(
                    f"  \U0001f534 {o['SHIP_ORD_NO']} | *{cust}*\n"
                    f"     {mat} | {fmt_num(o['SHIP_PLAN_QTY'])}개\n"
                    f"     납기 *{due_str}* vs 생산 *{prod_str}* (\U0001f4a5 {abs(o['BUFFER_DAYS'])}일 초과) | {o['PROD_STATUS']}"
                )
            blocks.append(section_block("\n".join(lines)))
            blocks.append(divider())

        if risky:
            lines = [f"\u26a0\ufe0f *납기 촉박 수주 — 선제 커뮤니케이션 권장 ({len(risky)}건, 여유 7일 이내)*"]
            for r in risky[:5]:
                cust = (r["CUSTOMER_DESC"] or r["CUSTOMER_CODE"] or "-")[:15]
                mat = (r["MAT_DESC"] or r["MAT_CODE"])[:18]
                due = r["DUE_DATE"]
                prod = r["PROD_DATE"]
                due_str = f"{due[:4]}-{due[4:6]}-{due[6:]}"
                prod_str = f"{prod[:4]}-{prod[4:6]}-{prod[6:]}"
                lines.append(
                    f"  \U0001f7e1 {r['SHIP_ORD_NO']} | *{cust}*\n"
                    f"     {mat} | {fmt_num(r['SHIP_PLAN_QTY'])}개\n"
                    f"     납기 *{due_str}* vs 생산 *{prod_str}* (여유 {r['BUFFER_DAYS']}일) | {r['PROD_STATUS']}"
                )
            blocks.append(section_block("\n".join(lines)))
            blocks.append(divider())

    # 1. 고객사별 진척
    customers = get_customer_progress(today)
    if customers:
        lines = ["*\U0001f465 고객사별 생산 진척 (최근 7일)*"]
        for c in customers[:8]:
            name = c["CUSTOMER_DESC"] or c["CUSTOMER_CODE"]
            if len(name) > 20:
                name = name[:20] + ".."
            pct = c["ACHIEVEMENT"] or 0
            lines.append(
                f"  {status_emoji(pct)} {name} | {fmt_num(c['PROD_QTY'])}/{fmt_num(c['PLAN_QTY'])} ({fmt_pct(pct)}) | {c['ORD_COUNT']}건"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 2. 납기 위험
    risks = check_delivery_risk()
    if risks:
        overdue = [r for r in risks if (r["DAYS_LEFT"] or 0) < 0]
        upcoming = [r for r in risks if 0 <= (r["DAYS_LEFT"] or 0) <= 3]

        if overdue:
            lines = [f"\U0001f534 *납기 초과 ({len(overdue)}건)*"]
            for r in overdue[:5]:
                cust = r["CUSTOMER_DESC"] or r["CUSTOMER_CODE"] or "-"
                lines.append(
                    f"  \u2022 {r['SHIP_ORD_NO']} | {cust} | D+{abs(r['DAYS_LEFT'])}일 초과"
                )
            blocks.append(section_block("\n".join(lines)))

        if upcoming:
            lines = [f"\U0001f7e1 *납기 임박 ({len(upcoming)}건, 3일 이내)*"]
            for r in upcoming[:5]:
                cust = r["CUSTOMER_DESC"] or r["CUSTOMER_CODE"] or "-"
                pd = r["SHIP_PLAN_DATE"]
                lines.append(
                    f"  \u2022 {r['SHIP_ORD_NO']} | {cust} | D-{r['DAYS_LEFT']}일 ({pd[:4]}-{pd[4:6]}-{pd[6:]})"
                )
            blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 3. 완제품 현황
    fg = get_finished_goods_status()
    if fg:
        lines = ["*\U0001f4e6 완제품 출하 현황 (최근 7일)*"]
        for f in fg:
            fc = config.FACTORY_NAMES.get(f["FACTORY_CODE"], f["FACTORY_CODE"])
            lines.append(
                f"  \u2022 {fc} | {fmt_num(f['TOTAL_LOTS'])} LOT ({fmt_num(f['TOTAL_QTY'])}개) | "
                f"{f['ORDER_COUNT']}건 작업지시"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 4. 검사 적체
    backlog = check_inspection_backlog()
    if backlog:
        lines = [f"\U0001f9ea *검사 적체 ({len(backlog)}건, 48시간+ 대기)*"]
        for b in backlog[:5]:
            fc = config.FACTORY_NAMES.get(b["FACTORY_CODE"], b["FACTORY_CODE"])
            wait_days = (b["WAIT_HOURS"] or 0) / 24
            lines.append(
                f"  \u2022 [{fc}] {b['INSP_NO']} | {fmt_num(b['INSP_REQ_QTY'])}개 | {wait_days:.1f}일 대기"
            )
        blocks.append(section_block("\n".join(lines)))

    # 5. 납기 위험 예측 (생산속도 기반)
    delivery_pred = predict_delivery_risk()
    if delivery_pred:
        lines = ["\U0001f52e *납기 예측 (생산속도 기반 예상 완료일)*"]
        for dp in delivery_pred[:5]:
            fc = config.FACTORY_NAMES.get(dp["FACTORY_CODE"], dp["FACTORY_CODE"])
            mat = (dp["MAT_DESC"] or dp["MAT_CODE"] or "")[:20]
            est = dp["EST_COMPLETE_DATE"]
            remain_days = dp["EST_REMAINING_DAYS"] or 0
            emoji = "\U0001f534" if remain_days > 7 else ("\U0001f7e1" if remain_days > 3 else "\U0001f7e2")
            lines.append(
                f"  {emoji} [{fc}] {mat}\n"
                f"     잔여 {fmt_num(dp['REMAIN_QTY'])}개 | 예상완료 *{est}* ({remain_days}일 소요)"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 6. 주별 생산 스케줄
    schedule = get_weekly_schedule()
    if schedule:
        lines = ["\U0001f4c5 *주별 생산 스케줄 (2주간)*"]
        current_week = None
        for sc in schedule:
            pd = sc["PLAN_DATE"]
            dt = datetime.strptime(pd, "%Y%m%d")
            week_num = dt.isocalendar()[1]
            if current_week != week_num:
                current_week = week_num
                lines.append(f"  *W{week_num} ({pd[:4]}-{pd[4:6]}-{pd[6:]}~)*")
            fc = config.FACTORY_NAMES.get(sc["FACTORY_CODE"], sc["FACTORY_CODE"])
            remain = sc["REMAIN_QTY"] or 0
            pct = ((sc["PROD_QTY"] or 0) / (sc["PLAN_QTY"] or 1) * 100)
            emoji = status_emoji(pct)
            lines.append(f"    {emoji} {fc} | {sc['ORD_COUNT']}건 | 잔여 {fmt_num(remain)}개")
        blocks.append(section_block("\n".join(lines)))

    if len(blocks) == 1:
        blocks.append(section_block("\u2705 영업 관련 이슈 없음"))

    send_message(f"영업 담당자 알림 ({date_str})", blocks=blocks)
    print(f"[OK] 영업 담당자 알림 전송 ({date_str})")


if __name__ == "__main__":
    run()
