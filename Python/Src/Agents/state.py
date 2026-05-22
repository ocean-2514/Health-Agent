"""Shared blackboard state for the multi-agent diagnosis graph.

The entire multi-agent collaboration communicates through ONE typed
object — ``DiagnosisState``. No agent calls another agent directly: each
agent reads the fields it needs and writes the fields it produces. The
graph edges (graph.py) define data flow; the Coordinator's routing
decision defines control flow.

``comm_log`` is NOT a data channel — data flows through the typed fields.
It is an append-only audit trail of inter-agent messages, kept for
explainability (it can be rendered as a sequence diagram). Because the
three inference nodes run in parallel and all append to it, the field
carries an ``operator.add`` reducer so LangGraph concatenates concurrent
writes instead of rejecting them. ``errors`` is reduced the same way.
"""
from __future__ import annotations

import operator
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Tools.dga_tool import DGAAnalysisResult
from Python.Src.Tools.fusion_tool import FusionResult
from Python.Src.Tools.inference_tool import (
    ImageInferenceResult,
    LogInferenceResult,
    OilInferenceResult,
)
from Python.Src.Tools.iotdb_tool import SensorTrend
from Python.Src.Tools.rul_tool import RULResult


# ---------------------------------------------------------------------------
# Inter-agent message (audit trail entry)
# ---------------------------------------------------------------------------

class AgentMessage(BaseModel):
    """One entry in the inter-agent communication audit trail.

    Deliberately shaped close to an A2A ``Message`` so that, if an agent is
    ever moved out-of-process, the trace maps onto the protocol with no
    redesign.
    """
    sender: str
    receiver: str = "broadcast"
    intent: str = Field(..., description="request | result | route | escalate | error")
    summary: str = Field(..., description="人类可读的一句话")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


def make_message(
    sender: str,
    intent: str,
    summary: str,
    receiver: str = "broadcast",
    confidence: Optional[float] = None,
) -> AgentMessage:
    """Terse constructor so agent nodes stay readable."""
    return AgentMessage(
        sender=sender, receiver=receiver, intent=intent,
        summary=summary, confidence=confidence,
    )


# ---------------------------------------------------------------------------
# The shared blackboard
# ---------------------------------------------------------------------------

class DiagnosisState(BaseModel):
    """The single typed object every agent reads from and writes to."""

    # --- input ---
    equipment_id: str = "tr01"
    substation: str = "station1"
    raw_input: Dict[str, Any] = Field(
        default_factory=dict, description="健康评估入参 (oil_*/dga_*/furan_level...)"
    )

    # --- Data Agent output ---
    scoring_trends: Optional[Dict[str, SensorTrend]] = None
    log_text: Optional[str] = None
    oil_values: Optional[List[float]] = None
    image_path: Optional[str] = None

    # --- Diagnosis Agent output ---
    bert_result: Optional[LogInferenceResult] = None
    cnn_result: Optional[OilInferenceResult] = None
    yolo_result: Optional[ImageInferenceResult] = None
    fusion_result: Optional[FusionResult] = None
    dga_analysis: Optional[DGAAnalysisResult] = None

    # --- Decision Agent output ---
    rul_result: Optional[RULResult] = None
    final_report: Optional[str] = None

    # --- control + communication ---
    next_agent: Optional[str] = Field(
        None, description="Coordinator 写入的下一跳; 'DONE' 表示结束"
    )
    comm_log: Annotated[List[AgentMessage], operator.add] = Field(default_factory=list)
    errors: Annotated[List[str], operator.add] = Field(default_factory=list)

    def snapshot(self) -> Dict[str, Any]:
        """Fully JSON-serialized view — handy for debugging / thesis figures."""
        return self.model_dump(mode="json")
