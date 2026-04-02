"""주간/월간 분석 리포트 - 생산성, 불량률, 추이 분석"""

from datetime import datetime, timedelta
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct, status_emoji,
    divider, header_block, section_block, context_block,
)


def get_period_summary(start_date, end_date):
    """기간별 공장 생산 요약"""
    sql = """
        SELECT
            o.FACTORY_CODE,
            COUNT(DISTINCT o.ORDER_NO) as ORD_COUNT,
            COUNT(DISTINCT o.PLAN_DATE) as WORK_DAYS,
            SUM(o.ORD_QTY) as PLAN_QTY,
            SUM(o.ORD_OUT_QTY) as PROD_QTY,
            SUM(o.RCV_GOOD_QTY) as GOOD_QTY,
            SUM(o.RCV_LOSS_QTY) as LOSS_QTY,
            CASE WHEN SUM(o.ORD_QTY) > 0
                 THEN CAST(100.0 * SUM(o.ORD_OUT_QTY) / SUM(o.ORD_QTY) AS decimal(5,2))
                 ELSE 0 END as ACHIEVEMENT
        FROM MWIPORDSTS o
        WHERE o.PLAN_DATE BETWEEN %s AND %s
        GROUP BY o.FACTORY_CODE
        ORDER BY o.FACTORY_CODE
    """
    return db.query(sql, (start_date, end_date))


def get_defect_top5(start_date, end_date):
    """불량률 Top 5 품목"""
    sql = """
        SELECT TOP 5
            o.FACTORY_CODE,
            o.MAT_CODE,
            m.MAT_DESC,
            SUM(o.RCV_GOOD_QTY) as GOOD_QTY,
            SUM(o.RCV_LOSS_QTY) as LOSS_QTY,
            CASE WHEN SUM(o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) > 0
                 THEN CAST(100.0 * SUM(o.RCV_LOSS_QTY) / SUM(o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) AS decimal(5,2))
                 ELSE 0 END as DEFECT_RATE
        FROM MWIPORDSTS o
        LEFT JOIN MWIPMATDEF m ON o.FACTORY_CODE = m.FACTORY_CODE AND o.MAT_CODE = m.MAT_CODE
        WHERE o.PLAN_DATE BETWEEN %s AND %s
          AND (o.RCV_GOOD_QTY + o.RCV_LOSS_QTY) > 100
        GROUP BY o.FACTORY_CODE, o.MAT_CODE, m.MAT_DESC
        HAVING SUM(o.RCV_LOSS_QTY) > 0
        ORDER BY DEFECT_RATE DESC
    """
    return db.query(sql, (start_date, end_date))


def get_line_productivity(start_date, end_date):
    """라인별 생산성 Top 5"""
    sql = """
        SELECT TOP 5
            o.FACTORY_CODE,
            o.LINE_CODE,
            l.LINE_DESC,
            SUM(o.ORD_OUT_QTY) as TOTAL_PROD,
            COUNT(DISTINCT o.PLAN_DATE) as WORK_DAYS,
            CAST(SUM(o.ORD_OUT_QTY) / NULLIF(COUNT(DISTINCT o.PLAN_DATE), 0) AS decimal(10,0)) as DAILY_AVG
        FROM MWIPORDSTS o
        LEFT JOIN MWIPLINDEF l ON o.FACTORY_CODE = l.FACTORY_CODE AND o.LINE_CODE = l.LINE_CODE
        WHERE o.PLAN_DATE BETWEEN %s AND %s
          AND o.ORD_OUT_QTY > 0
        GROUP BY o.FACTORY_CODE, o.LINE_CODE, l.LINE_DESC
        ORDER BY TOTAL_PROD DESC
    """
    return db.query(sql, (start_date, end_date))


