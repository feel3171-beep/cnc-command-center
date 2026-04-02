"""
C&C Command Center — Agent Server
FastAPI 메인 엔트리포인트
"""

import json
import traceback
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.production_agent import ProductionAgent
from app.agents.hr_agent import HRAgent
from app.agents.finance_agent import FinanceAgent
from app.agents.cost_agent import CostAgent
from app.chat.pm_chat import stream_chat
from app.kpi.production import get_summary, get_trend

app = FastAPI(title="C&C Command Center Agent Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AGENTS = {
    "PRODUCTION": ProductionAgent,
    "HR": HRAgent,
    "FINANCE": FinanceAgent,
    "COST": CostAgent,
}


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ── KPI Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/kpi/production/summary")
async def kpi_production_summary(date: Optional[str] = None):
    try:
        return get_summary(date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kpi/production/trend")
async def kpi_production_trend(days: int = 14):
    try:
        return {"data": get_trend(days)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Agent Execution ───────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    mission: str
    task_id: Optional[str] = None


@app.post("/api/agents/{agent_type}/run")
async def run_agent(agent_type: str, req: AgentRunRequest):
    agent_type = agent_type.upper()
    if agent_type not in AGENTS:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_type}")

    agent = AGENTS[agent_type]()
    try:
        result = agent.run(req.mission)
        return {
            "agent_type": agent_type,
            "status": "SUCCESS",
            "result": result["result"],
            "turns": result["turns"],
            "tokens": result["tokens"],
            "tool_log": result["tool_log"],
        }
    except Exception as e:
        return {
            "agent_type": agent_type,
            "status": "FAILED",
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


# ── PM Chat (SSE Streaming) ──────────────────────────────────────────────────

class ChatStreamRequest(BaseModel):
    message: str
    task_id: Optional[str] = None
    task_context: Optional[dict] = None


@app.post("/api/chat/stream")
async def chat_stream(req: ChatStreamRequest):
    return StreamingResponse(
        stream_chat(req.message, req.task_context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Scheduler Status ─────────────────────────────────────────────────────────

@app.get("/api/scheduler/jobs")
async def scheduler_jobs():
    # Default jobs from scheduler config
    jobs = [
        {"id": "prod_briefing", "name": "생산 브리핑", "cron": "0 8,12,17 * * 1-5", "agent": "PRODUCTION"},
        {"id": "anomaly_alert", "name": "이상 알림", "cron": "0 7-21/2 * * 1-5", "agent": "PRODUCTION"},
        {"id": "delivery_watch", "name": "납기 감시", "cron": "30 7,13 * * 1-5", "agent": "PRODUCTION"},
        {"id": "exec_briefing", "name": "경영진 브리핑", "cron": "0 18 * * 1-5", "agent": "FINANCE"},
        {"id": "weekly_report", "name": "주간 리포트", "cron": "0 9 * * 1", "agent": "PRODUCTION"},
        {"id": "hr_daily_briefing", "name": "인사팀 일일 브리핑", "cron": "0 10 * * 1-5", "agent": "HR"},
        {"id": "recruitment_pipeline", "name": "채용 파이프라인", "cron": "30 10 * * 1", "agent": "HR"},
    ]
    return {"jobs": jobs}


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
