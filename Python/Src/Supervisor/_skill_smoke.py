"""Smoke test for the prompt-style Skill layer (SKILL.md).

No LLM / no network. Verifies discovery, the load_skill Tool, and that the
Supervisor injects the skill catalogue into the system prompt.

Run::

    python -m Python.Src.Supervisor._skill_smoke
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

from Python.Src.Supervisor.skill import LoadSkillTool, SkillRegistry
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
    print("=== prompt-Skill layer smoke test ===\n")

    skills_dir = Path(project_root) / "skills"

    print("[1] SkillRegistry.discover() finds the SKILL.md skills")
    reg = SkillRegistry.discover([skills_dir])
    names = reg.names
    print(f"  discovered: {names}")
    assert "dga-interpretation" in names, names
    assert "maintenance-report" in names, names

    print("\n[2] each skill has description + non-empty body")
    for s in reg.list():
        assert s.description, f"{s.name} missing description"
        assert s.body.strip(), f"{s.name} empty body"
        print(f"  {s.name}: desc {len(s.description)} chars, body {len(s.body)} chars")

    print("\n[3] catalogue_text() renders one line per skill")
    cat = reg.catalogue_text()
    assert "dga-interpretation" in cat and "—" in cat
    print(f"  catalogue:\n{cat}")

    print("\n[4] LoadSkillTool.run() returns the body")
    lst = LoadSkillTool(reg)
    out = lst.run(name="dga-interpretation")
    assert out.found and "三比值" in out.body
    print(f"  ok, found={out.found}, body head: {out.body[:40]!r}")

    print("\n[5] LoadSkillTool.run() on missing skill → found=False")
    miss = lst.run(name="nope")
    assert miss.found is False and miss.error
    print(f"  ok, error: {miss.error}")

    print("\n[6] Supervisor injects catalogue + load_skill tool (LLM stubbed)")
    with patch("Python.Src.Supervisor.core.ChatOllama") as MockChat, \
         patch("Python.Src.Supervisor.core.create_react_agent") as mock_build:
        MockChat.return_value = MagicMock(name="fake-llm")
        mock_build.side_effect = lambda **kw: MagicMock(tools=kw["tools"], prompt=kw["prompt"])
        from Python.Src.Supervisor.core import Supervisor

        sup = Supervisor(tools=[_stub_tool("seed")], skill_dirs=[skills_dir])
        kw = mock_build.call_args.kwargs
        prompt = kw["prompt"]
        tool_names = [t.name for t in kw["tools"]]
        assert "## 可用知识技能" in prompt, "skill catalogue missing from prompt"
        assert "dga-interpretation" in prompt
        assert "load_skill" in tool_names, f"load_skill not wired: {tool_names}"
        assert sup.skill_names == reg.names
        print(f"  ok, tools={tool_names}")
        print(f"  prompt has catalogue: {'## 可用知识技能' in prompt}")

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
