"""Coordinator — rule-based, registry-driven router.

The Coordinator does NOT decide with an LLM: routing is deterministic, so
the workflow is reproducible and unit-testable. It walks the
``AgentRegistry`` in registration order and picks the first agent that is
*runnable* (all consumed fields populated) but not yet *satisfied* (some
produced field still missing). When every registered agent is satisfied it
returns ``DONE``.

Because the decision reads the registry rather than a hard-coded if/elif
chain, registering a new agent at runtime would extend the workflow with
no change to this file — the structural hook for a future dynamic platform.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.registry import AgentRegistry
from Python.Src.Agents.state import DiagnosisState, make_message

AGENT_NAME = "coordinator"
DONE = "DONE"


def decide_next_agent(state: DiagnosisState, registry: AgentRegistry) -> str:
    """Return the name of the next agent to run, or ``DONE``."""
    for card in registry.ordered():
        if card.is_runnable(state) and not card.is_satisfied(state):
            return card.name
    return DONE


def make_coordinator_node(registry: AgentRegistry) -> Callable[[DiagnosisState], dict]:
    """Build the Coordinator graph node bound to a specific registry."""

    def coordinator_node(state: DiagnosisState) -> dict:
        nxt = decide_next_agent(state, registry)
        if nxt == DONE:
            summary = "全部 agent 已完成, 诊断流程结束"
        else:
            summary = f"路由 → {nxt} agent"
        msg = make_message(
            sender=AGENT_NAME, receiver=nxt, intent="route", summary=summary,
        )
        return {"next_agent": nxt, "comm_log": [msg]}

    return coordinator_node
