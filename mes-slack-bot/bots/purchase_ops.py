"""구매 담당자 봇 — 자재 부족 예측, 소모율 이상, 유통기한, 입고 현황"""

from datetime import datetime, timedelta
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct,
    divider, header_block, section_block, context_block,
)


def predict_material_shortage():
    """BOM 기반 1주 자재 소요량 vs 현재고 비교"""
    sql = """
        SELECT
            b.CHILD_MAT_CODE as MAT_CODE,
            m.MAT_DESC,
            SUM(o.ORD_QTY * b.COMPONENT_QTY / 1000.0) as NEED_QTY,
            ISNULL(inv.STOCK_QTY, 0) as STOCK_QTY,
            ISNULL(inv.STOCK_QTY, 0) - SUM(o.ORD_QTY * b.COMPONENT_QTY / 1000.0) as BALANCE
        FROM MWIPORDSTS o
        INNER JOIN MWIPBOMCMP b ON o.MAT_CODE = b.BOM_SET_CODE
        LEFT JOIN MWIPMATDEF m ON o.FACTORY_CODE = m.FACTORY_CODE AND b.CHILD_MAT_CODE = m.MAT_CODE
        LEFT JOIN (
            SELECT MAT_CODE, SUM(QTY) as STOCK_QTY
            FROM CINVBASDAT
            WHERE STATUS = 'S' AND QTY > 0
            GROUP BY MAT_CODE
        ) inv ON b.CHILD_MAT_CODE = inv.MAT_CODE
        WHERE o.PLAN_DATE BETWEEN CONVERT(char(8), GETDATE(), 112)
                               AND CONVERT(char(8), DATEADD(day, 7, GETDATE()), 112)
          AND o.ORD_OUT_QTY = 0
        GROUP BY b.CHILD_MAT_CODE, m.MAT_DESC, inv.STOCK_QTY
        HAVING ISNULL(inv.STOCK_QTY, 0) - SUM(o.ORD_QTY * b.COMPONENT_QTY / 1000.0) < 0
        ORDER BY BALANCE ASC
    """
    return db.query(sql)


def check_material_loss_rate():
    """자재 소모율 이상 — BOM 기준 대비 실투입 비교"""
    sql = """
        SELECT TOP 10
            i.MAT_CODE,
            m.MAT_DESC,
            SUM(i.TRAN_QTY) as ISSUED_QTY,
            COUNT(*) as ISSUE_COUNT
        FROM MINVLOTISS i
        LEFT JOIN MWIPMATDEF m ON i.FACTORY_CODE = m.FACTORY_CODE AND i.MAT_CODE = m.MAT_CODE
        WHERE i.TRAN_TIME >= DATEADD(day, -7, GETDATE())
        GROUP BY i.MAT_CODE, m.MAT_DESC
        HAVING SUM(i.TRAN_QTY) > 1000
        ORDER BY ISSUED_QTY DESC
    """
    return db.query(sql)


def get_receiving_status():
    """최근 입고 현황"""
    sql = """
        SELECT TOP 10
            r.FACTORY_CODE,
            r.MAT_CODE,
            m.MAT_DESC,
            r.TRAN_QTY as QTY,
            r.TRAN_TIME
        FROM MINVLOTRCV r
        LEFT JOIN MWIPMATDEF m ON r.FACTORY_CODE = m.FACTORY_CODE AND r.MAT_CODE = m.MAT_CODE
        WHERE r.TRAN_TIME >= DATEADD(day, -3, GETDATE())
        ORDER BY r.TRAN_TIME DESC
    """
    return db.query(sql)


def check_expiring():
    """유통기한 임박/만료 자재"""
    sql = """
        SELECT
            CASE WHEN DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112)) < 0
                 THEN 'EXPIRED' ELSE 'EXPIRING' END as STATUS,
            COUNT(*) as CNT,
            SUM(QTY) as TOTAL_QTY
        FROM CINVBASDAT
        WHERE USE_TERM IS NOT NULL AND LEN(USE_TERM) = 8
          AND STATUS = 'S' AND QTY > 0
          AND DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112)) <= %s
        GROUP BY CASE WHEN DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112)) < 0
                      THEN 'EXPIRED' ELSE 'EXPIRING' END
    """
    return db.query(sql, (config.ALERT_EXPIRY_DAYS,))


def get_upcoming_deliveries():
    """이번주/다음주 입고 예정 스케줄"""
    sql = """
        SELECT
            d.DLV_DATE,
            d.MAT_CODE,
            m.MAT_DESC,
            d.DLV_QTY,
            d.UNIT,
            d.PO_NO,
            d.VENDOR_CODE,
            v.VENDOR_DESC,
            d.FACTORY_CODE,
            d.DLV_NO
        FROM IINVDLVDTL d
        LEFT JOIN MWIPMATDEF m ON d.FACTORY_CODE = m.FACTORY_CODE AND d.MAT_CODE = m.MAT_CODE
        LEFT JOIN MWIPVENDEF v ON d.FACTORY_CODE = v.FACTORY_CODE AND d.VENDOR_CODE = v.VENDOR_CODE
        WHERE d.IF_PROCESS_STATUS = 'S'
          AND d.IF_TYPE = 'C'
          AND LEN(d.DLV_DATE) = 8 AND ISDATE(d.DLV_DATE) = 1
          AND CONVERT(datetime, d.DLV_DATE, 112) BETWEEN GETDATE() AND DATEADD(day, 14, GETDATE())
        ORDER BY d.DLV_DATE ASC
    """
    return db.query(sql)


