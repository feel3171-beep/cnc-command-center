import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# MSSQL
DB_HOST = os.getenv("MSSQL_HOST", "192.161.0.15")
DB_PORT = int(os.getenv("MSSQL_PORT", "1433"))
DB_NAME = os.getenv("MSSQL_DATABASE", "MES")
DB_USER = os.getenv("MSSQL_USER", "mestmp")
DB_PASSWORD = os.getenv("MSSQL_PASSWORD", "")

# Slack
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")

# 공장 코드 → 이름
FACTORY_NAMES = {
    "1100": os.getenv("FACTORY_1100", "퍼플"),
    "1200": os.getenv("FACTORY_1200", "그린"),
    "1300": os.getenv("FACTORY_1300", "제3공장"),
}

# 알람 임계값
ALERT_DEFECT_RATE = 5.0        # 불량률 % 이상이면 알람
ALERT_ACHIEVEMENT_LOW = 50.0   # 달성률 % 미만이면 알람
ALERT_STOCK_MIN = 10000        # 재고 최소 수량
ALERT_EXPIRY_DAYS = 30         # 유통기한 임박 일수
