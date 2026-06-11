"""Smoke test for dynamic *remote* tool registration.

Requires the demo server::

    python -m a2a_demo_server.fake_search_server

Run::

    python -m Python.Src.Supervisor._remote_dynamic_smoke

Checks (LLM stubbed — testing registry plumbing, not Ollama):
  1. register_remote_tool(url) with no name → probes card, uses remote's name
  2. Probe-supplied description got the `[remote A2A agent @ ...]` suffix
  3. register_remote_tool against a dead URL still registers (fallback name
     required) and description carries the `unreachable at registration` note
  4. Caller-supplied name overrides probed name
  5. register_remote_tools_from_yaml reads Config/remote_tools.yaml (skip dups)
  6. The registered remote tool is callable end-to-end (real HTTP roundtrip)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from pydantic import BaseModel

from Python.Src.Supervisor.tool import ToolCard


class _NoIn(BaseModel):
    pass


class _Out(BaseModel):
    ok: bool = True


def _stub_tool(name: str):
    class _T:
        card = ToolCard(name=name, description=f"stub {name}",
                        input_model=_NoIn, output_model=_Out)

        def run(self, **kwargs):
            return _Out()
    return _T()


def main() -> int:
    print("=== remote dynamic registration smoke test ===\n")

    with patch("Python.Src.Supervisor.core.ChatOllama") as MockChat, \
         patch("Python.Src.Supervisor.core.create_react_agent") as mock_build, \
         patch("Python.Src.Supervisor.core.SkillRegistry") as MockSkillReg:
        MockChat.return_value = MagicMock(name="fake-llm")
        mock_build.side_effect = lambda **kw: MagicMock(name="fake-agent", tools=kw["tools"])
        empty_reg = MagicMock()
        empty_reg.list.return_value = []
        empty_reg.names = []
        empty_reg.catalogue_text.return_value = ""
        MockSkillReg.discover.return_value = empty_reg

        from Python.Src.Supervisor.core import Supervisor

        sup = Supervisor(tools=[_stub_tool("seed")])

        print("[1] register_remote_tool probes card when name omitted")
        name = sup.register_remote_tool("http://127.0.0.1:9001")
        assert name == "FakeDefectSearch", f"got {name!r}"
        print(f"  ok, registered as {name!r} (from card)")

        print("\n[2] description got remote-agent suffix")
        tool = sup._tools[name]  # noqa: SLF001
        assert "[remote A2A agent @ http://127.0.0.1:9001]" in tool.card.description
        print("  ok")

        print("\n[3] dead URL: still registers + unreachable note + fallback")
        dead_name = sup.register_remote_tool(
            "http://127.0.0.1:1", name="dead_remote", timeout_s=2,
        )
        assert dead_name == "dead_remote"
        assert "unreachable at registration" in sup._tools["dead_remote"].card.description
        print("  ok")

        print("\n[4] caller-supplied name overrides probed name")
        nm = sup.register_remote_tool("http://127.0.0.1:9001", name="my_custom_alias")
        assert nm == "my_custom_alias"
        assert "[remote A2A agent @ http://127.0.0.1:9001]" in sup._tools["my_custom_alias"].card.description
        print(f"  ok, registered as {nm!r} (probed desc kept)")

        print("\n[5] register_remote_tools_from_yaml — skips duplicates")
        added = sup.register_remote_tools_from_yaml()
        print(f"  added: {added}")
        assert "defect_kb_search" in added
        added2 = sup.register_remote_tools_from_yaml()
        assert added2 == []
        print("  ok, second call returned [] (idempotent)")

        print("\n[6] end-to-end call through dynamically-registered remote")
        out = sup._tools["my_custom_alias"].run(instruction="过热的判据?")
        assert out.success, f"call failed: {out.error}"
        assert out.raw_json and "matches" in out.raw_json
        print(f"  ok, got {len(out.raw_json['matches'])} matches")

        print(f"\nfinal tool list: {sup.tool_names}")

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
