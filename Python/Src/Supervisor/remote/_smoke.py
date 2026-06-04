"""End-to-end smoke test for Phase 7 — remote A2A skill integration.

Requires the demo server to be running::

    python -m a2a_demo_server.fake_search_server   # in another terminal

Run::

    python -m Python.Src.Supervisor.remote._smoke

Checks:
  1. load_remote_skills() picks up defect_kb_search from
     Config/remote_skills.yaml AND its description was enriched by the
     probe (i.e. the probe path actually hit the live server).
  2. load_skills() returns local + remote in a single flat list.
  3. RemoteA2ASkill.run() round-trips against the live server and parses
     the JSON reply into raw_json.
  4. skill_to_tool() wraps it so the supervisor's tool layer can invoke
     it like a local skill.
  5. Relaxed-probe failure path: load_remote_skills against a dead URL
     still registers the skill (with an "unreachable at startup" note)
     and a call returns success=false rather than raising.
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[4])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from Python.Src.Supervisor import (
    RemoteA2ASkill,
    load_remote_skills,
    load_skills,
    skill_to_tool,
)
from Python.Src.Supervisor.remote.a2a_client import A2AClient


def main() -> int:
    print("=== Phase 7 smoke test ===\n")

    print("[1] load_remote_skills() from Config/remote_skills.yaml")
    remotes = load_remote_skills()
    assert remotes, "expected at least one remote skill"
    for s in remotes:
        print(f"  - {s.card.name}  url={s.url}")
        print(f"      description: {s.card.description[:120]}...")
    # probe should have appended "[remote A2A agent: ...]" suffix
    assert any("[remote A2A agent:" in s.card.description for s in remotes), \
        "expected probe to enrich description"

    print("\n[2] load_skills() merges local + remote")
    all_skills = load_skills()
    names = [s.card.name for s in all_skills]
    print(f"  skills: {names}")
    assert "defect_kb_search" in names, "defect_kb_search missing from merged list"
    assert "transformer_diagnosis" in names, "local skill disappeared"

    print("\n[3] RemoteA2ASkill.run() round-trip")
    skill = next(s for s in remotes if s.card.name == "defect_kb_search")
    out = skill.run(instruction="局放和过热的判据是什么?")
    print(f"  success={out.success}, error={out.error}")
    print(f"  text head: {out.text[:120]!r}")
    print(f"  raw_json keys: {list(out.raw_json.keys()) if out.raw_json else None}")
    assert out.success, f"remote call failed: {out.error}"
    assert out.raw_json and "matches" in out.raw_json, "JSON shape unexpected"

    print("\n[4] skill_to_tool() wraps it for the supervisor")
    tool = skill_to_tool(skill)
    print(f"  tool.name={tool.name}")
    print(f"  args_schema={tool.args_schema.__name__}")
    invoked = tool.invoke({"instruction": "test"})
    print(f"  invoked keys: {list(invoked.keys())}")
    assert invoked.get("success") is True

    print("\n[5] Relaxed probe: unreachable URL still registers a skill")
    import io, logging
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    handler.setLevel(logging.WARNING)
    logging.getLogger("Python.Src.Supervisor.remote.loader").addHandler(handler)

    import tempfile, os
    with tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as fp:
        fp.write(
            "remote_skills:\n"
            "  - name: dead_remote\n"
            "    description: a remote that isn't there\n"
            "    url: http://127.0.0.1:1\n"
            "    timeout_s: 2\n"
            "    enabled: true\n"
        )
        tmp_path = fp.name
    try:
        dead = load_remote_skills(yaml_path=Path(tmp_path), client=A2AClient(default_timeout_s=2))
        assert len(dead) == 1, "should have registered the dead remote anyway"
        print(f"  registered: {dead[0].card.name} (description carries unreachable note)")
        assert "unreachable at startup" in dead[0].card.description
        # actual call should return success=false
        bad = dead[0].run(instruction="hi")
        assert bad.success is False
        print(f"  call returned success=false, error head: {bad.error[:60]!r}")
        warnings = log_buf.getvalue()
        assert "A2A probe failed" in warnings, "expected probe-failure warning"
    finally:
        os.unlink(tmp_path)

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
