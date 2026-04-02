"""긴급 품질검사 요청 봇 — 납기 대비 QC 여유 없는 오더 감지"""

from datetime import datetime
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct,
    divider, header_block, section_block, context_block,
)

# QC에 필요한 최소 일수 (생산 완료 → 검사 → 출하)
QC_MIN_DAYS = 2


def get_qc_urgent_orders():
    """생산 완료 예상일 + QC 2일 감안 시 납기를 못 맞추는 오더"""
    sql = """
        WITH order_data AS (
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
                o.ORD_QTY - o.ORD_OUT_QTY as REMAIN_QTY,
                o.LINE_CODE,
                l.LINE_DESC,
                o.FACTORY_CODE,
                CASE WHEN o.ORD_OUT_QTY = 0 THEN 'NOT_STARTED'
                     WHEN o.ORD_OUT_QTY < o.ORD_QTY THEN 'WIP'
                     ELSE 'DONE' END as PROD_STATUS,
                DATEDIFF(day, GETDATE(), CONVERT(datetime, s.SHIP_PLAN_DATE, 112)) as DAYS_TO_DUE,
                AVG_UPH.DAILY_AVG,
                CASE WHEN AVG_UPH.DAILY_AVG > 0
                     THEN CEILING((o.ORD_QTY - o.ORD_OUT_QTY) * 1.0 / AVG_UPH.DAILY_AVG)
                     ELSE NULL END as EST_PROD_DAYS,
                CASE WHEN AVG_UPH.DAILY_AVG > 0
                     THEN DATEDIFF(day, GETDATE(), CONVERT(datetime, s.SHIP_PLAN_DATE, 112))
                          - CEILING((o.ORD_QTY - o.ORD_OUT_QTY) * 1.0 / AVG_UPH.DAILY_AVG)
                     ELSE DATEDIFF(day, CONVERT(datetime, o.PLAN_DATE, 112),
                                        CONVERT(datetime, s.SHIP_PLAN_DATE, 112))
                     END as QC_BUFFER_DAYS
            FROM MINVSHPMST s
            INNER JOIN MINVSHPDTL sd ON s.FACTORY_CODE = sd.FACTORY_CODE AND s.SHIP_ORD_NO = sd.SHIP_ORD_NO
            INNER JOIN MWIPORDSTS o ON sd.FACTORY_CODE = o.FACTORY_CODE AND sd.MAT_CODE = o.MAT_CODE
                AND o.ORD_STATUS = 'CONFIRM' AND o.ORD_OUT_QTY < o.ORD_QTY AND o.ORD_QTY > 0
            LEFT JOIN MWIPCUSDEF c ON s.FACTORY_CODE = c.FACTORY_CODE AND s.CUSTOMER_CODE = c.CUSTOMER_CODE
            LEFT JOIN MWIPMATDEF m ON sd.FACTORY_CODE = m.FACTORY_CODE AND sd.MAT_CODE = m.MAT_CODE
            LEFT JOIN MWIPLINDEF l ON o.FACTORY_CODE = l.FACTORY_CODE AND o.LINE_CODE = l.LINE_CODE
            LEFT JOIN (
                SELECT FACTORY_CODE, LINE_CODE,
                    CAST(SUM(ORD_OUT_QTY) / NULLIF(COUNT(DISTINCT PLAN_DATE), 0) AS decimal(10,0)) as DAILY_AVG
                FROM MWIPORDSTS
                WHERE ORD_OUT_QTY > 0
                  AND PLAN_DATE >= CONVERT(char(8), DATEADD(day, -30, GETDATE()), 112)
                GROUP BY FACTORY_CODE, LINE_CODE
            ) AVG_UPH ON o.FACTORY_CODE = AVG_UPH.FACTORY_CODE AND o.LINE_CODE = AVG_UPH.LINE_CODE
            WHERE s.SHIP_STATUS NOT IN ('CLOSE', 'COMPLETE')
              AND LEN(s.SHIP_PLAN_DATE) = 8 AND ISDATE(s.SHIP_PLAN_DATE) = 1
              AND LEN(o.PLAN_DATE) = 8 AND ISDATE(o.PLAN_DATE) = 1 AND o.PLAN_DATE != '00000000'
        )
        SELECT *
        FROM order_data
        WHERE QC_BUFFER_DAYS < %s
        ORDER BY QC_BUFFER_DAYS ASC, DUE_DATE ASC
    """
    return db.query(sql, (QC_MIN_DAYS,))


def get_production_done_pending_qc():
    """생산 완료 → QC 대기 중인 건 (검사 의뢰는 했지만 미완료)"""
    sql = """
        SELECT TOP 10
            r.FACTORY_CODE, r.INSP_NO, r.MAT_CODE, m.MAT_DESC,
            r.INSP_REQ_QTY,
            r.INSP_STATUS,
            r.INSP_REQ_TIME,
            DATEDIFF(hour, r.INSP_REQ_TIME, GETDATE()) as WAIT_HOURS
        FROM MQCMREQSTS r
        LEFT JOIN MWIPMATDEF m ON r.FACTORY_CODE = m.FACTORY_CODE AND r.MAT_CODE = m.MAT_CODE
        WHERE r.INSP_STATUS NOT IN ('CLOSE', 'CANCEL')
          AND r.INSP_TIME IS NULL
          AND r.INSP_REQ_TIME IS NOT NULL
        ORDER BY r.INSP_REQ_TIME ASC
    """
    return db.query(sql)


