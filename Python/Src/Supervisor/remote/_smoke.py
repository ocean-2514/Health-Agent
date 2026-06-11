"""End-to-end smoke test for remote A2A tool integration.

Requires the demo server to be running::

    python -m a2a_demo_server.fake_search_server   # in another terminal

Run::

    python -m Python.Src.Supervisor.remote._smoke

Checks:
  1. load_remote_tools() picks up defect_kb_search from
     Config/remote_tools.yaml AND its description was enriched by the probe.
  2. load_tools() returns local + remote in a single flat list.
  3. RemoteA2ATool.run() round-trips against the live server and parses
     the JSON reply into raw_json.
  4. to_langchain_tool() wraps it so the supervisor's tool layer can invoke
     it like a local tool.
  5. Relaxed-probe failure path: load_remote_tools against a dead URL still
     registers the tool (with an "unreachable at startup" note) and a call
     returns success=false rather than raising.
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
    RemoteA2ATool,
    load_remote_tools,
    load_tools,
    to_langchain_tool,
)
from Python.Src.Supervisor.remote.a2a_client import A2AClient


def main() -> int:
    print("=== remote A2A tool smoke test ===\n")

    print("[1] load_remote_tools() from Config/remote_tools.yaml")
    remotes = load_remote_tools()
    assert remotes, "expected at least one remote tool"
    for t in remotes:
        print(f"  - {t.card.name}  url={t.url}")
        print(f"      description: {t.card.description[:120]}...")
    assert any("[remote A2A agent:" in t.card.description for t in remotes), \
        "expected probe to enrich description"

    print("\n[2] load_tools() merges local + remote")
    all_tools = load_tools()
    names = [t.card.name for t in all_tools]
    print(f"  tools: {names}")
    assert "defect_kb_search" in names, "defect_kb_search missing from merged list"
    assert "transformer_diagnosis" in names, "local tool disappeared"

    print("\n[3] RemoteA2ATool.run() round-trip")
    tool = next(t for t in remotes if t.card.name == "defect_kb_search")
    out = tool.run(instruction="局放和过热的判据是什么?")
    print(f"  success={out.success}, error={out.error}")
    print(f"  raw_json keys: {list(out.raw_json.keys()) if out.raw_json else None}")
    assert out.success, f"remote call failed: {out.error}"
    assert out.raw_json and "matches" in out.raw_json, "JSON shape unexpected"

    print("\n[4] to_langchain_tool() wraps it for the supervisor")
    lc = to_langchain_tool(tool)
    print(f"  lc.name={lc.name}, args_schema={lc.args_schema.__name__}")
    invoked = lc.invoke({"instruction": "test"})
    assert invoked.get("success") is True

    print("\n[5] Relaxed probe: unreachable URL still registers a tool")
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as fp:
        fp.write(
            "remote_tools:\n"
            "  - name: dead_remote\n"
            "    description: a remote that isn't there\n"
            "    url: http://127.0.0.1:1\n"
            "    timeout_s: 2\n"
            "    enabled: true\n"
        )
        tmp_path = fp.name
    try:
        dead = load_remote_tools(yaml_path=Path(tmp_path), client=A2AClient(default_timeout_s=2))
        assert len(dead) == 1, "should have registered the dead remote anyway"
        assert "unreachable at startup" in dead[0].card.description
        bad = dead[0].run(instruction="hi")
        assert bad.success is False
        print(f"  ok, call returned success=false: {bad.error[:50]!r}")
    finally:
        os.unlink(tmp_path)

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
