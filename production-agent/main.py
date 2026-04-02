import decimal
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import anthropic
import pyodbc
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="생산 분석 에이전트")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB 설정 ────────────────────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "192.161.0.16")
DB_PORT = os.getenv("DB_PORT", "1433")
DB_NAME = os.getenv("DB_NAME", "MES")
DB_USER = os.getenv("DB_USER", "mestmp")
DB_PASS = os.getenv("DB_PASS", "cncmgr123!")

ODBC_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server",
]


def get_conn_str() -> str:
    for drv in ODBC_DRIVERS:
        if drv in pyodbc.drivers():
            return (
                f"DRIVER={{{drv}}};"
                f"SERVER={DB_HOST},{DB_PORT};"
                f"DATABASE={DB_NAME};"
                f"UID={DB_USER};"
                f"PWD={DB_PASS};"
                "Encrypt=no;"
                "TrustServerCertificate=yes;"
            )
    raise RuntimeError("ODBC Driver를 찾을 수 없습니다. Microsoft ODBC Driver 17 for SQL Server를 설치하세요.")


FACTORY_NAMES = {"1100": "퍼플", "1200": "그린", "1300": "제3공장"}
CLAUDE_MODEL = "claude-sonnet-4-6"


# ── DB 헬퍼 ───────────────────────────────────────────────────────────────────
def run_query(sql: str, params=None) -> list[dict]:
    conn = pyodbc.connect(get_conn_str())
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params or [])
        cols = [d[0] for d in cursor.description]
        rows = []
        for r in cursor.fetchall():
            row = {}
            for c, v in zip(cols, r):
                if isinstance(v, decimal.Decimal):
                    v = float(v)
                row[c] = v
            rows.append(row)
        return rows
    finally:
        conn.close()


def fmt_date(s: str) -> str:
    """YYYY-MM-DD 또는 YYYYMMDD → YYYYMMDD"""
    return s.replace("-", "")


def calc_rate(actual: float, plan: float) -> float:
    return round(actual * 100 / plan, 1) if plan and plan > 0 else 0.0


# ── API 엔드포인트 ─────────────────────────────────────────────────────────────

@app.get("/api/recent-date")
async def recent_date():
    """데이터가 존재하는 가장 최근 작업일자 반환"""
    rows = run_query(
        "SELECT TOP 1 ORD_DATE FROM MWIPORDSTS "
        "WHERE ORD_STATUS NOT IN ('DELETE') AND ORD_OUT_QTY > 0 "
        "ORDER BY ORD_DATE DESC"
    )
    if rows:
        d = rows[0]["ORD_DATE"]
        return {"date": f"{d[:4]}-{d[4:6]}-{d[6:]}"}
    return {"date": datetime.now().strftime("%Y-%m-%d")}


@app.get("/api/summary")
async def summary(date: str = None):
    """공장별 일간 KPI 요약"""
    d = fmt_date(date) if date else datetime.now().strftime("%Y%m%d")

    rows = run_query(
        """
        SELECT
            FACTORY_CODE,
            SUM(CAST(ORD_QTY     AS BIGINT)) AS PLAN_QTY,
            SUM(CAST(ORD_OUT_QTY AS BIGINT)) AS ACTUAL_QTY,
            SUM(CAST(RCV_GOOD_QTY AS BIGINT)) AS GOOD_QTY,
            SUM(CAST(RCV_LOSS_QTY AS BIGINT)) AS LOSS_QTY,
            COUNT(DISTINCT ORDER_NO)           AS ORDER_CNT
        FROM MWIPORDSTS
        WHERE ORD_DATE = ? AND ORD_STATUS NOT IN ('DELETE')
        GROUP BY FACTORY_CODE
        """,
        [d],
    )

    factories = []
    total = dict(plan=0, actual=0, good=0, loss=0, orders=0)

    for r in sorted(rows, key=lambda x: x["FACTORY_CODE"]):
        fc    = r["FACTORY_CODE"]
        plan  = int(r["PLAN_QTY"]  or 0)
        act   = int(r["ACTUAL_QTY"] or 0)
        good  = int(r["GOOD_QTY"]  or 0)
        loss  = int(r["LOSS_QTY"]  or 0)
        orders = int(r["ORDER_CNT"] or 0)

        total["plan"]   += plan
        total["actual"] += act
        total["good"]   += good
        total["loss"]   += loss
        total["orders"] += orders

        factories.append({
            "factory_code":     fc,
            "factory_name":     FACTORY_NAMES.get(fc, fc),
            "plan_qty":         plan,
            "actual_qty":       act,
            "good_qty":         good,
            "loss_qty":         loss,
            "achievement_rate": calc_rate(act, plan),
            "good_rate":        calc_rate(good, act),
            "order_cnt":        orders,
        })

    return {
        "date": d,
        "total": {
            "plan_qty":         total["plan"],
            "actual_qty":       total["actual"],
            "good_qty":         total["good"],
            "loss_qty":         total["loss"],
            "achievement_rate": calc_rate(total["actual"], total["plan"]),
            "good_rate":        calc_rate(total["good"], total["actual"]),
            "order_cnt":        total["orders"],
        },
        "factories": factories,
    }


