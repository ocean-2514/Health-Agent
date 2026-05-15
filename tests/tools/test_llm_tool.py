"""Tests for llm_tool helpers. The actual LLM call goes through Ollama
which we cannot rely on in CI, so we verify the singleton + fallback
detection + prompt template stability without making network calls."""
from Python.Src.Tools.llm_tool import (
    get_llm,
    is_fallback,
    render_defect_prompt,
    render_rul_prompt,
)
from Python.Src.Utils.LLMService import LLMService


def test_get_llm_returns_singleton():
    a = get_llm()
    b = get_llm()
    assert a is b
    assert isinstance(a, LLMService)


def test_is_fallback_detects_prefix():
    assert is_fallback(f"{LLMService.FALLBACK_PREFIX} something failed") is True
    assert is_fallback("正常的 LLM 输出") is False


def test_is_fallback_handles_none_and_empty():
    assert is_fallback(None) is True
    assert is_fallback("") is True


def test_render_defect_prompt_includes_inputs():
    p = render_defect_prompt("起火", 0.95)
    assert "起火" in p
    assert "0.95" in p
    assert "现状评估" in p


def test_render_rul_prompt_includes_metrics_and_defect():
    p = render_rul_prompt(
        health_index=70.5,
        predicted_rul_years=12.3,
        physics_input={"future_load": 0.9},
        defect_cn="漏油",
    )
    assert "70.5" in p
    assert "12.3" in p
    assert "漏油" in p
    assert "future_load" in p


def test_render_rul_prompt_default_no_defect():
    p = render_rul_prompt(80.0, 20.0, {"future_load": 0.5})
    assert "未检测到明显缺陷" in p
