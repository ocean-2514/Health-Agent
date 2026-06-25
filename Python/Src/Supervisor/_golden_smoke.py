"""Golden-trace gate for the transformer-diagnosis pipeline (MUSE #2).

Runs the real diagnosis on fixed fixtures and checks the deterministic
output against recorded goldens — catching any reproducibility drift.

Each fixture is a full diagnosis (~75s: ML inference + LLM narrative), so
this is a CI / dev-time gate, NOT a startup or per-registration check.

Usage::

    python -m Python.Src.Supervisor._golden_smoke --record   # (re)record goldens
    python -m Python.Src.Supervisor._golden_smoke            # verify against goldens
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from Python.Src.Supervisor.eval_gate import (
    compare_golden,
    extract_deterministic,
    record_golden,
)
from Python.Src.Supervisor.session import SessionStore
from Python.Src.Supervisor.tools.transformer_diagnosis import TransformerDiagnosisTool

SUITE = "transformer_diagnosis"

# Fixed inputs → reproducible outputs. Add more fixtures (e.g. a severe-defect
# case that triggers forced_override) to widen coverage; each adds ~75s.
FIXTURES = {
    "tr01_default": {"equipment_id": "tr01", "raw_input": {}},
}


def main() -> int:
    record = "--record" in sys.argv
    # throwaway store so the gate doesn't pollute real diagnosis records
    store = SessionStore(db_path=Path(tempfile.gettempdir()) / "golden_sessions.db")
    tool = TransformerDiagnosisTool(session_store=store)

    print(f"=== golden-trace gate ({'RECORD' if record else 'VERIFY'}) ===\n")
    failed = 0
    for name, inp in FIXTURES.items():
        print(f"[{name}] running diagnosis (~75s)...")
        out = tool.run(**inp).model_dump(mode="json")
        data = extract_deterministic(out)
        if record:
            p = record_golden(SUITE, name, data)
            print(f"  recorded → {p}")
            for k, v in data.items():
                print(f"    {k} = {v}")
        else:
            ok, diffs = compare_golden(SUITE, name, data)
            print(f"  {'PASS' if ok else 'FAIL'}")
            for d in diffs:
                print(f"    ✗ {d}")
            if not ok:
                failed += 1

    if record:
        print("\n=== recorded ===")
        return 0
    print(f"\n=== {'OK' if not failed else str(failed) + ' FIXTURE(S) DRIFTED'} ===")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
