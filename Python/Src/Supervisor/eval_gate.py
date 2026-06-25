"""Golden-trace evaluation gate.

The transformer-diagnosis pipeline is the platform's reproducibility moat:
same input must yield the same numeric verdict. This module locks that down
with golden traces — a recorded snapshot of the **deterministic** output
fields that a later run is compared against; any drift fails the gate.

Only deterministic fields are golden-traced. The LLM-generated narrative
(``final_report``) and plugin ``extra_artifacts`` are excluded — they vary
run to run and are not part of the reproducibility contract.

Goldens live in ``golden/<suite>/<fixture>.json`` (git-tracked — they ARE
the spec). Because a full diagnosis takes ~75s (ML inference + LLM), this
is a CI / dev-time gate, not a per-registration startup check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

GOLDEN_DIR = Path(project_root) / "golden"

# The reproducibility contract: deterministic scalar/categorical outputs.
# (final_report = LLM text, extra_artifacts = plugin payloads — both excluded.)
DETERMINISTIC_FIELDS = [
    "health_index",
    "predicted_rul_years",
    "fusion_verdict_cn",
    "fusion_confidence",
    "dga_risk_score",
    "primary_threat",
    "forced_override",
]

# Tolerance for float fields — guards against tiny ML/float jitter across
# runs/hardware while still catching real drift.
FLOAT_TOL = 0.01


def extract_deterministic(output: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the golden-traced fields out of a TransformerDiagnosisOutput dict."""
    return {k: output.get(k) for k in DETERMINISTIC_FIELDS}


def _golden_path(suite: str, fixture: str) -> Path:
    return GOLDEN_DIR / suite / f"{fixture}.json"


def record_golden(suite: str, fixture: str, data: Dict[str, Any]) -> Path:
    p = _golden_path(suite, fixture)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_golden(suite: str, fixture: str) -> Optional[Dict[str, Any]]:
    p = _golden_path(suite, fixture)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def compare_golden(
    suite: str, fixture: str, data: Dict[str, Any], tol: float = FLOAT_TOL
) -> Tuple[bool, List[str]]:
    """Compare ``data`` against the recorded golden. Returns (ok, diffs)."""
    golden = load_golden(suite, fixture)
    if golden is None:
        return False, [f"no golden recorded for {suite}/{fixture} (run with --record)"]
    diffs: List[str] = []
    for k in DETERMINISTIC_FIELDS:
        g, a = golden.get(k), data.get(k)
        if isinstance(g, (int, float)) and isinstance(a, (int, float)):
            if abs(float(g) - float(a)) > tol:
                diffs.append(f"{k}: golden={g} actual={a} (Δ={abs(float(g)-float(a)):.4f})")
        elif g != a:
            diffs.append(f"{k}: golden={g!r} actual={a!r}")
    return (not diffs), diffs
