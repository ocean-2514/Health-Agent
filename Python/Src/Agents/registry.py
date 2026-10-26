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

``consumes`` / ``produces`` carry one of two shapes:

  * a bare ``str`` — names a typed ``DiagnosisState`` field (built-in
    agents) or an artifact key with no schema enforcement (legacy plugins);
  * an ``ArtifactSpec(key, schema_name, version)`` — names an open
    ``artifacts`` slot and the contract its payload must satisfy. The
    router uses (key, schema_name, version) to decide presence; a wrong
    schema or older version is **silently treated as absent**, so the
    agent simply does not get routed (no exception, no broken pipeline).

The ``AgentCard`` schema is intentionally close to an A2A *Agent Card*
(name / description / skills / endpoint). ``endpoint`` is ``None`` for an
in-process agent and a URL for a remote A2A agent.

``AgentRegistry.validate()`` does a *deferred* satisfiability sweep:
every ``ArtifactSpec`` in any agent's ``consumes`` must be produced by
some registered agent. Call it once all registrations are done (the
platform builder does — see ``loader.build_platform_registry``). Built-in
``str`` consumes refer to typed fields written by the built-in pipeline
and are trusted, so they are not validated here.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.state import ArtifactSpec, DiagnosisState

# A consumes / produces entry. ``str`` names a typed field or a bare
# artifact key (legacy); ``ArtifactSpec`` carries a schema contract.
Requirement = Union[ArtifactSpec, str]


class UnsatisfiableConsumer(ValueError):
    """A registered agent declares an ArtifactSpec input that nobody produces."""


def _has(state: DiagnosisState, item: Requirement) -> bool:
    """True if ``item`` is populated in ``state`` under its declared contract.

    Routing rules:
      * ``str`` — typed state field present, OR artifact key present (no
        schema check). Keeps built-ins and legacy plugins working.
      * ``ArtifactSpec`` — artifact present AND ``schema_name`` matches AND
        ``version >= spec.version``. Anything else is **silently treated as
        absent** so the agent is just not routed (per the design decision
        on schema mismatch handling).
    """
    if isinstance(item, str):
        value = getattr(state, item, None)
        if value is not None:
            return True
        return item in (getattr(state, "artifacts", None) or {})

    artifacts = getattr(state, "artifacts", None) or {}
    art = artifacts.get(item.key)
    if art is None:
        return False
    if art.schema_name != item.schema_name:
        return False
    if art.version < item.version:
        return False
    return True


@dataclass
class AgentCard:
    """Capability manifest for one agent.

    ``consumes`` / ``produces`` entries are each either a bare ``str``
    (typed field name, or a legacy artifact key with no schema check) or
    an ``ArtifactSpec`` carrying ``(key, schema_name, version)``.

    ``endpoint`` is ``None`` for an in-process agent. A remote agent
    carries a URL here, and the platform dispatches to it via a transport
    adapter (A2A) instead of a direct function call.
    """
    name: str
    description: str
    skills: List[str] = field(default_factory=list)
    consumes: List[Requirement] = field(default_factory=list)
    produces: List[Requirement] = field(default_factory=list)
    endpoint: Optional[str] = None

    def is_runnable(self, state: DiagnosisState) -> bool:
        """True when every consumed entry is satisfied → the agent can run."""
        return all(_has(state, k) for k in self.consumes)

    def is_satisfied(self, state: DiagnosisState) -> bool:
        """True when every produced entry is populated → nothing left to do."""
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

    def _someone_produces(self, spec: ArtifactSpec) -> bool:
        """True if any registered agent's ``produces`` covers ``spec``.

        Matching rule:
          * ``ArtifactSpec`` producer: same ``key`` + ``schema_name`` +
            producer ``version >= spec.version``.
          * bare ``str`` producer: matches the spec's ``key`` (legacy
            plugin compatibility — no schema enforcement on the producer
            side).
        """
        for card in self._cards.values():
            for p in card.produces:
                if isinstance(p, ArtifactSpec):
                    if (
                        p.key == spec.key
                        and p.schema_name == spec.schema_name
                        and p.version >= spec.version
                    ):
                        return True
                elif isinstance(p, str) and p == spec.key:
                    return True
        return False

    def validate(self) -> None:
        """Sweep: every ArtifactSpec consumed must have a matching producer.

        Order-independent — call after all registrations are done. Raises
        ``UnsatisfiableConsumer`` for the first violation found. Bare ``str``
        consumes are not validated (they refer to typed built-in fields
        which are trusted).
        """
        for card in self._cards.values():
            for need in card.consumes:
                if isinstance(need, ArtifactSpec) and not self._someone_produces(need):
                    raise UnsatisfiableConsumer(
                        f"agent {card.name!r} consumes {need.key!r} "
                        f"(schema {need.schema_name!r} v{need.version}), "
                        f"but no registered agent produces it"
                    )

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