@app.get("/api/lines")
async def lines(date: str = None, factory: str = None):
    """라인별 상세 현황"""
    d = fmt_date(date) if date else datetime.now().strftime("%Y%m%d")

    extra  = " AND FACTORY_CODE = ?" if factory else ""
    params = [d] + ([factory] if factory else [])

    rows = run_query(
        f"""
        SELECT
            FACTORY_CODE, LINE_CODE,
            COUNT(DISTINCT ORDER_NO)           AS ORDER_CNT,
            SUM(CAST(ORD_QTY      AS BIGINT))  AS PLAN_QTY,
            SUM(CAST(ORD_OUT_QTY  AS BIGINT))  AS ACTUAL_QTY,
            SUM(CAST(RCV_GOOD_QTY AS BIGINT))  AS GOOD_QTY,
            SUM(CAST(RCV_LOSS_QTY AS BIGINT))  AS LOSS_QTY
        FROM MWIPORDSTS
        WHERE ORD_DATE = ? AND ORD_STATUS NOT IN ('DELETE'){extra}
        GROUP BY FACTORY_CODE, LINE_CODE
        ORDER BY FACTORY_CODE, LINE_CODE
        """,
        params,
    )

    result = []
    for r in rows:
        fc   = r["FACTORY_CODE"]
        plan = int(r["PLAN_QTY"]  or 0)
        act  = int(r["ACTUAL_QTY"] or 0)
        good = int(r["GOOD_QTY"]  or 0)
        result.append({
            "factory_code":     fc,
            "factory_name":     FACTORY_NAMES.get(fc, fc),
            "line_code":        r["LINE_CODE"],
            "order_cnt":        int(r["ORDER_CNT"] or 0),
            "plan_qty":         plan,
            "actual_qty":       act,
            "good_qty":         good,
            "loss_qty":         int(r["LOSS_QTY"] or 0),
            "achievement_rate": calc_rate(act, plan),
            "good_rate":        calc_rate(good, act),
        })

    return {"date": d, "data": result}


@app.get("/api/trend")
async def trend(days: int = 14):
    """일별 생산 추이"""
    end   = datetime.now()
    start = end - timedelta(days=days - 1)

    rows = run_query(
        """
        SELECT
            ORD_DATE, FACTORY_CODE,
            SUM(CAST(ORD_QTY      AS BIGINT)) AS PLAN_QTY,
            SUM(CAST(ORD_OUT_QTY  AS BIGINT)) AS ACTUAL_QTY,
            SUM(CAST(RCV_GOOD_QTY AS BIGINT)) AS GOOD_QTY
        FROM MWIPORDSTS
        WHERE ORD_DATE >= ? AND ORD_DATE <= ?
          AND ORD_STATUS NOT IN ('DELETE')
        GROUP BY ORD_DATE, FACTORY_CODE
        ORDER BY ORD_DATE, FACTORY_CODE
        """,
        [start.strftime("%Y%m%d"), end.strftime("%Y%m%d")],
    )

    result = []
    for r in rows:
        fc   = r["FACTORY_CODE"]
        plan = int(r["PLAN_QTY"]  or 0)
        act  = int(r["ACTUAL_QTY"] or 0)
        d    = r["ORD_DATE"]
        result.append({
            "date":             f"{d[:4]}-{d[4:6]}-{d[6:]}",
            "factory_code":     fc,
            "factory_name":     FACTORY_NAMES.get(fc, fc),
            "plan_qty":         plan,
            "actual_qty":       act,
            "good_qty":         int(r["GOOD_QTY"] or 0),
            "achievement_rate": calc_rate(act, plan),
        })

    return {"data": result}


@app.get("/api/orders")
async def orders(date: str = None, factory: str = None, limit: int = 50):
    """작업지시 목록"""
    d = fmt_date(date) if date else datetime.now().strftime("%Y%m%d")

    extra  = " AND o.FACTORY_CODE = ?" if factory else ""
    params = [d] + ([factory] if factory else [])

    rows = run_query(
        f"""
        SELECT TOP {limit}
            o.FACTORY_CODE,
            o.ORDER_NO,
            o.LINE_CODE,
            o.MAT_CODE,
            o.ORD_STATUS,
            o.ORD_QTY,
            o.ORD_OUT_QTY,
            o.RCV_GOOD_QTY,
            o.RCV_LOSS_QTY,
            o.ORD_START_TIME,
            o.ORD_END_TIME
        FROM MWIPORDSTS o
        WHERE o.ORD_DATE = ? AND o.ORD_STATUS NOT IN ('DELETE'){extra}
        ORDER BY o.FACTORY_CODE, o.LINE_CODE, o.ORDER_NO
        """,
        params,
    )

    result = []
    for r in rows:
        fc   = r["FACTORY_CODE"]
        plan = int(r["ORD_QTY"]     or 0)
        act  = int(r["ORD_OUT_QTY"] or 0)
        result.append({
            "factory_code":     fc,
            "factory_name":     FACTORY_NAMES.get(fc, fc),
            "order_no":         r["ORDER_NO"],
            "line_code":        r["LINE_CODE"],
            "mat_code":         r["MAT_CODE"],
            "status":           r["ORD_STATUS"],
            "plan_qty":         plan,
            "actual_qty":       act,
            "good_qty":         int(r["RCV_GOOD_QTY"] or 0),
            "loss_qty":         int(r["RCV_LOSS_QTY"] or 0),
            "achievement_rate": calc_rate(act, plan),
            "start_time":       str(r["ORD_START_TIME"]) if r["ORD_START_TIME"] else None,
            "end_time":         str(r["ORD_END_TIME"])   if r["ORD_END_TIME"]   else None,
        })

    return {"date": d, "data": result}


