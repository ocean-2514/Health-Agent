"""Assemble and run the multi-agent diagnosis graph (LangGraph StateGraph).

Topology::

    START -> coordinator --(route)--> data | [bert,cnn,yolo] | decision | END
    data                       -> coordinator
    bert / cnn / yolo (parallel)-> fusion
    fusion                      -> dga
    dga                         -> coordinator
    decision                    -> coordinator

The Coordinator is the hub: every worker agent returns to it, and a single
conditional edge maps its routing decision onto the next node(s). The
``diagnosis`` decision fans out to the three parallel inference nodes.

Public entry point: ``run_diagnosis``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

from langgraph.graph import END, START, StateGraph

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.coordinator import DONE, make_coordinator_node
from Python.Src.Agents.data_agent import DATA_CARD, data_node
from Python.Src.Agents.decision_agent import DECISION_CARD, decision_node
from Python.Src.Agents.diagnosis_agent import (
    DIAGNOSIS_CARD,
    bert_node,
    cnn_node,
    dga_node,
    fusion_node,
    yolo_node,
)
from Python.Src.Agents.registry import AgentRegistry
from Python.Src.Agents.state import DiagnosisState


def build_default_registry() -> AgentRegistry:
    """Statically populate the registry with the four built-in agents.

    A future plugin loader would call ``registry.register(card)`` here at
    runtime; the rest of the system does not care how the registry is
    filled.
    """
    reg = AgentRegistry()
    reg.register(DATA_CARD)
    reg.register(DIAGNOSIS_CARD)
    reg.register(DECISION_CARD)
    return reg


def _route(state: DiagnosisState) -> Union[str, list]:
    """Conditional-edge function: map the Coordinator's decision to node(s)."""
    nxt = state.next_agent
    if nxt == DONE or nxt is None:
        return END
    if nxt == "diagnosis":
        return ["bert", "cnn", "yolo"]  # parallel fan-out
    return nxt  # "data" or "decision"


def build_graph(registry: Optional[AgentRegistry] = None):
    """Build and compile the multi-agent StateGraph."""
    registry = registry or build_default_registry()
    g = StateGraph(DiagnosisState)

    g.add_node("coordinator", make_coordinator_node(registry))
    g.add_node("data", data_node)
    g.add_node("bert", bert_node)
    g.add_node("cnn", cnn_node)
    g.add_node("yolo", yolo_node)
    g.add_node("fusion", fusion_node)
    g.add_node("dga", dga_node)
    g.add_node("decision", decision_node)

    g.add_edge(START, "coordinator")
    g.add_conditional_edges(
        "coordinator",
        _route,
        ["data", "bert", "cnn", "yolo", "decision", END],
    )
    g.add_edge("data", "coordinator")
    g.add_edge("bert", "fusion")
    g.add_edge("cnn", "fusion")
    g.add_edge("yolo", "fusion")
    g.add_edge("fusion", "dga")
    g.add_edge("dga", "coordinator")
    g.add_edge("decision", "coordinator")

    return g.compile()


# Default health-assessment parameters (mirror MCP ``assess_full_health``).
_DEFAULT_PARAMS: Dict[str, Any] = {
    "oil_bdv": 2, "oil_water": 2, "oil_acid": 1, "oil_ift": 2,
    "dga_h2": 2, "dga_ch4": 2, "dga_co": 1, "dga_co2": 1,
    "dga_c2h4": 1, "dga_c2h6": 1, "dga_c2h2": 1,
    "furan_level": "A", "future_load": 0.8, "ambient_temp": 25.0,
}


def run_diagnosis(
    equipment_id: str = "tr01",
    substation: str = "station1",
    params: Optional[Dict[str, Any]] = None,
) -> DiagnosisState:
    """Run the full multi-agent diagnosis and return the final state.

    ``params`` overrides the default health-assessment inputs.
    """
    raw = dict(_DEFAULT_PARAMS)
    if params:
        raw.update(params)

    graph = build_graph()
    initial = DiagnosisState(
        equipment_id=equipment_id, substation=substation, raw_input=raw,
    )
    result = graph.invoke(initial)
    if isinstance(result, DiagnosisState):
        return result
    return DiagnosisState.model_validate(result)


if __name__ == "__main__":
    # Windows consoles default to GBK; the LLM narrative may contain
    # characters GBK cannot encode. Force UTF-8 for this demo print.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    final = run_diagnosis("tr01")
    print("=== 智能体通信轨迹 (comm_log) ===")
    for m in final.comm_log:
        conf = f" [conf={m.confidence:.2f}]" if m.confidence is not None else ""
        print(f"  [{m.sender:>18} -> {m.receiver:<14}] {m.intent}: {m.summary}{conf}")
    print(f"\n=== errors === {final.errors or '无'}")
    print("\n=== final_report ===")
    print(final.final_report)
