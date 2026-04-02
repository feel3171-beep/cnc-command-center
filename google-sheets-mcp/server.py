import os
import json
import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
TOKEN_PATH = Path(__file__).parent / "token.json"

mcp = FastMCP("google-sheets")


def get_credentials():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
            client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
            if not client_id or not client_secret:
                raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set")
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def get_sheets_service():
    return build("sheets", "v4", credentials=get_credentials())


@mcp.tool()
def list_sheets(spreadsheet_id: str) -> str:
    """List all sheet names in a Google Spreadsheet.

    Args:
        spreadsheet_id: The ID from the spreadsheet URL
    """
    service = get_sheets_service()
    result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = result.get("sheets", [])
    names = [s["properties"]["title"] for s in sheets]
    return json.dumps({"spreadsheet_title": result.get("properties", {}).get("title", ""), "sheets": names}, ensure_ascii=False)


@mcp.tool()
def read_spreadsheet(spreadsheet_id: str, range: str = "") -> str:
    """Read data from a Google Spreadsheet.

    Args:
        spreadsheet_id: The ID from the spreadsheet URL
        range: A1 notation range (e.g. 'Sheet1!A1:D10'). If empty, reads the first sheet entirely.
    """
    service = get_sheets_service()
    if not range:
        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        first_sheet = meta["sheets"][0]["properties"]["title"]
        range = first_sheet
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=range
    ).execute()
    values = result.get("values", [])
    return json.dumps({"range": result.get("range", range), "total_rows": len(values), "data": values}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
