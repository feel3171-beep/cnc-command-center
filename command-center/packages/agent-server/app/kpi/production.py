"""Production KPI — ported from production-agent/main.py"""

from datetime import datetime, timedelta
from app.db.mssql import run_query
from app.config import FACTORY_NAMES


def calc_rate(actual: float, plan: float) -> float:
    return round(actual * 100 / plan, 1) if plan and plan > 0 else 0.0


def get_summary(date: str = None) -> dict:
    d = (date or datetime.now().strftime("%Y-%m-%d")).replace("-", "")

    rows = run_query("""
        SELECT
            FACTORY_CODE,
            SUM(CAST(ORD_QTY AS BIGINT)) AS PLAN_QTY,
            SUM(CAST(ORD_OUT_QTY AS BIGINT)) AS ACTUAL_QTY,
            SUM(CAST(RCV_GOOD_QTY AS BIGINT)) AS GOOD_QTY,
            SUM(CAST(RCV_LOSS_QTY AS BIGINT)) AS LOSS_QTY,
            COUNT(DISTINCT ORDER_NO) AS ORDER_CNT
        FROM MWIPORDSTS
        WHERE ORD_DATE = %s AND ORD_STATUS NOT IN ('DELETE')
        GROUP BY FACTORY_CODE
    """, (d,))

    factories = []
    total = dict(plan=0, actual=0, good=0, loss=0, orders=0)

    for r in sorted(rows, key=lambda x: x["FACTORY_CODE"]):
        fc = r["FACTORY_CODE"]
        plan = int(r["PLAN_QTY"] or 0)
        act = int(r["ACTUAL_QTY"] or 0)
        good = int(r["GOOD_QTY"] or 0)
        loss = int(r["LOSS_QTY"] or 0)
        orders = int(r["ORDER_CNT"] or 0)

        total["plan"] += plan
        total["actual"] += act
        total["good"] += good
        total["loss"] += loss
        total["orders"] += orders

        factories.append({
            "factory_code": fc,
            "factory_name": FACTORY_NAMES.get(fc, fc),
            "plan_qty": plan,
            "actual_qty": act,
            "good_qty": good,
            "loss_qty": loss,
            "achievement_rate": calc_rate(act, plan),
            "good_rate": calc_rate(good, act),
            "order_cnt": orders,
        })

    return {
        "date": d,
        "total": {
            "plan_qty": total["plan"],
            "actual_qty": total["actual"],
            "good_qty": total["good"],
            "loss_qty": total["loss"],
            "achievement_rate": calc_rate(total["actual"], total["plan"]),
            "good_rate": calc_rate(total["good"], total["actual"]),
            "order_cnt": total["orders"],
        },
        "factories": factories,
    }


def get_trend(days: int = 14) -> list[dict]:
    end = datetime.now()
    start = end - timedelta(days=days - 1)

    rows = run_query("""
        SELECT
            ORD_DATE, FACTORY_CODE,
            SUM(CAST(ORD_QTY AS BIGINT)) AS PLAN_QTY,
            SUM(CAST(ORD_OUT_QTY AS BIGINT)) AS ACTUAL_QTY,
            SUM(CAST(RCV_GOOD_QTY AS BIGINT)) AS GOOD_QTY
        FROM MWIPORDSTS
        WHERE ORD_DATE >= %s AND ORD_DATE <= %s
          AND ORD_STATUS NOT IN ('DELETE')
        GROUP BY ORD_DATE, FACTORY_CODE
        ORDER BY ORD_DATE, FACTORY_CODE
    """, (start.strftime("%Y%m%d"), end.strftime("%Y%m%d")))

    result = []
    for r in rows:
        fc = r["FACTORY_CODE"]
        plan = int(r["PLAN_QTY"] or 0)
        act = int(r["ACTUAL_QTY"] or 0)
        d = r["ORD_DATE"]
        result.append({
            "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
            "factory_code": fc,
            "factory_name": FACTORY_NAMES.get(fc, fc),
            "plan_qty": plan,
            "actual_qty": act,
            "good_qty": int(r["GOOD_QTY"] or 0),
            "achievement_rate": calc_rate(act, plan),
        })

    return result
