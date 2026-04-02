import os
from dotenv import dotenv_values
from pathlib import Path

# Load .env values directly (bypass empty env vars from parent process)
_env = dotenv_values(Path(__file__).parent.parent / ".env")

def _get(key: str, default: str = "") -> str:
    """Get from .env file first, then environment, then default."""
    return _env.get(key) or os.getenv(key, default)

# MSSQL
MSSQL_HOST = _get("MSSQL_HOST", "192.161.0.16")
MSSQL_PORT = int(_get("MSSQL_PORT", "1433"))
MSSQL_DATABASE = _get("MSSQL_DATABASE", "MES")
MSSQL_USER = _get("MSSQL_USER", "mestmp")
MSSQL_PASSWORD = _get("MSSQL_PASSWORD", "cncmgr123!")

# PostgreSQL
DATABASE_URL = _get("DATABASE_URL", "postgresql://cc_admin:cc2026!@localhost:5432/commandcenter")

# Anthropic
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
OPUS_MODEL = "claude-opus-4-6"
SONNET_MODEL = "claude-sonnet-4-6"

# Slack
SLACK_BOT_TOKEN = _get("SLACK_BOT_TOKEN")
SLACK_WEBHOOK_URL = _get("SLACK_WEBHOOK_URL")
SLACK_CHANNEL = _get("SLACK_CHANNEL", "C0APA5DBJ2Y")

# Factory names
FACTORY_NAMES = {"1100": "퍼플", "1200": "그린", "1300": "제3공장"}
