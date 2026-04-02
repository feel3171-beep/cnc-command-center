"""PM Chat — SSE streaming chat endpoint"""

import json
from typing import Optional
from app.agents.production_agent import ProductionAgent
from app.agents.hr_agent import HRAgent
from app.agents.finance_agent import FinanceAgent
from app.agents.cost_agent import CostAgent


AGENT_MAP = {
    "PRODUCTION": ProductionAgent,
    "HR": HRAgent,
    "FINANCE": FinanceAgent,
    "COST": CostAgent,
}


def get_agent(agent_type: Optional[str] = None):
    cls = AGENT_MAP.get(agent_type or "PRODUCTION", ProductionAgent)
    return cls()


def stream_chat(message: str, task_context: Optional[dict] = None):
    """Generator that yields SSE-formatted events."""
    agent_type = task_context.get("agent_type") if task_context else None
    agent = get_agent(agent_type)

    for event in agent.chat(message, context=task_context):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    yield "data: {\"type\": \"done\"}\n\n"
