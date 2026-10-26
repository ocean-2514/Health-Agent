"""Three-source D-S Murphy evidence fusion tool.

Thin wrapper over `Python.Src.Core.EvidenceFusion.transformer_three_source_fusion`.

The legacy fusion function is *path-oriented* — it always writes a JSON file
and returns the file path. This wrapper hides that detail: callers pass in
Pydantic inference results (or raw dicts), the tool runs fusion against a
temp file, parses the JSON, and returns a typed `FusionResult`. An optional
`save_path` keeps the file artifact around for debugging or audit.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.Core.EvidenceFusion import transformer_three_source_fusion
from Python.Src.Tools.inference_tool import (
    ImageInferenceResult,
    LogInferenceResult,
    OilInferenceResult,
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class FinalFusionDecision(BaseModel):
    """The high-level outcome of a fusion run — what most callers actually need."""
    final_result_en: str = Field(..., description="英文故障类别 (含 normal)")
    final_result_cn: str = Field(..., description="中文故障类别")
    final_confidence: float = Field(..., ge=0.0, le=1.0)
    is_definite: bool = Field(..., description="证据足够明确, 可作为决策依据")
    is_normal: bool
    is_fault: bool
    unknown_mass: float = Field(..., ge=0.0, le=1.0, description="不确定度 mass(Θ)")
    decision_note: str = Field(..., description="决策说明 / 警告 / 冲突标记")
    warnings: List[str] = Field(default_factory=list, description="多重风险预警的故障类别列表")
    all_mass_cn: Dict[str, float] = Field(
        default_factory=dict, description="各类别融合后的 mass (中文键)"
    )


class FusionResult(BaseModel):
    """Wrap the full legacy fusion JSON, exposing the most-used fields up top."""
    final_fusion_result: FinalFusionDecision
    evidence_sources: List[str] = Field(..., description="参与融合的有效模型名")
    fused_bpa: Dict[str, float] = Field(..., description="融合后的 BPA, 含 '未知(Θ)' 键")
    raw: Dict[str, Any] = Field(
        ..., description="完整的 legacy 融合结构, 供需要溯源的调用方使用"
    )


# ---------------------------------------------------------------------------
# Adapters: convert tool inputs to the dict shape EvidenceFusion expects
# ---------------------------------------------------------------------------

LogInput = Optional[Union[LogInferenceResult, Dict[str, Any]]]
OilInput = Optional[Union[OilInferenceResult, Dict[str, Any]]]
ImageInput = Optional[Union[ImageInferenceResult, Dict[str, Any]]]


def _to_dict(value: Optional[Union[BaseModel, Dict]]) -> Optional[Dict]:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump()
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fuse_evidence(
    log_result: LogInput = None,
    oil_result: OilInput = None,
    image_result: ImageInput = None,
    *,
    conf_threshold: float = 0.5,
    unknown_threshold: float = 0.3,
    save_path: Optional[str] = None,
) -> FusionResult:
    """Fuse 1-3 evidence sources via D-S Murphy and return a typed result.

    All three inputs are optional — pass ``None`` for a missing source and
    fusion runs over whichever sources are present (legacy behavior).

    If ``save_path`` is provided the underlying JSON is also written there
    for audit / UI consumption; otherwise a temp file is used and removed.
    """
    bert = _to_dict(log_result)
    cnn = _to_dict(oil_result)
    yolo = _to_dict(image_result)

    if bert is None and cnn is None and yolo is None:
        raise ValueError("fuse_evidence: at least one of log/oil/image must be provided")

    cleanup = save_path is None
    target_path = save_path or os.path.join(tempfile.gettempdir(), "fusion_output.json")

    out_path = transformer_three_source_fusion(
        bert_input=bert,
        cnn_input=cnn,
        yolo_input=yolo,
        save_path=target_path,
        conf_thresh=conf_threshold,
        unknown_thresh=unknown_threshold,
    )
    if out_path is None or not os.path.exists(out_path):
        raise RuntimeError("fuse_evidence: fusion produced no output (all sources invalid?)")

    try:
        with open(out_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    finally:
        if cleanup:
            try:
                os.remove(out_path)
            except OSError:
                pass

    final = raw["final_fusion_result"]
    return FusionResult(
        final_fusion_result=FinalFusionDecision(
            final_result_en=final["final_result_en"],
            final_result_cn=final["final_result_cn"],
            final_confidence=float(final["final_confidence"]),
            is_definite=bool(final["is_definite"]),
            is_normal=bool(final["is_normal"]),
            is_fault=bool(final["is_fault"]),
            unknown_mass=float(final["unknown_mass"]),
            decision_note=str(final["decision_note"]),
            warnings=list(final.get("warnings", [])),
            all_mass_cn=dict(final.get("all_mass_cn", {})),
        ),
        evidence_sources=list(raw["fusion_basic_info"]["evidence_sources"]),
        fused_bpa=dict(raw["bpa_info"]["fused_bpa"]),
        raw=raw,
    )


if __name__ == "__main__":
    # Smoke test using inline dicts in the legacy shape
    log = {"fault_prediction_result": {"all_probs_en": {"fire": 0.9, "normal": 0.1}, "is_fuzzy": False}}
    oil = {"fault_prediction": {"all_probs": {"overheating": 0.8, "normal": 0.2}, "is_fuzzy": False}}
    image = {"is_fault": True, "defect_count": 1, "defects": [{"class_name": "fire", "confidence": 0.95}]}

    result = fuse_evidence(log, oil, image)
    print("Final:", result.final_fusion_result.final_result_cn)
    print("Confidence:", result.final_fusion_result.final_confidence)
    print("Sources:", result.evidence_sources)
