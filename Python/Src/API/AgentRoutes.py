"""HTTP API for the refactored multi-agent platform (Supervisor).

Exposes the outer ``Supervisor`` (LLM tool-calling orchestrator over the
Tool / Skill / Agent layers) over HTTP, parallel to — and independent of —
the legacy ``/api/assess/*`` endpoints backed by ``AssessmentService``.
The frontend's new "智能体平台" page talks to these.

Endpoints (all under ``/api/agent``):
  * ``POST /chat``                 — one chat turn (may trigger tool calls)
  * ``POST /session``              — create a new chat session
  * ``GET  /sessions``             — list recent sessions
  * ``GET  /session/{id}/history`` — replay one session's messages
  * ``GET  /catalogue``            — available Tools + Skills (for the UI panel)

The Supervisor is built **lazily** on first use: constructing it loads the
inner platform registry / diagnosis graph and wires up Ollama, which we
don't want to do at server import time (keeps ``/api/assess/*`` working even
if the agent stack or Ollama is unavailable).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.session import default_store

router = APIRouter(prefix="/api/agent", tags=["agent"])

# --------------------------------------------------------------------------
# Lazy Supervisor singleton
# --------------------------------------------------------------------------

_supervisor = None  # type: ignore[var-annotated]


def _get_supervisor():
    """Build (once) and return the Supervisor. Raises HTTP 503 with a clear
    message if construction fails (e.g. Ollama down, config missing)."""
    global _supervisor
    if _supervisor is None:
        try:
            from Python.Src.Supervisor.core import Supervisor
            from Python.Src.Supervisor.loader import load_tools

            tools = load_tools()
            _supervisor = Supervisor(tools=tools)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=503,
                detail=f"智能体平台初始化失败: {e}",
            )
    return _supervisor


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class ChatReq(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResp(BaseModel):
    session_id: str
    answer: str
    tool_calls: List[Dict[str, Any]] = []


class RegisterRemoteReq(BaseModel):
    url: str
    name: Optional[str] = None


class LoadDirReq(BaseModel):
    path: str
    recursive: bool = True


def _catalogue_payload(sup) -> Dict[str, Any]:
    return {"tools": sup.tool_catalogue, "skills": sup.skill_catalogue}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResp)
def chat(req: ChatReq):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")
    sup = _get_supervisor()
    session_id = req.session_id or sup.new_session()
    try:
        result = sup.chat_verbose(session_id, req.message.strip())
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResp(
        session_id=session_id,
        answer=result["answer"],
        tool_calls=result.get("tool_calls", []),
    )


@router.post("/chat/stream")
async def chat_stream(req: ChatReq):
    """Streaming chat (SSE). Emits events: session, text, tool_call,
    tool_result, final, error — so the UI can show the workflow live."""
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")
    # Build the supervisor in a worker thread: first build may probe remote
    # A2A cards (asyncio.run), which must not run inside this event loop.
    sup = await asyncio.to_thread(_get_supervisor)
    session_id = req.session_id or sup.new_session()

    def _sse(d: Dict[str, Any]) -> str:
        return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"

    async def gen():
        yield _sse({"type": "session", "session_id": session_id})
        try:
            async for ev in sup.chat_stream(session_id, req.message.strip()):
                yield _sse(ev)
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})
        yield _sse({"type": "end"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/session")
def new_session():
    sup = _get_supervisor()
    return {"session_id": sup.new_session()}


@router.get("/sessions")
async def list_sessions(limit: int = 20):
    return {"sessions": default_store.list_sessions(limit=limit)}


@router.get("/session/{session_id}/history")
async def session_history(session_id: str):
    if not default_store.session_exists(session_id):
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return {
        "session_id": session_id,
        "messages": default_store.get_history(session_id),
    }


@router.get("/catalogue")
def catalogue():
    """Tools (callable) + Skills (loadable knowledge) the agent currently has."""
    sup = _get_supervisor()
    return _catalogue_payload(sup)


@router.get("/memory")
def memory():
    """Cross-session memories saved by the agent (newest first)."""
    from Python.Src.Supervisor.memory import list_memories
    return {
        "memories": [
            {"name": m.name, "description": m.description, "type": m.type, "filename": m.filename}
            for m in list_memories()
        ]
    }


# --------------------------------------------------------------------------
# Hot-loading — mutate the live registry without restarting the server.
# Every mutator returns the fresh catalogue so the UI can re-render in one round-trip.
# --------------------------------------------------------------------------

@router.post("/reload_skills")
def reload_skills():
    """Re-scan ``skills/*/SKILL.md`` from disk (picks up new / edited skills)."""
    sup = _get_supervisor()
    sup.reload_skills()
    return _catalogue_payload(sup)


@router.post("/tools/register_remote")
def register_remote(req: RegisterRemoteReq):
    """Hot-register a remote A2A agent by URL (wrapped as a Tool)."""
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="url 不能为空")
    sup = _get_supervisor()
    try:
        name = sup.register_remote_tool(req.url.strip(), name=req.name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"注册远程工具失败: {e}")
    return {"registered": name, **_catalogue_payload(sup)}


@router.post("/tools/reload_remote")
def reload_remote():
    """Re-read ``Config/remote_tools.yaml`` and register any new remote tools."""
    sup = _get_supervisor()
    added = sup.register_remote_tools_from_yaml()
    return {"added": added, **_catalogue_payload(sup)}


@router.post("/tools/load_dir")
def load_dir(req: LoadDirReq):
    """Scan a directory for Python modules exporting ``TOOL`` / ``TOOLS`` and
    register each (skips already-registered names). ``path`` may be absolute
    or relative to the repo root."""
    raw = (req.path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path 不能为空")
    target = Path(raw)
    if not target.is_absolute():
        target = Path(project_root) / target
    sup = _get_supervisor()
    try:
        added = sup.register_tools_from_path(str(target), recursive=req.recursive)
    except (FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"扫描目录失败: {e}")
    return {"added": added, **_catalogue_payload(sup)}


@router.post("/tools/{name}/enable")
def enable_tool(name: str):
    sup = _get_supervisor()
    changed = sup.enable_tool(name)
    return {"changed": changed, **_catalogue_payload(sup)}


@router.post("/tools/{name}/disable")
def disable_tool(name: str):
    sup = _get_supervisor()
    changed = sup.disable_tool(name)
    return {"changed": changed, **_catalogue_payload(sup)}


@router.delete("/tools/{name}")
def remove_tool(name: str):
    sup = _get_supervisor()
    if sup.is_builtin(name):
        raise HTTPException(status_code=400, detail=f"内置工具不可移除: {name}")
    removed = sup.unregister_tool(name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"工具不存在: {name}")
    return _catalogue_payload(sup)


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    if not default_store.session_exists(session_id):
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    default_store.delete_session(session_id)
    return {"deleted": session_id}
