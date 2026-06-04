"""Remote-skill integration: surface other agents (A2A protocol) as
regular Supervisor Skills.

A remote A2A agent is wrapped as a ``RemoteA2ASkill`` so it shows up in
``Supervisor.skill_names`` next to ``transformer_diagnosis`` /
``history_lookup`` — the LLM decides when to call it just like any local
skill. The transport details (card discovery, JSON-RPC, async client)
are hidden inside this package.

Public entry:
  * ``RemoteA2ASkill`` — the Skill-protocol adapter
  * ``load_remote_skills`` — read ``Config/remote_skills.yaml`` and build them
  * ``A2AClient`` — thin sync wrapper over ``a2a-sdk`` (mostly internal)
"""
from Python.Src.Supervisor.remote.a2a_client import A2AClient, A2AClientError
from Python.Src.Supervisor.remote.loader import load_remote_skills
from Python.Src.Supervisor.remote.remote_skill import RemoteA2ASkill

__all__ = [
    "RemoteA2ASkill",
    "load_remote_skills",
    "A2AClient",
    "A2AClientError",
]
