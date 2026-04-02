"""생산 담당자 봇 — 라인 병목, 연속 불량, 미착수 경고, 교대 인수인계, 라인부하 예측"""

from datetime import datetime, timedelta
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct, status_emoji,
    divider, header_block, section_block, context_block,
)


def check_bottleneck_lines(plan_date):
    """라인별 LOT 평균 체류시간 대비 병목 감지"""
    sql = """
        SELECT
            s.FACTORY_CODE, s.LINE_CODE, l.LINE_DESC,
            COUNT(*) as LOT_COUNT,
            AVG(DATEDIFF(minute, s.CREATE_TIME, s.UPDATE_TIME)) as AVG_MINUTES,
            MAX(DATEDIFF(minute, s.CREATE_TIME, s.UPDATE_TIME)) as MAX_MINUTES
        FROM MWIPLOTSTS s
        LEFT JOIN MWIPLINDEF l ON s.FACTORY_CODE = l.FACTORY_CODE AND s.LINE_CODE = l.LINE_CODE
        WHERE s.LOT_STATUS = 'WAIT'
          AND s.CREATE_TIME >= %s
          AND s.UPDATE_TIME IS NOT NULL
          AND DATEDIFF(minute, s.CREATE_TIME, s.UPDATE_TIME) > 0
        GROUP BY s.FACTORY_CODE, s.LINE_CODE, l.LINE_DESC
        HAVING AVG(DATEDIFF(minute, s.CREATE_TIME, s.UPDATE_TIME)) > 480
        ORDER BY AVG_MINUTES DESC
    """
    date_start = f"{plan_date[:4]}-{plan_date[4:6]}-{plan_date[6:]} 00:00:00"
    return db.query(sql, (date_start,))


def check_consecutive_defects():
    """동일 라인에서 연속 불량 LOT 감지"""
    sql = """
        SELECT TOP 10
            s.FACTORY_CODE, s.LINE_CODE, l.LINE_DESC,
            s.MAT_CODE, m.MAT_DESC,
            COUNT(*) as DEFECT_COUNT,
            MAX(s.UPDATE_TIME) as LAST_DEFECT_TIME
        FROM MWIPLOTSTS s
        LEFT JOIN MWIPLINDEF l ON s.FACTORY_CODE = l.FACTORY_CODE AND s.LINE_CODE = l.LINE_CODE
        LEFT JOIN MWIPMATDEF m ON s.FACTORY_CODE = m.FACTORY_CODE AND s.MAT_CODE = m.MAT_CODE
        WHERE s.DEFECT_FLAG = 1
          AND s.UPDATE_TIME >= DATEADD(hour, -24, GETDATE())
        GROUP BY s.FACTORY_CODE, s.LINE_CODE, l.LINE_DESC, s.MAT_CODE, m.MAT_DESC
        HAVING COUNT(*) >= 3
        ORDER BY DEFECT_COUNT DESC
    """
    return db.query(sql)


def check_unstarted_orders(plan_date):
    """계획일 대비 미착수 작업지시"""
    sql = """
        SELECT
            o.FACTORY_CODE, o.ORDER_NO, o.PLAN_DATE,
            o.MAT_CODE, m.MAT_DESC,
            o.LINE_CODE, l.LINE_DESC,
            o.ORD_QTY,
            DATEDIFF(day, CONVERT(datetime, o.PLAN_DATE, 112), GETDATE()) as DELAY_DAYS
        FROM MWIPORDSTS o
        LEFT JOIN MWIPMATDEF m ON o.FACTORY_CODE = m.FACTORY_CODE AND o.MAT_CODE = m.MAT_CODE
        LEFT JOIN MWIPLINDEF l ON o.FACTORY_CODE = l.FACTORY_CODE AND o.LINE_CODE = l.LINE_CODE
        WHERE o.ORD_STATUS = 'CONFIRM'
          AND o.ORD_OUT_QTY = 0
          AND o.PLAN_DATE < %s
          AND LEN(o.PLAN_DATE) = 8
          AND ISDATE(o.PLAN_DATE) = 1
        ORDER BY o.PLAN_DATE ASC
    """
    return db.query(sql, (plan_date,))


