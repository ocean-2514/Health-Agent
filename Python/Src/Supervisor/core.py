"""Supervisor — the outer-layer LLM tool-calling orchestrator.

Builds a LangGraph ReAct-style agent over a set of registered ``Skill``s.
On each ``chat()`` turn it loads the session history from
:class:`SessionStore`, runs the agent (which may invoke 0+ skills in
sequence as the LLM decides), persists the new exchange, and returns the
LLM's final answer.

LangChain 1.x reorganised its agent API; the simplest portable choice is
``langgraph.prebuilt.create_react_agent``, which compiles a tool-calling
loop into a LangGraph StateGraph. The supervisor itself contains no domain
logic — every action is either a direct LLM response or a tool call into
one of the Skills.

Dynamic skill registry (mirrors the pattern from the earlier
``D:/code/AI/project/agent`` SupervisorAgent's ``register_expert``):
``register_skill`` / ``unregister_skill`` / ``enable_skill`` /
``disable_skill`` / ``register_skill_from_config`` /
``register_skills_from_path`` all mutate the registry and recompile the
underlying agent. There is no public LangGraph API to splice tools into
a compiled graph, so each mutation triggers a rebuild — cheap relative
to one LLM call, but batch mutations via ``register_skills`` to avoid
N rebuilds.
"""
from __future__ import annotations

import logging
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Middleware.GlobalConfig import GlobalConfig
from Python.Src.Supervisor.session import SessionStore, default_store
from Python.Src.Supervisor.skill import Skill, skill_to_tool

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "你是变压器健康管控领域的助理。你可以调用下列工具来完成实际诊断、检索、"
    "历史查询等具体任务,也可以直接对用户的概念性 / 闲聊问题作答。\n\n"
    "调用工具的判断原则:\n"
    "  - 用户明确要求'诊断 / 体检 / 评估 / 查 RUL / 查健康指数' → 调 transformer_diagnosis\n"
    "  - 用户问'某缺陷怎么处理 / 某规程怎么规定' → 调 knowledge_qa(若已注册)\n"
    "  - 用户问'这台设备上次诊断结果 / 历史趋势' → 调 history_lookup(若已注册)\n"
    "  - 纯概念解释 / 寒暄 / follow-up(上一轮已给出的指标) → 直接作答, 不要重复调用工具\n"
    "  - 一次请求可以同时调多个独立工具, 提高效率\n\n"
    "工具返回结构化结果后, 用自然语言简洁回答用户; 数值类指标请直接引用, "
    "不要瞎编。"
)


