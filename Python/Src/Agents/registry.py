"""Agent registry — the forward-compatibility hook for a dynamic platform.

Each agent ships an ``AgentCard`` declaring which ``DiagnosisState`` fields
it consumes and produces. The Coordinator routes by traversing the
registry rather than a hard-coded if/elif chain, so the control flow is
already structurally dynamic.

Today the registry is populated statically (see ``graph.build_default_registry``).
But ``AgentRegistry.register()`` is exactly the entry point a future plugin
loader — or an A2A adapter wrapping a remote agent — would call at runtime.
When the state later grows an open artifact namespace, ``consumes`` /
``produces`` would name artifact keys instead of fixed fields, with no
change to the routing algorithm.

The ``AgentCard`` schema is intentionally close to an A2A *Agent Card*
(name / description / skills / endpoint) so going remote is incremental.
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
        """True when every consumed field is populated → the agent can run."""
        return all(getattr(state, f, None) is not None for f in self.consumes)

    def is_satisfied(self, state: DiagnosisState) -> bool:
        """True when every produced field is populated → nothing left to do."""
        if not self.produces:
            return False
        return all(getattr(state, f, None) is not None for f in self.produces)


class AgentRegistry:
    """Ordered collection of ``AgentCard`` manifests."""

    def __init__(self) -> None:
        self._cards: Dict[str, AgentCard] = {}
        self._order: List[str] = []

    def register(self, card: AgentCard) -> None:
        """Add (or replace) an agent. Insertion order is preserved and is the
        order the Coordinator scans — register agents in dependency order."""
        if card.name not in self._cards:
            self._order.append(card.name)
        self._cards[card.name] = card

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
