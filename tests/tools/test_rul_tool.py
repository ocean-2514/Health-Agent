"""Tests for rul_tool. The physics math comes from the legacy
TransformerRULCalculator and is unchanged — these tests cover the wrapper:
defaulting, defect-driven overrides, Pydantic validation."""
import pytest

from Python.Src.Tools.rul_tool import (
    DGAScores,
    DefectInfo,
    OilScores,
    RULInput,
    RULResult,
    compute_rul,
)


def _baseline_input(**overrides) -> RULInput:
    base = dict(
        oil=OilScores(bdv=2, water=2, acid=1, ift=2),
        dga=DGAScores(H2=2, CH4=2, CO=1, CO2=1, C2H4=1, C2H6=1, C2H2=1),
        furan_level="A",
        future_load=0.8,
        ambient_temp=25.0,
    )
    base.update(overrides)
    return RULInput(**base)


def test_baseline_returns_reasonable_rul():
    out = compute_rul(_baseline_input())
    assert isinstance(out, RULResult)
    assert 0.0 <= out.health_index <= 100.0
    assert out.predicted_rul_years > 0
    assert out.applied_penalty_factor == 1.0
    assert out.forced_override is None


def test_moisture_default_inferred_from_bdv():
    """If moisture is None, it should be derived from oil.bdv. We can't
    inspect the internal value, but we can verify the call doesn't crash
    and produces a sensible result for each bdv tier."""
    for bdv in (1, 2, 3):
        out = compute_rul(_baseline_input(oil=OilScores(bdv=bdv, water=2, acid=1, ift=2)))
        assert out.health_index > 0


def test_fire_defect_forces_zero_rul():
    out = compute_rul(_baseline_input(
        defect_info=DefectInfo(final_result_cn="检测到起火现象", final_confidence=0.85)
    ))
    assert out.predicted_rul_years == 0.0
    assert out.health_index == 10.0
    assert "起火" in (out.forced_override or "")


def test_oil_leak_defect_lowers_penalty():
    baseline = compute_rul(_baseline_input())
    leaked = compute_rul(_baseline_input(
        defect_info=DefectInfo(final_result_cn="发现漏油痕迹", final_confidence=0.7)
    ))
    assert leaked.applied_penalty_factor <= 0.7
    assert leaked.predicted_rul_years <= baseline.predicted_rul_years
    assert "漏油" in (leaked.forced_override or "")


def test_low_confidence_defect_ignored():
    """Defects below their confidence threshold should not trigger overrides."""
    out = compute_rul(_baseline_input(
        defect_info=DefectInfo(final_result_cn="疑似起火", final_confidence=0.4)
    ))
    assert out.forced_override is None
    assert out.predicted_rul_years > 0.0


def test_invalid_furan_level_rejected():
    with pytest.raises(Exception):
        # Pydantic will reject "Z" (pattern is A-E)
        RULInput(
            oil=OilScores(bdv=2, water=2, acid=1, ift=2),
            dga=DGAScores(H2=2, CH4=2, CO=1, CO2=1, C2H4=1, C2H6=1, C2H2=1),
            furan_level="Z",
            future_load=0.8,
            ambient_temp=25.0,
        )


def test_no_llm_call_in_tool():
    """rul_tool must not import LLMService nor call generate_response —
    that's a Phase 1 invariant. Uses AST so docstring mentions don't trigger."""
    import ast
    import Python.Src.Tools.rul_tool as mod

    src = open(mod.__file__, "r", encoding="utf-8").read()
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "LLMService" not in (node.module or ""), (
                f"rul_tool must not import LLMService (line {node.lineno})"
            )
        if isinstance(node, ast.Attribute) and node.attr == "generate_response":
            pytest.fail(f"rul_tool must not call generate_response (line {node.lineno})")
