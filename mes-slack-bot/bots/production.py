"""생산 현황 대시보드 - 공장별 생산/포장 달성률 요약"""

from datetime import datetime, timedelta
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct, status_emoji, change_arrow,
    divider, header_block, section_block, context_block,
)


def get_production_summary(plan_date):
    """공장별 생산 현황 집계"""
    sql = """
        SELECT
            o.FACTORY_CODE,
            COUNT(DISTINCT o.ORDER_NO) as ORD_COUNT,
            SUM(o.ORD_QTY) as PLAN_QTY,
            SUM(o.ORD_OUT_QTY) as PROD_QTY,
            SUM(o.RCV_GOOD_QTY) as GOOD_QTY,
            SUM(o.RCV_LOSS_QTY) as LOSS_QTY
        FROM MWIPORDSTS o
        WHERE o.PLAN_DATE = %s
        GROUP BY o.FACTORY_CODE
        ORDER BY o.FACTORY_CODE
    """
    return db.query(sql, (plan_date,))


def get_line_summary(plan_date, factory_code):
    """라인별 생산 현황"""
    sql = """
        SELECT
            o.LINE_CODE,
            l.LINE_DESC,
            SUM(o.ORD_QTY) as PLAN_QTY,
            SUM(o.ORD_OUT_QTY) as PROD_QTY,
            SUM(o.RCV_GOOD_QTY) as GOOD_QTY,
            SUM(o.RCV_LOSS_QTY) as LOSS_QTY
        FROM MWIPORDSTS o
        LEFT JOIN MWIPLINDEF l
            ON o.FACTORY_CODE = l.FACTORY_CODE AND o.LINE_CODE = l.LINE_CODE
        WHERE o.PLAN_DATE = %s AND o.FACTORY_CODE = %s
        GROUP BY o.LINE_CODE, l.LINE_DESC
        ORDER BY o.LINE_CODE
    """
    return db.query(sql, (plan_date, factory_code))


def build_factory_section(name, data, prev_data=None):
    """공장별 섹션 메시지 생성"""
    plan = data["PLAN_QTY"] or 0
    prod = data["PROD_QTY"] or 0
    good = data["GOOD_QTY"] or 0
    loss = data["LOSS_QTY"] or 0
    pct = (prod / plan * 100) if plan > 0 else 0
    emoji = status_emoji(pct)

    prev_prod = prev_data["PROD_QTY"] if prev_data else None
    change = change_arrow(prod, prev_prod) if prev_prod else ""

    lines = [
        f"*{name}* {emoji}",
        f"  생산: {fmt_num(prod)} / {fmt_num(plan)} (*{fmt_pct(pct)}*) {change}",
        f"  양품: {fmt_num(good)} | 불량: {fmt_num(loss)}",
    ]
    if plan > 0 and loss > 0:
        defect_rate = loss / (good + loss) * 100 if (good + loss) > 0 else 0
        lines.append(f"  불량률: {fmt_pct(defect_rate)}")

    return section_block("\n".join(lines))


def run(target_date=None):
    """대시보드 실행"""
    today = target_date or datetime.now().strftime("%Y%m%d")
    yesterday = (datetime.strptime(today, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")

    today_data = get_production_summary(today)
    yesterday_data = get_production_summary(yesterday)

    if not today_data:
        send_message(f":clipboard: *{today}* 생산 데이터가 없습니다.")
        return

    # 전일 데이터를 dict로 변환
    prev_map = {r["FACTORY_CODE"]: r for r in yesterday_data}

    # 전체 합계 계산
    total_plan = sum(r["PLAN_QTY"] or 0 for r in today_data)
    total_prod = sum(r["PROD_QTY"] or 0 for r in today_data)
    total_good = sum(r["GOOD_QTY"] or 0 for r in today_data)
    total_loss = sum(r["LOSS_QTY"] or 0 for r in today_data)
    total_pct = (total_prod / total_plan * 100) if total_plan > 0 else 0

    prev_total_prod = sum(r["PROD_QTY"] or 0 for r in yesterday_data) if yesterday_data else None
    total_change = change_arrow(total_prod, prev_total_prod)

    # 메시지 블록 구성
    date_str = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    blocks = [
        header_block(f"\U0001f4cb 생산 현황 대시보드 ({date_str})"),
        section_block(
            f"*전체 합계* {status_emoji(total_pct)}\n"
            f"  생산: {fmt_num(total_prod)} / {fmt_num(total_plan)} (*{fmt_pct(total_pct)}*) {total_change}\n"
            f"  양품: {fmt_num(total_good)} | 불량: {fmt_num(total_loss)}"
        ),
        divider(),
    ]

    # 공장별 섹션
    for row in today_data:
        fc = row["FACTORY_CODE"]
        name = config.FACTORY_NAMES.get(fc, fc)
        prev = prev_map.get(fc)
        blocks.append(build_factory_section(name, row, prev))
        blocks.append(divider())

    # 전일 대비 요약
    if prev_total_prod is not None and prev_total_prod > 0:
        diff_pct = (total_prod - prev_total_prod) / prev_total_prod * 100
        blocks.append(context_block(
            f"\u2194\ufe0f *전일 대비*: 생산 {fmt_num(prev_total_prod)} \u2192 {fmt_num(total_prod)} ({diff_pct:+.1f}%)"
        ))

    send_message(f"생산 현황 ({date_str})", blocks=blocks)
    print(f"[OK] 생산 대시보드 전송 완료 ({date_str})")


if __name__ == "__main__":
    run()