def get_overdue_deliveries():
    """입고 예정일 지났는데 실제 입고 안 된 건"""
    sql = """
        SELECT
            d.DLV_DATE,
            d.MAT_CODE,
            m.MAT_DESC,
            d.DLV_QTY,
            d.UNIT,
            d.PO_NO,
            d.VENDOR_CODE,
            v.VENDOR_DESC,
            d.FACTORY_CODE,
            d.DLV_NO,
            DATEDIFF(day, CONVERT(datetime, d.DLV_DATE, 112), GETDATE()) as OVERDUE_DAYS,
            ISNULL(rcv.RCV_QTY, 0) as RCV_QTY
        FROM IINVDLVDTL d
        LEFT JOIN MWIPMATDEF m ON d.FACTORY_CODE = m.FACTORY_CODE AND d.MAT_CODE = m.MAT_CODE
        LEFT JOIN MWIPVENDEF v ON d.FACTORY_CODE = v.FACTORY_CODE AND d.VENDOR_CODE = v.VENDOR_CODE
        LEFT JOIN (
            SELECT FACTORY_CODE, MAT_CODE, SUM(TRAN_QTY) as RCV_QTY
            FROM MINVLOTRCV
            WHERE TRAN_TIME >= DATEADD(day, -30, GETDATE())
            GROUP BY FACTORY_CODE, MAT_CODE
        ) rcv ON d.FACTORY_CODE = rcv.FACTORY_CODE AND d.MAT_CODE = rcv.MAT_CODE
        WHERE d.IF_PROCESS_STATUS = 'S'
          AND d.IF_TYPE = 'C'
          AND LEN(d.DLV_DATE) = 8 AND ISDATE(d.DLV_DATE) = 1
          AND CONVERT(datetime, d.DLV_DATE, 112) < GETDATE()
          AND CONVERT(datetime, d.DLV_DATE, 112) >= DATEADD(day, -30, GETDATE())
          AND ISNULL(rcv.RCV_QTY, 0) < d.DLV_QTY
        ORDER BY OVERDUE_DAYS DESC
    """
    return db.query(sql)


def predict_stockout_date():
    """자재 소진 예측일 — 최근 소모 속도 기반"""
    sql = """
        SELECT TOP 10
            inv.MAT_CODE,
            m.MAT_DESC,
            inv.STOCK_QTY,
            usage.DAILY_USAGE,
            CASE WHEN usage.DAILY_USAGE > 0
                 THEN CAST(inv.STOCK_QTY / usage.DAILY_USAGE AS decimal(10,1))
                 ELSE 999 END as DAYS_UNTIL_STOCKOUT,
            CASE WHEN usage.DAILY_USAGE > 0
                 THEN CONVERT(char(10), DATEADD(day,
                    CAST(inv.STOCK_QTY / usage.DAILY_USAGE AS int), GETDATE()), 23)
                 ELSE '-' END as STOCKOUT_DATE
        FROM (
            SELECT MAT_CODE, SUM(QTY) as STOCK_QTY
            FROM CINVBASDAT WHERE STATUS = 'S' AND QTY > 0 AND MAT_TYPE = 'ROH'
            GROUP BY MAT_CODE
        ) inv
        INNER JOIN (
            SELECT MAT_CODE,
                CAST(SUM(TRAN_QTY) / NULLIF(DATEDIFF(day, MIN(TRAN_TIME), GETDATE()), 0) AS decimal(10,1)) as DAILY_USAGE
            FROM MINVLOTISS
            WHERE TRAN_TIME >= DATEADD(day, -30, GETDATE())
            GROUP BY MAT_CODE
            HAVING SUM(TRAN_QTY) > 0
        ) usage ON inv.MAT_CODE = usage.MAT_CODE
        LEFT JOIN MWIPMATDEF m ON inv.MAT_CODE = m.MAT_CODE
        WHERE usage.DAILY_USAGE > 0
        ORDER BY DAYS_UNTIL_STOCKOUT ASC
    """
    return db.query(sql)


