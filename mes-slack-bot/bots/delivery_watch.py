"""납기 변경 감시 봇 — 납기 변동, 자재 미입고, 생산 미연동, 일정 지연 감지"""

from datetime import datetime
import db
import config
from slack_sender import (
    send_message, fmt_num, fmt_pct,
    divider, header_block, section_block, context_block,
)


def detect_delivery_date_changes():
    """납기일이 변경된 출하 건 감지 (IINVSHPMST I/F 이력 기반)"""
    sql = """
        WITH ranked AS (
            SELECT
                SHIP_ORD_NO, SHIP_PLAN_DATE, CUSTOMER_CODE,
                IF_SQ, IF_TYPE, IF_PROCESS_DT,
                LAG(SHIP_PLAN_DATE) OVER (PARTITION BY SHIP_ORD_NO ORDER BY IF_SQ) as PREV_DATE
            FROM IINVSHPMST
            WHERE SHIP_PLAN_DATE IS NOT NULL AND SHIP_PLAN_DATE != ''
        )
        SELECT
            r.SHIP_ORD_NO,
            r.PREV_DATE as OLD_DATE,
            r.SHIP_PLAN_DATE as NEW_DATE,
            r.CUSTOMER_CODE,
            c.CUSTOMER_DESC,
            r.IF_PROCESS_DT,
            CASE WHEN r.SHIP_PLAN_DATE < r.PREV_DATE THEN 'EARLIER'
                 ELSE 'LATER' END as DIRECTION,
            DATEDIFF(day,
                CONVERT(datetime, r.PREV_DATE, 112),
                CONVERT(datetime, r.SHIP_PLAN_DATE, 112)) as DIFF_DAYS
        FROM ranked r
        LEFT JOIN MWIPCUSDEF c ON r.CUSTOMER_CODE = c.CUSTOMER_CODE
        WHERE r.PREV_DATE IS NOT NULL
          AND r.SHIP_PLAN_DATE != r.PREV_DATE
          AND LEN(r.PREV_DATE) = 8 AND LEN(r.SHIP_PLAN_DATE) = 8
          AND ISDATE(r.PREV_DATE) = 1 AND ISDATE(r.SHIP_PLAN_DATE) = 1
        ORDER BY r.IF_PROCESS_DT DESC
    """
    return db.query(sql)


def detect_changed_but_no_material():
    """납기가 변경(앞당겨짐)되었는데 자재 입고가 안 된 건"""
    sql = """
        WITH latest_date AS (
            SELECT SHIP_ORD_NO,
                MAX(SHIP_PLAN_DATE) as LATEST_DATE,
                MIN(SHIP_PLAN_DATE) as FIRST_DATE
            FROM IINVSHPMST
            WHERE SHIP_PLAN_DATE IS NOT NULL AND SHIP_PLAN_DATE != ''
              AND LEN(SHIP_PLAN_DATE) = 8 AND ISDATE(SHIP_PLAN_DATE) = 1
            GROUP BY SHIP_ORD_NO
            HAVING COUNT(DISTINCT SHIP_PLAN_DATE) > 1
        )
        SELECT
            ld.SHIP_ORD_NO,
            ld.FIRST_DATE as 최초납기,
            ld.LATEST_DATE as 현재납기,
            sd.MAT_CODE,
            m.MAT_DESC,
            sd.SHIP_PLAN_QTY,
            ISNULL(rcv.RCV_QTY, 0) as 입고수량,
            sd.SHIP_PLAN_QTY - ISNULL(rcv.RCV_QTY, 0) as 미입고수량
        FROM latest_date ld
        INNER JOIN MINVSHPDTL sd ON ld.SHIP_ORD_NO = sd.SHIP_ORD_NO
        LEFT JOIN MWIPMATDEF m ON sd.FACTORY_CODE = m.FACTORY_CODE AND sd.MAT_CODE = m.MAT_CODE
        LEFT JOIN (
            SELECT MAT_CODE, SUM(TRAN_QTY) as RCV_QTY
            FROM MINVLOTRCV
            WHERE TRAN_TIME >= DATEADD(day, -90, GETDATE())
            GROUP BY MAT_CODE
        ) rcv ON sd.MAT_CODE = rcv.MAT_CODE
        WHERE sd.SHIP_PLAN_QTY > ISNULL(rcv.RCV_QTY, 0)
        ORDER BY 미입고수량 DESC
    """
    return db.query(sql)