def get_shift_summary(plan_date):
    """현재 교대 기준 공장별 생산 현황 요약"""
    sql = """
        SELECT
            o.FACTORY_CODE,
            COUNT(*) as ORD_COUNT,
            SUM(o.ORD_QTY) as PLAN_QTY,
            SUM(o.ORD_OUT_QTY) as PROD_QTY,
            SUM(o.RCV_GOOD_QTY) as GOOD_QTY,
            SUM(o.RCV_LOSS_QTY) as LOSS_QTY,
            SUM(CASE WHEN o.ORD_OUT_QTY = 0 THEN 1 ELSE 0 END) as NOT_STARTED,
            SUM(CASE WHEN o.ORD_OUT_QTY > 0 AND o.ORD_OUT_QTY < o.ORD_QTY THEN 1 ELSE 0 END) as IN_PROGRESS,
            SUM(CASE WHEN o.ORD_OUT_QTY >= o.ORD_QTY AND o.ORD_QTY > 0 THEN 1 ELSE 0 END) as COMPLETED
        FROM MWIPORDSTS o
        WHERE o.PLAN_DATE = %s
        GROUP BY o.FACTORY_CODE
        ORDER BY o.FACTORY_CODE
    """
    return db.query(sql, (plan_date,))


def predict_line_load():
    """라인별 미완료 수량 기반 부하 예측 — 과거 UPH로 소요일 추정"""
    sql = """
        SELECT
            o.FACTORY_CODE, o.LINE_CODE, l.LINE_DESC,
            SUM(o.ORD_QTY - o.ORD_OUT_QTY) as REMAIN_QTY,
            AVG_UPH.UPH,
            CASE WHEN AVG_UPH.UPH > 0
                 THEN CAST(SUM(o.ORD_QTY - o.ORD_OUT_QTY) / AVG_UPH.UPH / 8.0 AS decimal(5,1))
                 ELSE 99 END as EST_DAYS
        FROM MWIPORDSTS o
        LEFT JOIN MWIPLINDEF l ON o.FACTORY_CODE = l.FACTORY_CODE AND o.LINE_CODE = l.LINE_CODE
        LEFT JOIN (
            SELECT FACTORY_CODE, LINE_CODE,
                CAST(SUM(ORD_OUT_QTY) / NULLIF(COUNT(DISTINCT PLAN_DATE), 0) / 8.0 AS decimal(10,1)) as UPH
            FROM MWIPORDSTS
            WHERE ORD_OUT_QTY > 0 AND PLAN_DATE >= CONVERT(char(8), DATEADD(day, -30, GETDATE()), 112)
            GROUP BY FACTORY_CODE, LINE_CODE
        ) AVG_UPH ON o.FACTORY_CODE = AVG_UPH.FACTORY_CODE AND o.LINE_CODE = AVG_UPH.LINE_CODE
        WHERE o.ORD_STATUS = 'CONFIRM'
          AND o.ORD_OUT_QTY < o.ORD_QTY AND o.ORD_QTY > 0
          AND o.FACTORY_CODE IN ('1100','1200','1300')
        GROUP BY o.FACTORY_CODE, o.LINE_CODE, l.LINE_DESC, AVG_UPH.UPH
        HAVING SUM(o.ORD_QTY - o.ORD_OUT_QTY) > 100
        ORDER BY EST_DAYS DESC
    """
    return db.query(sql)


