"""MSSQL connection helper — ported from production-agent/agent.py"""

import decimal
import json
from datetime import datetime
from typing import Optional

import pymssql
from app.config import MSSQL_HOST, MSSQL_PORT, MSSQL_DATABASE, MSSQL_USER, MSSQL_PASSWORD


def get_connection():
    return pymssql.connect(
        server=MSSQL_HOST,
        port=MSSQL_PORT,
        user=MSSQL_USER,
        password=MSSQL_PASSWORD,
        database=MSSQL_DATABASE,
        charset="utf8",
    )


def run_query(sql: str, params: Optional[tuple] = None, max_rows: int = 500) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute(sql, params or ())
        rows = cursor.fetchmany(max_rows)
        result = []
        for row in rows:
            clean = {}
            for k, v in row.items():
                if isinstance(v, decimal.Decimal):
                    v = float(v)
                elif isinstance(v, datetime):
                    v = v.isoformat()
                elif isinstance(v, bytes):
                    v = v.decode("utf-8", errors="replace")
                clean[k] = v
            result.append(clean)
        return result
    finally:
        conn.close()


def run_query_json(sql: str, params: Optional[tuple] = None, max_rows: int = 300) -> str:
    rows = run_query(sql, params, max_rows)
    return json.dumps(rows, ensure_ascii=False, default=str)
