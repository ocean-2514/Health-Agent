"""DGA (dissolved gas analysis) trend analysis tool.

Migrated from ``Python/Src/Agent/FaultExpertAgent.FaultAnalyticEngine``. The
core algorithm is preserved verbatim — residual scoring + linkage detection
inspired by iTransformer / CATCH — and packaged with Pydantic types so the
MCP server can introspect inputs and outputs.

This tool does **not** call the LLM. The legacy `get_detailed_fault_analysis`
and `get_expert_advice` are pure templating and are kept here as
`render_*` helpers (a caller can choose to surface them or replace them
with an LLM-generated narrative).
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.Tools.iotdb_tool import SensorTrend


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class FaultProbability(BaseModel):
    type: str = Field(..., description="故障类型 (中文)")
    probability: float = Field(..., ge=0.0, le=100.0, description="百分制概率")


class RiskCurve(BaseModel):
    x: List[int] = Field(..., description="时间轴 (年份)")
    y: List[float] = Field(..., description="对应风险评分 (0-100)")


class DGAAnalysisResult(BaseModel):
    overall_risk_score: float = Field(..., ge=0.0, le=100.0)
    primary_threat: str = Field(..., description="主要威胁类型, 或 '无显著威胁'")
    breakdown: List[FaultProbability] = Field(..., description="按概率降序排列的故障分项")
    fault_risk_curve: RiskCurve = Field(..., description="未来 0-8 年的风险演化曲线")
    algorithm_insight: str = Field(..., description="算法层面的简短说明")


# ---------------------------------------------------------------------------
# Core analysis (deterministic, no LLM)
# ---------------------------------------------------------------------------

def analyze_dga_trends(trends: Dict[str, SensorTrend]) -> DGAAnalysisResult:
    """Compute fault probability and risk curve from DGA gas histories.

    Algorithm (preserved from legacy FaultAnalyticEngine):
      1. For each gas, compute residual = (mean of last 24 samples - mean of
         earlier history) / (mean of earlier history + 0.1).
      2. Linkage scores blend gases known to co-vary in physical fault modes:
         - discharge linkage = 0.5*H2 + 2.0*C2H2
         - thermal linkage   = 0.8*CH4 + 1.2*C2H4
      3. Base risk starts at 5.0, lifted by the linkage scores.
      4. Risk curve over the next 8 years grows as base + y^1.8 * acceleration.

    Requires gases with at least 24 samples; gases below that are ignored
    in the residual step (matches legacy behavior).
    """
    residual_scores: Dict[str, float] = {}
    for gas, trend in trends.items():
        vals = trend.values
        if len(vals) < 24:
            continue
        hist_mean = float(np.mean(vals[:-24]))
        recent_mean = float(np.mean(vals[-24:]))
        residual_scores[gas] = (recent_mean - hist_mean) / (hist_mean + 0.1)

    linkage_discharge = residual_scores.get("H2", 0.0) * 0.5 + residual_scores.get("C2H2", 0.0) * 2.0
    linkage_thermal = residual_scores.get("CH4", 0.0) * 0.8 + residual_scores.get("C2H4", 0.0) * 1.2

    base_prob = 5.0
    if linkage_discharge > 0.5:
        base_prob += linkage_discharge * 30
    if linkage_thermal > 0.3:
        base_prob += linkage_thermal * 20

    fault_breakdown = [
        FaultProbability(type="过热故障", probability=min(95.0, round(linkage_thermal * 40 + 5, 2))),
        FaultProbability(type="放电故障", probability=min(95.0, round(linkage_discharge * 60 + 2, 2))),
    ]
    fault_breakdown.sort(key=lambda x: x.probability, reverse=True)

    now_year = datetime.datetime.now().year
    years_offsets = list(range(0, 9))
    real_years = [now_year + y for y in years_offsets]
    acceleration = 1.0 + (base_prob / 100.0)
    risk_trend = [
        min(99.0, round(base_prob + (y ** 1.8) * acceleration, 2))
        for y in years_offsets
    ]

    primary = fault_breakdown[0].type if base_prob > 20 else "无显著威胁"

    return DGAAnalysisResult(
        overall_risk_score=min(99.0, round(base_prob, 2)),
        primary_threat=primary,
        breakdown=fault_breakdown,
        fault_risk_curve=RiskCurve(x=real_years, y=risk_trend),
        algorithm_insight=(
            "基于 iTransformer 维度反转捕捉的长期趋势，"
            "结合 CATCH 频域补丁识别的多通道联动异常。"
        ),
    )


# ---------------------------------------------------------------------------
# Markdown / text rendering helpers (pure, deterministic, no LLM)
# ---------------------------------------------------------------------------

def render_detailed_analysis(
    result: DGAAnalysisResult, trends: Dict[str, SensorTrend]
) -> str:
    """Format a markdown narrative from a DGA analysis. Optional helper."""
    score = result.overall_risk_score
    threat = result.primary_threat
    severity = "高风险" if score > 60 else "中等风险" if score > 30 else "低风险监测"

    lines = [
        "### 变压器故障深度机理分析",
        "",
        f"**1. 综合风险研判**: 当前设备综合故障风险评分为 **{score}%**, 处于**{severity}**状态。",
        "",
        f"**2. 核心威胁识别**: 主要故障特征指向为 **{threat}**。",
    ]
    if "过热" in threat:
        lines.append(" 主要由甲烷、乙烯比例上升驱动，可能存在铁芯多点接地或绕组局部温升过高。")
    elif "放电" in threat:
        lines.append(" 主要由氢气和乙炔异常波动驱动，可能存在油中电弧放电或绕组绝缘局部击穿风险。")
    else:
        lines.append(" 各项特征指标基本平稳，未见明显发展性故障迹象。")

    lines += ["", "**3. 联动趋势推演**: "]
    for gas, trend in trends.items():
        vals = trend.values
        if not vals:
            continue
        if abs(vals[-1] - vals[0]) / max(vals[0], 1e-9) < 0.1:
            direction = "平稳"
        else:
            direction = "上升" if vals[-1] > vals[0] else "下降"
        lines.append(f"- **{gas}**: 过去 7 天呈现{direction}态势。")

    return "\n".join(lines)


def render_expert_advice(result: DGAAnalysisResult) -> str:
    """Short maintenance recommendation from the risk score."""
    score = result.overall_risk_score
    threat = result.primary_threat
    if score < 30:
        return "设备状态平稳。建议维持常规巡检频率（每季度一次油样分析）。"
    if score < 60:
        return f"检测到潜伏性 {threat} 趋势。建议缩短取油周期至每月一次，并密切监视。"
    return f"【重要警告】系统预测存在严重 {threat} 风险！建议立即进行带电检测。"


if __name__ == "__main__":
    from Python.Src.Tools.iotdb_tool import IotDBClient

    client = IotDBClient(mode="mock")
    trends = client.get_all_dga_trends(equipment_id="tr01", days=7)
    result = analyze_dga_trends(trends)
    print(f"Risk: {result.overall_risk_score}  Threat: {result.primary_threat}")
    print(render_expert_advice(result))