# ── AI 채팅 ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    date: Optional[str] = None


@app.post("/api/chat")
async def chat(req: ChatRequest):
    client = anthropic.Anthropic()
    today  = fmt_date(req.date) if req.date else datetime.now().strftime("%Y%m%d")

    tools = [
        {
            "name": "execute_sql",
            "description": (
                "MES 데이터베이스에서 T-SQL 쿼리를 실행합니다. "
                "주요 테이블: MWIPORDSTS(작업지시), MWIPLOTSTS(Lot현황), "
                "MWIPLOTMVH(Lot이력), MWIPMATDEF(자재정보), MWIPLINDEF(라인정보)"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "sql":         {"type": "string", "description": "실행할 T-SQL 쿼리"},
                    "description": {"type": "string", "description": "쿼리 목적 요약"},
                },
                "required": ["sql"],
            },
        }
    ]

    system = f"""당신은 화장품 제조 공장의 생산 관리 분석 AI입니다.
MES(Manufacturing Execution System) 데이터베이스를 실시간으로 조회하여 실용적인 인사이트를 제공합니다.

기준 날짜: {today[:4]}-{today[4:6]}-{today[6:]}

[주요 테이블 스키마]
MWIPORDSTS (작업지시 현황):
  FACTORY_CODE  varchar  공장코드 (1100=퍼플, 1200=그린, 1300=제3공장)
  ORDER_NO      varchar  작업지시번호
  ORD_DATE      varchar  작업일자 (YYYYMMDD 문자열, 예: '20260331')
  LINE_CODE     varchar  라인코드
  MAT_CODE      varchar  자재코드
  ORD_STATUS    varchar  상태 (OPEN=진행중, CLOSE=완료, DELETE=삭제)
  ORD_QTY       int      계획수량
  ORD_OUT_QTY   int      생산수량(실적)
  RCV_GOOD_QTY  int      양품수량
  RCV_LOSS_QTY  int      불량수량
  ORD_START_TIME datetime 작업시작
  ORD_END_TIME  datetime 작업종료

MWIPLOTSTS (Lot 현재 상태):
  LOT_ID, FACTORY_CODE, MAT_CODE, LINE_CODE
  LOT_STATUS  varchar  (WAIT/ACTIVE 등)
  HOLD_FLAG   int      홀드여부 (1=홀드)
  RWK_FLAG    int      재작업여부 (1=재작업)
  OPER_IN_QTY int      투입수량

MWIPLOTMVH (Lot 이동 이력):
  LOT_ID, FACTORY_CODE, HIST_SEQ, TRAN_CODE, TRAN_TIME
  PROC_TIME   int  처리시간(초)
  QUEUE_TIME  int  대기시간(초)
  FLOW_CODE, OPER_CODE, TO_OPER_CODE

[규칙]
- 항상 ORD_STATUS NOT IN ('DELETE') 조건 포함
- 숫자는 천단위 구분기호 포함하여 표시 (예: 123,456개)
- 달성률 = 실적/계획 × 100 (%)
- 답변은 한국어로, 핵심만 간결하게
- 표나 목록으로 정리하면 더 좋음"""

    messages = [{"role": "user", "content": req.message}]

    for _ in range(6):
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system,
            tools=tools,
            messages=messages,
        )

        if resp.stop_reason == "end_turn":
            text = next((b.text for b in resp.content if hasattr(b, "text")), "응답 없음")
            return {"response": text}

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    try:
                        rows    = run_query(block.input["sql"])
                        content = json.dumps(rows[:200], ensure_ascii=False, default=str)
                    except Exception as e:
                        content = f"SQL 오류: {e}"
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     content,
                    })
            messages.append({"role": "user", "content": tool_results})

    return {"response": "분석을 완료했습니다."}


# ── 프론트엔드 서빙 ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    path = os.path.join(os.path.dirname(__file__), "index.html")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="index.html을 찾을 수 없습니다.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