def run(target_date=None):
    today = target_date or datetime.now().strftime("%Y%m%d")
    date_str = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    blocks = [header_block(f"\U0001f6d2 구매 담당자 알림 ({date_str})")]

    # 1. 자재 부족 예측
    shortages = predict_material_shortage()
    if shortages:
        lines = [f"\U0001f534 *자재 부족 예측 ({len(shortages)}건, 향후 7일 기준)*"]
        for s in shortages[:8]:
            mat = (s["MAT_DESC"] or s["MAT_CODE"])[:25]
            lines.append(
                f"  \u2022 {mat}\n"
                f"     필요 {fmt_num(round(s['NEED_QTY']))} | 재고 {fmt_num(round(s['STOCK_QTY']))} | "
                f"*부족 {fmt_num(abs(round(s['BALANCE'])))}*"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 2. 유통기한
    expiry = check_expiring()
    if expiry:
        lines = [f"\u23f0 *유통기한 알림*"]
        for e in expiry:
            if e["STATUS"] == "EXPIRED":
                lines.append(f"  \U0001f534 만료: {e['CNT']}건 ({fmt_num(round(e['TOTAL_QTY']))}개)")
            else:
                lines.append(f"  \U0001f7e1 임박({config.ALERT_EXPIRY_DAYS}일내): {e['CNT']}건 ({fmt_num(round(e['TOTAL_QTY']))}개)")
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 3. 자재 투입 현황 (Top 소모)
    loss = check_material_loss_rate()
    if loss:
        lines = ["*\U0001f4c8 자재 투입 Top 10 (최근 7일)*"]
        for l in loss[:7]:
            mat = (l["MAT_DESC"] or l["MAT_CODE"])[:25]
            lines.append(f"  \u2022 {mat} | {fmt_num(round(l['ISSUED_QTY']))}개 ({l['ISSUE_COUNT']}회)")
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 4. 최근 입고
    rcv = get_receiving_status()
    if rcv:
        lines = ["*\U0001f69a 최근 입고 현황 (3일)*"]
        for r in rcv[:5]:
            fc = config.FACTORY_NAMES.get(r["FACTORY_CODE"], r["FACTORY_CODE"])
            mat = (r["MAT_DESC"] or r["MAT_CODE"])[:20]
            lines.append(f"  \u2022 [{fc}] {mat} | {fmt_num(round(r['QTY']))}개")
        blocks.append(section_block("\n".join(lines)))

    # 5. 입고 지연 (예정일 지났는데 미입고)
    overdue = get_overdue_deliveries()
    if overdue:
        lines = [f"\U0001f534 *입고 지연 ({len(overdue)}건, 예정일 경과 미입고)*"]
        for od in overdue[:6]:
            fc = config.FACTORY_NAMES.get(od["FACTORY_CODE"], od["FACTORY_CODE"])
            mat = (od["MAT_DESC"] or od["MAT_CODE"])[:20]
            vendor = (od["VENDOR_DESC"] or od["VENDOR_CODE"] or "-")[:15]
            dlv = od["DLV_DATE"]
            dlv_str = f"{dlv[:4]}-{dlv[4:6]}-{dlv[6:]}" if dlv else "-"
            lines.append(
                f"  \u2022 [{fc}] {mat}\n"
                f"     PO {od['PO_NO']} | {vendor} | 예정 {dlv_str} (*D+{od['OVERDUE_DAYS']}일*)\n"
                f"     예정 {fmt_num(od['DLV_QTY'])}{od['UNIT'] or ''} / 입고 {fmt_num(od['RCV_QTY'])}"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 6. 입고 예정 스케줄 (향후 2주)
    upcoming = get_upcoming_deliveries()
    if upcoming:
        lines = [f"\U0001f4c5 *입고 예정 스케줄 ({len(upcoming)}건, 향후 2주)*"]
        current_date = None
        for uc in upcoming[:10]:
            dlv = uc["DLV_DATE"]
            dlv_str = f"{dlv[:4]}-{dlv[4:6]}-{dlv[6:]}" if dlv else "-"
            if current_date != dlv:
                current_date = dlv
                lines.append(f"  *{dlv_str}*")
            fc = config.FACTORY_NAMES.get(uc["FACTORY_CODE"], uc["FACTORY_CODE"])
            mat = (uc["MAT_DESC"] or uc["MAT_CODE"])[:20]
            vendor = (uc["VENDOR_DESC"] or uc["VENDOR_CODE"] or "-")[:12]
            lines.append(
                f"    \u2022 [{fc}] {mat} | {fmt_num(uc['DLV_QTY'])}{uc['UNIT'] or ''} | {vendor}"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 7. 자재 소진 예측
    stockout = predict_stockout_date()
    if stockout:
        lines = ["\U0001f52e *자재 소진 예측 (소모속도 기반)*"]
        for so in stockout[:6]:
            mat = (so["MAT_DESC"] or so["MAT_CODE"])[:25]
            days = so["DAYS_UNTIL_STOCKOUT"] or 0
            emoji = "\U0001f534" if days < 7 else ("\U0001f7e1" if days < 14 else "\U0001f7e2")
            lines.append(
                f"  {emoji} {mat}\n"
                f"     재고 {fmt_num(round(so['STOCK_QTY']))} | 일소모 {fmt_num(round(so['DAILY_USAGE']))} | "
                f"*{so['STOCKOUT_DATE']}* 소진 예상 (D-{days:.0f})"
            )
        blocks.append(section_block("\n".join(lines)))

    if len(blocks) == 1:
        blocks.append(section_block("\u2705 구매 관련 이슈 없음"))

    send_message(f"구매 담당자 알림 ({date_str})", blocks=blocks)
    print(f"[OK] 구매 담당자 알림 전송 ({date_str})")


if __name__ == "__main__":
    run()