def detect_changed_but_no_production():
    """납기가 변경되었는데 생산 계획에 안 잡힌 건"""
    sql = """
        WITH latest_ship AS (
            SELECT SHIP_ORD_NO,
                MAX(SHIP_PLAN_DATE) as CURRENT_DUE,
                MIN(SHIP_PLAN_DATE) as ORIGINAL_DUE
            FROM IINVSHPMST
            WHERE SHIP_PLAN_DATE IS NOT NULL AND SHIP_PLAN_DATE != ''
              AND LEN(SHIP_PLAN_DATE) = 8 AND ISDATE(SHIP_PLAN_DATE) = 1
            GROUP BY SHIP_ORD_NO
            HAVING COUNT(DISTINCT SHIP_PLAN_DATE) > 1
        )
        SELECT
            ls.SHIP_ORD_NO,
            ls.ORIGINAL_DUE as 최초납기,
            ls.CURRENT_DUE as 현재납기,
            sd.MAT_CODE,
            m.MAT_DESC,
            sd.SHIP_PLAN_QTY,
            ISNULL(prod.PLAN_QTY, 0) as 생산계획수량,
            ISNULL(prod.PROD_QTY, 0) as 생산완료수량,
            CASE WHEN ISNULL(prod.PLAN_QTY, 0) = 0 THEN 'NO_PLAN'
                 WHEN ISNULL(prod.PROD_QTY, 0) = 0 THEN 'NOT_STARTED'
                 WHEN ISNULL(prod.PROD_QTY, 0) < sd.SHIP_PLAN_QTY THEN 'IN_PROGRESS'
                 ELSE 'OK' END as STATUS
        FROM latest_ship ls
        INNER JOIN MINVSHPDTL sd ON ls.SHIP_ORD_NO = sd.SHIP_ORD_NO
        LEFT JOIN MWIPMATDEF m ON sd.FACTORY_CODE = m.FACTORY_CODE AND sd.MAT_CODE = m.MAT_CODE
        LEFT JOIN (
            SELECT MAT_CODE, FACTORY_CODE,
                SUM(ORD_QTY) as PLAN_QTY,
                SUM(ORD_OUT_QTY) as PROD_QTY
            FROM MWIPORDSTS
            WHERE ORD_STATUS = 'CONFIRM'
            GROUP BY MAT_CODE, FACTORY_CODE
        ) prod ON sd.MAT_CODE = prod.MAT_CODE AND sd.FACTORY_CODE = prod.FACTORY_CODE
        WHERE ISNULL(prod.PROD_QTY, 0) < sd.SHIP_PLAN_QTY
        ORDER BY
            CASE WHEN ISNULL(prod.PLAN_QTY, 0) = 0 THEN 0
                 WHEN ISNULL(prod.PROD_QTY, 0) = 0 THEN 1
                 ELSE 2 END,
            ls.CURRENT_DUE ASC
    """
    return db.query(sql)


