"""Integration tests for the Phase 3 multi-agent diagnosis graph.

Covers: graph compilation, the registry-driven rule router (including the
runtime-extensibility hook), the Data Agent node in isolation, and a full
end-to-end run asserting the shared blackboard, the parallel inference leg
and the comm_log audit trail.
"""
import json

import pytest

from Python.Src.Agents.coordinator import DONE, decide_next_agent
from Python.Src.Agents.data_agent import DATA_CARD, data_node
from Python.Src.Agents.decision_agent import DECISION_CARD
from Python.Src.Agents.diagnosis_agent import DIAGNOSIS_CARD
from Python.Src.Agents.graph import build_default_registry, build_graph, run_diagnosis
from Python.Src.Agents.registry import AgentCard
from Python.Src.Agents.state import DiagnosisState


# ---------------------------------------------------------------------------
# Shared end-to-end run (expensive: loads ML models + calls the LLM once)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def final_state() -> DiagnosisState:
    return run_diagnosis("tr01")


def _state_at(stage: str) -> DiagnosisState:
    """Build a DiagnosisState frozen at a given pipeline stage (sentinels only)."""
    fields = dict(equipment_id="tr01")
    if stage != "start":
        fields.update(scoring_trends={}, log_text="x", oil_values=[1.0], image_path="x")
    if stage in ("diagnosis_done", "decision_done"):
        fields.update(fusion_result=object(), dga_analysis=object())
    if stage == "decision_done":
        fields.update(rul_result=object(), final_report="x")
    return DiagnosisState.model_construct(**fields)


# ------------------------------------------------------------------ structure

def test_graph_compiles():
    assert build_graph() is not None


def test_default_registry_has_three_agents():
    reg = build_default_registry()
    assert len(reg) == 3
    assert reg.names() == ["data", "diagnosis", "decision"]


def test_agent_card_runnable_and_satisfied():
    empty = DiagnosisState()
    assert DATA_CARD.is_runnable(empty)          # no consumes → always runnable
    assert not DATA_CARD.is_satisfied(empty)     # produces still missing
    assert not DIAGNOSIS_CARD.is_runnable(empty) # needs the Data Agent outputs
    assert not DECISION_CARD.is_runnable(empty)


# ----------------------------------------------------------------- routing

def test_decide_next_agent_progression():
    reg = build_default_registry()
    assert decide_next_agent(_state_at("start"), reg) == "data"
    assert decide_next_agent(_state_at("data_done"), reg) == "diagnosis"
    assert decide_next_agent(_state_at("diagnosis_done"), reg) == "decision"
    assert decide_next_agent(_state_at("decision_done"), reg) == DONE


def test_registry_is_runtime_extensible():
    """Forward-compat hook: registering a new agent changes routing with no
    change to the Coordinator — the basis for a future dynamic platform."""
    reg = build_default_registry()
    reg.register(AgentCard(
        name="searcher",
        description="动态加载的缺陷知识搜索 agent (示例)",
        consumes=["final_report"],
        produces=["search_notes"],
    ))
    assert len(reg) == 4
    # Pipeline is otherwise done; the newly registered agent is now next.
    assert decide_next_agent(_state_at("decision_done"), reg) == "searcher"


# ------------------------------------------------------------------ data node

def test_data_node_produces_all_inputs():
    out = data_node(DiagnosisState(equipment_id="tr01"))
    assert out["scoring_trends"]
    assert isinstance(out["oil_values"], list) and len(out["oil_values"]) == 7
    assert out["log_text"]
    assert out["image_path"]
    assert len(out["comm_log"]) == 1


# --------------------------------------------------------------- end-to-end

def test_run_diagnosis_end_to_end(final_state):
    assert final_state.next_agent == DONE
    assert final_state.fusion_result is not None
    assert final_state.dga_analysis is not None
    assert final_state.rul_result is not None
    assert final_state.final_report and len(final_state.final_report) > 0


def test_parallel_inference_results_present(final_state):
    assert final_state.bert_result is not None
    assert final_state.cnn_result is not None
    assert final_state.yolo_result is not None


def test_comm_log_records_every_agent(final_state):
    senders = {m.sender for m in final_state.comm_log}
    for expected in (
        "coordinator", "data", "diagnosis.bert", "diagnosis.cnn",
        "diagnosis.yolo", "diagnosis.fusion", "diagnosis.dga", "decision",
    ):
        assert expected in senders, f"comm_log missing sender: {expected}"
    # Coordinator routes exactly 4 times: data, diagnosis, decision, DONE.
    routes = [m for m in final_state.comm_log if m.sender == "coordinator"]
    assert len(routes) == 4


def test_state_snapshot_is_json_serializable(final_state):
    snap = final_state.snapshot()
    assert "comm_log" in snap and "final_report" in snap
    assert len(json.dumps(snap, ensure_ascii=False)) > 0
