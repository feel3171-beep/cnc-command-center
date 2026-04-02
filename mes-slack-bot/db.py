import pymssql
import config


def get_connection():
    return pymssql.connect(
        server=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8",
    )


def query(sql, params=None):
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        return rows
    finally:
        conn.close()


def query_one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None
