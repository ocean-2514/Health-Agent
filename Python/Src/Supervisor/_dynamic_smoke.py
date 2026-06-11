"""Smoke test for the dynamic Tool registry.

Avoids touching Ollama by stubbing the LLM out and only exercising the
registry mutators + verifying that the underlying tool list & compiled
agent reflect each mutation.

Run::

    python -m Python.Src.Supervisor._dynamic_smoke
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from Python.Src.Supervisor.tool import ToolCard


class _NoIn(BaseModel):
    pass


class _Out(BaseModel):
    ok: bool = True


def _make_tool(name: str):
    class _Local:
        card = ToolCard(
            name=name, description=f"stub {name}",
            input_model=_NoIn, output_model=_Out,
        )

        def run(self, **kwargs):
            return _Out()

    return _Local()


def main() -> int:
    print("=== dynamic Tool-registry smoke test ===\n")

    with patch("Python.Src.Supervisor.core.ChatOllama") as MockChat, \
         patch("Python.Src.Supervisor.core.create_react_agent") as mock_build, \
         patch("Python.Src.Supervisor.core.SkillRegistry") as MockSkillReg:
        MockChat.return_value = MagicMock(name="fake-llm")
        mock_build.side_effect = lambda **kw: MagicMock(name="fake-agent", tools=kw["tools"])
        # No prompt-skills in this test → empty registry (so no load_skill tool)
        empty_reg = MagicMock()
        empty_reg.list.return_value = []
        empty_reg.names = []
        empty_reg.catalogue_text.return_value = ""
        MockSkillReg.discover.return_value = empty_reg

        from Python.Src.Supervisor.core import Supervisor

        print("[1] init with one tool")
        sup = Supervisor(tools=[_make_tool("alpha")])
        assert sup.tool_names == ["alpha"]
        builds_after_init = mock_build.call_count
        assert builds_after_init == 1, "init should rebuild exactly once"
        print(f"  ok, builds={builds_after_init}")

        print("\n[2] register_tool triggers one rebuild")
        sup.register_tool(_make_tool("beta"))
        assert sup.tool_names == ["alpha", "beta"], sup.tool_names
        assert mock_build.call_count == builds_after_init + 1
        print(f"  ok, names={sup.tool_names}")

        print("\n[3] register_tools (batch) — N tools, 1 rebuild")
        before = mock_build.call_count
        sup.register_tools([_make_tool("g1"), _make_tool("g2"), _make_tool("g3")])
        assert mock_build.call_count == before + 1, "batch should rebuild only once"
        assert sup.tool_names == ["alpha", "beta", "g1", "g2", "g3"]
        print(f"  ok, names={sup.tool_names}")

        print("\n[4] disable hides from LLM but keeps in registry")
        sup.disable_tool("beta")
        assert sup.tool_names == ["alpha", "g1", "g2", "g3"]
        assert sup.disabled_tool_names == ["beta"]
        assert sup.all_tool_names == ["alpha", "beta", "g1", "g2", "g3"]
        last_tools = mock_build.call_args.kwargs["tools"]
        assert {t.name for t in last_tools} == {"alpha", "g1", "g2", "g3"}
        print(f"  ok, tools after disable: {[t.name for t in last_tools]}")

        print("\n[5] enable restores")
        sup.enable_tool("beta")
        assert sup.tool_names == ["alpha", "beta", "g1", "g2", "g3"]
        print("  ok")

        print("\n[6] unregister removes")
        assert sup.unregister_tool("g2") is True
        assert "g2" not in sup.all_tool_names
        assert sup.unregister_tool("g2") is False  # idempotent miss
        print(f"  ok, names={sup.tool_names}")

        print("\n[7] re-register with same name overwrites + keeps slot")
        sup.register_tool(_make_tool("alpha"))
        assert sup.tool_names[0] == "alpha"
        print("  ok, alpha kept first slot")

        print("\n[8] register_tool_from_config (good path)")
        sup.register_tool_from_config({
            "class_path": "examples.hot_tools.echo_tool.EchoTool",
            "enabled": True,
        })
        assert "echo" in sup.tool_names
        print(f"  ok, echo registered: {'echo' in sup.tool_names}")

        print("\n[9] register_tool_from_config (bad class_path → ToolLoadError)")
        from Python.Src.Supervisor.loader import ToolLoadError
        try:
            sup.register_tool_from_config({"class_path": "nonexistent.module.Foo"})
        except ToolLoadError as e:
            print(f"  ok, raised: {str(e)[:60]}...")
        else:
            raise AssertionError("expected ToolLoadError")

        print("\n[10] register_tools_from_path on examples/hot_tools")
        added = sup.register_tools_from_path(
            str(Path(project_root) / "examples" / "hot_tools")
        )
        print(f"  added: {added}")
        assert "echo" not in added, "echo should be skipped (already present)"
        assert "current_time" in added and "current_year" in added
        print(f"  ok, all_tools now: {sup.all_tool_names}")

        print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
