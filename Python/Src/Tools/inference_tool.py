"""ML inference tool — thin wrapper over the legacy InferenceService.

Provides Pydantic-typed entry points for the three real fine-tuned models:

* BERT log classifier (`infer_log`)
* CNN oil-chromatography classifier (`infer_oil`)
* YOLO image defect detector (`infer_image`)

InferenceService itself already implements lazy model loading and a
deterministic fallback path when weights are missing, so this module
just adapts dict outputs into Pydantic models for the MCP layer.

InferenceService is imported lazily because it pulls in torch /
ultralytics — we don't want to pay that import cost at module-load time.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)


# ---------------------------------------------------------------------------
# Pydantic result schemas
# ---------------------------------------------------------------------------

class LogPrediction(BaseModel):
    predicted_fault: str = Field(..., description="英文故障类别")
    predicted_cn: str = Field(..., description="中文故障类别")
    confidence: float = Field(..., ge=0.0, le=1.0)
    all_probs_en: Dict[str, float] = Field(default_factory=dict)
    is_fuzzy: bool = False


class LogInferenceResult(BaseModel):
    fault_prediction_result: LogPrediction
    is_realtime: bool = Field(..., description="True 表示走的真实 BERT 模型, False 表示降级")
    error: Optional[str] = None


class OilPrediction(BaseModel):
    predicted_fault: str
    predicted_fault_cn: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_normal: bool
    all_probs: Dict[str, float] = Field(default_factory=dict)


class OilInferenceResult(BaseModel):
    fault_prediction: OilPrediction
    is_realtime: bool
    error: Optional[str] = None


class ImageDefect(BaseModel):
    class_id: int
    class_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class ImageInferenceResult(BaseModel):
    defect_count: int = Field(..., ge=0)
    defects: List[ImageDefect] = Field(default_factory=list)
    is_fault: bool
    is_realtime: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Singleton accessor (avoid re-loading model weights on every call)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_service():
    from Python.Src.Utils.InferenceService import InferenceService
    return InferenceService()


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

def infer_log_text(text: str) -> LogInferenceResult:
    """Run BERT classification on a free-text inspection log."""
    raw = _get_service().infer_log(text)
    return LogInferenceResult.model_validate(raw)


def infer_oil_chromatogram(values: List[float]) -> OilInferenceResult:
    """Run CNN classification on a 7-dim DGA reading.

    Expected order: [H2, CH4, C2H6, C2H4, C2H2, CO, CO2].
    """
    raw = _get_service().infer_oil(values)
    return OilInferenceResult.model_validate(raw)


def infer_image(image_path: str) -> ImageInferenceResult:
    """Run YOLO defect detection on a transformer image file."""
    raw = _get_service().infer_image(image_path)
    return ImageInferenceResult.model_validate(raw)


if __name__ == "__main__":
    print("Log:", infer_log_text("变压器套管温度持续升高，疑似过热").model_dump())
    print("Oil:", infer_oil_chromatogram([350.0, 40.0, 15.0, 30.0, 5.0, 200.0, 700.0]).model_dump())
