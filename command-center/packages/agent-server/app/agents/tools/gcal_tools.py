"""Google Calendar tool — 일정 조회"""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone


def _get_service():
    """Get authenticated Google Calendar API service."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = Path(__file__).parent.parent.parent / "token.json"

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
            raise RuntimeError("Calendar 인증 필요: token.json 없음 또는 만료")

    return build("calendar", "v3", credentials=creds)


TOOL_LIST_CALENDAR = {
    "name": "list_calendar_events",
    "description": "Google Calendar에서 일정을 조회합니다. 오늘 또는 이번 주 일정을 확인할 수 있습니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "오늘부터 며칠 뒤까지 조회할지 (기본 7, 오늘만 보려면 1)",
            },
            "calendar_id": {
                "type": "string",
                "description": "캘린더 ID (기본 'primary')",
            },
        },
        "required": [],
    },
}


def handle_list_calendar(tool_input: dict) -> str:
    days_ahead = tool_input.get("days_ahead", 7)
    calendar_id = tool_input.get("calendar_id", "primary")

    try:
        service = _get_service()

        now = datetime.now(timezone.utc)
        time_min = now.replace(hour=0, minute=0, second=0).isoformat()
        time_max = (now + timedelta(days=days_ahead)).replace(
            hour=23, minute=59, second=59
        ).isoformat()

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=50,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return json.dumps({"events": [], "count": 0}, ensure_ascii=False)

        items = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date", ""))
            end = event["end"].get("dateTime", event["end"].get("date", ""))
            attendees = [a.get("email", "") for a in event.get("attendees", [])]

            items.append({
                "id": event["id"],
                "title": event.get("summary", "(제목 없음)"),
                "start": start,
                "end": end,
                "location": event.get("location", ""),
                "description": (event.get("description", "") or "")[:300],
                "attendees": attendees,
                "status": event.get("status", ""),
                "organizer": event.get("organizer", {}).get("email", ""),
            })

        return json.dumps({"events": items, "count": len(items)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
