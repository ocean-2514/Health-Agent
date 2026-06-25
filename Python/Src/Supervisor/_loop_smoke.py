"""Offline smoke test for the self-controlled agent loop (P1).

No network / no real LLM — a scripted fake OpenAI client drives the loop so
we can verify: tool-calling round-trips, errors-as-data, result protection,
and the Supervisor end-to-end with the new engine.

Run::

    python -m Python.Src.Supervisor._loop_smoke
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import asyncio

from pydantic import BaseModel, Field

from Python.Src.Supervisor.agent_loop import (
    AgentLoop,
    persist_large_result,
    truncate_result,
    tool_to_openai_schema,
)
from Python.Src.Supervisor.skill import SkillRegistry
from Python.Src.Supervisor.tool import ToolCard


# ── a tiny echo tool ────────────────────────────────────────────────────
class EchoIn(BaseModel):
    text: str = Field(..., description="echo this")


class EchoOut(BaseModel):
    echoed: str


class EchoTool:
    card = ToolCard(name="echo", description="echo text back",
                    input_model=EchoIn, output_model=EchoOut)

    def run(self, **kwargs):
        return EchoOut(echoed=EchoIn(**kwargs).text)


class BoomTool:
    card = ToolCard(name="boom", description="always raises",
                    input_model=EchoIn, output_model=EchoOut)

    def run(self, **kwargs):
        raise RuntimeError("kaboom")


# ── scripted fake OpenAI client ─────────────────────────────────────────
class _FnCall:
    def __init__(self, name, arguments, _id="call_1"):
        self.id = _id
        self.type = "function"
        self.function = type("F", (), {"name": name, "arguments": arguments})()


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Usage:
    def __init__(self, p=10, c=5):
        self.prompt_tokens = p
        self.completion_tokens = c


class _Resp:
    def __init__(self, msg):
        self.choices = [type("C", (), {"message": msg})()]
        self.usage = _Usage()


class _ScriptedCompletions:
    def __init__(self, script):
        self._script = list(script)

    async def create(self, **kwargs):
        return self._script.pop(0)


class _ScriptedClient:
    def __init__(self, script):
        self.chat = type("Chat", (), {"completions": _ScriptedCompletions(script)})()


async def _run_loop(script, tools):
    loop = AgentLoop(_ScriptedClient(script), "fake-model")
    by_name = {t.card.name: t for t in tools}

    async def dispatch(name, args):
        tool = by_name.get(name)
        if tool is None:
            return f"Unknown tool: {name}"
        try:
            r = await asyncio.to_thread(tool.run, **args)
        except Exception as e:  # noqa: BLE001
            return f"Tool error ({name}): {e}"
        import json
        return json.dumps(r.model_dump(mode="json"), ensure_ascii=False)

    return await loop.run(
        system_prompt="sys", history=[], user_input="hi",
        tools=tools, dispatch=dispatch,
    )


def main() -> int:
    print("=== P1 agent-loop smoke test ===\n")

    print("[1] result protection helpers")
    assert truncate_result("x" * 10) == "x" * 10
    big = "y" * 60_000
    t = truncate_result(big)
    assert "truncated" in t and len(t) < 60_000
    persisted = persist_large_result("echo", "z" * (40 * 1024))
    assert "结果过大" in persisted and "var" in persisted
    print("  ok (truncate + persist)")

    print("\n[2] tool_to_openai_schema from ToolCard")
    sch = tool_to_openai_schema(EchoTool())
    assert sch["type"] == "function" and sch["function"]["name"] == "echo"
    assert "text" in sch["function"]["parameters"]["properties"]
    print("  ok")

    print("\n[3] loop: tool call → dispatch → final answer")
    script = [
        _Resp(_Msg(content="", tool_calls=[_FnCall("echo", '{"text": "hello"}')])),
        _Resp(_Msg(content="echoed it back for you")),
    ]
    out = asyncio.run(_run_loop(script, [EchoTool()]))
    print(f"  answer={out['answer']!r}, tool_calls={out['tool_calls']}")
    assert out["answer"] == "echoed it back for you"
    assert out["tool_calls"] == [{"name": "echo", "args": {"text": "hello"}}]
    assert out["usage"]["input"] == 20  # two calls × 10
    print("  ok")

    print("\n[4] errors-as-data: a raising tool yields a string, loop continues")
    script = [
        _Resp(_Msg(content="", tool_calls=[_FnCall("boom", "{}")])),
        _Resp(_Msg(content="recovered after tool error")),
    ]
    out = asyncio.run(_run_loop(script, [BoomTool()]))
    # find the tool result message
    tool_msgs = [m for m in out["messages"] if m.get("role") == "tool"]
    assert tool_msgs and "Tool error (boom): kaboom" in tool_msgs[0]["content"]
    assert out["answer"] == "recovered after tool error"
    print(f"  ok, tool result: {tool_msgs[0]['content']!r}")

    print("\n[5] no tools / direct answer")
    out = asyncio.run(_run_loop([_Resp(_Msg(content="just chatting"))], [EchoTool()]))
    assert out["answer"] == "just chatting" and out["tool_calls"] == []
    print("  ok")

    print("\n[6] Supervisor end-to-end with patched openai client")
    script = [
        _Resp(_Msg(content="", tool_calls=[_FnCall("echo", '{"text": "tr01"}')])),
        _Resp(_Msg(content="done: tr01")),
    ]

    def _fake_async_openai(**kwargs):
        return _ScriptedClient(script)

    with patch("Python.Src.Supervisor.core.openai.AsyncOpenAI", _fake_async_openai):
        from Python.Src.Supervisor.core import Supervisor
        from Python.Src.Supervisor.session import SessionStore
        import tempfile
        tmp_db = Path(tempfile.gettempdir()) / "p1_smoke_sessions.db"
        if tmp_db.exists():
            tmp_db.unlink()
        store = SessionStore(db_path=tmp_db)
        sup = Supervisor(
            tools=[EchoTool()],
            session_store=store,
            skill_registry=SkillRegistry(),  # empty → no load_skill, no scan
        )
        sid = sup.new_session()
        result = sup.chat_verbose(sid, "echo tr01")
        print(f"  answer={result['answer']!r}, tool_calls={result['tool_calls']}")
        assert result["answer"] == "done: tr01"
        assert result["tool_calls"] == [{"name": "echo", "args": {"text": "tr01"}}]
        # history persisted (user + assistant)
        hist = store.get_history(sid)
        assert len(hist) == 2 and hist[0]["role"] == "user" and hist[1]["role"] == "assistant"
        print(f"  ok, history persisted: {[h['role'] for h in hist]}")

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
