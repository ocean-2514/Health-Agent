"""Tests for the fusion tool wrapper. Reuses the fusion math validated in
test_evidence_fusion.py — these tests focus on the wrapper contract:
Pydantic typing, file-vs-tempfile handling, and rejection of empty input."""
import json
from pathlib import Path

import pytest

from Python.Src.Tools.fusion_tool import FusionResult, fuse_evidence


def _log_dict(probs):
    return {"fault_prediction_result": {"all_probs_en": probs, "is_fuzzy": False}}


def _oil_dict(probs):
    return {"fault_prediction": {"all_probs": probs, "is_fuzzy": False}}


def _image_dict_normal():
    return {"is_fault": False, "defect_count": 0, "defects": []}


def _image_dict_fire(conf=0.95):
    return {
        "is_fault": True,
        "defect_count": 1,
        "defects": [{"class_name": "fire", "confidence": conf}],
    }


def test_returns_pydantic_fusion_result():
    result = fuse_evidence(
        log_result=_log_dict({"normal": 0.9, "fire": 0.1}),
        oil_result=_oil_dict({"normal": 0.85, "overheating": 0.15}),
        image_result=_image_dict_normal(),
    )
    assert isinstance(result, FusionResult)
    assert result.final_fusion_result.is_normal is True
    assert "bert" in result.evidence_sources


def test_partial_evidence_works():
    result = fuse_evidence(
        log_result=_log_dict({"normal": 0.9, "fire": 0.1}),
        oil_result=_oil_dict({"normal": 0.85}),
        image_result=None,
    )
    assert result.evidence_sources == ["bert", "cnn"]


def test_empty_input_rejected():
    with pytest.raises(ValueError):
        fuse_evidence(None, None, None)


def test_save_path_persists_file(tmp_path: Path):
    save = tmp_path / "audit.json"
    result = fuse_evidence(
        log_result=_log_dict({"fire": 0.95, "normal": 0.05}),
        oil_result=_oil_dict({"overheating": 0.8, "normal": 0.2}),
        image_result=_image_dict_fire(0.92),
        save_path=str(save),
    )
    assert save.exists(), "save_path should keep the JSON for audit"
    persisted = json.loads(save.read_text(encoding="utf-8"))
    assert persisted["final_fusion_result"]["final_result_en"] == result.final_fusion_result.final_result_en


def test_no_save_path_does_not_leave_files(tmp_path: Path, monkeypatch):
    """When save_path is omitted, the temp file should be cleaned up."""
    # Redirect tempdir into tmp_path so we can inspect cleanup behavior
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))

    fuse_evidence(
        log_result=_log_dict({"normal": 0.9, "fire": 0.1}),
        oil_result=_oil_dict({"normal": 0.85}),
    )
    leftover = list(tmp_path.glob("fusion_output*.json"))
    assert leftover == [], f"temp file should be removed, found {leftover}"
