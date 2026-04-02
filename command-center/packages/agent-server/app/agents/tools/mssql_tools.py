"""MSSQL tool definitions and handlers for Claude agents"""

from app.db.mssql import run_query_json

TOOL_QUERY_PRODUCTION_DB = {
    "name": "query_production_db",
    "description": (
        "MES 데이터베이스에서 생산 데이터를 조회합니다. "
        "MWIPORDSTS(작업지시: ORD_DATE='YYYYMMDD', FACTORY_CODE, LINE_CODE, "
        "ORD_QTY=계획, ORD_OUT_QTY=실적, RCV_GOOD_QTY=양품, RCV_LOSS_QTY=불량, "
        "ORD_STATUS NOT IN('DELETE')), "
        "MWIPLOTSTS(Lot현황: HOLD_FLAG, RWK_FLAG), "
        "MWIPLOTMVH(이력: PROC_TIME초, QUEUE_TIME초), "
        "MWIPMATDEF(자재정보: MAT_CODE, MAT_DESC), "
        "MWIPLINDEF(라인정보), "
        "IWIPORDSTS(수주현황: SO_NO, CUSTOMER_CODE, MAT_CODE, SO_QTY, DELIVERY_DATE), "
        "MWIPBOMCMP(BOM: BOM_SET_CODE, CHILD_MAT_CODE, COMPONENT_QTY) 사용 가능."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "실행할 T-SQL SELECT 쿼리"},
            "description": {"type": "string", "description": "이 쿼리의 목적"},
        },
        "required": ["sql"],
    },
}

TOOL_QUERY_SALES_DB = {
    "name": "query_sales_db",
    "description": (
        "매출/수주 데이터를 조회합니다. "
        "IWIPORDSTS(수주: SO_NO, CUSTOMER_CODE, MAT_CODE, SO_QTY, DELIVERY_DATE, SO_STATUS), "
        "IINVSHPMST(출하: SHIP_NO, SHIP_STATUS, SHIP_DATE), "
        "CINVBASDAT(재고: MAT_CODE, QTY, STATUS, USE_TERM) 사용 가능."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "실행할 T-SQL SELECT 쿼리"},
            "description": {"type": "string", "description": "쿼리 목적"},
        },
        "required": ["sql"],
    },
}


def handle_query_db(tool_input: dict) -> str:
    sql = tool_input["sql"]
    # Security: only allow SELECT
    if not sql.strip().upper().startswith("SELECT"):
        return "오류: SELECT 쿼리만 허용됩니다."
    try:
        return run_query_json(sql)
    except Exception as e:
        return f"SQL 오류: {e}"
