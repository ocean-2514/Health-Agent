"""Outer SupervisorAgent layer — three cleanly separated concepts.

Wraps the Phase 3-5 transformer-diagnosis platform and puts it behind a
LangChain tool-calling supervisor that takes natural-language requests,
decides which capability to use, and returns an aggregated answer.

The three concepts (see ``tool.py`` / ``skill.py`` / ``remote/``):

  * **Tool**  — the only thing the LLM calls directly (function-calling).
    Wraps a primitive, a deterministic Workflow (the inner diagnosis
    graph), or a remote Agent. Contract: ``ToolCard`` + ``run``.
  * **Skill** — loadable prompt / domain knowledge (``SKILL.md``), surfaced
    as a catalogue and pulled in via the built-in ``load_skill`` Tool.
  * **Agent** — autonomous / remote delegate, reached *through* a Tool
    (``RemoteA2ATool``), never called by the LLM directly.

Public entry:
  * ``Supervisor``  — the multi-turn chat orchestrator (see ``core.py``)
  * ``Tool`` / ``ToolCard`` / ``to_langchain_tool`` — the Tool contract
  * ``Skill`` / ``SkillRegistry`` / ``LoadSkillTool`` — the prompt-Skill layer
  * ``SessionStore`` — SQLite-backed chat history
"""
from Python.Src.Supervisor.core import Supervisor
from Python.Src.Supervisor.discovery import discover_tools_from_path
from Python.Src.Supervisor.loader import ToolLoadError, load_tools
from Python.Src.Supervisor.remote import (
    A2AClient,
    A2AClientError,
    RemoteA2ATool,
    load_remote_tools,
)
from Python.Src.Supervisor.session import SessionStore
from Python.Src.Supervisor.skill import (
    LoadSkillTool,
    Skill,
    SkillRegistry,
)
from Python.Src.Supervisor.tool import Tool, ToolCard, to_langchain_tool

__all__ = [
    "Supervisor", "SessionStore",
    # Tool layer (LLM-callable)
    "Tool", "ToolCard", "to_langchain_tool",
    "load_tools", "ToolLoadError", "discover_tools_from_path",
    # Skill layer (prompt / knowledge)
    "Skill", "SkillRegistry", "LoadSkillTool",
    # Agent layer (remote, via Tool)
    "RemoteA2ATool", "load_remote_tools",
    "A2AClient", "A2AClientError",
]