class Supervisor:
    """Multi-turn chat orchestrator over a mutable set of Skills."""

    def __init__(
        self,
        skills: Sequence[Skill],
        *,
        session_store: SessionStore = default_store,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        if not skills:
            raise ValueError("Supervisor requires at least one Skill")

        cfg = GlobalConfig.config.get("LLM", {}).get("Local", {})
        self._model_name = model_name or cfg.get("ModelName", "gpt-oss:120b-cloud")
        self._base_url = base_url or cfg.get("BaseURL", "http://localhost:11434")
        self._temperature = temperature

        self._store = session_store
        self._llm = ChatOllama(
            model=self._model_name,
            base_url=self._base_url,
            temperature=self._temperature,
        )

        # ordered registry: insertion order = display order. Disabled
        # skills stay here so enable/disable is non-destructive.
        self._skills: "OrderedDict[str, Skill]" = OrderedDict()
        self._disabled: Set[str] = set()

        self.register_skills(skills)  # also performs the initial rebuild

    # =========================================================== dynamic API

    def register_skill(self, skill: Skill) -> str:
        """Register one skill. If the name already exists it is overwritten
        (matching the original ``register_expert`` semantics). Returns the
        registered name."""
        name = self._add_one(skill)
        self._rebuild_agent()
        return name

    def register_skills(self, skills: Iterable[Skill]) -> List[str]:
        """Batch register; one rebuild at the end (much cheaper than N)."""
        names: List[str] = []
        for s in skills:
            names.append(self._add_one(s))
        self._rebuild_agent()
        return names

    def unregister_skill(self, name: str) -> bool:
        """Remove a skill (also clears any disabled flag). Returns whether
        it was present."""
        present = name in self._skills
        self._skills.pop(name, None)
        self._disabled.discard(name)
        if present:
            self._rebuild_agent()
        return present

    def disable_skill(self, name: str) -> bool:
        """Soft-disable: skill stays in the registry but is hidden from the
        LLM until re-enabled. Returns whether anything changed."""
        if name not in self._skills:
            return False
        if name in self._disabled:
            return False
        self._disabled.add(name)
        self._rebuild_agent()
        return True

    def enable_skill(self, name: str) -> bool:
        if name not in self._skills:
            return False
        if name not in self._disabled:
            return False
        self._disabled.discard(name)
        self._rebuild_agent()
        return True

    def register_skill_from_config(self, spec: Dict[str, Any]) -> str:
        """Instantiate one skill from a spec dict (same shape as a YAML
        entry) and register it. ``spec['class_path']`` and optional
        ``init_kwargs`` are required; ``enabled: false`` is honoured."""
        # Local import: keeps the loader module's heavier dependencies
        # (yaml, importlib chains) off the common path.
        from Python.Src.Supervisor.loader import _import_class, SkillLoadError

        if not spec.get("enabled", True):
            raise SkillLoadError(f"refusing to register disabled spec: {spec}")
        class_path = spec.get("class_path")
        if not class_path:
            raise SkillLoadError(f"register spec missing class_path: {spec}")
        cls = _import_class(class_path)
        init_kwargs: Dict[str, Any] = spec.get("init_kwargs") or {}
        try:
            skill = cls(**init_kwargs)
        except Exception as e:
            raise SkillLoadError(f"failed to instantiate {class_path}: {e}") from e
        if not (hasattr(skill, "card") and hasattr(skill, "run")):
            raise SkillLoadError(
                f"{class_path} does not satisfy Skill protocol (need card + run)"
            )
        return self.register_skill(skill)

    def register_remote_skill(
        self,
        url: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        timeout_s: float = 30.0,
    ) -> str:
        """Hot-register a remote A2A agent by URL.

        If ``name`` or ``description`` is missing, probe the remote's
        agent card and use its ``name`` / ``description``. Probe failure
        falls back to a synthesised description (matches the relaxed
        startup behaviour in ``load_remote_skills``) so a temporarily-down
        remote can still be registered for later use.
        """
        # Local import: keeps a2a-sdk / httpx off the hot path for callers
        # that never touch remotes.
        from Python.Src.Supervisor.remote import (
            A2AClient,
            A2AClientError,
            RemoteA2ASkill,
        )

        probed_name: Optional[str] = None
        probed_desc: Optional[str] = None
        if name is None or description is None:
            try:
                card = A2AClient(default_timeout_s=timeout_s).discover_card(
                    url, timeout_s=timeout_s
                )
                probed_name = card.get("name")
                probed_desc = card.get("description")
            except A2AClientError as e:
                logger.warning(
                    "register_remote_skill probe failed for %s: %s "
                    "— registering with caller/fallback values",
                    url, e,
                )

        final_name = name or probed_name
        if not final_name:
            raise ValueError(
                f"could not determine skill name for {url}: pass name= "
                f"or make sure the remote serves an agent-card with 'name'"
            )
        final_desc = (
            description
            or probed_desc
            or f"Remote A2A agent at {url} (no description available)."
        )
        if probed_name or probed_desc:
            final_desc = f"{final_desc} [remote A2A agent @ {url}]"
        else:
            final_desc = f"{final_desc} [remote: {url}, unreachable at registration]"

        return self.register_skill(
            RemoteA2ASkill(
                name=final_name,
                description=final_desc,
                url=url,
                timeout_s=timeout_s,
            )
        )

    def register_remote_skills_from_yaml(
        self, yaml_path: Optional[str | Path] = None
    ) -> List[str]:
        """Load every enabled entry from a ``remote_skills.yaml`` file
        (default: ``Config/remote_skills.yaml``) and register them. Reuses
        the same loader + relaxed-probe behaviour as startup loading."""
        from Python.Src.Supervisor.remote import load_remote_skills

        path = Path(yaml_path) if yaml_path else None
        new = load_remote_skills(yaml_path=path)
        # Skip duplicates (same name already registered) — matches the
        # behaviour of register_skills_from_path so re-running is safe.
        fresh = [s for s in new if s.card.name not in self._skills]
        if not fresh:
            return []
        return self.register_skills(fresh)

    def register_skills_from_path(
        self, directory: str | Path, recursive: bool = True
    ) -> List[str]:
        """Scan ``directory`` for Python modules that declare
        ``SKILL = ...`` or ``SKILLS = [...]`` at module level, instantiate
        nothing (the module already did), and register each. Returns the
        names of newly-registered skills (skipping anything whose name
        was already present)."""
        from Python.Src.Supervisor.discovery import discover_skills_from_path

        discovered = discover_skills_from_path(directory, recursive=recursive)
        new: List[Skill] = []
        for s in discovered:
            name = getattr(s.card, "name", None)
            if not name:
                logger.warning("discovered object has no .card.name, skipping: %r", s)
                continue
            if name in self._skills:
                logger.info("skill %r already registered, leaving existing", name)
                continue
            new.append(s)
        if not new:
            return []
        return self.register_skills(new)

    # ============================================================ chat path

    def chat(self, session_id: str, user_input: str) -> str:
        """Run one chat turn against ``session_id`` and return the answer."""
        messages: List[BaseMessage] = self._load_history(session_id)
        messages.append(HumanMessage(content=user_input))

        try:
            result = self._agent.invoke({"messages": messages})
        except Exception as e:  # noqa: BLE001
            answer = f"[supervisor 内部错误] {e}"
        else:
            answer = self._extract_final_answer(result.get("messages", []))

        if not answer:
            answer = "(模型未返回有效内容)"

        self._store.save_message(session_id, "user", user_input)
        self._store.save_message(session_id, "assistant", answer)
        return answer

    def new_session(self) -> str:
        return self._store.create_session()

    # =============================================================== views

    @property
    def skill_names(self) -> List[str]:
        """Names exposed to the LLM right now (excludes disabled)."""
        return [n for n in self._skills if n not in self._disabled]

    @property
    def all_skill_names(self) -> List[str]:
        """All registered names, including disabled."""
        return list(self._skills.keys())

    @property
    def disabled_skill_names(self) -> List[str]:
        return [n for n in self._skills if n in self._disabled]

    # ============================================================ internals

    def _add_one(self, skill: Skill) -> str:
        if not (hasattr(skill, "card") and hasattr(skill, "run")):
            raise TypeError(
                f"{skill!r} does not satisfy the Skill protocol (need card + run)"
            )
        name = skill.card.name
        if not name:
            raise ValueError(f"skill {skill!r} has empty card.name")
        if name in self._skills:
            logger.info("re-registering skill %r (overwrite)", name)
        self._skills[name] = skill
        self._disabled.discard(name)
        return name

    def _rebuild_agent(self) -> None:
        """Recompile the underlying ReAct agent over the currently-active
        skills. Called by every public mutator."""
        active = [s for n, s in self._skills.items() if n not in self._disabled]
        self._tools = [skill_to_tool(s) for s in active]
        self._agent = create_react_agent(
            model=self._llm,
            tools=self._tools,
            prompt=_SYSTEM_PROMPT,
        )

    def _load_history(self, session_id: str) -> List[BaseMessage]:
        msgs: List[BaseMessage] = []
        for row in self._store.get_history(session_id):
            role, content = row["role"], row["content"]
            if role == "user":
                msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
        return msgs

    @staticmethod
    def _extract_final_answer(messages: Sequence[BaseMessage]) -> str:
        """Pull the last natural-language assistant message out of the agent
        trace. Skips tool-call / tool-result frames."""
        for msg in reversed(messages):
            kind = getattr(msg, "type", "")
            if kind == "tool":
                continue
            content = getattr(msg, "content", None)
            if not content:
                continue
            if isinstance(content, list):
                # Some chat models return content as a list of parts.
                parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                joined = "".join(parts).strip()
                if joined:
                    return joined
                continue
            text = str(content).strip()
            if text:
                return text
        return ""
