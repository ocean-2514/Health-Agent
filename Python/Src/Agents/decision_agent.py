"""Decision Agent — physical RUL + LLM lifecycle narrative + final report.

Consumes the fused defect verdict and the scoring trends, runs the physics
RUL model (biased by any detected defect), then asks the LLM for a
lifecycle narrative. The LLM is non-critical: a degraded response is
detected via ``is_fallback`` and replaced with a deterministic summary, and
the degradation is recorded in ``state.errors``.
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.registry import AgentCard
from Python.Src.Agents.state import DiagnosisState, make_message
from Python.Src.Tools.dga_tool import render_expert_advice
from Python.Src.Tools.llm_tool import get_llm, is_fallback, render_rul_prompt
from Python.Src.Tools.rul_tool import (
    DGAScores,
    DefectInfo,
    OilScores,
    RULInput,
    RULResult,
    compute_rul,
)

AGENT_NAME = "decision"

DECISION_CARD = AgentCard(
    name=AGENT_NAME,
    description="物理 RUL 计算 + LLM 生命周期推演 + 汇总最终诊断报告",
    skills=["rul_physics", "llm_narrative", "report_synthesis"],
    consumes=["fusion_result", "scoring_trends"],
    produces=["rul_result", "final_report"],
)


def _build_rul_input(state: DiagnosisState) -> RULInput:
    """Assemble the physics-model input from raw params + fused defect."""
    p = state.raw_input
    defect_info = None
    if state.fusion_result is not None:
        final = state.fusion_result.final_fusion_result
        if final.final_result_cn:
            defect_info = DefectInfo(
                final_result_cn=final.final_result_cn,
                final_confidence=final.final_confidence,
            )
    return RULInput(
        oil=OilScores(
            bdv=p.get("oil_bdv", 2), water=p.get("oil_water", 2),
            acid=p.get("oil_acid", 1), ift=p.get("oil_ift", 2),
        ),
        dga=DGAScores(
            H2=p.get("dga_h2", 2), CH4=p.get("dga_ch4", 2),
            CO=p.get("dga_co", 1), CO2=p.get("dga_co2", 1),
            C2H4=p.get("dga_c2h4", 1), C2H6=p.get("dga_c2h6", 1),
            C2H2=p.get("dga_c2h2", 1),
        ),
        furan_level=p.get("furan_level", "A"),
        future_load=p.get("future_load", 0.8),
        ambient_temp=p.get("ambient_temp", 25.0),
        moisture=p.get("moisture"),
        penalty_factor=p.get("penalty_factor"),
        defect_info=defect_info,
        # DL/T 1685 原始状态量测量 (可选); 提供时启用标准扣分制评价驱动 HI/RUL。
        dlt_measurements=p.get("dlt_measurements"),
        voltage_kv=p.get("voltage_kv", 220.0),
    )


def _render_report(state: DiagnosisState, rul: RULResult, narrative: str) -> str:
    """Synthesize the human-readable final diagnosis report."""
    lines = [f"# {state.equipment_id} 变压器健康诊断报告", ""]

    if state.fusion_result is not None:
        f = state.fusion_result.final_fusion_result
        lines.append(f"- 缺陷识别: {f.final_result_cn} (置信度 {f.final_confidence:.2f})")
    if state.dga_analysis is not None:
        d = state.dga_analysis
        lines.append(f"- DGA 风险评分: {d.overall_risk_score} / 主要威胁: {d.primary_threat}")
    lines.append(f"- 健康指数 (HI): {rul.health_index}")
    lines.append(f"- 预测剩余寿命 (RUL): {rul.predicted_rul_years} 年")
    if rul.forced_override:
        lines.append(f"- ⚠ {rul.forced_override}")
    if state.dga_analysis is not None:
        lines.append(f"- 维护建议: {render_expert_advice(state.dga_analysis)}")

    lines += ["", "## 生命周期推演", narrative]
    return "\n".join(lines)


def decision_node(state: DiagnosisState) -> dict:
    """Decision Agent graph node: RUL → LLM narrative → final report."""
    rul = compute_rul(_build_rul_input(state))

    defect_cn = None
    if state.fusion_result is not None:
        defect_cn = state.fusion_result.final_fusion_result.final_result_cn

    prompt = render_rul_prompt(
        health_index=rul.health_index,
        predicted_rul_years=rul.predicted_rul_years,
        physics_input={
            "future_load": state.raw_input.get("future_load", 0.8),
            "ambient_temp": state.raw_input.get("ambient_temp", 25.0),
            "applied_penalty_factor": rul.applied_penalty_factor,
        },
        defect_cn=defect_cn,
    )
    narrative = get_llm().generate_response(prompt)
    llm_ok = not is_fallback(narrative)
    if not llm_ok:
        narrative = (
            f"健康指数 {rul.health_index}, 预测剩余寿命 {rul.predicted_rul_years} 年。"
            "(LLM 服务暂不可用, 当前为物理模型推演结果。)"
        )

    report = _render_report(state, rul, narrative)
    errors = [] if llm_ok else ["decision: LLM narrative degraded to fallback"]

    msg = make_message(
        sender=AGENT_NAME, receiver="coordinator", intent="result",
        summary=(
            f"HI={rul.health_index}, RUL={rul.predicted_rul_years}年, 诊断报告已生成"
        ),
    )
    return {
        "rul_result": rul,
        "final_report": report,
        "comm_log": [msg],
        "errors": errors,
    }