def fmt_date(d):
    if not d or len(d) < 8:
        return "-"
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def run(target_date=None):
    today = target_date or datetime.now().strftime("%Y%m%d")
    date_str = fmt_date(today)
    blocks = [header_block(f"\U0001f9ea 긴급 품질검사 요청 ({date_str})")]
    alerts_found = False

    # 1. QC 여유 없는 오더
    urgent = get_qc_urgent_orders()
    if urgent:
        # 중복 제거
        seen = set()
        no_time = []     # QC 여유 0일 이하 (검사 불가능)
        tight = []       # QC 여유 1일 (당일 검사 필요)

        for u in urgent:
            key = (u["SHIP_ORD_NO"], u["ORDER_NO"])
            if key in seen:
                continue
            seen.add(key)
            qc_buf = u["QC_BUFFER_DAYS"]
            if qc_buf is not None and qc_buf <= 0:
                no_time.append(u)
            else:
                tight.append(u)

        if no_time:
            alerts_found = True
            total_qty = sum(r["REMAIN_QTY"] or 0 for r in no_time)
            lines = [
                f"\U0001f6a8 *QC 시간 없음 — 즉시 검사 필요 ({len(no_time)}건, {fmt_num(total_qty)}개)*",
                f"_생산 완료 후 QC {QC_MIN_DAYS}일 확보 불가 → 생산과 동시 검사 또는 긴급 검사 필요_"
            ]
            for n in no_time[:8]:
                fc = config.FACTORY_NAMES.get(n["FACTORY_CODE"], n["FACTORY_CODE"])
                cust = (n["CUSTOMER_DESC"] or n["CUSTOMER_CODE"] or "-")[:13]
                mat = (n["MAT_DESC"] or n["MAT_CODE"])[:18]
                qc_buf = n["QC_BUFFER_DAYS"]
                qc_txt = f"QC 여유 *{qc_buf}일*" if qc_buf is not None else "산출불가"
                prod_days = f", 생산 {n['EST_PROD_DAYS']}일" if n["EST_PROD_DAYS"] else ""
                lines.append(
                    f"  \U0001f534 [{fc}] *{cust}*\n"
                    f"     {mat} | {fmt_num(n['REMAIN_QTY'])}개 | {n['PROD_STATUS']}\n"
                    f"     납기 *{fmt_date(n['DUE_DATE'])}* (D-{n['DAYS_TO_DUE']}) | {qc_txt}{prod_days}"
                )
            blocks.append(section_block("\n".join(lines)))
            blocks.append(divider())

        if tight:
            alerts_found = True
            total_qty = sum(r["REMAIN_QTY"] or 0 for r in tight)
            lines = [
                f"\u26a0\ufe0f *QC 촉박 — 우선 검사 대상 ({len(tight)}건, {fmt_num(total_qty)}개)*",
                f"_QC 여유 {QC_MIN_DAYS}일 미만 → 검사 우선순위 상향 필요_"
            ]
            for t in tight[:6]:
                fc = config.FACTORY_NAMES.get(t["FACTORY_CODE"], t["FACTORY_CODE"])
                cust = (t["CUSTOMER_DESC"] or t["CUSTOMER_CODE"] or "-")[:13]
                mat = (t["MAT_DESC"] or t["MAT_CODE"])[:18]
                qc_buf = t["QC_BUFFER_DAYS"]
                qc_txt = f"QC 여유 *{qc_buf}일*" if qc_buf is not None else "산출불가"
                lines.append(
                    f"  \U0001f7e1 [{fc}] *{cust}* | {mat}\n"
                    f"     {fmt_num(t['REMAIN_QTY'])}개 | 납기 {fmt_date(t['DUE_DATE'])} | {qc_txt}"
                )
            blocks.append(section_block("\n".join(lines)))
            blocks.append(divider())

    # 2. 현재 QC 대기 중인 건
    pending = get_production_done_pending_qc()
    if pending:
        alerts_found = True
        lines = [f"\u23f3 *검사 대기 중 ({len(pending)}건)*"]
        for p in pending:
            fc = config.FACTORY_NAMES.get(p["FACTORY_CODE"], p["FACTORY_CODE"])
            mat = (p["MAT_DESC"] or p["MAT_CODE"])[:20]
            wait_h = p["WAIT_HOURS"] or 0
            wait_txt = f"{wait_h // 24}일 {wait_h % 24}h" if wait_h >= 24 else f"{wait_h}h"
            emoji = "\U0001f534" if wait_h >= 48 else ("\U0001f7e1" if wait_h >= 24 else "\u23f3")
            lines.append(
                f"  {emoji} [{fc}] {p['INSP_NO']} | {mat} | {fmt_num(p['INSP_REQ_QTY'])}개 | 대기 {wait_txt}"
            )
        blocks.append(section_block("\n".join(lines)))

    if not alerts_found:
        blocks.append(section_block("\u2705 긴급 품질검사 건 없음"))

    blocks.append(context_block(
        f"\U0001f4a1 기준: 생산완료 → QC → 출하에 최소 *{QC_MIN_DAYS}일* 필요 | "
        f"\U0001f534 여유 0일 이하 = 즉시검사 | \U0001f7e1 여유 1일 = 우선검사"
    ))

    send_message(f"긴급 품질검사 요청 ({date_str})", blocks=blocks)
    print(f"[OK] 긴급 품질검사 요청 알림 전송 ({date_str})")


if __name__ == "__main__":
    run()
