"""Agent plugins — drop a package here and ``PluginLoader`` discovers it.

A plugin module / sub-package must expose a module-level ``AGENT`` that
satisfies the ``Agent`` protocol: an ``AgentCard`` plus a
``run(state) -> dict`` method (the easiest way is
``LocalPluginAgent(card, node_fn)``).

The card's ``consumes`` / ``produces`` — typed ``DiagnosisState`` fields or
open ``artifacts`` keys — determine where the Coordinator slots the agent
into the workflow. No core file needs editing to add a plugin.
"""
