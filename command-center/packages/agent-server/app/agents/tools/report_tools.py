"""Report save tool"""

from datetime import datetime
from pathlib import Path

REPORTS_DIR = Path(__file__).parent.parent.parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

TOOL_SAVE_REPORT = {
    "name": "save_report",
    "description": "분석 리포트를 파일로 저장합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "저장할 리포트 내용"},
            "date": {"type": "string", "description": "날짜 (YYYYMMDD)"},
            "filename": {"type": "string", "description": "파일명 (선택)"},
        },
        "required": ["content"],
    },
}


def handle_save_report(tool_input: dict) -> str:
    content = tool_input["content"]
    date_str = tool_input.get("date", datetime.now().strftime("%Y%m%d"))
    filename = tool_input.get("filename", f"report_{date_str}.md")
    path = REPORTS_DIR / filename
    path.write_text(content, encoding="utf-8")
    return f"리포트 저장 완료: {path.name}"
