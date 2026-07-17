"""Top-level Tool — the entire transformer-defect-detection platform.

Wraps ``Python.Src.Agents.graph.run_diagnosis`` (the Phase 3-5 LangGraph +
plugin platform) as a single ``Tool`` the supervisor can call. The inner
graph is a deterministic **Workflow**; from the supervisor's view this Tool
is opaque: input = device + parameters; output = indicators + report. The
four-agent collaboration, parallel inference, fusion, RUL and the search
plugin all stay private — and crucially stay *deterministic* (the LLM never
reshapes the inner graph).

Built on top of the platform registry (``build_platform_registry``) so any
locally discovered plugin (e.g. the ``search_agent``) participates
automatically; no additional wiring at the outer layer.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parents[4])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.graph import run_diagnosis
from Python.Src.Agents.loader import build_platform_registry
from Python.Src.Supervisor.session import SessionStore, default_store
from Python.Src.Supervisor.tool import ToolCard


# ---------------------------------------------------------------------------
# IO contracts (Pydantic — JSON Schema auto-derived for the LLM tool def)
# ---------------------------------------------------------------------------

class TransformerDiagnosisInput(BaseModel):
    """Input to a full transformer diagnosis run."""

    equipment_id: str = Field(
        "tr01", description="变压器设备 ID, 例如 'tr01' / 'tr02'."
    )
    substation: str = Field(
        "station1", description="变电站标识 (默认 'station1')."
    )
    raw_input: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "可选覆盖参数, 缺省即用默认评分. 常见键: oil_bdv/oil_water/oil_acid/"
            "oil_ift (1-3), dga_h2/dga_ch4/.../dga_c2h2 (1-6), furan_level (A-E), "
            "future_load (0-1.5), ambient_temp (摄氏度)."
        ),
    )


class TransformerDiagnosisOutput(BaseModel):
    """Structured digest of one diagnosis run."""

    health_index: float = Field(..., description="健康指数 0-100")
    predicted_rul_years: float = Field(..., description="预测剩余寿命 (年)")
    fusion_verdict_cn: str = Field(..., description="三源融合判定的中文故障类别")
    fusion_confidence: float = Field(..., description="融合判定的置信度 0-1")
    dga_risk_score: Optional[float] = Field(None, description="DGA 综合风险评分 0-100")
    primary_threat: Optional[str] = Field(None, description="主要威胁类型")
    forced_override: Optional[str] = Field(
        None, description="若严重缺陷/标准状态强制调整了 RUL/HI, 这里说明原因"
    )
    overall_state: Optional[str] = Field(
        None, description="DL/T 1685 整体状态 (正常/注意/异常/严重); 未做标准评价时为 None"
    )
    dlt_evaluation: Optional[Dict[str, Any]] = Field(
        None, description="DL/T 1685 评价明细 (各部件状态/扣分)"
    )
    final_report: str = Field(..., description="人类可读的完整诊断报告 (markdown)")
    extra_artifacts: Dict[str, Any] = Field(
        default_factory=dict,
        description="平台插件产出的额外 artifact 摘要 (key -> 简要 dict)",
    )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class TransformerDiagnosisTool:
    """Outer-level Tool that runs the inner deterministic Workflow end-to-end."""

    card = ToolCard(
        name="transformer_diagnosis",
        description=(
            "对指定变压器执行一次完整健康诊断: 拉 IoTDB 数据 → BERT/CNN/YOLO "
            "三源缺陷识别 → D-S 证据融合 → 物理 RUL 计算 → LLM 生成报告. "
            "用于: 用户要求'体检/诊断/评估变压器状态/查 RUL'等场景. "
            "调用一次约 30-60 秒; 若仅是聊天/概念问题不要调用."
        ),
        input_model=TransformerDiagnosisInput,
        output_model=TransformerDiagnosisOutput,
    )

    def __init__(self, session_store: SessionStore = default_store) -> None:
        # Build the platform registry once at construction time; the inner
        # graph is recompiled per request (cheap), but plugin discovery and
        # registry validation should not repeat.
        self._registry = build_platform_registry()
        self._store = session_store

    def run(self, **kwargs: Any) -> TransformerDiagnosisOutput:
        inp = TransformerDiagnosisInput(**kwargs)
        state = run_diagnosis(
            equipment_id=inp.equipment_id,
            substation=inp.substation,
            params=inp.raw_input or None,
            registry=self._registry,
        )

        # Surface the most useful indicators flat; bundle the rest into
        # extra_artifacts so the LLM can reference plugin output if relevant.
        extra = {
            key: {
                "producer": art.producer,
                "schema_name": art.schema_name,
                "version": art.version,
                "payload": art.payload,
            }
            for key, art in (state.artifacts or {}).items()
        }

        rul = state.rul_result
        fusion_final = state.fusion_result.final_fusion_result if state.fusion_result else None
        dga = state.dga_analysis

        out = TransformerDiagnosisOutput(
            health_index=float(rul.health_index) if rul else 0.0,
            predicted_rul_years=float(rul.predicted_rul_years) if rul else 0.0,
            fusion_verdict_cn=fusion_final.final_result_cn if fusion_final else "未知",
            fusion_confidence=float(fusion_final.final_confidence) if fusion_final else 0.0,
            dga_risk_score=float(dga.overall_risk_score) if dga else None,
            primary_threat=dga.primary_threat if dga else None,
            forced_override=rul.forced_override if rul else None,
            overall_state=rul.overall_state if rul else None,
            dlt_evaluation=rul.dlt_evaluation if rul else None,
            final_report=state.final_report or "(报告生成失败)",
            extra_artifacts=extra,
        )

        # Persist a structured record so history_lookup can find this run
        # later (possibly from a different chat session).
        try:
            self._store.save_diagnosis_record(
                equipment_id=inp.equipment_id,
                substation=inp.substation,
                health_index=out.health_index,
                predicted_rul_years=out.predicted_rul_years,
                fusion_verdict_cn=out.fusion_verdict_cn,
                fusion_confidence=out.fusion_confidence,
                dga_risk_score=out.dga_risk_score,
                primary_threat=out.primary_threat,
                forced_override=out.forced_override,
                extras={"artifact_keys": list((state.artifacts or {}).keys())},
            )
        except Exception:
            # Persistence failure should not break the user-facing answer.
            pass

        return out