def predict_completion():
    """미완료 작업지시의 예상 완료일 추정"""
    sql = """
        SELECT TOP 10
            o.FACTORY_CODE, o.ORDER_NO, o.MAT_CODE, m.MAT_DESC,
            o.LINE_CODE, o.ORD_QTY, o.ORD_OUT_QTY,
            (o.ORD_QTY - o.ORD_OUT_QTY) as REMAIN_QTY,
            AVG_UPH.DAILY_AVG,
            CASE WHEN AVG_UPH.DAILY_AVG > 0
                 THEN CONVERT(char(10),
                    DATEADD(day,
                        CEILING((o.ORD_QTY - o.ORD_OUT_QTY) * 1.0 / AVG_UPH.DAILY_AVG),
                        GETDATE()
                    ), 23)
                 ELSE '산출불가' END as EST_COMPLETE
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


def run(target_date=None):
    today = target_date or datetime.now().strftime("%Y%m%d")
    date_str = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    now_hour = datetime.now().hour
    if now_hour < 14:
        shift = "주간"
    elif now_hour < 22:
        shift = "오후"
    else:
        shift = "야간"

    blocks = [header_block(f"\U0001f3ed 생산 담당자 알림 ({date_str} {shift})")]

    # 1. 교대 인수인계 요약
    shift_data = get_shift_summary(today)
    if shift_data:
        lines = [f"*\U0001f4cb 공장별 현황*"]
        for s in shift_data:
            fc = config.FACTORY_NAMES.get(s["FACTORY_CODE"], s["FACTORY_CODE"])
            plan = s["PLAN_QTY"] or 0
            prod = s["PROD_QTY"] or 0
            pct = (prod / plan * 100) if plan > 0 else 0
            lines.append(
                f"  {status_emoji(pct)} *{fc}* | {fmt_num(prod)}/{fmt_num(plan)} ({fmt_pct(pct)}) | "
                f"미착수 {s['NOT_STARTED']} / 진행 {s['IN_PROGRESS']} / 완료 {s['COMPLETED']}"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 2. 미착수 작업지시
    unstarted = check_unstarted_orders(today)
    if unstarted:
        lines = [f"\u26a0\ufe0f *미착수 작업지시 ({len(unstarted)}건)*"]
        for u in unstarted[:5]:
            fc = config.FACTORY_NAMES.get(u["FACTORY_CODE"], u["FACTORY_CODE"])
            mat = (u["MAT_DESC"] or u["MAT_CODE"] or "")[:25]
            lines.append(
                f"  \u2022 [{fc}] {u['ORDER_NO']} | {mat} | "
                f"{fmt_num(u['ORD_QTY'])}개 | D+{u['DELAY_DAYS']}일 지연"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 3. 연속 불량
    defects = check_consecutive_defects()
    if defects:
        lines = [f"\U0001f534 *연속 불량 LOT 감지*"]
        for d in defects[:5]:
            fc = config.FACTORY_NAMES.get(d["FACTORY_CODE"], d["FACTORY_CODE"])
            mat = (d["MAT_DESC"] or d["MAT_CODE"] or "")[:20]
            lines.append(
                f"  \u2022 [{fc}] {d['LINE_DESC'] or d['LINE_CODE']} | {mat} | "
                f"연속 {d['DEFECT_COUNT']}건 불량"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 4. 라인 병목
    bottlenecks = check_bottleneck_lines(today)
    if bottlenecks:
        lines = [f"\U0001f6a7 *라인 병목 감지 (LOT 체류 8시간+)*"]
        for b in bottlenecks[:5]:
            fc = config.FACTORY_NAMES.get(b["FACTORY_CODE"], b["FACTORY_CODE"])
            avg_h = (b["AVG_MINUTES"] or 0) / 60
            lines.append(
                f"  \u2022 [{fc}] {b['LINE_DESC'] or b['LINE_CODE']} | "
                f"평균 {avg_h:.1f}h | {b['LOT_COUNT']}LOT"
            )
        blocks.append(section_block("\n".join(lines)))

    # 5. 라인별 부하 예측 (미완료 작업지시 기반)
    line_load = predict_line_load()
    if line_load:
        lines = ["\U0001f52e *라인 부하 예측 (미완료 기준)*"]
        for ll in line_load[:6]:
            fc = config.FACTORY_NAMES.get(ll["FACTORY_CODE"], ll["FACTORY_CODE"])
            est_days = ll["EST_DAYS"] or 0
            emoji = "\U0001f534" if est_days > 5 else ("\U0001f7e1" if est_days > 3 else "\U0001f7e2")
            lines.append(
                f"  {emoji} [{fc}] {ll['LINE_DESC'] or ll['LINE_CODE']} | "
                f"잔여 {fmt_num(ll['REMAIN_QTY'])}개 | *예상 {est_days:.1f}일 소요*"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 6. 미완료 작업지시 예상 완료일
    unfinished = predict_completion()
    if unfinished:
        lines = ["\U0001f4c5 *미완료 작업 예상 완료일*"]
        for uf in unfinished[:5]:
            fc = config.FACTORY_NAMES.get(uf["FACTORY_CODE"], uf["FACTORY_CODE"])
            mat = (uf["MAT_DESC"] or uf["MAT_CODE"] or "")[:20]
            remain = uf["REMAIN_QTY"] or 0
            est = uf["EST_COMPLETE"]
            lines.append(
                f"  \u2022 [{fc}] {mat} | 잔여 {fmt_num(remain)}개 | 예상완료 *{est}*"
            )
        blocks.append(section_block("\n".join(lines)))

    if len(blocks) == 1:
        blocks.append(section_block("\u2705 현재 생산 이슈 없음"))

    send_message(f"생산 담당자 알림 ({date_str})", blocks=blocks)
    print(f"[OK] 생산 담당자 알림 전송 ({date_str} {shift})")


if __name__ == "__main__":
    run()
