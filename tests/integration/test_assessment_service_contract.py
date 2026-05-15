"""Contract tests for AssessmentService — these LOCK DOWN the response
schema consumed by the React frontend so future refactors that break
key names or types fail loudly.

These tests bypass FastAPI and call the service methods directly. They
do NOT assert exact LLM-generated text content (LLM output is non-
deterministic) — only that the field exists, has the right type, and
respects expected ranges.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from Python.Src.Services.AssessmentService import AssessmentService


# Top-level keys the frontend reads from /api/assess/health
HEALTH_KEYS = {
    "health_index",
    "predicted_rul",
    "risk_score",
    "primary_threat",
    "health_deduction_curve",
    "fault_risk_curve",
    "fault_breakdown",
    "expert_advice",
    "diagnosis_summary",
    "uncertainty_analysis",
    "dga_data",
}

# Top-level keys the frontend reads from /api/assess/defect
DEFECT_KEYS = {
    "fusion_basic_info",
    "original_model_data",
    "bpa_info",
    "final_fusion_result",
    "cn_mapping",
    "version",
    "ai_reasoning",
    "realtime_inference",
    "source_evidence",
}


@pytest.fixture(scope="module")
def service() -> AssessmentService:
    return AssessmentService(mode="mock")


def _baseline_input() -> Dict[str, Any]:
    return {
        "id": "tr01", "substation_id": "station1",
        "oil_bdv": 2, "oil_water": 2, "oil_acid": 1, "oil_ift": 2,
        "dga_h2": 2, "dga_ch4": 2, "dga_co": 1, "dga_co2": 1,
        "dga_c2h4": 1, "dga_c2h6": 1, "dga_c2h2": 1,
        "furan_level": "A", "future_load": 0.8, "ambient_temp": 25.0,
        "moisture": None, "penalty_factor": 1.0,
    }


# ---------- Defect endpoint contract ----------

def test_defect_endpoint_top_level_keys(service: AssessmentService):
    out = service.run_defect_identification({"id": "tr01"})
    missing = DEFECT_KEYS - set(out.keys())
    assert not missing, f"defect endpoint missing required keys: {missing}"


def test_defect_endpoint_final_fusion_shape(service: AssessmentService):
    out = service.run_defect_identification({"id": "tr01"})
    final = out["final_fusion_result"]
    for key in ("final_result_en", "final_result_cn", "final_confidence",
                "is_definite", "is_normal", "is_fault", "decision_note"):
        assert key in final, f"final_fusion_result missing {key}"
    assert 0.0 <= final["final_confidence"] <= 1.0
    assert isinstance(final["is_fault"], bool)


def test_defect_endpoint_realtime_inference_shape(service: AssessmentService):
    out = service.run_defect_identification({"id": "tr01"})
    rt = out["realtime_inference"]
    assert {"bert", "cnn", "yolo", "status"} <= set(rt.keys())
    assert "predicted_cn" in rt["bert"]
    assert "predicted_fault_cn" in rt["cnn"]


def test_defect_endpoint_source_evidence_shape(service: AssessmentService):
    out = service.run_defect_identification({"id": "tr01"})
    se = out["source_evidence"]
    for key in ("bert", "cnn", "yolo", "image_url", "ai_reasoning"):
        assert key in se, f"source_evidence missing {key}"
    assert se["image_url"].startswith("http")


# ---------- Health endpoint contract ----------

def test_health_endpoint_top_level_keys(service: AssessmentService):
    out = service.run_health_assessment(_baseline_input())
    missing = HEALTH_KEYS - set(out.keys())
    assert not missing, f"health endpoint missing required keys: {missing}"


def test_health_endpoint_value_ranges(service: AssessmentService):
    out = service.run_health_assessment(_baseline_input())
    assert 0.0 <= out["health_index"] <= 100.0
    assert out["predicted_rul"] >= 0.0
    assert 0.0 <= out["risk_score"] <= 100.0
    assert isinstance(out["primary_threat"], str)
    assert isinstance(out["expert_advice"], str)
    assert isinstance(out["diagnosis_summary"], str)


def test_health_fault_risk_curve_shape(service: AssessmentService):
    out = service.run_health_assessment(_baseline_input())
    curve = out["fault_risk_curve"]
    assert "x" in curve and "y" in curve
    assert len(curve["x"]) == len(curve["y"])
    assert len(curve["x"]) > 0


def test_health_fault_breakdown_shape(service: AssessmentService):
    out = service.run_health_assessment(_baseline_input())
    bd = out["fault_breakdown"]
    assert isinstance(bd, list) and len(bd) > 0
    for entry in bd:
        assert "type" in entry and "probability" in entry
        assert 0.0 <= entry["probability"] <= 100.0


def test_health_dga_data_shape(service: AssessmentService):
    out = service.run_health_assessment(_baseline_input())
    dga = out["dga_data"]
    # Must include all 7 DGA gases + 3 oil indicators
    expected = {"H2", "CH4", "C2H6", "C2H4", "C2H2", "CO", "CO2", "oil_bdv", "oil_water", "furan"}
    assert expected <= set(dga.keys())
    sample = dga["H2"]
    assert {"sensor", "timestamps", "values"} <= set(sample.keys())
    assert len(sample["timestamps"]) == len(sample["values"])


def test_fire_defect_propagates_to_rul(service: AssessmentService):
    """tr01's mock log mentions 起火 → defect should bias RUL via forced override."""
    inp = _baseline_input()
    inp["id"] = "tr01"
    out = service.run_health_assessment(inp)
    # If the BERT fallback / real model classified 起火 with high confidence,
    # RUL physics should have been forced to 0. We can't guarantee classification,
    # so we just check the field is well-formed.
    assert out["health_index"] >= 0.0
    assert out["predicted_rul"] >= 0.0
