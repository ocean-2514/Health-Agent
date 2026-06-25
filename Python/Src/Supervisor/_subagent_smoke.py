"""Offline smoke test for the sub-agent system (P4).

No network — a scripted fake OpenAI client drives both the parent and the
sub-agents. Verifies fork-return, context isolation, concurrency, recursion
exclusion (no nesting), role tool-restriction, and error isolation.

Run::

    python -m Python.Src.Supervisor._subagent_smoke
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from pydantic import BaseModel, Field

from Python.Src.Supervisor.agent_loop import AgentLoop
from Python.Src.Supervisor.subagent import (
    SPAWN_TOOL_NAME,
    SpawnAgentTool,
    sub_agent_tools,
)
from Python.Src.Supervisor.tool import ToolCard


# ── stub tools ──────────────────────────────────────────────────────────
class _In(BaseModel):
    pass


class _Out(BaseModel):
    ok: bool = True


def _stub(name: str):
    class _T:
        card = ToolCard(name=name, description=f"stub {name}", input_model=_In, output_model=_Out)

        def run(self, **kwargs):
            return _Out()
    return _T()


# fake RemoteA2ATool (class name is what sub_agent_tools checks)
class RemoteA2ATool:
    def __init__(self, name):
        self.card = ToolCard(name=name, description="remote", input_model=_In, output_model=_Out)

    def run(self, **kwargs):
        return _Out()


# ── scripted client: returns a plain-text final answer for every call ───
class _ScriptedClient:
    def __init__(self, reply="sub done"):
        self._reply = reply
        comp = type("C", (), {})()
        async def _create(**kwargs):
            msg = type("M", (), {"content": self._reply, "tool_calls": None})()
            usage = type("U", (), {"prompt_tokens": 7, "completion_tokens": 3})()
            return type("R", (), {"choices": [type("Ch", (), {"message": msg})()], "usage": usage})()
        comp.create = _create
        self.chat = type("Chat", (), {"completions": comp})()


def main() -> int:
    print("=== P4 sub-agent smoke test ===\n")

    loop = AgentLoop(_ScriptedClient("sub done"), "fake-model")

    # parent pool: a read-only tool, a remote tool, a heavy/write tool, built-ins
    pool = {
        "history_lookup": _stub("history_lookup"),
        "load_skill": _stub("load_skill"),
        "defect_kb_search": RemoteA2ATool("defect_kb_search"),
        "transformer_diagnosis": _stub("transformer_diagnosis"),
        "save_memory": _stub("save_memory"),
        SPAWN_TOOL_NAME: _stub(SPAWN_TOOL_NAME),  # must be excluded from sub pool
    }

    print("[1] role tool-restriction")
    explore = {t.card.name for t in sub_agent_tools("explore", {k: v for k, v in pool.items() if k != SPAWN_TOOL_NAME})}
    general = {t.card.name for t in sub_agent_tools("general", {k: v for k, v in pool.items() if k != SPAWN_TOOL_NAME})}
    print(f"  explore tools: {sorted(explore)}")
    print(f"  general tools: {sorted(general)}")
    assert explore == {"history_lookup", "load_skill", "defect_kb_search"}, explore
    assert "transformer_diagnosis" in general and "save_memory" in general
    # neither role gets spawn_agent (no nesting)
    assert SPAWN_TOOL_NAME not in explore and SPAWN_TOOL_NAME not in general
    print("  ok: explore=read-only, general=full, neither can spawn")

    print("\n[2] SpawnAgentTool excludes spawn from its pool automatically")
    spawn = SpawnAgentTool(loop, pool)  # pass full pool incl. spawn_agent
    assert SPAWN_TOOL_NAME not in spawn._pool  # noqa: SLF001
    print("  ok")

    print("\n[3] single fork-return")
    out = spawn.run(tasks=[{"type": "explore", "description": "查历史", "prompt": "tr01 历史"}])
    assert len(out.results) == 1 and out.results[0].success
    assert out.results[0].text == "sub done" and out.results[0].type == "explore"
    print(f"  ok: {out.results[0].description} → {out.results[0].text!r}, tokens={out.results[0].tokens}")

    print("\n[4] concurrent multi-task fork-return (multi-device pattern)")
    tasks = [
        {"type": "general", "description": f"诊断 tr0{i}", "prompt": f"诊断 tr0{i}"}
        for i in range(1, 4)
    ]
    out = spawn.run(tasks=tasks)
    assert len(out.results) == 3 and all(r.success for r in out.results)
    print(f"  ok: {len(out.results)} sub-agents returned: {[r.description for r in out.results]}")

    print("\n[5] error isolation: one bad sub-agent doesn't crash the batch")
    class _BoomClient(_ScriptedClient):
        def __init__(self):
            super().__init__()
            comp = type("C", (), {})()
            async def _create(**kwargs):
                raise RuntimeError("subagent kaboom")
            comp.create = _create
            self.chat = type("Chat", (), {"completions": comp})()
    boom_loop = AgentLoop(_BoomClient(), "fake-model")
    boom_spawn = SpawnAgentTool(boom_loop, pool)
    out = boom_spawn.run(tasks=[{"type": "general", "description": "会崩", "prompt": "x"}])
    assert len(out.results) == 1 and out.results[0].success is False
    assert "kaboom" in (out.results[0].error or "")
    print(f"  ok: failure returned as data: {out.results[0].error!r}")

    print("\n[6] task cap enforced")
    many = [{"type": "general", "description": str(i), "prompt": "x"} for i in range(20)]
    out = spawn.run(tasks=many)
    assert len(out.results) <= 8, len(out.results)
    print(f"  ok: 20 tasks capped to {len(out.results)}")

    print("\n[7] Supervisor wires spawn_agent into active tools (no nesting in pool)")
    from unittest.mock import patch, MagicMock
    from Python.Src.Supervisor.skill import SkillRegistry
    with patch("Python.Src.Supervisor.core.openai.AsyncOpenAI", lambda **kw: MagicMock()):
        from Python.Src.Supervisor.core import Supervisor
        sup = Supervisor(tools=[_stub("transformer_diagnosis")], skill_registry=SkillRegistry())
        names = [t.card.name for t in sup._active_tools()]  # noqa: SLF001
        assert SPAWN_TOOL_NAME in names, names
        # find the spawn tool, confirm its pool excludes itself
        spawn_tool = next(t for t in sup._active_tools() if t.card.name == SPAWN_TOOL_NAME)  # noqa: SLF001
        assert SPAWN_TOOL_NAME not in spawn_tool._pool  # noqa: SLF001
        print(f"  ok, active tools: {names}")

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
