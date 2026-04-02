"""재고/자재 알람 - 재고 부족, 유통기한 임박 감지"""

from datetime import datetime
import db
import config
from slack_sender import (
    send_message, fmt_num,
    divider, header_block, section_block, context_block,
)


def check_low_stock():
    """재고 부족 원자재 감지"""
    sql = """
        SELECT
            FACTORY_CODE, MAT_CODE, QTY,
            VENDOR_DESC, OPER_DESC
        FROM CINVBASDAT
        WHERE MAT_TYPE = 'ROH'
          AND STATUS = 'S'
          AND QTY < %s
          AND QTY > 0
        ORDER BY QTY ASC
    """
    return db.query(sql, (config.ALERT_STOCK_MIN,))


def check_expiring_materials():
    """유통기한 임박 자재 감지"""
    sql = """
        SELECT
            FACTORY_CODE, MAT_CODE, QTY,
            USE_TERM, VENDOR_DESC,
            DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112)) as DAYS_LEFT
        FROM CINVBASDAT
        WHERE USE_TERM IS NOT NULL
          AND LEN(USE_TERM) = 8
          AND STATUS = 'S'
          AND QTY > 0
          AND DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112)) BETWEEN 0 AND %s
        ORDER BY DAYS_LEFT ASC
    """
    return db.query(sql, (config.ALERT_EXPIRY_DAYS,))


def check_expired_materials():
    """유통기한 만료 자재"""
    sql = """
        SELECT
            FACTORY_CODE, MAT_CODE, QTY,
            USE_TERM, VENDOR_DESC,
            ABS(DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112))) as DAYS_OVER
        FROM CINVBASDAT
        WHERE USE_TERM IS NOT NULL
          AND LEN(USE_TERM) = 8
          AND STATUS = 'S'
          AND QTY > 0
          AND DATEDIFF(day, GETDATE(), CONVERT(datetime, USE_TERM, 112)) < 0
        ORDER BY DAYS_OVER DESC
    """
    return db.query(sql)


def run():
    """재고 알람 실행"""
    today = datetime.now().strftime("%Y-%m-%d")
    blocks = [header_block(f"\U0001f4e6 재고/자재 알람 ({today})")]
    alerts_found = False

    # 1. 유통기한 만료
    expired = check_expired_materials()
    if expired:
        alerts_found = True
        lines = [f"\U0001f534 *유통기한 만료 자재 ({len(expired)}건)*"]
        for e in expired[:10]:
            fc_name = config.FACTORY_NAMES.get(e["FACTORY_CODE"], e["FACTORY_CODE"])
            term = e["USE_TERM"]
            term_str = f"{term[:4]}-{term[4:6]}-{term[6:]}" if term else "-"
            lines.append(
                f"  \u2022 [{fc_name}] {e['MAT_CODE']} | {fmt_num(e['QTY'])}개 | "
                f"만료 {term_str} ({e['DAYS_OVER']}일 경과)"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 2. 유통기한 임박
    expiring = check_expiring_materials()
    if expiring:
        alerts_found = True
        lines = [f"\U0001f7e1 *유통기한 임박 자재 ({len(expiring)}건, {config.ALERT_EXPIRY_DAYS}일 이내)*"]
        for e in expiring[:10]:
            fc_name = config.FACTORY_NAMES.get(e["FACTORY_CODE"], e["FACTORY_CODE"])
            term = e["USE_TERM"]
            term_str = f"{term[:4]}-{term[4:6]}-{term[6:]}" if term else "-"
            lines.append(
                f"  \u2022 [{fc_name}] {e['MAT_CODE']} | {fmt_num(e['QTY'])}개 | "
                f"만료 {term_str} (D-{e['DAYS_LEFT']})"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 3. 재고 부족
    low_stock = check_low_stock()
    if low_stock:
        alerts_found = True
        lines = [f"\U0001f4e6 *재고 부족 원자재 ({len(low_stock)}건, {fmt_num(config.ALERT_STOCK_MIN)}개 미만)*"]
        for s in low_stock[:10]:
            fc_name = config.FACTORY_NAMES.get(s["FACTORY_CODE"], s["FACTORY_CODE"])
            vendor = s["VENDOR_DESC"] or "-"
            lines.append(
                f"  \u2022 [{fc_name}] {s['MAT_CODE']} | 잔량 {fmt_num(s['QTY'])}개 | {vendor}"
            )
        blocks.append(section_block("\n".join(lines)))

    if not alerts_found:
        blocks.append(section_block("\u2705 재고/자재 이상 없음"))

    send_message(f"재고/자재 알람 ({today})", blocks=blocks)
    print(f"[OK] 재고/자재 알람 전송 완료 ({today}), 알람 {'있음' if alerts_found else '없음'}")


if __name__ == "__main__":
    run()
