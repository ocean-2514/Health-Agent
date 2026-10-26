"""Search agent plugin package.

Re-exports ``AGENT`` so ``PluginLoader`` finds it on the package itself.
"""
from Python.Src.Agents.plugins.search_agent.agent import AGENT

__all__ = ["AGENT"]
