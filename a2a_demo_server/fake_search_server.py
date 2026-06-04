"""Tiny A2A server that pretends to be a defect-knowledge search agent.

Run::

    python -m a2a_demo_server.fake_search_server

It exposes:
  * ``GET  /.well-known/agent-card.json`` — discovery
  * ``POST /``                            — A2A JSON-RPC endpoint

The executor accepts any text input and replies with a canned defect
knowledge list. Purpose: give Phase 7's RemoteA2ASkill a real remote
process to talk to (HTTP round-trip, real protobuf, real card discovery)
so smoke tests aren't quietly mocked away.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import uvicorn
from starlette.applications import Starlette

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers import DefaultRequestHandlerV2
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.client.client_factory import PROTOCOL_VERSION_CURRENT, TransportProtocol
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Message,
    Part,
    Role,
)


_CANNED_KB = {
    "matches": [
        {
            "defect": "局部放电",
            "severity": "中等",
            "evidence": "频谱中 200-800kHz 段持续脉冲",
            "ref": "GB/T 7252-2016 5.3.2",
        },
        {
            "defect": "绕组过热",
            "severity": "高",
            "evidence": "C2H4 / C2H6 比值 > 1.5",
            "ref": "DL/T 722-2014 附录 B",
        },
        {
            "defect": "铁芯多点接地",
            "severity": "中等",
            "evidence": "接地电流 > 0.1A 且 H2 升高",
            "ref": "Q/GDW 11447-2015",
        },
    ],
    "source": "fake_defect_kb (demo)",
}


def _extract_query_text(message: Any) -> str:
    if message is None:
        return ""
    for part in getattr(message, "parts", []):
        text = getattr(part, "text", "") or ""
        if text:
            return text
    return ""


class FakeSearchExecutor(AgentExecutor):
    """Always returns the same canned defect KB regardless of query."""

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        query = _extract_query_text(context.message)
        body = {
            "echo_query": query,
            **_CANNED_KB,
        }
        reply_text = json.dumps(body, ensure_ascii=False, indent=2)

        reply = Message(
            message_id=uuid.uuid4().hex,
            context_id=context.context_id or "",
            role=Role.ROLE_AGENT,
            parts=[Part(text=reply_text)],
        )
        await event_queue.enqueue_event(reply)

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        return


def build_agent_card(public_url: str = "http://localhost:9001") -> AgentCard:
    return AgentCard(
        name="FakeDefectSearch",
        description=(
            "Demo A2A agent: returns canned transformer defect knowledge. "
            "Used only for HealthAgent Phase 7 end-to-end tests."
        ),
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="search",
                name="search",
                description="Look up canned defect KB entries by query text.",
                tags=["search", "knowledge", "demo"],
            )
        ],
        supported_interfaces=[
            AgentInterface(
                url=public_url,
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            )
        ],
    )


def make_app(card: AgentCard | None = None) -> Starlette:
    card = card or build_agent_card()
    handler = DefaultRequestHandlerV2(
        agent_executor=FakeSearchExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, rpc_url="/"),
    ]
    return Starlette(routes=routes)


def main(host: str = "127.0.0.1", port: int = 9001) -> None:
    uvicorn.run(make_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
