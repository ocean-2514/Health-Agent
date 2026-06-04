"""Smoke test for Phase 8.7-8.10 — dynamic *remote* skill registration.

Requires the demo server::

    python -m a2a_demo_server.fake_search_server

Run::

    python -m Python.Src.Supervisor._remote_dynamic_smoke

Checks (LLM still stubbed — we're testing the registry plumbing, not Ollama):

  1. register_remote_skill(url) with no name → probes card, uses remote's name
  2. Probe-supplied description got the `[remote A2A agent @ ...]` suffix
  3. register_remote_skill against a dead URL still registers (fallback name required)
     and the description carries the `unreachable at registration` note
  4. Caller-supplied name overrides probed name
  5. register_remote_skills_from_yaml reads Config/remote_skills.yaml and registers
     (skipping duplicates from earlier steps)
  6. The registered remote skill is callable end-to-end (real HTTP roundtrip)
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

from Python.Src.Supervisor.skill import SkillCard


class _NoIn(BaseModel):
    pass


class _Out(BaseModel):
    ok: bool = True


def _stub_skill(name: str):
    class _S:
        card = SkillCard(name=name, description=f"stub {name}",
                         input_model=_NoIn, output_model=_Out)

        def run(self, **kwargs):
            return _Out()
    return _S()


def main() -> int:
    print("=== Phase 8.7-8.10 remote dynamic registration ===\n")

    with patch("Python.Src.Supervisor.core.ChatOllama") as MockChat, \
         patch("Python.Src.Supervisor.core.create_react_agent") as mock_build:
        MockChat.return_value = MagicMock(name="fake-llm")
        mock_build.side_effect = lambda **kw: MagicMock(name="fake-agent", tools=kw["tools"])

        from Python.Src.Supervisor.core import Supervisor

        sup = Supervisor(skills=[_stub_skill("seed")])

        print("[1] register_remote_skill probes card when name omitted")
        name = sup.register_remote_skill("http://127.0.0.1:9001")
        assert name == "FakeDefectSearch", f"got {name!r}"
        print(f"  ok, registered as {name!r} (from card)")

        print("\n[2] description got remote-agent suffix")
        skill = next(s for n, s in sup._skills.items() if n == name)
        desc = skill.card.description
        print(f"  desc head: {desc[:80]!r}")
        assert "[remote A2A agent @ http://127.0.0.1:9001]" in desc
        print("  ok")

        print("\n[3] dead URL: still registers + unreachable note + fallback")
        # Must pass an explicit name since the probe will fail and card has no name.
        dead_name = sup.register_remote_skill(
            "http://127.0.0.1:1",
            name="dead_remote",
            timeout_s=2,
        )
        assert dead_name == "dead_remote"
        dead = sup._skills["dead_remote"]
        assert "unreachable at registration" in dead.card.description
        print(f"  ok, desc: {dead.card.description}")

        print("\n[4] caller-supplied name overrides probed name")
        nm = sup.register_remote_skill(
            "http://127.0.0.1:9001",
            name="my_custom_alias",
        )
        assert nm == "my_custom_alias"
        # The probed description should still be present
        custom = sup._skills["my_custom_alias"]
        assert "[remote A2A agent @ http://127.0.0.1:9001]" in custom.card.description
        print(f"  ok, registered as {nm!r} (probed desc kept)")

        print("\n[5] register_remote_skills_from_yaml — skips duplicates")
        # Config/remote_skills.yaml declares defect_kb_search; not yet present
        added = sup.register_remote_skills_from_yaml()
        print(f"  added: {added}")
        assert "defect_kb_search" in added

        # Run again — every entry now duplicates, nothing new
        added2 = sup.register_remote_skills_from_yaml()
        assert added2 == []
        print("  ok, second call returned [] (idempotent)")

        print("\n[6] end-to-end call through the dynamically-registered remote")
        out = sup._skills["my_custom_alias"].run(instruction="过热的判据?")
        assert out.success, f"call failed: {out.error}"
        assert out.raw_json and "matches" in out.raw_json
        print(f"  ok, got {len(out.raw_json['matches'])} matches")

        print(f"\nfinal skill list: {sup.skill_names}")

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
