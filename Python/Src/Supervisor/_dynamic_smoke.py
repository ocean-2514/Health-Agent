"""Smoke test for Phase 8 — dynamic skill registry.

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

from Python.Src.Supervisor.skill import SkillCard


class _NoIn(BaseModel):
    pass


class _Out(BaseModel):
    ok: bool = True


def _make_skill(name: str):
    class _Local:
        card = SkillCard(
            name=name, description=f"stub {name}",
            input_model=_NoIn, output_model=_Out,
        )

        def run(self, **kwargs):
            return _Out()

    return _Local()


def main() -> int:
    print("=== Phase 8 dynamic-registry smoke test ===\n")

    # Stub the LLM so __init__ doesn't try to talk to Ollama. We also
    # stub create_react_agent so each rebuild is observable.
    with patch("Python.Src.Supervisor.core.ChatOllama") as MockChat, \
         patch("Python.Src.Supervisor.core.create_react_agent") as mock_build:
        MockChat.return_value = MagicMock(name="fake-llm")
        mock_build.side_effect = lambda **kw: MagicMock(name="fake-agent", tools=kw["tools"])

        from Python.Src.Supervisor.core import Supervisor

        print("[1] init with one skill")
        sup = Supervisor(skills=[_make_skill("alpha")])
        assert sup.skill_names == ["alpha"]
        builds_after_init = mock_build.call_count
        assert builds_after_init == 1, "init should rebuild exactly once"
        print(f"  ok, builds={builds_after_init}")

        print("\n[2] register_skill triggers one rebuild")
        sup.register_skill(_make_skill("beta"))
        assert sup.skill_names == ["alpha", "beta"], sup.skill_names
        assert mock_build.call_count == builds_after_init + 1
        print(f"  ok, names={sup.skill_names}")

        print("\n[3] register_skills (batch) — N skills, 1 rebuild")
        before = mock_build.call_count
        sup.register_skills([_make_skill("g1"), _make_skill("g2"), _make_skill("g3")])
        assert mock_build.call_count == before + 1, "batch should rebuild only once"
        assert sup.skill_names == ["alpha", "beta", "g1", "g2", "g3"]
        print(f"  ok, names={sup.skill_names}")

        print("\n[4] disable hides from LLM but keeps in registry")
        sup.disable_skill("beta")
        assert sup.skill_names == ["alpha", "g1", "g2", "g3"]
        assert sup.disabled_skill_names == ["beta"]
        assert sup.all_skill_names == ["alpha", "beta", "g1", "g2", "g3"]
        last_tools = mock_build.call_args.kwargs["tools"]
        assert {t.name for t in last_tools} == {"alpha", "g1", "g2", "g3"}
        print(f"  ok, tools after disable: {[t.name for t in last_tools]}")

        print("\n[5] enable restores")
        sup.enable_skill("beta")
        assert sup.skill_names == ["alpha", "beta", "g1", "g2", "g3"]
        print("  ok")

        print("\n[6] unregister removes")
        assert sup.unregister_skill("g2") is True
        assert "g2" not in sup.all_skill_names
        assert sup.unregister_skill("g2") is False  # idempotent miss
        print(f"  ok, names={sup.skill_names}")

        print("\n[7] re-register with same name overwrites")
        new_alpha = _make_skill("alpha")
        sup.register_skill(new_alpha)
        # ordering stays at original position (alpha was first)
        assert sup.skill_names[0] == "alpha"
        print("  ok, alpha kept first slot")

        print("\n[8] register_skill_from_config (good path)")
        sup.register_skill_from_config({
            "class_path": "examples.hot_skills.echo_skill.EchoSkill",
            "enabled": True,
        })
        assert "echo" in sup.skill_names
        print(f"  ok, echo registered: {'echo' in sup.skill_names}")

        print("\n[9] register_skill_from_config (bad class_path → SkillLoadError)")
        from Python.Src.Supervisor.loader import SkillLoadError
        try:
            sup.register_skill_from_config({"class_path": "nonexistent.module.Foo"})
        except SkillLoadError as e:
            print(f"  ok, raised: {str(e)[:60]}...")
        else:
            raise AssertionError("expected SkillLoadError")

        print("\n[10] register_skills_from_path on examples/hot_skills")
        before_names = set(sup.all_skill_names)
        added = sup.register_skills_from_path(
            str(Path(project_root) / "examples" / "hot_skills")
        )
        print(f"  added: {added}")
        # echo is already registered above (step 8), so should be skipped
        assert "echo" not in added, "echo should be skipped (already present)"
        # time_skill exports two
        assert "current_time" in added and "current_year" in added
        print(f"  ok, all_skills now: {sup.all_skill_names}")

        print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
