"""Google Sheets tool — 인사/생산 데이터 읽기"""

import json
import gspread
from pathlib import Path

# Spreadsheet ID
SHEET_ID = "1U5x5obWAd2FRFJX5ks4mJivl0bFXzBEbhqoR1rAtIeI"

TOOL_READ_GSHEET = {
    "name": "read_google_sheet",
    "description": "Google Sheets에서 데이터를 읽습니다. 인사_인사팀, 인사_데이터, 인사_MES 등의 시트를 조회할 수 있습니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sheet_name": {
                "type": "string",
                "description": "시트 이름 (예: '인사_인사팀', '인사_데이터', '인사_MES', '생산_실적')",
            },
            "range": {
                "type": "string",
                "description": "A1 표기법 범위 (예: 'A1:Z50'). 생략 시 전체 시트.",
            },
        },
        "required": ["sheet_name"],
    },
}


def _get_client():
    """Get authenticated gspread client."""
    # Try service account first, then OAuth
    sa_path = Path(__file__).parent.parent.parent / "service_account.json"
    if sa_path.exists():
        return gspread.service_account(filename=str(sa_path))

    creds_path = Path(__file__).parent.parent.parent / "credentials.json"
    token_path = Path(__file__).parent.parent.parent / "token.json"
    if creds_path.exists():
        return gspread.oauth(
            credentials_filename=str(creds_path),
            authorized_user_filename=str(token_path),
        )

    raise RuntimeError("Google Sheets 인증 파일 없음 (service_account.json 또는 credentials.json)")


def handle_read_gsheet(tool_input: dict) -> str:
    """Read data from Google Sheets."""
    sheet_name = tool_input["sheet_name"]
    range_str = tool_input.get("range", "")

    try:
        gc = _get_client()
        spreadsheet = gc.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet(sheet_name)

        if range_str:
            data = worksheet.get(range_str)
        else:
            data = worksheet.get_all_values()

        # Limit rows to prevent token overflow
        if len(data) > 100:
            data = data[:100]
            return json.dumps({
                "data": data,
                "truncated": True,
                "message": f"100행까지만 반환 (전체 {len(data)}행)",
            }, ensure_ascii=False)

        return json.dumps({"data": data, "rows": len(data)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
