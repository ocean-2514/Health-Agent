"""Tests for the DGA analysis tool. Builds synthetic trends inline so the
tests do not depend on the IoTDB mock generator's specific seeding."""
from __future__ import annotations

from typing import List

import pytest

from Python.Src.Tools.dga_tool import (
    DGAAnalysisResult,
    analyze_dga_trends,
    render_expert_advice,
)
from Python.Src.Tools.iotdb_tool import SensorTrend


def _flat_trend(gas: str, value: float, n: int = 48) -> SensorTrend:
    """A flat n-point series (n must be ≥ 24 to enter the residual calc)."""
    return SensorTrend(sensor=gas, timestamps=[f"t{i}" for i in range(n)], values=[value] * n)


def _spiking_trend(gas: str, baseline: float, recent: float, n: int = 48) -> SensorTrend:
    """First n-24 points at baseline, last 24 at recent (simulates a spike)."""
    vals: List[float] = [baseline] * (n - 24) + [recent] * 24
    return SensorTrend(sensor=gas, timestamps=[f"t{i}" for i in range(n)], values=vals)


def test_flat_trends_yield_low_risk():
    trends = {
        gas: _flat_trend(gas, 10.0)
        for gas in ["H2", "CH4", "C2H6", "C2H4", "C2H2", "CO", "CO2"]
    }
    result = analyze_dga_trends(trends)
    assert isinstance(result, DGAAnalysisResult)
    assert result.overall_risk_score < 30, "flat trends should not trigger high risk"
    assert result.primary_threat == "无显著威胁"


def test_c2h2_spike_triggers_discharge():
    trends = {
        "H2": _spiking_trend("H2", baseline=10, recent=80),
        "C2H2": _spiking_trend("C2H2", baseline=0.1, recent=2.0),
        "CH4": _flat_trend("CH4", 8),
        "C2H4": _flat_trend("C2H4", 2),
    }
    result = analyze_dga_trends(trends)
    assert result.overall_risk_score > 30
    assert "放电" in result.primary_threat


def test_c2h4_spike_triggers_thermal():
    trends = {
        "CH4": _spiking_trend("CH4", baseline=8, recent=40),
        "C2H4": _spiking_trend("C2H4", baseline=2, recent=20),
        "H2": _flat_trend("H2", 10),
        "C2H2": _flat_trend("C2H2", 0.1),
    }
    result = analyze_dga_trends(trends)
    assert result.overall_risk_score > 20
    assert "过热" in result.primary_threat


def test_short_series_skipped_safely():
    """Series with <24 samples must not crash the residual calc."""
    trends = {
        "H2": SensorTrend(sensor="H2", timestamps=["t1", "t2"], values=[10.0, 12.0]),
        "CH4": _flat_trend("CH4", 8),
    }
    result = analyze_dga_trends(trends)
    assert result.fault_risk_curve.x and result.fault_risk_curve.y


def test_risk_curve_monotonic_nondecreasing():
    """Risk curve over future years should not decrease (it's a degradation
    projection, not a recovery model)."""
    trends = {gas: _flat_trend(gas, 10.0) for gas in ["H2", "CH4", "C2H4"]}
    result = analyze_dga_trends(trends)
    y = result.fault_risk_curve.y
    assert all(y[i] <= y[i + 1] for i in range(len(y) - 1))


def test_advice_severity_levels():
    low = DGAAnalysisResult(
        overall_risk_score=10.0, primary_threat="无显著威胁",
        breakdown=[], fault_risk_curve={"x": [2026], "y": [10.0]},
        algorithm_insight="",
    )
    mid = low.model_copy(update={"overall_risk_score": 45.0, "primary_threat": "过热故障"})
    high = low.model_copy(update={"overall_risk_score": 80.0, "primary_threat": "放电故障"})

    assert "常规巡检" in render_expert_advice(low)
    assert "缩短" in render_expert_advice(mid)
    assert "重要警告" in render_expert_advice(high)
