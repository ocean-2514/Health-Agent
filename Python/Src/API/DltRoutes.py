"""HTTP API for DL/T 1685-2017 standard state-evaluation.

Powers the frontend "标准评价" page: the user fills in whatever state
quantities they have (missing ones simply aren't deducted — clause 6e), can
pull a few measurable ones straight from IoTDB, then either compute the
standard score or run a full diagnosis biased by those measurements.

Endpoints (all under ``/api/dlt1685``):
  * ``GET  /catalogue``     — all 状态量 grouped by component, with input type /
                              qualitative levels / basis hint (drives the form)
  * ``POST /evaluate``      — measurements → 部件/整体状态 + 扣分明细 + HI
  * ``POST /diagnose``      — measurements → full diagnosis (inner graph) biased
                              by the standard evaluation
  * ``GET  /iotdb_import``  — map a device's IoTDB series onto DL/T item keys

The evaluation engine itself lives in ``Core.dlt1685`` / ``Core.rules_dlt1685``;
this module only introspects the rule table for the UI and marshals IO.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Core.dlt1685 import (
    COMPONENTS,
    LEVEL_ORDER,
    deduction_to_hi,
    evaluate,
)
from Python.Src.Core.rules_dlt1685 import ITEMS, RULES

router = APIRouter(prefix="/api/dlt1685", tags=["dlt1685"])


# --------------------------------------------------------------------------
# Rule-table introspection (drives the input form)
# --------------------------------------------------------------------------

def _rules_of(key: str) -> List[Dict[str, Any]]:
    return [r for r in RULES if r["key"] == key]


def _input_kind(key: str) -> str:
    """A pure-``obs`` item is a qualitative dropdown; anything with a numeric
    criterion (num/numv/interp) takes a raw measured value."""
    kinds = {r["criterion"][0] for r in _rules_of(key)}
    return "qualitative" if kinds <= {"obs"} else "numeric"


def _levels(key: str) -> List[str]:
    """Deterioration levels this item can reach (for the qualitative dropdown)."""
    return sorted({r["level"] for r in _rules_of(key)}, key=lambda lv: LEVEL_ORDER[lv])


def _hint(key: str) -> str:
    """Human-readable basis, e.g. 'Ⅱ: 接地电流0.1A~0.3A / Ⅳ: 接地电流>0.3A'."""
    return " / ".join(f"{r['level']}: {r['basis']}" for r in _rules_of(key))


@router.get("/catalogue")
def catalogue() -> Dict[str, Any]:
    """All state quantities grouped by the five DL/T 1685 components."""
    comps: List[Dict[str, Any]] = []
    for comp in COMPONENTS:
        items = [
            {
                "key": key,
                "name": meta["name"],
                "group": meta.get("group"),
                "input": _input_kind(key),
                "levels": _levels(key),
                "hint": _hint(key),
            }
            for key, meta in ITEMS.items()
            if meta["component"] == comp
        ]
        comps.append({"component": comp, "items": items})
    return {
        "components": comps,
        "levels_all": ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ"],
        "voltage_options": [110, 220, 330, 500],
    }


# --------------------------------------------------------------------------
# Evaluate / diagnose
# --------------------------------------------------------------------------

# Blank / "正常" means "not measured" → no deduction (clause 6e), so drop them
# before handing measurements to the engine.
_EMPTY = (None, "", "正常")


def _clean(measurements: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (measurements or {}).items():
        if v in _EMPTY:
            continue
        out[k] = v
    return out


class EvaluateReq(BaseModel):
    measurements: Dict[str, Any] = {}
    voltage_kv: float = 220.0


@router.post("/evaluate")
def evaluate_route(req: EvaluateReq) -> Dict[str, Any]:
    """Standard state evaluation → components/overall + deduction detail + HI."""
    try:
        res = evaluate(_clean(req.measurements), req.voltage_kv)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"评价失败: {e}")
    return {**res.to_dict(), "health_index": deduction_to_hi(res)}


class DiagnoseReq(BaseModel):
    equipment_id: str = "tr01"
    substation: str = "station1"
    measurements: Dict[str, Any] = {}
    voltage_kv: float = 220.0


_diag_tool = None  # type: ignore[var-annotated]


def _get_diag_tool():
    """Build the inner-graph diagnosis Tool once (loads the platform registry)."""
    global _diag_tool
    if _diag_tool is None:
        from Python.Src.Supervisor.tools.transformer_diagnosis import (
            TransformerDiagnosisTool,
        )

        _diag_tool = TransformerDiagnosisTool()
    return _diag_tool


@router.post("/diagnose")
def diagnose(req: DiagnoseReq) -> Dict[str, Any]:
    """Full diagnosis run (三源识别 → 融合 → RUL) biased by the standard
    evaluation. Synchronous (~30-60s); runs in FastAPI's threadpool."""
    try:
        tool = _get_diag_tool()
        out = tool.run(
            equipment_id=req.equipment_id,
            substation=req.substation,
            raw_input={
                "dlt_measurements": _clean(req.measurements),
                "voltage_kv": req.voltage_kv,
            },
        )
    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"诊断失败: {e}")
    return out.model_dump()


# --------------------------------------------------------------------------
# IoTDB import — map measurable series onto DL/T item keys
# --------------------------------------------------------------------------

@router.get("/iotdb_import")
def iotdb_import(equipment_id: str = "tr01", substation: str = "station1") -> Dict[str, Any]:
    """Pull the latest value of each IoTDB series and map the ones that
    correspond to a DL/T 1685 state quantity onto its item key.

    Only the directly-measurable subset is imported (DGA gases, 油击穿电压,
    水分); the rest of the form is left to the user. This reads IoTDB but does
    **not** alter the diagnosis data path (B.2 scope)."""
    from Python.Src.Tools.iotdb_tool import IotDBClient

    client = IotDBClient(mode="mock")
    scoring = client.get_all_scoring_data(equipment_id=equipment_id, substation=substation)

    def last(metric: str) -> Optional[float]:
        tr = scoring.get(metric)
        if tr and tr.values:
            return float(tr.values[-1])
        return None

    h2, ch4, c2h6, c2h4, c2h2 = (
        last("H2"), last("CH4"), last("C2H6"), last("C2H4"), last("C2H2"),
    )
    total_hc = sum(v for v in (ch4, c2h6, c2h4, c2h2) if v is not None)
    bdv, water = last("oil_bdv"), last("oil_water")

    imported: List[Dict[str, Any]] = []

    def add(key: str, value: Optional[float], sensor: str, ndigits: int = 2) -> None:
        if value is None:
            return
        imported.append({
            "key": key,
            "name": ITEMS[key]["name"],
            "value": round(value, ndigits),
            "sensor": sensor,
        })

    add("b_dga_h2", h2, "H2")
    add("b_dga_c2h2", c2h2, "C2H2", ndigits=3)
    add("b_dga_hydrocarbon", total_hc or None, "CH4+C2H6+C2H4+C2H2")
    add("b_oil_breakdown", bdv, "oil_bdv")
    add("b_moisture", water, "oil_water")

    return {
        "equipment_id": equipment_id,
        "substation": substation,
        "measurements": {it["key"]: it["value"] for it in imported},
        "imported": imported,
    }
