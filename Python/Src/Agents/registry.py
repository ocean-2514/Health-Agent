"""Agent registry — the forward-compatibility hook for a dynamic platform.

Each agent ships an ``AgentCard`` declaring which ``DiagnosisState`` fields
it consumes and produces. The Coordinator routes by traversing the
registry rather than a hard-coded if/elif chain, so the control flow is
already structurally dynamic.

The built-in agents are registered statically (see
``graph.build_default_registry``); plugin agents are registered at startup
by ``loader.PluginLoader``; remote agents are registered by the A2A remote
loader. All three paths funnel through ``AgentRegistry.register()`` — the
rest of the platform does not care how a card got there.

``consumes`` / ``produces`` name either a typed ``DiagnosisState`` field or
an open ``artifacts`` key; ``AgentCard`` checks both uniformly, so a plugin
that only touches the artifact namespace routes exactly like a built-in.

The ``AgentCard`` schema is intentionally close to an A2A *Agent Card*
(name / description / skills / endpoint). ``endpoint`` is ``None`` for an
in-process agent and a URL for a remote A2A agent.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.state import DiagnosisState


def _has(state: DiagnosisState, key: str) -> bool:
    """True if ``key`` is populated — as a typed state field OR an artifact.

    This single check is what makes the closed core fields and the open
    artifact namespace route uniformly.
    """
    value = getattr(state, key, None)
    if value is not None:
        return True
    return key in (getattr(state, "artifacts", None) or {})


@dataclass
class AgentCard:
    """Capability manifest for one agent.

    ``endpoint`` is ``None`` for an in-process agent. A future remote agent
    would carry a URL here, and the Coordinator would dispatch to it via a
    transport adapter (MCP / A2A) instead of a direct function call.
    """
    name: str
    description: str
    skills: List[str] = field(default_factory=list)
    consumes: List[str] = field(default_factory=list)
    produces: List[str] = field(default_factory=list)
    endpoint: Optional[str] = None

    def is_runnable(self, state: DiagnosisState) -> bool:
        """True when every consumed key is populated → the agent can run."""
        return all(_has(state, k) for k in self.consumes)

    def is_satisfied(self, state: DiagnosisState) -> bool:
        """True when every produced key is populated → nothing left to do."""
        if not self.produces:
            return False
        return all(_has(state, k) for k in self.produces)


class AgentRegistry:
    """Ordered collection of ``AgentCard`` manifests (+ optional runnables)."""

    def __init__(self) -> None:
        self._cards: Dict[str, AgentCard] = {}
        self._order: List[str] = []
        self._runnables: Dict[str, object] = {}

    def register(self, card: AgentCard, runnable: Optional[object] = None) -> None:
        """Add (or replace) an agent. Insertion order is preserved and is the
        order the Coordinator scans — register agents in dependency order.

        ``runnable`` is the object whose ``run(state)`` the graph calls for a
        generically-dispatched agent (local plugin / remote A2A proxy). The
        four built-in agents pass ``None`` — they are wired into the graph by
        hand (the Diagnosis agent in particular fans out to parallel nodes).
        """
        if card.name not in self._cards:
            self._order.append(card.name)
        self._cards[card.name] = card
        if runnable is not None:
            self._runnables[card.name] = runnable

    def runnable_of(self, name: str) -> Optional[object]:
        """The ``run``-able object for a generically-dispatched agent, or
        ``None`` for a built-in agent that the graph wires by hand."""
        return self._runnables.get(name)

    def get(self, name: str) -> AgentCard:
        return self._cards[name]

    def ordered(self) -> List[AgentCard]:
        return [self._cards[n] for n in self._order]

    def names(self) -> List[str]:
        return list(self._order)

    def __len__(self) -> int:
        return len(self._cards)

    def __contains__(self, name: str) -> bool:
        return name in self._cards
