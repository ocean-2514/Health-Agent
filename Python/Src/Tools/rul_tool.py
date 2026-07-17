"""Remaining-useful-life (RUL) physics tool.

Migrated from ``Python/Src/Agent/LifecycleDeductionAgent.TransformerLifePredictionTool``.
Two changes from the legacy class:

* The LLM call (``diagnosis_summary``) is **removed**. Tools never call the
  LLM directly; the legacy AssessmentService still produces that field for
  API back-compat by calling LLMService after this tool returns.
* The hardcoded ``uncertainty_analysis`` string that overwrote the real
  Monte-Carlo output is **removed**. The MC result from
  ``TransformerRULCalculator.run_monte_carlo_simulation`` is preserved
  verbatim — that was actually a latent bug in the legacy code.

CrewAI ``BaseTool`` inheritance is dropped — pure Python + Pydantic.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.Core.PhysicsModels import TransformerRULCalculator


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class OilScores(BaseModel):
    bdv: int = Field(..., ge=1, le=3, description="击穿电压评分 1-3")
    water: int = Field(..., ge=1, le=3, description="含水量评分 1-3")
    acid: int = Field(..., ge=1, le=3, description="酸值评分 1-3")
    ift: int = Field(..., ge=1, le=3, description="界面张力评分 1-3")


class DGAScores(BaseModel):
    H2: int = Field(..., ge=1, le=6)
    CH4: int = Field(..., ge=1, le=6)
    CO: int = Field(..., ge=1, le=6)
    CO2: int = Field(..., ge=1, le=6)
    C2H4: int = Field(..., ge=1, le=6)
    C2H6: int = Field(..., ge=1, le=6)
    C2H2: int = Field(..., ge=1, le=6)


class DefectInfo(BaseModel):
    """Optional defect-detection summary that biases RUL via penalty / forced
    override (e.g. 'fire' detected → forced RUL = 0)."""
    final_result_cn: str
    final_confidence: float = Field(..., ge=0.0, le=1.0)


class RULInput(BaseModel):
    oil: OilScores
    dga: DGAScores
    furan_level: str = Field(..., pattern="^[A-E]$", description="糠醛等级 A-E")
    future_load: float = Field(..., ge=0.0, le=1.5, description="预测负载率 0.0-1.5")
    ambient_temp: float = Field(..., description="环境温度 °C")
    moisture: Optional[float] = Field(
        None, description="绝缘纸水分 %; None 时按 oil.bdv 推断 (1→1.2, 2→2.2, 其它→3.5)"
    )
    penalty_factor: Optional[float] = Field(
        None, ge=0.5, le=1.0, description="风险系数 0.5-1.0; None 时默认 1.0"
    )
    defect_info: Optional[DefectInfo] = None
    # DL/T 1685-2017 原始状态量测量 (key→原始实测值/劣化程度)。提供时启用标准
    # 扣分制状态评价, 由整体状态驱动 HI/风险系数; 缺省则沿用原有评分路径。
    dlt_measurements: Optional[Dict[str, Any]] = Field(
        None, description="DL/T 1685 状态量测量; 见 Core.rules_dlt1685 的 key"
    )
    voltage_kv: float = Field(220.0, description="电压等级 kV (影响 DL/T 阈值分档)")


class RULResult(BaseModel):
    health_index: float = Field(..., description="健康指数 0-100")
    predicted_rul_years: float = Field(..., description="剩余寿命预测 (年)")
    health_deduction_curve: Optional[Dict[str, Any]] = Field(
        None, description="未来健康度演化曲线"
    )
    uncertainty_analysis: Optional[Dict[str, Any]] = Field(
        None, description="蒙特卡洛不确定度分析"
    )
    applied_penalty_factor: float = Field(..., description="实际生效的风险系数")
    forced_override: Optional[str] = Field(
        None, description="若因严重缺陷/标准状态强制调整了 RUL/HI, 这里说明触发原因"
    )
    overall_state: Optional[str] = Field(
        None, description="DL/T 1685 整体状态 (正常/注意/异常/严重); 未做标准评价时为 None"
    )
    dlt_evaluation: Optional[Dict[str, Any]] = Field(
        None, description="DL/T 1685 评价明细 (各部件状态/扣分); 未做标准评价时为 None"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# DL/T 1685 整体状态 → 风险系数(加速老化系数)。**工程外延, 非标准定义**:
# 状态越差, 老化越快, RUL 越短。
_STATE_PENALTY = {"正常": 1.0, "注意": 0.9, "异常": 0.75, "严重": 0.5}


def compute_rul(input_data: RULInput) -> RULResult:
    """Compute health index and remaining useful life via the physics model.

    评分/寿命调整来源(按“更严重优先”合并):
      1. **DL/T 1685-2017 状态评价**(当提供 ``dlt_measurements`` 时): 扣分制得出整体
         状态, HI 用 ``deduction_to_hi``, 风险系数按状态下调(注意/异常/严重→0.9/0.75/0.5)。
      2. **缺陷检测强制覆盖**(保留): 起火+置信>0.6 → RUL=0/HI=10; 漏油>0.5 → penalty≤0.7;
         异常>0.5 → penalty≤0.8。
    未提供 ``dlt_measurements`` 且无缺陷覆盖时, HI 由物理模型按 oil/dga/furan 计算(原路径)。
    """
    moisture = input_data.moisture
    if moisture is None:
        bdv = input_data.oil.bdv
        moisture = 1.2 if bdv == 1 else 2.2 if bdv == 2 else 3.5

    penalty = input_data.penalty_factor if input_data.penalty_factor is not None else 1.0
    notes: list[str] = []
    forced_hi: Optional[float] = None
    forced_rul: Optional[float] = None

    physics_input: Dict[str, Any] = {
        "oil": input_data.oil.model_dump(),
        "dga": input_data.dga.model_dump(),
        "furan": {"level": input_data.furan_level},
        "future_load": input_data.future_load,
        "ambient_temp": input_data.ambient_temp,
        "moisture": moisture,
        "penalty_factor": penalty,
    }

    # 1) DL/T 1685-2017 标准状态评价 → 驱动 HI / 风险系数
    dlt_eval: Optional[Dict[str, Any]] = None
    overall_state: Optional[str] = None
    if input_data.dlt_measurements:
        from Python.Src.Core.dlt1685 import deduction_to_hi, evaluate
        res = evaluate(input_data.dlt_measurements, input_data.voltage_kv)
        overall_state = res.overall_state
        dlt_eval = res.to_dict()
        hi_state = deduction_to_hi(res)
        forced_hi = hi_state
        penalty = min(penalty, _STATE_PENALTY.get(overall_state, 1.0))
        notes.append(
            f"DL/T 1685 整体状态={overall_state}, HI={hi_state}, 风险系数={penalty}"
        )

    # 2) 缺陷检测强制覆盖(与标准结果按“更严重优先”合并)
    if input_data.defect_info is not None:
        cn = input_data.defect_info.final_result_cn
        conf = input_data.defect_info.final_confidence
        if "起火" in cn and conf > 0.6:
            forced_rul = 0.0
            forced_hi = 10.0 if forced_hi is None else min(forced_hi, 10.0)
            notes.append(f"检测到起火 (置信度 {conf:.2f})，强制 RUL=0 / HI≤10")
        elif "漏油" in cn and conf > 0.5:
            penalty = min(penalty, 0.7)
            notes.append(f"检测到漏油，加速老化系数下调至 {penalty}")
        elif "异常" in cn and conf > 0.5:
            penalty = min(penalty, 0.8)
            notes.append(f"检测到异常，加速老化系数下调至 {penalty}")

    physics_input["penalty_factor"] = penalty
    if forced_hi is not None:
        physics_input["forced_hi"] = forced_hi
    if forced_rul is not None:
        physics_input["forced_rul"] = forced_rul

    raw = TransformerRULCalculator().run_full_analysis(physics_input)

    return RULResult(
        health_index=float(raw.get("health_index", 0.0)),
        predicted_rul_years=float(raw.get("predicted_rul_years", 0.0)),
        health_deduction_curve=raw.get("health_deduction_curve"),
        uncertainty_analysis=raw.get("uncertainty_analysis"),
        applied_penalty_factor=float(raw.get("ai_penalty_factor_applied", penalty)),
        forced_override="; ".join(notes) if notes else None,
        overall_state=overall_state,
        dlt_evaluation=dlt_eval,
    )


if __name__ == "__main__":
    sample = RULInput(
        oil=OilScores(bdv=2, water=2, acid=1, ift=2),
        dga=DGAScores(H2=2, CH4=2, CO=1, CO2=1, C2H4=1, C2H6=1, C2H2=1),
        furan_level="A",
        future_load=0.8,
        ambient_temp=25.0,
    )
    out = compute_rul(sample)
    print(f"HI={out.health_index}  RUL={out.predicted_rul_years}y  penalty={out.applied_penalty_factor}")
