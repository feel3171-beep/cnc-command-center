"""Slack notification tool — ported from mes-slack-bot/slack_sender.py"""

import requests
from app.config import SLACK_BOT_TOKEN, SLACK_WEBHOOK_URL, SLACK_CHANNEL

TOOL_SEND_SLACK = {
    "name": "send_slack_notification",
    "description": "분석 결과를 Slack 채널에 발송합니다. info=일반, warning=주의, critical=긴급.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "발송할 메시지 (마크다운)"},
            "level": {"type": "string", "enum": ["info", "warning", "critical"]},
        },
        "required": ["message", "level"],
    },
}


def handle_send_slack(tool_input: dict) -> str:
    message = tool_input["message"]
    level = tool_input.get("level", "info")
    emoji = {"info": "📊", "warning": "⚠️", "critical": "🚨"}.get(level, "📊")
    text = f"{emoji} *Command Center Agent*\n{message}"

    if SLACK_BOT_TOKEN and SLACK_CHANNEL:
        try:
            resp = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={"channel": SLACK_CHANNEL, "text": text},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                return "Slack 발송 완료"
            return f"Slack 오류: {data.get('error', 'unknown')}"
        except Exception as e:
            return f"Slack 연결 실패: {e}"
    elif SLACK_WEBHOOK_URL:
        try:
            resp = requests.post(
                SLACK_WEBHOOK_URL,
                json={"text": text},
                timeout=10,
            )
            return "Slack 발송 완료" if resp.status_code == 200 else f"Slack 오류: {resp.status_code}"
        except Exception as e:
            return f"Slack 연결 실패: {e}"
    else:
        return f"Slack 미발송 (설정 없음). 내용: {message[:200]}"
