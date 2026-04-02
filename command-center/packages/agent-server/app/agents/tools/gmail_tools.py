"""Gmail tool — 이메일 읽기/검색 (Google Gmail API)"""

import json
import base64
import re
from pathlib import Path
from datetime import datetime


def _get_service():
    """Get authenticated Gmail API service."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = Path(__file__).parent.parent.parent / "token.json"
    creds_path = Path(__file__).parent.parent.parent / "credentials.json"

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
        ])

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        else:
            raise RuntimeError("Gmail 인증 필요: token.json 없음 또는 만료")

    return build("gmail", "v1", credentials=creds)


def _decode_body(payload) -> str:
    """Extract plain text body from Gmail message payload."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    break
        if not body:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                        body = re.sub(r"<[^>]+>", " ", html)
                        body = re.sub(r"\s+", " ", body).strip()
                        break
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return body[:2000]


def _parse_headers(headers: list) -> dict:
    return {h["name"]: h["value"] for h in headers}


# ── Tool 정의 ──────────────────────────────────────────────────────────────

TOOL_SEARCH_GMAIL = {
    "name": "search_gmail",
    "description": (
        "Gmail에서 이메일을 검색합니다. "
        "Gmail 검색 문법 사용 가능: is:unread, from:, subject:, after:, label: 등"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색 쿼리. 예: 'is:unread', 'subject:결재', 'from:cnccosmetic.com is:unread after:2026/4/1'",
            },
            "max_results": {
                "type": "integer",
                "description": "최대 결과 수 (기본 50, 최대 200)",
            },
        },
        "required": ["query"],
    },
}

TOOL_READ_GMAIL = {
    "name": "read_gmail_message",
    "description": "특정 이메일의 전체 내용을 읽습니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "search_gmail로 얻은 메시지 ID",
            },
        },
        "required": ["message_id"],
    },
}


# ── 핸들러 ─────────────────────────────────────────────────────────────────

def handle_search_gmail(tool_input: dict) -> str:
    query = tool_input["query"]
    max_results = min(tool_input.get("max_results", 50), 200)

    try:
        service = _get_service()
        result = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = result.get("messages", [])
        if not messages:
            return json.dumps({"messages": [], "count": 0}, ensure_ascii=False)

        items = []
        for msg in messages:
            detail = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"]
            ).execute()

            headers = _parse_headers(detail.get("payload", {}).get("headers", []))
            snippet = detail.get("snippet", "")
            label_ids = detail.get("labelIds", [])

            items.append({
                "id": msg["id"],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": snippet[:200],
                "unread": "UNREAD" in label_ids,
                "important": "IMPORTANT" in label_ids,
                "labels": label_ids,
            })

        return json.dumps({"messages": items, "count": len(items)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_read_gmail(tool_input: dict) -> str:
    message_id = tool_input["message_id"]

    try:
        service = _get_service()
        detail = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = _parse_headers(detail.get("payload", {}).get("headers", []))
        body = _decode_body(detail.get("payload", {}))

        return json.dumps({
            "id": message_id,
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
