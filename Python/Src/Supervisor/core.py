"""Supervisor — the outer-layer LLM tool-calling orchestrator.

Builds a LangGraph ReAct-style agent over a set of registered ``Tool``s.
On each ``chat()`` turn it loads the session history from
:class:`SessionStore`, runs the agent (which may invoke 0+ tools in
sequence as the LLM decides), persists the new exchange, and returns the
LLM's final answer.

Three cleanly separated concepts meet here (see ``tool.py`` / ``skill.py``):

  * **Tool**  — the only thing the LLM calls directly (function-calling).
    A Tool may wrap a primitive, a deterministic Workflow (the Phase 3-5
    diagnosis graph), or a remote Agent (A2A).
  * **Skill** — loadable prompt / domain knowledge (``SKILL.md``). Surfaced
    to the LLM as a one-line catalogue in the system prompt; the body is
    pulled in on demand via the built-in ``load_skill`` Tool.
  * **Agent** — an autonomous / remote delegate, reached *through* a Tool
    (e.g. ``RemoteA2ATool``), never called by the LLM directly.

LangChain 1.x reorganised its agent API; the simplest portable choice is
``langgraph.prebuilt.create_react_agent``, which compiles a tool-calling
loop into a LangGraph StateGraph. The supervisor itself contains no domain
logic.

Dynamic Tool registry (mirrors the earlier ``D:/code/AI/project/agent``
SupervisorAgent's ``register_expert``): ``register_tool`` /
``unregister_tool`` / ``enable_tool`` / ``disable_tool`` /
``register_tool_from_config`` / ``register_tools_from_path`` /
``register_remote_tool`` / ``register_remote_tools_from_yaml`` all mutate
the registry and recompile the underlying agent. There is no public
LangGraph API to splice tools into a compiled graph, so each mutation
triggers a rebuild — cheap relative to one LLM call, but batch mutations
via ``register_tools`` to avoid N rebuilds.
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
from Python.Src.Supervisor.skill import LoadSkillTool, SkillRegistry
from Python.Src.Supervisor.tool import Tool, to_langchain_tool

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "你是变压器健康管控领域的助理。你可以调用下列工具来完成实际诊断、检索、"
    "历史查询等具体任务,也可以直接对用户的概念性 / 闲聊问题作答。\n\n"
    "调用工具的判断原则:\n"
    "  - 用户明确要求'诊断 / 体检 / 评估 / 查 RUL / 查健康指数' → 调 transformer_diagnosis\n"
    "  - 用户问'这台设备上次诊断结果 / 历史趋势' → 调 history_lookup(若已注册)\n"
    "  - 任务匹配某条'可用知识技能' → 先 load_skill 加载其正文, 再据此作答\n"
    "  - 纯概念解释 / 寒暄 / follow-up(上一轮已给出的指标) → 直接作答, 不要重复调用工具\n"
    "  - 一次请求可以同时调多个独立工具, 提高效率\n\n"
    "工具返回结构化结果后, 用自然语言简洁回答用户; 数值类指标请直接引用, "
    "不要瞎编。"
)


class Supervisor:
    """Multi-turn chat orchestrator over a mutable set of Tools + Skills."""

    def __init__(
        self,
        tools: Sequence[Tool],
        *,
        session_store: SessionStore = default_store,
        skill_registry: Optional[SkillRegistry] = None,
        skill_dirs: Optional[List[Path]] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        if not tools:
            raise ValueError("Supervisor requires at least one Tool")

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

        # Prompt-style Skills (SKILL.md). Surfaced as a catalogue in the
        # system prompt; bodies loaded on demand via the built-in load_skill.
        self._skill_registry = skill_registry or SkillRegistry.discover(skill_dirs)

        # ordered Tool registry: insertion order = display order. Disabled
        # tools stay here so enable/disable is non-destructive.
        self._tools: "OrderedDict[str, Tool]" = OrderedDict()
        self._disabled: Set[str] = set()

        self.register_tools(tools)  # also performs the initial rebuild

    # =========================================================== dynamic API

    def register_tool(self, tool: Tool) -> str:
        """Register one tool. If the name already exists it is overwritten
        (matching the original ``register_expert`` semantics). Returns the
        registered name."""
        name = self._add_one(tool)
        self._rebuild_agent()
        return name

    def register_tools(self, tools: Iterable[Tool]) -> List[str]:
        """Batch register; one rebuild at the end (much cheaper than N)."""
        names: List[str] = []
        for t in tools:
            names.append(self._add_one(t))
        self._rebuild_agent()
        return names

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool (also clears any disabled flag). Returns whether
        it was present."""
        present = name in self._tools
        self._tools.pop(name, None)
        self._disabled.discard(name)
        if present:
            self._rebuild_agent()
        return present

    def disable_tool(self, name: str) -> bool:
        """Soft-disable: tool stays in the registry but is hidden from the
        LLM until re-enabled. Returns whether anything changed."""
        if name not in self._tools:
            return False
        if name in self._disabled:
            return False
        self._disabled.add(name)
        self._rebuild_agent()
        return True

    def enable_tool(self, name: str) -> bool:
        if name not in self._tools:
            return False
        if name not in self._disabled:
            return False
        self._disabled.discard(name)
        self._rebuild_agent()
        return True

    def register_tool_from_config(self, spec: Dict[str, Any]) -> str:
        """Instantiate one tool from a spec dict (same shape as a YAML
        entry) and register it. ``spec['class_path']`` and optional
        ``init_kwargs`` are required; ``enabled: false`` is honoured."""
        from Python.Src.Supervisor.loader import _import_class, ToolLoadError

        if not spec.get("enabled", True):
            raise ToolLoadError(f"refusing to register disabled spec: {spec}")
        class_path = spec.get("class_path")
        if not class_path:
            raise ToolLoadError(f"register spec missing class_path: {spec}")
        cls = _import_class(class_path)
        init_kwargs: Dict[str, Any] = spec.get("init_kwargs") or {}
        try:
            tool = cls(**init_kwargs)
        except Exception as e:
            raise ToolLoadError(f"failed to instantiate {class_path}: {e}") from e
        if not (hasattr(tool, "card") and hasattr(tool, "run")):
            raise ToolLoadError(
                f"{class_path} does not satisfy Tool protocol (need card + run)"
            )
        return self.register_tool(tool)

    def register_tools_from_path(
        self, directory: str | Path, recursive: bool = True
    ) -> List[str]:
        """Scan ``directory`` for Python modules that declare ``TOOL = ...``
        or ``TOOLS = [...]`` at module level, and register each. Returns the
        names of newly-registered tools (skipping anything whose name was
        already present)."""
        from Python.Src.Supervisor.discovery import discover_tools_from_path

        discovered = discover_tools_from_path(directory, recursive=recursive)
        new: List[Tool] = []
        for t in discovered:
            name = getattr(t.card, "name", None)
            if not name:
                logger.warning("discovered object has no .card.name, skipping: %r", t)
                continue
            if name in self._tools:
                logger.info("tool %r already registered, leaving existing", name)
                continue
            new.append(t)
        if not new:
            return []
        return self.register_tools(new)

    def register_remote_tool(
        self,
        url: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        timeout_s: float = 30.0,
    ) -> str:
        """Hot-register a remote A2A agent by URL (wrapped as a Tool).

        If ``name`` or ``description`` is missing, probe the remote's
        agent card and use its ``name`` / ``description``. Probe failure
        falls back to a synthesised description (matches the relaxed
        startup behaviour in ``load_remote_tools``) so a temporarily-down
        remote can still be registered for later use.
        """
        from Python.Src.Supervisor.remote import (
            A2AClient,
            A2AClientError,
            RemoteA2ATool,
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
                    "register_remote_tool probe failed for %s: %s "
                    "— registering with caller/fallback values",
                    url, e,
                )

        final_name = name or probed_name
        if not final_name:
            raise ValueError(
                f"could not determine tool name for {url}: pass name= "
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

        return self.register_tool(
            RemoteA2ATool(
                name=final_name,
                description=final_desc,
                url=url,
                timeout_s=timeout_s,
            )
        )

    def register_remote_tools_from_yaml(
        self, yaml_path: Optional[str | Path] = None
    ) -> List[str]:
        """Load every enabled entry from a ``remote_tools.yaml`` file
        (default: ``Config/remote_tools.yaml``) and register them. Reuses
        the same loader + relaxed-probe behaviour as startup loading."""
        from Python.Src.Supervisor.remote import load_remote_tools

        path = Path(yaml_path) if yaml_path else None
        new = load_remote_tools(yaml_path=path)
        fresh = [t for t in new if t.card.name not in self._tools]
        if not fresh:
            return []
        return self.register_tools(fresh)

    # ============================================================ skill API

    def reload_skills(self, skill_dirs: Optional[List[Path]] = None) -> List[str]:
        """Re-discover prompt-style Skills from disk and rebuild. Returns the
        current skill names."""
        self._skill_registry = SkillRegistry.discover(skill_dirs)
        self._rebuild_agent()
        return self._skill_registry.names

    # ============================================================ chat path

    def chat(self, session_id: str, user_input: str) -> str:
        """Run one chat turn against ``session_id`` and return the answer."""
        return self.chat_verbose(session_id, user_input)["answer"]

    def chat_verbose(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """Like :meth:`chat`, but also reports which Tools the LLM called.

        Returns ``{"answer": str, "tool_calls": [{"name", "args"}, ...]}``.
        Used by the HTTP API so the frontend can show "调用了
        transformer_diagnosis" alongside the natural-language answer.
        """
        messages: List[BaseMessage] = self._load_history(session_id)
        messages.append(HumanMessage(content=user_input))

        tool_calls: List[Dict[str, Any]] = []
        try:
            result = self._agent.invoke({"messages": messages})
        except Exception as e:  # noqa: BLE001
            answer = f"[supervisor 内部错误] {e}"
        else:
            trace = result.get("messages", [])
            tool_calls = self._extract_tool_calls(trace)
            answer = self._extract_final_answer(trace)

        if not answer:
            answer = "(模型未返回有效内容)"

        self._store.save_message(session_id, "user", user_input)
        self._store.save_message(session_id, "assistant", answer)
        return {"answer": answer, "tool_calls": tool_calls}

    def new_session(self) -> str:
        return self._store.create_session()

    # =============================================================== views

    @property
    def tool_names(self) -> List[str]:
        """Tool names exposed to the LLM right now (excludes disabled)."""
        return [n for n in self._tools if n not in self._disabled]

    @property
    def all_tool_names(self) -> List[str]:
        """All registered tool names, including disabled."""
        return list(self._tools.keys())

    @property
    def disabled_tool_names(self) -> List[str]:
        return [n for n in self._tools if n in self._disabled]

    @property
    def skill_names(self) -> List[str]:
        """Prompt-style Skill names available for load_skill."""
        return self._skill_registry.names

    @property
    def tool_catalogue(self) -> List[Dict[str, Any]]:
        """Name + description + disabled flag for every registered Tool."""
        return [
            {
                "name": n,
                "description": t.card.description,
                "disabled": n in self._disabled,
            }
            for n, t in self._tools.items()
        ]

    @property
    def skill_catalogue(self) -> List[Dict[str, Any]]:
        """Name + description for every discovered prompt-style Skill."""
        return [
            {"name": s.name, "description": s.description}
            for s in self._skill_registry.list()
        ]

    # ============================================================ internals

    def _add_one(self, tool: Tool) -> str:
        if not (hasattr(tool, "card") and hasattr(tool, "run")):
            raise TypeError(
                f"{tool!r} does not satisfy the Tool protocol (need card + run)"
            )
        name = tool.card.name
        if not name:
            raise ValueError(f"tool {tool!r} has empty card.name")
        if name in self._tools:
            logger.info("re-registering tool %r (overwrite)", name)
        self._tools[name] = tool
        self._disabled.discard(name)
        return name

    def _build_prompt(self) -> str:
        """System prompt + the Skill catalogue (progressive disclosure)."""
        prompt = _SYSTEM_PROMPT
        catalogue = self._skill_registry.catalogue_text()
        if catalogue:
            prompt += (
                "\n\n## 可用知识技能\n"
                "(用 load_skill(name) 加载正文后再作答)\n" + catalogue
            )
        return prompt

    def _rebuild_agent(self) -> None:
        """Recompile the underlying ReAct agent over the currently-active
        tools (+ the built-in load_skill if any Skill exists). Called by
        every public mutator."""
        active = [t for n, t in self._tools.items() if n not in self._disabled]
        lc_tools = [to_langchain_tool(t) for t in active]
        if self._skill_registry.list():
            lc_tools.append(to_langchain_tool(LoadSkillTool(self._skill_registry)))
        self._agent = create_react_agent(
            model=self._llm,
            tools=lc_tools,
            prompt=self._build_prompt(),
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
    def _extract_tool_calls(messages: Sequence[BaseMessage]) -> List[Dict[str, Any]]:
        """Pull every tool call the LLM emitted out of the agent trace,
        in order. Each entry is ``{"name": str, "args": dict}``."""
        calls: List[Dict[str, Any]] = []
        for msg in messages:
            tcs = getattr(msg, "tool_calls", None)
            if not tcs:
                continue
            for tc in tcs:
                # LangChain tool_calls are dicts: {name, args, id, type}
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                if name:
                    calls.append({"name": name, "args": args or {}})
        return calls

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
                parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                joined = "".join(parts).strip()
                if joined:
                    return joined
                continue
            text = str(content).strip()
            if text:
                return text
        return ""
