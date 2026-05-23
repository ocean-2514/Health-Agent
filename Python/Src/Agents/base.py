"""Agent abstraction — the uniform runnable interface for the platform.

Three kinds of thing satisfy ``Agent``:
  - the four built-in agents (wired into the graph by hand — they conform
    conceptually but do not need a wrapper);
  - a local plugin discovered from ``Python/Src/Agents/plugins/`` — wrapped
    here as ``LocalPluginAgent``;
  - a remote A2A agent — wrapped as ``A2AAgentProxy`` (see a2a_proxy.py).

The graph dispatches all of them identically: read the ``AgentCard`` for
routing, call ``run(state)`` for execution. Whether ``run`` is a local
function call or a network round-trip is the wrapper's concern, not the
platform's. ``AgentCard.endpoint`` is the discriminator — ``None`` for
in-process, a URL for remote.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.registry import AgentCard
from Python.Src.Agents.state import DiagnosisState

# A graph node: reads the blackboard, returns a partial state update.
NodeFn = Callable[[DiagnosisState], dict]


@runtime_checkable
class Agent(Protocol):
    """A routable + runnable agent: an ``AgentCard`` plus a ``run`` method."""

    card: AgentCard

    def run(self, state: DiagnosisState) -> dict:
        """Execute against the blackboard; return a partial state update."""
        ...


@dataclass
class LocalPluginAgent:
    """An in-process agent discovered from the plugins directory.

    ``run`` is a direct function call — the simplest transport. A remote
    agent (``A2AAgentProxy``) exposes the same interface but marshals the
    call over the A2A protocol instead.
    """
    card: AgentCard
    node: NodeFn

    def run(self, state: DiagnosisState) -> dict:
        return self.node(state)
