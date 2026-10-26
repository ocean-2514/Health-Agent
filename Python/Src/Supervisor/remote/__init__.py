"""Remote-tool integration: surface other agents (A2A protocol) as
regular Supervisor Tools.

A remote A2A agent is wrapped as a ``RemoteA2ATool`` so it shows up in
``Supervisor.tool_names`` next to ``transformer_diagnosis`` /
``history_lookup`` — the LLM decides when to call it just like any local
tool. The transport details (card discovery, JSON-RPC, async client) are
hidden inside this package. Conceptually the remote peer is an *Agent*;
locally it is reached through a *Tool*.

Public entry:
  * ``RemoteA2ATool`` — the Tool-protocol adapter
  * ``load_remote_tools`` — read ``Config/remote_tools.yaml`` and build them
  * ``A2AClient`` — thin sync wrapper over ``a2a-sdk`` (mostly internal)
"""
from Python.Src.Supervisor.remote.a2a_client import A2AClient, A2AClientError
from Python.Src.Supervisor.remote.loader import load_remote_tools
from Python.Src.Supervisor.remote.remote_tool import RemoteA2ATool

__all__ = [
    "RemoteA2ATool",
    "load_remote_tools",
    "A2AClient",
    "A2AClientError",
]
