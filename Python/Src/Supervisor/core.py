"""Supervisor — the outer-layer LLM tool-calling orchestrator.

Runs a **self-controlled** tool-calling loop (see ``agent_loop.py``) over an
OpenAI-compatible endpoint. The same code path serves Ollama
(``/v1``) and cloud APIs like DeepSeek — switching providers is config-only
(``LLM.Agent`` in ``GlobalConfig.yaml``). LangGraph's ``create_react_agent``
black box is gone; owning the loop gives us tool-result protection,
errors-as-data, retries, and a seam for context compression.

Three cleanly separated concepts meet here (see ``tool.py`` / ``skill.py``):

  * **Tool**  — the only thing the LLM calls directly (function-calling).
    Wraps a primitive, a deterministic Workflow (the Phase 3-5 diagnosis
    graph), or a remote Agent (A2A).
  * **Skill** — loadable prompt / domain knowledge (``SKILL.md``), surfaced
    as a catalogue in the system prompt; the body is pulled in on demand via
    the built-in ``load_skill`` Tool.
  * **Agent** — an autonomous / remote delegate, reached *through* a Tool
    (e.g. ``RemoteA2ATool``), never called by the LLM directly.

Dynamic Tool registry (``register_tool`` / ``unregister_tool`` /
``enable_tool`` / ``disable_tool`` / ``register_tool_from_config`` /
``register_tools_from_path`` / ``register_remote_tool`` /
``register_remote_tools_from_yaml``) mutates a live ``OrderedDict``. Unlike
the old compiled-graph design, there is **no rebuild step** — the active
tool list is read fresh on every turn.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import openai
from pydantic import BaseModel
from datetime import datetime

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Middleware.GlobalConfig import GlobalConfig
from Python.Src.Supervisor.agent_loop import AgentLoop, make_dispatch
from Python.Src.Supervisor.memory import (
    MAX_SESSION_MEMORY_BYTES,
    SaveMemoryTool,
    build_memory_prompt_section,
    format_memories_for_injection,
    select_relevant_memories,
)
from Python.Src.Supervisor.session import SessionStore, default_store
from Python.Src.Supervisor.skill import AppendSkillMemoryTool, LoadSkillTool, SkillRegistry
from Python.Src.Supervisor.tool import Tool

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "你是变压器健康管控领域的助理。你可以调用下列工具来完成实际诊断、检索、"
    "历史查询等具体任务,也可以直接对用户的概念性 / 闲聊问题作答。\n\n"
    "调用工具的判断原则:\n"
    "  - 用户明确要求'诊断 / 体检 / 评估 / 查 RUL / 查健康指数' → 调 transformer_diagnosis\n"
    "  - 用户问'这台设备上次诊断结果 / 历史趋势' → 调 history_lookup(若已注册)\n"
    "  - 任务匹配某条'可用知识技能' → 先 load_skill 加载其正文, 再据此作答\n"
    "  - 多个可并行的独立子任务(如同时诊断/对比多台变压器), 或读多会撑爆上下文的探索 → "
    "用 spawn_agent 派子智能体(一次传多个任务会并发); 单个工具能办的小事不要 spawn\n"
    "  - 纯概念解释 / 寒暄 / follow-up(上一轮已给出的指标) → 直接作答, 不要重复调用工具\n"
    "  - 一次请求可以同时调多个独立工具, 提高效率\n\n"
    "工具返回结构化结果后, 用自然语言简洁回答用户; 数值类指标请直接引用, "
    "不要瞎编。"
)


def _configured(value: Any) -> bool:
    """A config value counts as set only if non-empty and not a placeholder."""
    return bool(value) and not str(value).startswith("YOUR_")


# Raw context windows by model family (tokens). Used to size the compression
# budget; overridable via LLM.Agent.EffectiveWindowOverride.
_MODEL_CONTEXT = {
    "deepseek": 128_000,
    "gpt-oss": 32_000,
    "qwen": 32_000,
    "llama": 32_000,
    "gpt-4o": 128_000,
}
_CONTEXT_RESERVE = 8_000   # leave room for the response
_COMPACT_TRIGGER = 0.85    # compact when est. history > this fraction of effective
_KEEP_RECENT_MESSAGES = 6  # ~3 exchanges kept verbatim after a compact


def _raw_window_for(model: str) -> int:
    m = model.lower()
    for key, win in _MODEL_CONTEXT.items():
        if key in m:
            return win
    return 32_000  # conservative default for unknown local models


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
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> None:
        if not tools:
            raise ValueError("Supervisor requires at least one Tool")

        llm = GlobalConfig.config.get("LLM", {})
        agent_cfg = llm.get("Agent") or {}
        local_cfg = llm.get("Local", {})

        # Pick the backend: the Agent section wins only when its APIKey is a
        # real key (so a placeholder DeepSeek block falls back to local Ollama
        # out of the box). Explicit constructor args always override.
        if _configured(agent_cfg.get("APIKey")):
            src = agent_cfg
            default_base = agent_cfg.get("BaseURL")
        else:
            src = local_cfg
            # Ollama exposes an OpenAI-compatible API under /v1.
            default_base = str(local_cfg.get("BaseURL", "http://localhost:11434")).rstrip("/") + "/v1"

        self._base_url = base_url or default_base
        self._api_key = api_key or src.get("APIKey") or "sk-noauth"
        self._model_name = model_name or src.get("ModelName") or "gpt-oss:120b-cloud"
        self._temperature = (
            temperature if temperature is not None
            else float(src.get("Temperature", 0.1))
        )
        max_tokens = int(agent_cfg.get("MaxTokens", 4096))
        timeout = float(src.get("Timeout", 120))
        max_retries = int(src.get("MaxRetries", 3))

        override = int(agent_cfg.get("EffectiveWindowOverride", 0) or 0)
        raw_window = override if override > 0 else _raw_window_for(self._model_name)
        self._effective_window = max(raw_window - _CONTEXT_RESERVE, 4000)

        client = openai.AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=timeout,
        )
        self._loop = AgentLoop(
            client,
            self._model_name,
            max_tokens=max_tokens,
            temperature=self._temperature,
            max_retries=max_retries,
            effective_window=self._effective_window,
        )

        self._store = session_store

        # Prompt-style Skills (SKILL.md). Surfaced as a catalogue in the
        # system prompt; bodies loaded on demand via the built-in load_skill.
        self._skill_registry = skill_registry or SkillRegistry.discover(skill_dirs)

        # ordered Tool registry: insertion order = display order. Disabled
        # tools stay here so enable/disable is non-destructive.
        self._tools: "OrderedDict[str, Tool]" = OrderedDict()
        self._disabled: Set[str] = set()
        self.register_tools(tools)
        # Tools present at construction (declared in tools.yaml) are built-in
        # and protected from removal — they are core platform capabilities.
        self._builtin: Set[str] = set(self._tools.keys())

        # Per-session memory-recall state (Supervisor is shared across
        # sessions, so keep surfaced/budget keyed by session id).
        self._recall_surfaced: Dict[str, Set[str]] = {}
        self._recall_bytes: Dict[str, int] = {}

    # =========================================================== dynamic API

    def register_tool(self, tool: Tool) -> str:
        """Register one tool (overwrite on name clash). Returns the name."""
        return self._add_one(tool)

    def register_tools(self, tools: Iterable[Tool]) -> List[str]:
        return [self._add_one(t) for t in tools]

    def is_builtin(self, name: str) -> bool:
        """Built-in tools (declared in tools.yaml) are protected from removal."""
        return name in self._builtin

    def unregister_tool(self, name: str) -> bool:
        if name in self._builtin:
            return False  # protected; callers should check is_builtin first
        present = name in self._tools
        self._tools.pop(name, None)
        self._disabled.discard(name)
        return present

    def disable_tool(self, name: str) -> bool:
        if name not in self._tools or name in self._disabled:
            return False
        self._disabled.add(name)
        return True

    def enable_tool(self, name: str) -> bool:
        if name not in self._tools or name not in self._disabled:
            return False
        self._disabled.discard(name)
        return True

    def register_tool_from_config(self, spec: Dict[str, Any]) -> str:
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
        from Python.Src.Supervisor.discovery import discover_tools_from_path

        discovered = discover_tools_from_path(directory, recursive=recursive)
        added: List[str] = []
        for t in discovered:
            name = getattr(t.card, "name", None)
            if not name:
                logger.warning("discovered object has no .card.name, skipping: %r", t)
                continue
            if name in self._tools:
                logger.info("tool %r already registered, leaving existing", name)
                continue
            added.append(self._add_one(t))
        return added

    def register_remote_tool(
        self,
        url: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        timeout_s: float = 30.0,
    ) -> str:
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
        from Python.Src.Supervisor.remote import load_remote_tools

        path = Path(yaml_path) if yaml_path else None
        new = load_remote_tools(yaml_path=path)
        fresh = [t for t in new if t.card.name not in self._tools]
        if not fresh:
            return []
        return self.register_tools(fresh)

    # ============================================================ skill API

    def reload_skills(self, skill_dirs: Optional[List[Path]] = None) -> List[str]:
        self._skill_registry = SkillRegistry.discover(skill_dirs)
        return self._skill_registry.names

    # ============================================================ chat path

    def chat(self, session_id: str, user_input: str) -> str:
        return self.chat_verbose(session_id, user_input)["answer"]

    def chat_verbose(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """Run one chat turn against ``session_id``.

        Returns ``{"answer": str, "tool_calls": [{"name", "args"}, ...]}``.

        NOTE: synchronous wrapper around the async pipeline via ``asyncio.run``
        — must NOT be called from inside a running event loop. The FastAPI
        routes are sync (``def``, run in a threadpool) and the CLI is sync,
        so this holds.
        """
        try:
            return asyncio.run(self._achat(session_id, user_input))
        except Exception as e:  # noqa: BLE001
            return {"answer": f"[supervisor 内部错误] {e}", "tool_calls": []}

    async def _achat(self, session_id: str, user_input: str) -> Dict[str, Any]:
        history = await self._maybe_compact_and_load(session_id)

        # Semantic memory recall — inject relevant cross-session memories
        # as a system-reminder before the model sees the new input.
        recalled = await self._recall_memories(session_id, user_input)
        if recalled:
            history = history + [
                {"role": "user", "content": format_memories_for_injection(recalled)}
            ]

        active = self._active_tools()
        by_name = {t.card.name: t for t in active}
        dispatch = make_dispatch(by_name)

        result = await self._loop.run(
            system_prompt=self._build_prompt(),
            history=history,
            user_input=user_input,
            tools=active,
            dispatch=dispatch,
        )
        answer = result["answer"] or "(模型未返回有效内容)"
        tool_calls = result.get("tool_calls", [])

        self._store.save_message(session_id, "user", user_input)
        self._store.save_message(session_id, "assistant", answer)
        return {"answer": answer, "tool_calls": tool_calls}

    async def chat_stream(self, session_id: str, user_input: str):
        """Streaming chat turn — async generator of events for SSE.

        Same pipeline as :meth:`_achat` (compact → recall → loop) but yields
        the loop's events live, then persists the final answer. Errors are
        emitted as an ``{"type":"error"}`` event, never raised into the
        SSE stream."""
        try:
            history = await self._maybe_compact_and_load(session_id)
            recalled = await self._recall_memories(session_id, user_input)
            if recalled:
                history = history + [
                    {"role": "user", "content": format_memories_for_injection(recalled)}
                ]
            active = self._active_tools()
            by_name = {t.card.name: t for t in active}
            dispatch = make_dispatch(by_name)

            final_answer = ""
            async for ev in self._loop.run_stream(
                system_prompt=self._build_prompt(),
                history=history,
                user_input=user_input,
                tools=active,
                dispatch=dispatch,
            ):
                if ev.get("type") == "final":
                    final_answer = ev.get("answer", "")
                yield ev
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": str(e)}
            final_answer = f"[supervisor 内部错误] {e}"

        self._store.save_message(session_id, "user", user_input)
        self._store.save_message(session_id, "assistant", final_answer or "(模型未返回有效内容)")

    def new_session(self) -> str:
        return self._store.create_session()

    # =============================================================== views

    @property
    def tool_names(self) -> List[str]:
        return [n for n in self._tools if n not in self._disabled]

    @property
    def all_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    @property
    def disabled_tool_names(self) -> List[str]:
        return [n for n in self._tools if n in self._disabled]

    @property
    def skill_names(self) -> List[str]:
        return self._skill_registry.names

    @property
    def tool_catalogue(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": n,
                "description": t.card.description,
                "disabled": n in self._disabled,
                "builtin": n in self._builtin,
            }
            for n, t in self._tools.items()
        ]

    @property
    def skill_catalogue(self) -> List[Dict[str, Any]]:
        return [
            {"name": s.name, "description": s.description}
            for s in self._skill_registry.list()
        ]

    @property
    def backend_info(self) -> Dict[str, Any]:
        return {"model": self._model_name, "base_url": self._base_url}

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

    def _active_tools(self) -> List[Tool]:
        """Tools exposed to the LLM this turn: enabled registry tools + the
        built-ins (load_skill when any prompt-Skill exists, save_memory always,
        spawn_agent for delegation).

        ``spawn_agent`` is built over the *other* active tools (its sub-agent
        pool) and excludes itself — sub-agents therefore cannot spawn
        (depth capped at 1)."""
        from Python.Src.Supervisor.subagent import SpawnAgentTool

        active: List[Tool] = [t for n, t in self._tools.items() if n not in self._disabled]
        if self._skill_registry.list():
            active.append(LoadSkillTool(self._skill_registry))
            active.append(AppendSkillMemoryTool(self._skill_registry))
        active.append(SaveMemoryTool())
        # spawn_agent sees everything above as its sub-agent pool (no nesting).
        pool = {t.card.name: t for t in active}
        active.append(SpawnAgentTool(self._loop, pool))
        return active

    def _build_prompt(self) -> str:
        prompt = _SYSTEM_PROMPT
        catalogue = self._skill_registry.catalogue_text()
        if catalogue:
            prompt += (
                "\n\n## 可用知识技能\n"
                "(用 load_skill(name) 加载正文+累积经验后再作答; "
                "若在使用某技能时学到可复用教训, 用 append_skill_memory 记下)\n" + catalogue
            )
        prompt += "\n\n" + build_memory_prompt_section()
        prompt += "\n 当前时间：" + self._get_time() 
        return prompt
    
    def _get_time(self) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        return current_date

    async def _side_query(self, system: str, user: str) -> str:
        return await self._loop.side_query(system, user)

    async def _recall_memories(self, session_id: str, user_input: str):
        """Semantic recall, gated: skip single-word queries and sessions whose
        cumulative recall budget is spent. Never raises — recall must not break
        a turn."""
        if not re.search(r"\s", user_input.strip()):
            return []
        if self._recall_bytes.get(session_id, 0) >= MAX_SESSION_MEMORY_BYTES:
            return []
        surfaced = self._recall_surfaced.setdefault(session_id, set())
        try:
            mems = await select_relevant_memories(user_input, self._side_query, surfaced)
        except Exception as e:  # noqa: BLE001
            logger.warning("memory recall failed for %s: %s", session_id, e)
            return []
        for m in mems:
            surfaced.add(m.path)
            self._recall_bytes[session_id] = (
                self._recall_bytes.get(session_id, 0) + len(m.content.encode("utf-8"))
            )
        return mems

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Cheap char/4 estimate — no extra API call."""
        return len(text) // 4

    def _summary_prefix(self, summary: str) -> List[Dict[str, Any]]:
        """Render a rolling summary as a user+assistant pair so message
        alternation stays clean for the next turn."""
        return [
            {"role": "user", "content": f"[对话摘要]\n{summary}"},
            {"role": "assistant", "content": "已了解之前的对话上下文。"},
        ]

    async def _maybe_compact_and_load(self, session_id: str) -> List[Dict[str, Any]]:
        """Load prior turns as OpenAI messages, summarising the older portion
        when the replayed history would crowd the context window.

        Our stored history is clean alternating user/assistant text (no tool
        messages), so slicing it anywhere is safe — no tool_use/tool_result
        pair can be orphaned. The rolling summary is persisted
        (``session_summaries``) so we never re-summarise the same turns."""
        summary_row = self._store.get_summary(session_id)
        prior_summary = summary_row["summary"] if summary_row else ""
        covered = summary_row["covered_until"] if summary_row else 0

        active = self._store.get_messages(session_id, after_id=covered)

        def render(rows: List[Dict[str, Any]], summary: str) -> List[Dict[str, Any]]:
            msgs: List[Dict[str, Any]] = []
            if summary:
                msgs.extend(self._summary_prefix(summary))
            msgs.extend(
                {"role": r["role"], "content": r["content"]}
                for r in rows
                if r["role"] in ("user", "assistant") and r["content"]
            )
            return msgs

        candidate = render(active, prior_summary)
        est = self._estimate_tokens(self._build_prompt()) + sum(
            self._estimate_tokens(m["content"]) for m in candidate
        )
        if est <= self._effective_window * _COMPACT_TRIGGER or len(active) <= _KEEP_RECENT_MESSAGES:
            return candidate

        # Compact: summarise everything except the most recent few messages.
        to_summarize = active[:-_KEEP_RECENT_MESSAGES]
        kept = active[-_KEEP_RECENT_MESSAGES:]
        try:
            new_summary = await self._loop.summarize(
                prior_summary,
                [{"role": r["role"], "content": r["content"]} for r in to_summarize],
            )
            new_covered = to_summarize[-1]["id"]
            self._store.upsert_summary(session_id, new_summary, new_covered)
            logger.info(
                "compacted session %s: summarised %d msgs up to id %d",
                session_id, len(to_summarize), new_covered,
            )
            return render(kept, new_summary)
        except Exception as e:  # noqa: BLE001 — compaction failure must not break chat
            logger.warning("auto-compact failed for %s: %s — using raw history", session_id, e)
            return candidate
