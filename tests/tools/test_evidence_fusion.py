"""Smoke + invariant tests for the D-S Murphy fusion in EvidenceFusion.py.

These tests exercise the public API `transformer_three_source_fusion` and the
internal `DSEvidenceFusion.generate_bpa`. They do NOT depend on Ollama or any
ML model — only the deterministic fusion math.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from Python.Src.Core.EvidenceFusion import (
    DSEvidenceFusion,
    UNIFIED_FRAME,
    transformer_three_source_fusion,
)


def _bert(probs_en: dict, is_fuzzy: bool = False) -> dict:
    """Build a BERT-shape input dict from a probability mapping."""
    return {"fault_prediction_result": {"all_probs_en": probs_en, "is_fuzzy": is_fuzzy}}


def _cnn(probs: dict, is_fuzzy: bool = False) -> dict:
    """Build a CNN-shape input dict (uses 'all_probs' key)."""
    return {"fault_prediction": {"all_probs": probs, "is_fuzzy": is_fuzzy}}


def _yolo_normal() -> dict:
    return {"is_fault": False, "defect_count": 0, "defects": []}


def _yolo_fire(confidence: float = 0.92) -> dict:
    return {
        "is_fault": True,
        "defect_count": 1,
        "defects": [{"class_name": "fire", "confidence": confidence}],
    }


def test_bpa_sums_to_one():
    """generate_bpa must always produce a valid BPA: sum(mass) + mass(Θ) ≈ 1."""
    dse = DSEvidenceFusion()
    bpa = dse.generate_bpa(
        "bert",
        {"fire": 0.6, "normal": 0.3, "overheating": 0.1},
        is_fuzzy=False,
    )
    assert bpa.shape == (len(UNIFIED_FRAME) + 1,)
    assert pytest.approx(bpa.sum(), abs=1e-6) == 1.0


def test_three_source_agree_fire(tmp_path: Path):
    """All three sources point to 'fire' with high confidence → fused = fire."""
    save = tmp_path / "fusion.json"
    out = transformer_three_source_fusion(
        bert_input=_bert({"fire": 0.95, "normal": 0.05}),
        cnn_input=_cnn({"overheating": 0.8, "normal": 0.1, "discharge": 0.1}),
        yolo_input=_yolo_fire(0.93),
        save_path=str(save),
    )
    assert out is not None
    data = json.loads(save.read_text(encoding="utf-8"))
    final = data["final_fusion_result"]
    assert final["is_fault"] is True
    assert final["is_normal"] is False


def test_three_source_agree_normal(tmp_path: Path):
    """All three sources say normal → fused = normal."""
    save = tmp_path / "fusion.json"
    out = transformer_three_source_fusion(
        bert_input=_bert({"normal": 0.95, "fire": 0.02, "overheating": 0.03}),
        cnn_input=_cnn({"normal": 0.92, "overheating": 0.04, "discharge": 0.04}),
        yolo_input=_yolo_normal(),
        save_path=str(save),
    )
    assert out is not None
    data = json.loads(save.read_text(encoding="utf-8"))
    final = data["final_fusion_result"]
    assert final["final_result_en"] == "normal"
    assert final["is_normal"] is True


def test_partial_evidence_yolo_missing(tmp_path: Path):
    """If one source is None, fusion still runs over the remaining valid sources."""
    save = tmp_path / "fusion.json"
    out = transformer_three_source_fusion(
        bert_input=_bert({"normal": 0.9, "fire": 0.1}),
        cnn_input=_cnn({"normal": 0.85, "overheating": 0.15}),
        yolo_input=None,
        save_path=str(save),
    )
    assert out is not None
    data = json.loads(save.read_text(encoding="utf-8"))
    assert data["fusion_basic_info"]["evidence_sources"] == ["bert", "cnn"]
    assert "final_fusion_result" in data


def test_yolo_fire_overrides_normal_majority(tmp_path: Path):
    """Catastrophic safety logic: even if BERT/CNN both say normal, a single
    fire detection from YOLO must not be silently overridden into 'normal'.
    (See `fusion_decision` -- 故障绝对优先判别逻辑)."""
    save = tmp_path / "fusion.json"
    out = transformer_three_source_fusion(
        bert_input=_bert({"normal": 0.95, "fire": 0.05}),
        cnn_input=_cnn({"normal": 0.9, "overheating": 0.1}),
        yolo_input=_yolo_fire(0.95),
        save_path=str(save),
    )
    assert out is not None
    data = json.loads(save.read_text(encoding="utf-8"))
    final = data["final_fusion_result"]
    assert final["is_fault"] is True, (
        f"Fire should not be silently dropped. Got: {final['final_result_cn']}, "
        f"note: {final['decision_note']}"
    )
