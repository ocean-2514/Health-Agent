"""Tavily Search Agent as A2A Server - 兼容客户端版本"""

from __future__ import annotations

import json
import uuid
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.requests import Request
from tavily import TavilyClient

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
    SendMessageResponse,
    Task,
    TaskState,
    Artifact,
)

# Tavily API Key
TAVILY_API_KEY = "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"


def _extract_query_text(message: Any) -> str:
    if message is None:
        return ""
    for part in getattr(message, "parts", []):
        text = getattr(part, "text", "") or ""
        if text:
            return text
    return ""


class TavilySearchExecutor(AgentExecutor):
    """Tavily 搜索 Agent"""

    def __init__(self):
        self.client = TavilyClient(api_key=TAVILY_API_KEY)

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        query = _extract_query_text(context.message)
        
        print(f"📝 Received query: {query}")
        
        # 执行搜索
        try:
            response = self.client.search(query=query, search_depth="basic")
            body = {
                "query": query,
                "success": True,
                "results": response.get("results", []),
                "answer": response.get("answer", ""),
            }
        except Exception as e:
            print(f"❌ Search failed: {e}")
            body = {
                "query": query,
                "success": False,
                "error": str(e),
            }
        
        reply_text = json.dumps(body, ensure_ascii=False, indent=2)
        
        # 使用 Role.ROLE_AGENT 以兼容客户端
        reply = Message(
            message_id=uuid.uuid4().hex,
            context_id=context.context_id or "",
            role=Role.ROLE_AGENT,  # 注意：使用 ROLE_AGENT 而不是 AGENT
            parts=[Part(text=reply_text)],
        )
        await event_queue.enqueue_event(reply)

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        return


# 简单 HTTP API 接口
async def search_api(request: Request):
    """简单的搜索 API，支持 GET 和 POST"""
    
    # 获取查询参数
    if request.method == "GET":
        query = request.query_params.get("q") or request.query_params.get("query")
    else:
        try:
            body = await request.json()
            query = body.get("q") or body.get("query")
        except:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    
    if not query:
        return JSONResponse(
            {"error": "Missing query parameter. Use ?q=your_query"}, 
            status_code=400
        )
    
    # 执行搜索
    client = TavilyClient(api_key=TAVILY_API_KEY)
    try:
        response = client.search(query=query, search_depth="basic")
        return JSONResponse({
            "success": True,
            "query": query,
            "results": response.get("results", []),
            "answer": response.get("answer", ""),
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


async def health_check(request: Request):
    """健康检查"""
    return JSONResponse({"status": "healthy", "service": "TavilySearchAgent"})


def build_agent_card(public_url: str = "http://localhost:9002") -> AgentCard:
    return AgentCard(
        name="TavilySearchAgent",
        description="Real internet search agent powered by Tavily API",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="web_search",
                name="web_search",
                description="Search the internet for real-time information",
                tags=["search", "tavily", "web"],
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
        agent_executor=TavilySearchExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    
    # 添加简单接口 + A2A 接口
    routes = [
        Route("/health", health_check, methods=["GET"]),
        Route("/api/search", search_api, methods=["GET", "POST"]),
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, rpc_url="/"),
    ]
    return Starlette(routes=routes)


def main(host: str = "127.0.0.1", port: int = 9002) -> None:
    print("=" * 60)
    print("🚀 Tavily Search Agent 启动")
    print("=" * 60)
    print(f"📡 服务地址: http://{host}:{port}")
    print("\n📖 可用接口:")
    print(f"  1. 简单搜索 API (推荐):")
    print(f"     GET  http://localhost:{port}/api/search?q=人工智能")
    print(f"     POST http://localhost:{port}/api/search -d '{{\"query\": \"test\"}}'")
    print(f"  2. 健康检查:")
    print(f"     GET  http://localhost:{port}/health")
    print(f"  3. Agent Card:")
    print(f"     GET  http://localhost:{port}/.well-known/agent-card.json")
    print("=" * 60)
    
    uvicorn.run(make_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()