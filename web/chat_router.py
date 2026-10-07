"""Chat and Agent Router with Integrated Load Balancing.

Features:
- Dynamic model selection across GEMINI_MODELS pool with circuit breaking on 429/quota limits.
- Agent device load balancer for WebSocket connected agents.
- Real-time agent status inspection endpoint (/api/chat/agents/status).
"""

import os
import json
import base64
import secrets
import logging
import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Query,
    Request,
)
from starlette.responses import StreamingResponse

from engine.agent_balancer import (
    AgentModelLoadBalancer,
    WebSocketAgentBalancer,
    BalancingStrategy,
    DEFAULT_GEMINI_MODELS,
)

logger = logging.getLogger("OmniBuy.Chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Configure Model Fleet Balancer
agent_balancer = AgentModelLoadBalancer(
    models=DEFAULT_GEMINI_MODELS,
    strategy=BalancingStrategy.LEAST_BUSY,
    cooldown_seconds=60.0,
)

# Configure WebSocket Agent Balancer
connection_manager = WebSocketAgentBalancer()


@router.get("/agents/status")
def get_agent_pool_status():
    """Inspect real-time health, active requests, and cooldown state of the agent pool."""
    return {
        "strategy": agent_balancer.strategy.value,
        "models": agent_balancer.get_status(),
        "healthy_count": len(agent_balancer.get_healthy_models()),
        "total_count": len(agent_balancer.models),
    }


@router.post("/procure")
async def chat_procure_stream(req: Request):
    """
    Streaming AI Procurement endpoint:
    - Analyzes complex multi-item prompts.
    - Searches boss-recommended suppliers + broad internet.
    - Verifies technical specs (PoE, Gigabit, etc.).
    - Streams real-time thoughts and structured product results.
    """
    body = await req.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt-ul nu poate fi gol.")

    country = body.get("country")
    suppliers = body.get("suppliers")
    include_web_search = body.get("include_web_search", True)

    from engine.procurement_agent import run_procurement_agent

    async def sse_event_stream():
        try:
            async for update in run_procurement_agent(
                user_prompt=prompt,
                country=country,
                supplier_ids=suppliers,
                include_web_search=include_web_search,
            ):
                payload = json.dumps(update, ensure_ascii=False)
                yield f"data: {payload}\n\n".encode("utf-8")
        except Exception as e:
            logger.error("Procurement agent failed: %s", e)
            err_data = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield f"data: {err_data}\n\n".encode("utf-8")

    return StreamingResponse(sse_event_stream(), media_type="text/event-stream")


@router.get("/pick-agent/{tenant_slug}")
def pick_agent_for_tenant(tenant_slug: str, strategy: str = "round_robin"):
    """Pick an available connected WebSocket agent for a tenant using load balancing."""
    chosen_uuid = connection_manager.pick_agent(tenant_slug, strategy=strategy)
    if not chosen_uuid:
        raise HTTPException(status_code=404, detail=f"No online agents found for tenant: {tenant_slug}")
    return {"tenant_slug": tenant_slug, "assigned_device_uuid": chosen_uuid}


@router.websocket("/ws/agent/{tenant_key}/{device_uuid}")
async def agent_chat_ws(websocket: WebSocket, tenant_key: str, device_uuid: str):
    """WebSocket endpoint for worker agents to connect."""
    await websocket.accept()
    tenant_slug = tenant_key  # Or resolve via DB
    connection_manager.register_agent(websocket, tenant_slug, device_uuid)
    logger.info("Agent connected: tenant=%s device=%s", tenant_slug, device_uuid)

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug("Received from agent [%s]: %s", device_uuid, data)
    except WebSocketDisconnect:
        connection_manager.unregister_agent(tenant_slug, device_uuid)
        logger.info("Agent disconnected: tenant=%s device=%s", tenant_slug, device_uuid)
