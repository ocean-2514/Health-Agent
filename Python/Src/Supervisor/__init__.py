"""Phase 6 — outer SupervisorAgent layer.

Wraps the Phase 3-5 transformer-diagnosis platform as ONE *skill* and puts
it behind a LangChain tool-calling supervisor that takes natural-language
requests, decides which skill(s) to invoke (alone or in combination), and
returns an aggregated answer.

The inner platform (``Python/Src/Agents/*``) is not touched. From the
outside it looks like a single skill: ``transformer_diagnosis(equipment_id,
substation, raw_input)`` -> ``{health_index, predicted_rul_years,
fusion_verdict_cn, final_report, ...}``. New top-level skills
(``knowledge_qa``, ``history_lookup``, future remote A2A agents) sit at
the same level.

Public entry:
  * ``Supervisor`` — the multi-turn chat orchestrator (see ``core.py``)
  * ``Skill`` / ``SkillCard`` — the protocol every skill satisfies
  * ``SessionStore`` — SQLite-backed chat history
"""
from Python.Src.Supervisor.core import Supervisor
from Python.Src.Supervisor.discovery import discover_skills_from_path
from Python.Src.Supervisor.loader import SkillLoadError, load_skills
from Python.Src.Supervisor.remote import (
    A2AClient,
    A2AClientError,
    RemoteA2ASkill,
    load_remote_skills,
)
from Python.Src.Supervisor.session import SessionStore
from Python.Src.Supervisor.skill import Skill, SkillCard, skill_to_tool

__all__ = [
    "Supervisor", "SessionStore",
    "Skill", "SkillCard", "skill_to_tool",
    "load_skills", "SkillLoadError",
    "discover_skills_from_path",
    "RemoteA2ASkill", "load_remote_skills",
    "A2AClient", "A2AClientError",
]