def run_weekly(target_date=None):
    """주간 리포트"""
    today = datetime.strptime(target_date, "%Y%m%d") if target_date else datetime.now()
    # 이번주 월~오늘
    week_start = today - timedelta(days=today.weekday())
    this_start = week_start.strftime("%Y%m%d")
    this_end = today.strftime("%Y%m%d")
    # 전주
    prev_start = (week_start - timedelta(days=7)).strftime("%Y%m%d")
    prev_end = (week_start - timedelta(days=1)).strftime("%Y%m%d")

    this_data = get_period_summary(this_start, this_end)
    prev_data = get_period_summary(prev_start, prev_end)
    defect_top = get_defect_top5(this_start, this_end)
    line_top = get_line_productivity(this_start, this_end)

    prev_map = {r["FACTORY_CODE"]: r for r in prev_data}

    date_range = f"{this_start[:4]}-{this_start[4:6]}-{this_start[6:]} ~ {this_end[:4]}-{this_end[4:6]}-{this_end[6:]}"
    blocks = [header_block(f"\U0001f4ca 주간 생산 리포트 ({date_range})")]

    # 공장별 요약
    total_plan = sum(r["PLAN_QTY"] or 0 for r in this_data)
    total_prod = sum(r["PROD_QTY"] or 0 for r in this_data)
    total_good = sum(r["GOOD_QTY"] or 0 for r in this_data)
    total_loss = sum(r["LOSS_QTY"] or 0 for r in this_data)
    total_pct = (total_prod / total_plan * 100) if total_plan > 0 else 0

    blocks.append(section_block(
        f"*전체 요약*\n"
        f"  생산: {fmt_num(total_prod)} / {fmt_num(total_plan)} ({fmt_pct(total_pct)})\n"
        f"  양품: {fmt_num(total_good)} | 불량: {fmt_num(total_loss)}"
    ))
    blocks.append(divider())

    for row in this_data:
        fc = row["FACTORY_CODE"]
        name = config.FACTORY_NAMES.get(fc, fc)
        prev = prev_map.get(fc)
        pct = row["ACHIEVEMENT"] or 0
        emoji = status_emoji(pct)

        text = f"*{name}* {emoji}\n"
        text += f"  생산: {fmt_num(row['PROD_QTY'])} / {fmt_num(row['PLAN_QTY'])} ({fmt_pct(pct)})\n"
        text += f"  작업일수: {row['WORK_DAYS']}일 | 지시: {row['ORD_COUNT']}건"
        if prev:
            prev_prod = prev["PROD_QTY"] or 0
            curr_prod = row["PROD_QTY"] or 0
            if prev_prod > 0:
                diff = (curr_prod - prev_prod) / prev_prod * 100
                text += f"\n  전주 대비: {diff:+.1f}%"
        blocks.append(section_block(text))

    blocks.append(divider())

    # 불량률 Top 5
    if defect_top:
        lines = ["*\U0001f534 불량률 Top 5 품목*"]
        for i, d in enumerate(defect_top, 1):
            fc_name = config.FACTORY_NAMES.get(d["FACTORY_CODE"], d["FACTORY_CODE"])
            mat = d["MAT_DESC"] or d["MAT_CODE"]
            if len(mat) > 25:
                mat = mat[:25] + "..."
            lines.append(f"  {i}. [{fc_name}] {mat} — {fmt_pct(d['DEFECT_RATE'])} (불량 {fmt_num(d['LOSS_QTY'])}개)")
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 생산성 Top 5 라인
    if line_top:
        lines = ["*\U0001f3ed 생산성 Top 5 라인*"]
        for i, lt in enumerate(line_top, 1):
            fc_name = config.FACTORY_NAMES.get(lt["FACTORY_CODE"], lt["FACTORY_CODE"])
            lines.append(
                f"  {i}. [{fc_name}] {lt['LINE_DESC'] or lt['LINE_CODE']} — "
                f"총 {fmt_num(lt['TOTAL_PROD'])}개 (일평균 {fmt_num(lt['DAILY_AVG'])}개)"
            )
        blocks.append(section_block("\n".join(lines)))

    send_message(f"주간 리포트 ({date_range})", blocks=blocks)
    print(f"[OK] 주간 리포트 전송 완료 ({date_range})")


def run(target_date=None):
    run_weekly(target_date)


if __name__ == "__main__":
    run()