def detect_delayed_production():
    """생산 일정이 납기 대비 뒤로 밀린 건 — 생산계획일이 출하 납기 이후"""
    sql = """
        SELECT
            s.SHIP_ORD_NO,
            s.SHIP_PLAN_DATE as 납기일,
            s.CUSTOMER_CODE,
            c.CUSTOMER_DESC,
            sd.MAT_CODE,
            m.MAT_DESC,
            sd.SHIP_PLAN_QTY,
            o.ORDER_NO,
            o.PLAN_DATE as 생산계획일,
            o.ORD_QTY,
            o.ORD_OUT_QTY,
            DATEDIFF(day,
                CONVERT(datetime, s.SHIP_PLAN_DATE, 112),
                CONVERT(datetime, o.PLAN_DATE, 112)) as 지연일수
        FROM MINVSHPMST s
        INNER JOIN MINVSHPDTL sd ON s.FACTORY_CODE = sd.FACTORY_CODE AND s.SHIP_ORD_NO = sd.SHIP_ORD_NO
        INNER JOIN MWIPORDSTS o ON sd.FACTORY_CODE = o.FACTORY_CODE AND sd.MAT_CODE = o.MAT_CODE
            AND o.ORD_STATUS = 'CONFIRM' AND o.ORD_OUT_QTY < o.ORD_QTY
        LEFT JOIN MWIPMATDEF m ON sd.FACTORY_CODE = m.FACTORY_CODE AND sd.MAT_CODE = m.MAT_CODE
        LEFT JOIN MWIPCUSDEF c ON s.FACTORY_CODE = c.FACTORY_CODE AND s.CUSTOMER_CODE = c.CUSTOMER_CODE
        WHERE s.SHIP_STATUS NOT IN ('CLOSE', 'COMPLETE')
          AND LEN(s.SHIP_PLAN_DATE) = 8 AND ISDATE(s.SHIP_PLAN_DATE) = 1
          AND LEN(o.PLAN_DATE) = 8 AND ISDATE(o.PLAN_DATE) = 1 AND o.PLAN_DATE != '00000000'
          AND o.PLAN_DATE > s.SHIP_PLAN_DATE
        ORDER BY 지연일수 DESC
    """
    return db.query(sql)


