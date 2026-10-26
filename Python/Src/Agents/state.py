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

Phase 4 adds the ``artifacts`` field — an OPEN namespace. The typed fields
above are the closed core for the four built-in agents; dynamically
loaded plugin / remote agents have no field of their own, so they read
and write ``artifacts[key]`` instead. ``AgentCard.consumes`` / ``produces``
name either a typed field or an artifact key — the router treats both
uniformly (see registry.py). This is what lets an agent be added at
runtime without touching the state schema.
"""
from __future__ import annotations

import operator
import sys
from dataclasses import dataclass
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
# Artifact — one entry in the open namespace
# ---------------------------------------------------------------------------

class Artifact(BaseModel):
    """A typed envelope around a value produced by a plugin / remote agent.

    Built-in agents write their own typed state fields; everything loaded
    at runtime writes ``Artifact`` entries into ``DiagnosisState.artifacts``
    instead. The envelope (producer / schema_name / version) keeps the open
    region self-describing — and maps cleanly onto the A2A ``Artifact`` type
    when an agent is reached over the network.
    """
    key: str = Field(..., description="artifacts 字典里的键")
    producer: str = Field(..., description="产出该 artifact 的 agent 名")
    schema_name: str = Field("raw", description="payload 的逻辑类型名")
    version: int = 1
    payload: Any = Field(..., description="实际数据 (应可 JSON 序列化)")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


def merge_artifacts(
    left: Dict[str, "Artifact"], right: Dict[str, "Artifact"]
) -> Dict[str, "Artifact"]:
    """Reducer for the ``artifacts`` channel: last write wins per key.

    Needed because parallel agents may emit artifacts in the same LangGraph
    superstep; without a reducer LangGraph rejects concurrent writes to a
    shared key.
    """
    merged = dict(left or {})
    merged.update(right or {})
    return merged


# ---------------------------------------------------------------------------
# ArtifactSpec — the typed contract carried in AgentCard.consumes / produces
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArtifactSpec:
    """A schema-aware reference to an artifact slot.

    An ``AgentCard`` lists ``ArtifactSpec`` entries in ``consumes`` / ``produces``
    instead of bare strings whenever it wants the platform to enforce a
    payload contract (vs. matching on key alone). The router uses
    (key, schema_name, version) to decide presence; ``consume(state, spec)``
    raises explicitly if the live artifact violates the contract.

    Mirrors the shape of an A2A skill input / output declaration so the same
    spec can later drive a remote A2A binding without restating the contract.
    """
    key: str
    schema_name: str
    version: int = 1
    description: str = ""


# ---------------------------------------------------------------------------
# Schema contract violations (raised by ``consume``)
# ---------------------------------------------------------------------------

class ArtifactContractError(Exception):
    """Base class for any violation of an artifact's typed contract."""


class MissingArtifact(ArtifactContractError):
    """The expected artifact key is not present in state.artifacts."""


class SchemaMismatch(ArtifactContractError):
    """The artifact exists but its schema_name does not match the contract."""


class SchemaTooOld(ArtifactContractError):
    """The artifact's version is older than the consumer requires."""


def consume(state: "DiagnosisState", spec: ArtifactSpec) -> Any:
    """Read an artifact under a typed contract; raise on any mismatch.

    Agents should use this instead of ``state.artifacts[key]`` whenever they
    declared the input as an ``ArtifactSpec`` — it turns wrong schema /
    missing artifact into an explicit failure right at the read site instead
    of a downstream ``AttributeError`` deep inside the agent's logic.

    The router (``AgentCard.is_runnable``) already skips an agent whose
    inputs do not satisfy the contract, so reaching this function with a
    mismatch usually means a bug — fail loud.
    """
    art = (state.artifacts or {}).get(spec.key)
    if art is None:
        raise MissingArtifact(spec.key)
    if art.schema_name != spec.schema_name:
        raise SchemaMismatch(
            f"artifact {spec.key!r}: expected schema {spec.schema_name!r}, "
            f"got {art.schema_name!r}"
        )
    if art.version < spec.version:
        raise SchemaTooOld(
            f"artifact {spec.key!r}: consumer requires version >= {spec.version}, "
            f"got {art.version}"
        )
    return art.payload


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

    # --- open namespace (Phase 4): plugin / remote agents read & write here ---
    artifacts: Annotated[Dict[str, Artifact], merge_artifacts] = Field(
        default_factory=dict,
        description="动态加载的 agent 的产出物, 按 key 寻址",
    )

    # --- control + communication ---
    next_agent: Optional[str] = Field(
        None, description="Coordinator 写入的下一跳; 'DONE' 表示结束"
    )
    comm_log: Annotated[List[AgentMessage], operator.add] = Field(default_factory=list)
    errors: Annotated[List[str], operator.add] = Field(default_factory=list)

    def snapshot(self) -> Dict[str, Any]:
        """Fully JSON-serialized view — handy for debugging / thesis figures."""
        return self.model_dump(mode="json")
