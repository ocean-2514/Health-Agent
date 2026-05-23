"""Assemble and run the multi-agent diagnosis graph (LangGraph StateGraph).

Topology::

    START -> coordinator --(route)--> data | [bert,cnn,yolo] | decision
                                      | <plugin/remote agents> | END
    data                       -> coordinator
    bert / cnn / yolo (parallel)-> fusion
    fusion                      -> dga
    dga                         -> coordinator
    decision                    -> coordinator
    <each plugin/remote agent>  -> coordinator

The Coordinator is the hub: every worker agent returns to it, and a single
conditional edge maps its routing decision onto the next node(s). The four
built-in agents are wired by hand (the Diagnosis agent fans out to three
parallel inference nodes). Any agent registered with a *runnable* — a local
plugin or a remote A2A proxy — is wired generically: one node, one edge
back to the Coordinator. Adding such an agent needs no change here beyond
it being present in the registry.

Public entry point: ``run_diagnosis``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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

_BUILTIN_NODES = {"coordinator", "data", "bert", "cnn", "yolo", "fusion", "dga", "decision"}


def build_default_registry() -> AgentRegistry:
    """Populate a registry with just the three built-in worker agents.

    Plugin agents are added on top of this by ``loader.load_plugins``;
    remote A2A agents by the remote loader. The rest of the system does not
    care how the registry was filled.
    """
    reg = AgentRegistry()
    reg.register(DATA_CARD)
    reg.register(DIAGNOSIS_CARD)
    reg.register(DECISION_CARD)
    return reg


def _route(state: DiagnosisState) -> Union[str, List[str]]:
    """Conditional-edge function: map the Coordinator's decision to node(s)."""
    nxt = state.next_agent
    if nxt == DONE or nxt is None:
        return END
    if nxt == "diagnosis":
        return ["bert", "cnn", "yolo"]  # parallel fan-out
    return nxt  # "data" | "decision" | any plugin / remote agent name


def build_graph(registry: Optional[AgentRegistry] = None):
    """Build and compile the multi-agent StateGraph.

    Built-in agents are wired by hand; every agent in ``registry`` that
    carries a runnable (plugin / remote) is wired generically.
    """
    registry = registry or build_default_registry()
    g = StateGraph(DiagnosisState)

    # --- built-in agents: hand-wired (Diagnosis fans out to bert/cnn/yolo) ---
    g.add_node("coordinator", make_coordinator_node(registry))
    g.add_node("data", data_node)
    g.add_node("bert", bert_node)
    g.add_node("cnn", cnn_node)
    g.add_node("yolo", yolo_node)
    g.add_node("fusion", fusion_node)
    g.add_node("dga", dga_node)
    g.add_node("decision", decision_node)

    # --- plugin / remote agents: generic wiring (coordinator <-> agent) ---
    extra_targets: List[str] = []
    for card in registry.ordered():
        runnable = registry.runnable_of(card.name)
        if runnable is None:
            continue  # a built-in — already wired above
        if card.name in _BUILTIN_NODES:
            raise ValueError(f"plugin agent name collides with a built-in: {card.name!r}")
        g.add_node(card.name, runnable.run)  # type: ignore[attr-defined]
        g.add_edge(card.name, "coordinator")
        extra_targets.append(card.name)

    g.add_edge(START, "coordinator")
    g.add_conditional_edges(
        "coordinator",
        _route,
        ["data", "bert", "cnn", "yolo", "decision", END] + extra_targets,
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
    registry: Optional[AgentRegistry] = None,
) -> DiagnosisState:
    """Run the full multi-agent diagnosis and return the final state.

    ``params`` overrides the default health-assessment inputs. ``registry``
    lets a caller supply a registry already extended with plugin / remote
    agents; when omitted only the three built-in agents run.
    """
    raw = dict(_DEFAULT_PARAMS)
    if params:
        raw.update(params)

    graph = build_graph(registry)
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