def fmt_date(d):
    if not d or len(d) < 8:
        return "-"
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def run(target_date=None):
    today = target_date or datetime.now().strftime("%Y%m%d")
    date_str = fmt_date(today)
    blocks = [header_block(f"\U0001f4e2 납기 변경 감시 알림 ({date_str})")]
    alerts_found = False

    # 1. 납기일 변경 감지
    changes = detect_delivery_date_changes()
    if changes:
        alerts_found = True
        earlier = [c for c in changes if c["DIRECTION"] == "EARLIER"]
        later = [c for c in changes if c["DIRECTION"] == "LATER"]

        if earlier:
            lines = [f"\u23e9 *납기 앞당겨짐 ({len(earlier)}건)* — 생산 가속 필요"]
            for c in earlier[:5]:
                cust = (c["CUSTOMER_DESC"] or c["CUSTOMER_CODE"] or "-")[:18]
                lines.append(
                    f"  \U0001f534 {c['SHIP_ORD_NO']} | {cust}\n"
                    f"     {fmt_date(c['OLD_DATE'])} \u2192 *{fmt_date(c['NEW_DATE'])}* ({c['DIFF_DAYS']}일 앞당김)"
                )
            blocks.append(section_block("\n".join(lines)))
            blocks.append(divider())

        if later:
            lines = [f"\u23ea *납기 연기 ({len(later)}건)*"]
            for c in later[:5]:
                cust = (c["CUSTOMER_DESC"] or c["CUSTOMER_CODE"] or "-")[:18]
                lines.append(
                    f"  \U0001f7e1 {c['SHIP_ORD_NO']} | {cust}\n"
                    f"     {fmt_date(c['OLD_DATE'])} \u2192 *{fmt_date(c['NEW_DATE'])}* (+{c['DIFF_DAYS']}일)"
                )
            blocks.append(section_block("\n".join(lines)))
            blocks.append(divider())

    # 2. 납기 변경 + 자재 미입고
    no_mat = detect_changed_but_no_material()
    if no_mat:
        alerts_found = True
        lines = [f"\U0001f4e6 *납기 변경 + 자재 미입고 ({len(no_mat)}건)*"]
        for nm in no_mat[:5]:
            mat = (nm["MAT_DESC"] or nm["MAT_CODE"])[:20]
            lines.append(
                f"  \U0001f534 {nm['SHIP_ORD_NO']} | {mat}\n"
                f"     납기 {fmt_date(nm['최초납기'])}\u2192{fmt_date(nm['현재납기'])} | "
                f"필요 {fmt_num(nm['SHIP_PLAN_QTY'])} / 입고 {fmt_num(nm['입고수량'])} / *미입고 {fmt_num(nm['미입고수량'])}*"
            )
        blocks.append(section_block("\n".join(lines)))
        blocks.append(divider())

    # 3. 납기 변경 + 생산 미계획/미착수
    no_prod = detect_changed_but_no_production()
    if no_prod:
        no_plan = [p for p in no_prod if p["STATUS"] == "NO_PLAN"]
        not_started = [p for p in no_prod if p["STATUS"] == "NOT_STARTED"]

        if no_plan:
            alerts_found = True
            lines = [f"\U0001f6a8 *납기 변경 + 생산 미계획 ({len(no_plan)}건)* — 즉시 조치 필요!"]
            for np in no_plan[:5]:
                mat = (np["MAT_DESC"] or np["MAT_CODE"])[:20]
                lines.append(
                    f"  \U0001f534 {np['SHIP_ORD_NO']} | {mat}\n"
                    f"     납기 {fmt_date(np['현재납기'])} | 출하 {fmt_num(np['SHIP_PLAN_QTY'])}개 | *생산계획 없음!*"
                )
            blocks.append(section_block("\n".join(lines)))
            blocks.append(divider())

        if not_started:
            alerts_found = True
            lines = [f"\u26a0\ufe0f *납기 변경 + 생산 미착수 ({len(not_started)}건)*"]
            for ns in not_started[:5]:
                mat = (ns["MAT_DESC"] or ns["MAT_CODE"])[:20]
                lines.append(
                    f"  \U0001f7e1 {ns['SHIP_ORD_NO']} | {mat}\n"
                    f"     납기 {fmt_date(ns['현재납기'])} | 계획 {fmt_num(ns['생산계획수량'])}개 | 생산 0개"
                )
            blocks.append(section_block("\n".join(lines)))
            blocks.append(divider())

    # 4. 생산 일정 > 납기 (밀린 건)
    delayed = detect_delayed_production()
    if delayed:
        alerts_found = True
        lines = [f"\U0001f4c5 *생산 일정 납기 초과 ({len(delayed)}건)* — 생산이 납기보다 늦음"]
        for d in delayed[:5]:
            cust = (d["CUSTOMER_DESC"] or d["CUSTOMER_CODE"] or "-")[:15]
            mat = (d["MAT_DESC"] or d["MAT_CODE"])[:18]
            lines.append(
                f"  \U0001f534 {d['SHIP_ORD_NO']} | {cust} | {mat}\n"
                f"     납기 *{fmt_date(d['납기일'])}* vs 생산계획 *{fmt_date(d['생산계획일'])}* "
                f"(\U0001f4a5 {d['지연일수']}일 초과)"
            )
        blocks.append(section_block("\n".join(lines)))

    if not alerts_found:
        blocks.append(section_block("\u2705 납기 관련 이상 없음"))

    blocks.append(context_block(
        "\U0001f4a1 조치 우선순위: "
        "\U0001f6a8 생산미계획 > \U0001f534 납기앞당김+미입고 > \U0001f534 일정초과 > \U0001f7e1 미착수 > \u23ea 연기"
    ))

    send_message(f"납기 변경 감시 ({date_str})", blocks=blocks)
    print(f"[OK] 납기 변경 감시 알림 전송 ({date_str})")


if __name__ == "__main__":
    run()
