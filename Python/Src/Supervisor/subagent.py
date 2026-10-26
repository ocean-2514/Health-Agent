"""Sub-agent system (fork-return) — MUSE/Claude-Code style delegation.

The orchestrating LLM can spawn one or more **sub-agents** via the built-in
``spawn_agent`` tool. Each sub-agent is the same :class:`AgentLoop` run with
a fixed *role* (a restricted tool subset + a role system prompt) over an
**isolated** context (fresh message history — it does NOT see the parent's
conversation). The sub-agent's final text is returned to the parent as the
tool result; large intermediate tool outputs stay inside the sub-agent,
keeping the parent's context lean (context isolation is the core value).

Design decisions (confirmed):
  * **Fixed roles, LLM picks role + writes the task** — not free-form
    runtime role authoring. Bounded tools = auditable, testable, safe for a
    regulated domain. Two roles: ``explore`` (read-only) and ``general``
    (full minus spawn).
  * **Concurrent fork-return** — one ``spawn_agent`` call takes a list of
    tasks and runs them with ``asyncio.gather`` (the multi-equipment case).
  * **No nesting** — sub-agents never receive ``spawn_agent`` (the pool we
    hand them already excludes it), so depth is capped at 1: prevents
    exponential token blowup.
  * **Bounded + isolated** — concurrency cap, per-task error isolation
    (one sub-agent failing returns an error string, others continue).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.agent_loop import AgentLoop, make_dispatch
from Python.Src.Supervisor.tool import Tool, ToolCard

SPAWN_TOOL_NAME = "spawn_agent"
MAX_SUBAGENTS = 5            # concurrency / fan-out cap per spawn_agent call
MAX_TASKS = 8               # hard ceiling on tasks accepted in one call

# explore role: read-only investigation. Curated allowlist by name; remote
# A2A tools (queries, no local side effect) are also included.
_EXPLORE_TOOL_NAMES = {"history_lookup", "load_skill"}

_ROLE_PROMPTS = {
    "explore": (
        "你是一个**只读**探索子智能体。只查不改:查历史诊断、加载领域知识、检索缺陷资料。"
        "不要尝试运行诊断或写入。完成后用一段简洁中文返回你的发现与结论。"
    ),
    "general": (
        "你是一个通用子智能体,独立完成被指派的子任务(可调用包括 transformer_diagnosis 在内的工具)。"
        "完成后用一段简洁中文返回结果与关键指标。"
    ),
}


def _is_remote_tool(tool: Tool) -> bool:
    return type(tool).__name__ == "RemoteA2ATool"


def sub_agent_tools(role: str, pool: Dict[str, Tool]) -> List[Tool]:
    """Resolve the tool subset for a role from the parent's tool pool.

    ``pool`` already excludes ``spawn_agent`` (no nesting). For ``explore``
    we keep only read-only tools; ``general`` gets the whole pool."""
    if role == "explore":
        return [
            t for name, t in pool.items()
            if name in _EXPLORE_TOOL_NAMES or _is_remote_tool(t)
        ]
    return list(pool.values())  # general


# ─── IO contracts ───────────────────────────────────────────────────────

class SubAgentTask(BaseModel):
    type: str = Field("general", description="子智能体角色: 'explore'(只读探索) 或 'general'(全能)")
    description: str = Field(..., description="子任务的简短描述 (3-8 字)")
    prompt: str = Field(
        ...,
        description="给子智能体的完整自包含指令 (它看不到当前对话, 需把所需上下文写全)",
    )


class SubAgentResult(BaseModel):
    type: str
    description: str
    text: str = ""
    success: bool = True
    error: Optional[str] = None
    tokens: int = 0


class SpawnAgentInput(BaseModel):
    tasks: List[SubAgentTask] = Field(
        ...,
        description="一个或多个子任务; 传多个会并发执行 (用于多设备并行/对比等独立子任务)",
    )


class SpawnAgentOutput(BaseModel):
    results: List[SubAgentResult] = Field(default_factory=list)


class SpawnAgentTool:
    """Built-in Tool: launch sub-agents (fork-return), optionally concurrently.

    Reuses the parent's :class:`AgentLoop` (same client/model) — the loop is
    stateless per run, and ``openai.AsyncOpenAI`` is concurrency-safe, so
    several sub-agents can run in parallel. The tool pool handed in already
    excludes ``spawn_agent`` (no nesting)."""

    card = ToolCard(
        name=SPAWN_TOOL_NAME,
        description=(
            "派生一个或多个子智能体独立完成子任务并返回结果 (fork-return)。"
            "用于: ①可并行的独立子任务(如同时诊断/对比多台变压器) ②读多、会撑爆主上下文的"
            "探索(用 explore 只返回结论)。角色: explore(只读) / general(全能)。"
            "传 tasks 列表, 多个会并发。不要为一次普通工具调用就 spawn。"
        ),
        input_model=SpawnAgentInput,
        output_model=SpawnAgentOutput,
    )

    def __init__(self, loop: AgentLoop, pool: Dict[str, Tool],
                 max_concurrency: int = MAX_SUBAGENTS) -> None:
        # pool MUST exclude spawn_agent itself (enforced by caller)
        self._loop = loop
        self._pool = {n: t for n, t in pool.items() if n != SPAWN_TOOL_NAME}
        self._max_concurrency = max_concurrency

    def run(self, **kwargs: Any) -> SpawnAgentOutput:
        inp = SpawnAgentInput(**kwargs)
        tasks = inp.tasks[:MAX_TASKS]
        # run() is invoked via asyncio.to_thread in the parent dispatch, so
        # there is no running loop in this thread → asyncio.run is safe and
        # gives us true concurrency across sub-agents.
        return asyncio.run(self._run_all(tasks))

    async def _run_all(self, tasks: List[SubAgentTask]) -> SpawnAgentOutput:
        sem = asyncio.Semaphore(self._max_concurrency)

        async def guarded(task: SubAgentTask) -> SubAgentResult:
            async with sem:
                return await self._run_one(task)

        results = await asyncio.gather(*[guarded(t) for t in tasks])
        return SpawnAgentOutput(results=list(results))

    async def _run_one(self, task: SubAgentTask) -> SubAgentResult:
        role = task.type if task.type in _ROLE_PROMPTS else "general"
        tools = sub_agent_tools(role, self._pool)
        by_name = {t.card.name: t for t in tools}
        dispatch = make_dispatch(by_name)
        try:
            r = await self._loop.run(
                system_prompt=_ROLE_PROMPTS[role],
                history=[],                      # isolated context
                user_input=task.prompt,
                tools=tools,
                dispatch=dispatch,
            )
            return SubAgentResult(
                type=role, description=task.description,
                text=r["answer"], success=True,
                tokens=r.get("usage", {}).get("input", 0) + r.get("usage", {}).get("output", 0),
            )
        except Exception as e:  # noqa: BLE001 — sub-agent failure must not crash parent
            return SubAgentResult(
                type=role, description=task.description,
                text="", success=False, error=str(e),
            )
