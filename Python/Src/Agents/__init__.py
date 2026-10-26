"""Phase 3 — multi-agent collaboration layer.

A LangGraph ``StateGraph`` orchestrates four agents (Coordinator / Data /
Diagnosis / Decision) over a single shared typed blackboard
(``DiagnosisState``).

Communication model (confirmed in design review):
  - Data channel: the typed ``DiagnosisState`` — agents never call each
    other directly, they read the fields they need and write the fields
    they produce.
  - Control channel: the Coordinator routes by traversing an
    ``AgentRegistry`` of ``AgentCard`` manifests (rule-based, no LLM).
  - Audit channel: ``DiagnosisState.comm_log`` — an append-only trace of
    inter-agent messages, kept purely for explainability.

The registry indirection is the forward-compatibility hook for a future
dynamic agent platform: today it is populated statically in ``graph.py``,
but ``AgentRegistry.register()`` is exactly where a plugin loader or an
A2A adapter would hook in at runtime.

Public entry point: ``Python.Src.Agents.graph.run_diagnosis``.
"""
