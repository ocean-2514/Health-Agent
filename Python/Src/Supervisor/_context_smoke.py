"""Offline smoke test for P2 context management.

No network. Covers:
  * in-turn budget (shrink oversized tool results)
  * in-turn snip (drop stale tool results, keep recent N)
  * cross-turn auto-compact (summarise old history, persist, reload trimmed)

Run::

    python -m Python.Src.Supervisor._context_smoke
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from pydantic import BaseModel

from Python.Src.Supervisor.agent_loop import AgentLoop, SNIP_PLACEHOLDER
from Python.Src.Supervisor.skill import SkillRegistry
from Python.Src.Supervisor.tool import ToolCard


class _NoIn(BaseModel):
    pass


class _Out(BaseModel):
    ok: bool = True


def _stub_tool(name: str):
    class _T:
        card = ToolCard(name=name, description="stub", input_model=_NoIn, output_model=_Out)

        def run(self, **kwargs):
            return _Out()
    return _T()


# fake openai client that returns a fixed text for any create() call
class _FixedClient:
    def __init__(self, text: str):
        comp = type("Comp", (), {})()
        async def _create(**kwargs):
            msg = type("M", (), {"content": text, "tool_calls": None})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()
        comp.create = _create
        self.chat = type("Chat", (), {"completions": comp})()


def main() -> int:
    print("=== P2 context-management smoke test ===\n")

    print("[1] in-turn budget: oversized tool result gets shrunk")
    big = "x" * 40_000
    msgs = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": big},
    ]
    # utilization 0.75 → budget 15000
    AgentLoop._budget_tool_results(msgs, 0.75)
    assert "budgeted" in msgs[2]["content"] and len(msgs[2]["content"]) < 40_000
    print(f"  ok, shrunk {len(big)} → {len(msgs[2]['content'])} chars")

    print("\n[2] in-turn budget no-op below threshold")
    small = [{"role": "tool", "tool_call_id": "1", "content": "y" * 40_000}]
    AgentLoop._budget_tool_results(small, 0.40)
    assert len(small[0]["content"]) == 40_000
    print("  ok (utilization < 0.5 → untouched)")

    print("\n[3] in-turn snip: keep recent 3 tool results, snip older")
    five = []
    for i in range(5):
        five.append({"role": "tool", "tool_call_id": str(i), "content": f"result {i}"})
    AgentLoop._snip_stale_results(five, 0.70)
    snipped = [m["content"] == SNIP_PLACEHOLDER for m in five]
    assert snipped == [True, True, False, False, False], snipped
    print(f"  ok, snipped first 2 of 5, kept last 3")

    print("\n[4] cross-turn auto-compact: summarise + persist + reload trimmed")
    with patch("Python.Src.Supervisor.core.openai.AsyncOpenAI",
               lambda **kw: _FixedClient("[SUMMARY] tr01 HI=82 RUL=18y 放电")):
        from Python.Src.Supervisor.core import Supervisor
        from Python.Src.Supervisor.session import SessionStore

        tmp_db = Path(tempfile.gettempdir()) / "p2_smoke_sessions.db"
        if tmp_db.exists():
            tmp_db.unlink()
        store = SessionStore(db_path=tmp_db)
        sup = Supervisor(tools=[_stub_tool("seed")], session_store=store,
                         skill_registry=SkillRegistry())
        # force a tiny window so compaction triggers
        sup._effective_window = 50  # noqa: SLF001

        sid = sup.new_session()
        for i in range(10):
            store.save_message(sid, "user", f"问题 {i} " + "字" * 20)
            store.save_message(sid, "assistant", f"回答 {i} " + "字" * 20)

        before = store.get_messages(sid)
        loaded = asyncio.run(sup._maybe_compact_and_load(sid))  # noqa: SLF001

        summary = store.get_summary(sid)
        print(f"  before: {len(before)} msgs; after load: {len(loaded)} msgs")
        print(f"  summary persisted: {summary is not None}, covered_until={summary['covered_until'] if summary else None}")
        assert summary is not None, "summary should be persisted"
        assert loaded[0]["content"].startswith("[对话摘要]"), loaded[0]
        assert len(loaded) < len(before), "compacted history should be shorter"
        # second load must NOT re-summarise (covered_until advanced) → no error
        loaded2 = asyncio.run(sup._maybe_compact_and_load(sid))  # noqa: SLF001
        assert loaded2[0]["content"].startswith("[对话摘要]")
        print(f"  ok, idempotent reload: {len(loaded2)} msgs")

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
