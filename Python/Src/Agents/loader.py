"""Plugin discovery — load agents from ``Python/Src/Agents/plugins/``.

A plugin is a module or sub-package under ``plugins/`` that exposes a
module-level ``AGENT`` satisfying the ``Agent`` protocol (an ``AgentCard``
plus a ``run(state) -> dict`` method). ``PluginLoader.discover()`` imports
every such module and returns the agents; ``load_plugins()`` registers them
into a registry.

This is the "dynamic" in dynamic agent platform: dropping a new package
into ``plugins/`` extends the workflow with zero change to the core. Like
most plugin systems (pytest, VS Code extensions), discovery happens once at
startup — so the graph is still built a single time, just from a registry
that now also contains the plugins. (Loading a *remote* agent over A2A is a
separate path; see a2a_proxy.py / a2a_server.py.)
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import List, Optional

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.base import Agent
from Python.Src.Agents.graph import build_default_registry
from Python.Src.Agents.registry import AgentRegistry

_PLUGINS_PKG = "Python.Src.Agents.plugins"


class PluginLoader:
    """Discovers in-process agent plugins under a package."""

    def __init__(self, plugins_pkg: str = _PLUGINS_PKG) -> None:
        self.plugins_pkg = plugins_pkg

    def discover(self) -> List[Agent]:
        """Import every plugin module and return its ``AGENT``.

        A module without an ``AGENT`` attribute is skipped (a helper, not a
        plugin). A module whose ``AGENT`` is malformed raises ``TypeError``.
        """
        pkg = importlib.import_module(self.plugins_pkg)
        agents: List[Agent] = []
        for _finder, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
            if modname.startswith("_"):
                continue
            module = importlib.import_module(f"{self.plugins_pkg}.{modname}")
            agent = getattr(module, "AGENT", None)
            if agent is None:
                continue
            if not (hasattr(agent, "card") and hasattr(agent, "run")):
                raise TypeError(
                    f"plugin '{modname}': AGENT must expose a 'card' and a 'run' method"
                )
            agents.append(agent)
        return agents


def load_plugins(
    registry: AgentRegistry, loader: Optional[PluginLoader] = None
) -> AgentRegistry:
    """Discover plugins and register each into ``registry``; returns it."""
    loader = loader or PluginLoader()
    for agent in loader.discover():
        registry.register(agent.card, runnable=agent)
    return registry


def build_platform_registry() -> AgentRegistry:
    """Built-in agents + every discovered plugin — the full platform registry.

    Runs ``AgentRegistry.validate()`` once everyone is in, so any
    ArtifactSpec consumer without a matching producer fails loud right
    here rather than at first execution.
    """
    registry = load_plugins(build_default_registry())
    registry.validate()
    return registry
