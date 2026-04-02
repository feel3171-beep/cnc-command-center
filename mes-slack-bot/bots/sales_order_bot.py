"""
영업담당자용 슬랙봇
- Sale Order별 납기/생산일정 현황
- 납기 변경 알림
- 주차별 납기/생산 스케줄
- 납기 vs 생산일정 리스크 감지
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pymssql
import config
from datetime import datetime, timedelta
from slack_sender import (
    send_message, fmt_num, divider,
    header_block, section_block, context_block,
)

CONN_PARAMS = dict(
    server=config.DB_HOST,
    port=config.DB_PORT,
    database=config.DB_NAME,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    charset="utf8",
)

FACTORY = {
    "1100": "퍼플",
    "1200": "그린",
    "1300": "제3공장",
}


def get_conn():
    return pymssql.connect(**CONN_PARAMS)


def get_customer_name(conn, code):
    """고객코드 → 고객명"""
    if not code:
        return "-"
    cur = conn.cursor(as_dict=True)
    cur.execute("""
        SELECT TOP 1 CUSTOMER_DESC FROM MWIPCUSDEF WHERE CUSTOMER_CODE = %s
    """, (code,))
    row = cur.fetchone()
    if row and row.get("CUSTOMER_DESC"):
        return row["CUSTOMER_DESC"]
    return code


def get_mat_name(conn, code):
    """자재코드 → 자재명"""
    if not code:
        return "-"
    cur = conn.cursor(as_dict=True)
    cur.execute("""
        SELECT TOP 1 MAT_DESC FROM MWIPMATDEF WHERE MAT_CODE = %s
    """, (code,))
    row = cur.fetchone()
    if row and row.get("MAT_DESC"):
        return row["MAT_DESC"]
    return code


def fmt_date(d):
    """YYYYMMDD → YYYY-MM-DD"""
    if not d or len(str(d)) < 8:
        return "-"
    s = str(d)[:8]
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def get_week_label(dt):
    """날짜 → W13 (월) 형태"""
    iso = dt.isocalendar()
    return f"W{iso[1]:02d}"


# ──────────────────────────────────────────
# 1. 주간 납기/생산 스케줄
# ──────────────────────────────────────────
def weekly_schedule():
    """이번주 + 다음주 생산 스케줄을 주차별로 정리"""
    conn = get_conn()
    cur = conn.cursor(as_dict=True)

    today = datetime.now()
    # 이번주 월요일 ~ 다음주 금요일
    mon = today - timedelta(days=today.weekday())
    fri_next = mon + timedelta(days=11)

    start = mon.strftime("%Y%m%d")
    end = fri_next.strftime("%Y%m%d")

    cur.execute("""
        SELECT
            o.FACTORY_CODE,
            o.ORDER_NO,
            o.PLAN_DATE,
            o.ORD_DATE,
            o.ORD_STATUS,
            o.CUSTOMER_CODE,
            o.MAT_CODE,
            o.ORD_QTY,
            o.ORD_OUT_QTY,
            o.ORD_CMF_3 AS SO_NO,
            o.ORD_CMF_5 AS DESCRIPTION,
            m.MAT_DESC
        FROM MWIPORDSTS o
        LEFT JOIN MWIPMATDEF m ON o.MAT_CODE = m.MAT_CODE
        WHERE o.PLAN_DATE BETWEEN %s AND %s
          AND o.ORD_STATUS IN ('PROCESS', 'WAIT', 'CLOSE')
        ORDER BY o.PLAN_DATE ASC, o.FACTORY_CODE ASC
    """, (start, end))

    rows = cur.fetchall()
    conn.close()

    if not rows:
        return None, "해당 기간 생산 스케줄 없음"

    # 주차별 그룹핑
    weeks = {}
    for r in rows:
        pd = str(r["PLAN_DATE"])
        dt = datetime(int(pd[:4]), int(pd[4:6]), int(pd[6:8]))
        wk = get_week_label(dt)
        if wk not in weeks:
            weeks[wk] = []
        weeks[wk].append(r)

    return weeks, None


def build_weekly_blocks():
    """주간 스케줄 슬랙 메시지 생성"""
    weeks, err = weekly_schedule()
    if err:
        return [section_block(f":calendar: {err}")]

    today_str = datetime.now().strftime("%Y-%m-%d")
    blocks = [
        header_block(f"📅 주간 납기/생산 스케줄 ({today_str})"),
        divider(),
    ]

    for wk, orders in weeks.items():
        # 주차별 요약
        total_qty = sum(int(o.get("ORD_QTY") or 0) for o in orders)
        done_qty = sum(int(o.get("ORD_OUT_QTY") or 0) for o in orders)
        pct = (done_qty / total_qty * 100) if total_qty > 0 else 0

        status_icon = "🟢" if pct >= 80 else ("🟡" if pct >= 50 else "🔴")

        blocks.append(section_block(
            f"*{wk}* {status_icon}  |  오더 {len(orders)}건  |  "
            f"계획 {fmt_num(total_qty)}  |  완료 {fmt_num(done_qty)} ({pct:.0f}%)"
        ))

        # 상위 5건 상세
        for o in orders[:5]:
            fac = FACTORY.get(o["FACTORY_CODE"], o["FACTORY_CODE"])
            status = {"PROCESS": "🔄진행", "WAIT": "⏳대기", "CLOSE": "✅완료"}.get(o["ORD_STATUS"], o["ORD_STATUS"])
            desc = o.get("DESCRIPTION") or o.get("MAT_DESC") or o["MAT_CODE"]
            so = o.get("SO_NO") or "-"

            blocks.append(context_block(
                f"[{fac}] {fmt_date(o['PLAN_DATE'])} | {status} | "
                f"수주#{so} | {desc[:25]} | {fmt_num(o['ORD_QTY'])}EA"
            ))

        if len(orders) > 5:
            blocks.append(context_block(f"  ... 외 {len(orders)-5}건"))

        blocks.append(divider())

    return blocks


# ──────────────────────────────────────────
# 2. 납기 변경 감지 (ORG_DUE_TIME vs SCH_DUE_TIME)
# ──────────────────────────────────────────
def detect_due_date_changes():
    """납기 변경된 오더 감지"""
    conn = get_conn()
    cur = conn.cursor(as_dict=True)

    # MWIPLOTSTS에서 ORG_DUE_TIME != SCH_DUE_TIME 인 LOT 조회
    cur.execute("""
        SELECT
            l.LOT_ID, l.ORDER_NO, l.MAT_CODE, l.QTY,
            l.ORG_DUE_TIME, l.SCH_DUE_TIME, l.LOT_STATUS,
            l.FACTORY_CODE,
            m.MAT_DESC
        FROM MWIPLOTSTS l
        LEFT JOIN MWIPMATDEF m ON l.MAT_CODE = m.MAT_CODE
        WHERE l.ORG_DUE_TIME IS NOT NULL
          AND l.SCH_DUE_TIME IS NOT NULL
          AND l.ORG_DUE_TIME != l.SCH_DUE_TIME
          AND l.DELETE_FLAG = 0
        ORDER BY l.SCH_DUE_TIME ASC
    """)

    rows = cur.fetchall()
    conn.close()
    return rows


def build_due_change_blocks():
    """납기 변경 알림 블록"""
    changes = detect_due_date_changes()

    blocks = [
        header_block("⚠️ 납기 변경 알림"),
        divider(),
    ]

    if not changes:
        blocks.append(section_block("✅ 납기가 변경된 오더가 없습니다."))
        return blocks

    blocks.append(section_block(f"🔔 *{len(changes)}건*의 납기가 변경되었습니다:"))

    for c in changes[:10]:
        fac = FACTORY.get(c["FACTORY_CODE"], c["FACTORY_CODE"])
        desc = c.get("MAT_DESC") or c["MAT_CODE"]
        org = fmt_date(c["ORG_DUE_TIME"])
        sch = fmt_date(c["SCH_DUE_TIME"])

        blocks.append(context_block(
            f"[{fac}] {c['ORDER_NO']} | {desc[:20]} | "
            f"원래납기: {org} → 변경: {sch}"
        ))

    if len(changes) > 10:
        blocks.append(context_block(f"  ... 외 {len(changes)-10}건"))

    blocks.append(divider())
    return blocks


# ──────────────────────────────────────────
# 3. 납기 리스크 감지 (납기 - 생산계획일 여유 부족)
# ──────────────────────────────────────────
def detect_delivery_risk():
    """납기 대비 생산일정이 촉박한 오더 (충전~납기 5일 미만 (QC 여유 부족))"""
    conn = get_conn()
    cur = conn.cursor(as_dict=True)

    cur.execute("""
        SELECT
            l.LOT_ID, l.ORDER_NO, l.MAT_CODE, l.QTY,
            l.ORG_DUE_TIME, l.SCH_DUE_TIME, l.LOT_STATUS,
            l.FACTORY_CODE,
            o.PLAN_DATE, o.ORD_STATUS, o.ORD_CMF_3 AS SO_NO, o.ORD_CMF_5 AS DESCRIPTION,
            m.MAT_DESC
        FROM MWIPLOTSTS l
        LEFT JOIN MWIPORDSTS o ON l.ORDER_NO = o.ORDER_NO AND l.FACTORY_CODE = o.FACTORY_CODE
        LEFT JOIN MWIPMATDEF m ON l.MAT_CODE = m.MAT_CODE
        WHERE l.SCH_DUE_TIME IS NOT NULL
          AND l.DELETE_FLAG = 0
          AND l.LOT_STATUS NOT IN ('SHIP', 'DELETE')
          AND o.ORD_STATUS IN ('PROCESS', 'WAIT')
    """)

    rows = cur.fetchall()
    conn.close()

    risks = []
    today = datetime.now()

    for r in rows:
        due = r.get("SCH_DUE_TIME") or r.get("ORG_DUE_TIME")
        plan = r.get("PLAN_DATE")
        if not due or not plan:
            continue

        due_str = str(due)[:8]
        plan_str = str(plan)[:8]

        try:
            due_dt = datetime(int(due_str[:4]), int(due_str[4:6]), int(due_str[6:8]))
            plan_dt = datetime(int(plan_str[:4]), int(plan_str[4:6]), int(plan_str[6:8]))
        except (ValueError, IndexError):
            continue

        gap_days = (due_dt - plan_dt).days

        # 충전 후 QC 5일 필요 → 5일 미만이면 리스크
        if gap_days < 5:
            r["GAP_DAYS"] = gap_days
            r["DUE_DT"] = due_dt
            r["PLAN_DT"] = plan_dt
            risks.append(r)

    risks.sort(key=lambda x: x["GAP_DAYS"])
    return risks


def build_risk_blocks():
    """납기 리스크 블록"""
    risks = detect_delivery_risk()

    blocks = [
        header_block("🚨 납기 리스크 오더"),
        divider(),
    ]

    if not risks:
        blocks.append(section_block("✅ 납기 리스크 오더가 없습니다. (납기-생산 여유 3일 이내 없음)"))
        return blocks

    # 긴급 (2일 이하 = QC 불가) vs 주의 (3~4일 = QC 촉박)
    urgent = [r for r in risks if r["GAP_DAYS"] <= 2]
    warning = [r for r in risks if 2 < r["GAP_DAYS"] < 5]

    if urgent:
        blocks.append(section_block(f"🔴 *긴급* — QC 불가 (충전~납기 2일 이하, {len(urgent)}건)"))
        for r in urgent[:5]:
            fac = FACTORY.get(r["FACTORY_CODE"], r["FACTORY_CODE"])
            desc = r.get("DESCRIPTION") or r.get("MAT_DESC") or r["MAT_CODE"]
            so = r.get("SO_NO") or "-"
            blocks.append(context_block(
                f"[{fac}] 수주#{so} | {desc[:20]} | "
                f"충전: {fmt_date(r['PLAN_DATE'])} → 납기: {fmt_date(r['SCH_DUE_TIME'] or r['ORG_DUE_TIME'])} | "
                f"*{r['GAP_DAYS']}일* (QC 5일 필요)"
            ))

    if warning:
        blocks.append(section_block(f"🟡 *주의* — QC 촉박 (충전~납기 3~4일, {len(warning)}건)"))
        for r in warning[:5]:
            fac = FACTORY.get(r["FACTORY_CODE"], r["FACTORY_CODE"])
            desc = r.get("DESCRIPTION") or r.get("MAT_DESC") or r["MAT_CODE"]
            so = r.get("SO_NO") or "-"
            blocks.append(context_block(
                f"[{fac}] 수주#{so} | {desc[:20]} | "
                f"충전: {fmt_date(r['PLAN_DATE'])} → 납기: {fmt_date(r['SCH_DUE_TIME'] or r['ORG_DUE_TIME'])} | "
                f"*{r['GAP_DAYS']}일* (QC 5일 필요)"
            ))

    blocks.append(divider())
    blocks.append(context_block("💡 충전 후 QC 5일 필요 — 고객과 선제적 커뮤니케이션이 필요한 오더입니다."))
    return blocks


# ──────────────────────────────────────────
# 4. 고객별 오더 현황 요약
# ──────────────────────────────────────────
def customer_summary():
    """고객별 진행중 오더 요약"""
    conn = get_conn()
    cur = conn.cursor(as_dict=True)

    cur.execute("""
        SELECT
            o.CUSTOMER_CODE,
            o.ORD_STATUS,
            COUNT(*) AS CNT,
            SUM(CAST(o.ORD_QTY AS bigint)) AS TOTAL_QTY,
            SUM(CAST(o.ORD_OUT_QTY AS bigint)) AS DONE_QTY,
            MIN(o.PLAN_DATE) AS EARLIEST_PLAN,
            MAX(o.PLAN_DATE) AS LATEST_PLAN
        FROM MWIPORDSTS o
        WHERE o.CUSTOMER_CODE IS NOT NULL
          AND o.ORD_STATUS IN ('PROCESS', 'WAIT')
        GROUP BY o.CUSTOMER_CODE, o.ORD_STATUS
        ORDER BY o.CUSTOMER_CODE, o.ORD_STATUS
    """)

    rows = cur.fetchall()

    # 고객명 조회
    cust_names = {}
    for r in rows:
        cc = r["CUSTOMER_CODE"]
        if cc not in cust_names:
            cust_names[cc] = get_customer_name(conn, cc)

    conn.close()

    # 고객별 집계
    summary = {}
    for r in rows:
        cc = r["CUSTOMER_CODE"]
        if cc not in summary:
            summary[cc] = {"name": cust_names.get(cc, cc), "orders": 0, "qty": 0, "done": 0, "earliest": None, "latest": None}
        summary[cc]["orders"] += r["CNT"]
        summary[cc]["qty"] += r["TOTAL_QTY"] or 0
        summary[cc]["done"] += r["DONE_QTY"] or 0
        if r["EARLIEST_PLAN"]:
            if not summary[cc]["earliest"] or r["EARLIEST_PLAN"] < summary[cc]["earliest"]:
                summary[cc]["earliest"] = r["EARLIEST_PLAN"]
        if r["LATEST_PLAN"]:
            if not summary[cc]["latest"] or r["LATEST_PLAN"] > summary[cc]["latest"]:
                summary[cc]["latest"] = r["LATEST_PLAN"]

    return summary


def build_customer_blocks():
    """고객별 요약 블록"""
    summary = customer_summary()

    blocks = [
        header_block("👥 고객별 오더 현황"),
        divider(),
    ]

    if not summary:
        blocks.append(section_block("진행중인 고객 오더가 없습니다."))
        return blocks

    # 오더 수 기준 내림차순
    sorted_custs = sorted(summary.values(), key=lambda x: x["orders"], reverse=True)

    for c in sorted_custs[:10]:
        pct = (c["done"] / c["qty"] * 100) if c["qty"] > 0 else 0
        icon = "🟢" if pct >= 80 else ("🟡" if pct >= 50 else "🔴")

        blocks.append(section_block(
            f"{icon} *{c['name']}*\n"
            f"  오더 {c['orders']}건 | 계획 {fmt_num(c['qty'])}EA | "
            f"완료 {fmt_num(c['done'])}EA ({pct:.0f}%)\n"
            f"  생산기간: {fmt_date(c['earliest'])} ~ {fmt_date(c['latest'])}"
        ))

    if len(sorted_custs) > 10:
        blocks.append(context_block(f"  ... 외 {len(sorted_custs)-10}개 고객"))

    blocks.append(divider())
    return blocks


# ──────────────────────────────────────────
# 메인: 전체 영업 알림 발송
# ──────────────────────────────────────────
def run():
    today_str = datetime.now().strftime("%Y-%m-%d")

    all_blocks = []

    # 1) 주간 스케줄
    all_blocks.extend(build_weekly_blocks())

    # 2) 납기 변경 알림
    all_blocks.extend(build_due_change_blocks())

    # 3) 납기 리스크
    all_blocks.extend(build_risk_blocks())

    # 4) 고객별 현황
    all_blocks.extend(build_customer_blocks())

    # 푸터
    all_blocks.append(context_block(f"📊 영업담당자 알림 | {today_str} | MES Bot"))

    send_message(f"영업담당자 알림 ({today_str})", blocks=all_blocks)
    print(f"[{today_str}] 영업담당자 알림 전송 완료")


if __name__ == "__main__":
    run()
