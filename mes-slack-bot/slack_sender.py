import json
import requests
import config


def send_message(text, blocks=None, channel=None):
    ch = channel or config.SLACK_CHANNEL
    token = config.SLACK_BOT_TOKEN

    if token and ch:
        # Bot Token 방식 (chat.postMessage API)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = {"channel": ch, "text": text}
        if blocks:
            payload["blocks"] = blocks
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp
    else:
        # Webhook 방식 (폴백)
        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        resp = requests.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return resp


def fmt_num(n):
    if n is None:
        return "-"
    if isinstance(n, float):
        if n == int(n):
            n = int(n)
    return f"{n:,}"


def fmt_pct(n):
    if n is None:
        return "-"
    return f"{n:.1f}%"


def status_emoji(pct):
    if pct is None:
        return "\u2b1c"
    if pct >= 80:
        return "\U0001f7e2"
    if pct >= 50:
        return "\U0001f7e1"
    return "\U0001f534"


def change_arrow(current, previous):
    if previous is None or previous == 0 or current is None:
        return ""
    diff_pct = (current - previous) / previous * 100
    if diff_pct > 0:
        return f"\u2197\ufe0f +{diff_pct:.1f}%"
    elif diff_pct < 0:
        return f"\u2198\ufe0f {diff_pct:.1f}%"
    return "\u2194\ufe0f 0%"


def divider():
    return {"type": "divider"}


def header_block(text):
    return {
        "type": "header",
        "text": {"type": "plain_text", "text": text, "emoji": True},
    }


def section_block(text):
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    }


def context_block(text):
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": text}],
    }
