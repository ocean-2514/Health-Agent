"""Tests for inference_tool. These exercise the InferenceService fallback
path so they pass even when the bysj/ ML weights are unreachable."""
from Python.Src.Tools.inference_tool import (
    ImageInferenceResult,
    LogInferenceResult,
    OilInferenceResult,
    infer_image,
    infer_log_text,
    infer_oil_chromatogram,
)


def test_log_fallback_detects_fire_keyword():
    result = infer_log_text("变压器起火，温度急剧上升")
    assert isinstance(result, LogInferenceResult)
    assert result.fault_prediction_result.predicted_cn == "起火"
    assert result.fault_prediction_result.confidence > 0.9


def test_log_fallback_detects_normal():
    result = infer_log_text("设备运行平稳")
    assert result.fault_prediction_result.predicted_fault == "normal"


def test_oil_fallback_high_h2_flags_overheating():
    # H2 > 150 triggers fallback's "overheating" heuristic
    result = infer_oil_chromatogram([350.0, 40.0, 15.0, 30.0, 5.0, 200.0, 700.0])
    assert isinstance(result, OilInferenceResult)
    assert result.fault_prediction.predicted_fault == "overheating"
    assert result.fault_prediction.is_normal is False


def test_oil_fallback_low_values_normal():
    result = infer_oil_chromatogram([10.0, 5.0, 3.0, 1.0, 0.05, 100.0, 500.0])
    assert result.fault_prediction.is_normal is True


def test_image_fallback_returns_valid_schema_for_unknown_path():
    result = infer_image("not_a_real_path.jpg")
    assert isinstance(result, ImageInferenceResult)
    assert result.is_realtime is False
    # No "fire" / "leak" in path → no defects in fallback heuristic
    assert result.defect_count == 0
