"""Self-controlled agent loop — the Supervisor's tool-calling engine.

Replaces LangGraph's ``create_react_agent`` black box with a loop we own,
modelled on the OpenAI-backend loop from the ``claude-code-from-scratch``
reference. Talks to any **OpenAI-compatible** endpoint — the same code path
serves Ollama (``http://localhost:11434/v1``) and cloud APIs like
DeepSeek — so switching providers is config-only.

Owning the loop buys us what the black box couldn't:
  * tool-result protection (truncate + persist-large-to-disk),
  * errors-as-data (a failing tool returns a string the model can read and
    recover from, never an opaque exception),
  * retry with backoff on transient API errors,
  * an iteration guard against weak models looping forever,
  * a clean seam for the Phase-2 compression pipeline.

The loop is intentionally stateless across turns: ``run()`` takes the
system prompt + prior history + the new user input, and returns the final
answer, the tool calls made, and the full message list. Session
persistence stays in the Supervisor / SessionStore.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.tool import Tool

logger = logging.getLogger(__name__)

# Tool-result guards (mirror the reference's Level-0 / Level-0.5).
MAX_RESULT_CHARS = 50_000          # hard truncation ceiling
PERSIST_THRESHOLD = 30 * 1024      # >30 KB → spill to disk, keep preview
PREVIEW_LINES = 200
# Guard against a weak model that keeps calling tools without converging.
MAX_TOOL_ITERATIONS = 25

# In-turn compression (operates on tool-result messages accumulated within
# one turn). Thresholds are fractions of the effective context window.
BUDGET_THRESHOLD = 0.50            # start shrinking tool results past 50%
BUDGET_TIGHT = 0.70               # shrink harder past 70%
SNIP_THRESHOLD = 0.60              # start snipping stale results past 60%
KEEP_RECENT_RESULTS = 3            # always keep the newest N tool results intact
SNIP_PLACEHOLDER = "[旧工具结果已省略 — 如需可重新调用]"

ToolDispatch = Callable[[str, Dict[str, Any]], Awaitable[str]]

_TOOL_RESULTS_DIR = Path(project_root) / "var" / "tool-results"


# ---------------------------------------------------------------------------
# Result protection
# ---------------------------------------------------------------------------

def truncate_result(result: str) -> str:
    """Keep head + tail when a result blows past ``MAX_RESULT_CHARS``.

    Head keeps structure (imports, opening of a report); tail keeps the
    parts that matter for command/diagnosis output (error summaries,
    final verdicts)."""
    if len(result) <= MAX_RESULT_CHARS:
        return result
    keep = (MAX_RESULT_CHARS - 60) // 2
    return (
        result[:keep]
        + f"\n\n[... truncated {len(result) - keep * 2} chars ...]\n\n"
        + result[-keep:]
    )


def persist_large_result(tool_name: str, result: str) -> str:
    """Spill a >30 KB result to disk and return a preview + path.

    Unlike truncation this is loss-less — the full output stays on disk and
    the model can fetch it later. Keeps huge diagnosis reports / remote JSON
    from flooding the context window."""
    if len(result.encode("utf-8")) <= PERSIST_THRESHOLD:
        return result
    try:
        _TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"{int(time.time() * 1000)}-{tool_name}.txt"
        fpath = _TOOL_RESULTS_DIR / fname
        fpath.write_text(result, encoding="utf-8")
        lines = result.split("\n")
        preview = "\n".join(lines[:PREVIEW_LINES])
        size_kb = len(result.encode("utf-8")) / 1024
        return (
            f"[结果过大 ({size_kb:.1f} KB, {len(lines)} 行), 完整内容已存到 {fpath}. "
            f"如需全文可读取该文件.]\n\n预览 (前 {PREVIEW_LINES} 行):\n{preview}"
        )
    except Exception as e:  # noqa: BLE001 — persistence must never break a turn
        logger.warning("persist_large_result failed: %s", e)
        return truncate_result(result)


def make_dispatch(tools_by_name: Dict[str, "Tool"]) -> "ToolDispatch":
    """Build an async tool dispatcher over a fixed name→Tool map.

    Shared by the Supervisor (parent turn) and sub-agents (restricted tool
    subset). Errors are data: a missing tool / bad args / raised exception
    all come back as a string the model can read and recover from. Sync
    ``Tool.run`` is offloaded to a thread so it never blocks the loop."""
    async def dispatch(name: str, args: Dict[str, Any]) -> str:
        tool = tools_by_name.get(name)
        if tool is None:
            return f"Unknown tool: {name}. Available: {', '.join(tools_by_name) or '(none)'}"
        try:
            result = await asyncio.to_thread(tool.run, **args)
        except TypeError as e:
            return f"Tool error ({name}): bad arguments — {e}"
        except Exception as e:  # noqa: BLE001 — errors are data
            return f"Tool error ({name}): {e}"
        if isinstance(result, BaseModel):
            return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        return str(result)
    return dispatch


def tool_to_openai_schema(tool: Tool) -> Dict[str, Any]:
    """Build an OpenAI ``tools=[...]`` entry from a :class:`Tool`'s card.

    The input model's JSON Schema (Pydantic v2) becomes the function
    parameters — the same contract the LLM's tool-calling interface needs."""
    card = tool.card
    return {
        "type": "function",
        "function": {
            "name": card.name,
            "description": card.description,
            "parameters": card.input_model.model_json_schema(),
        },
    }


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------

def _is_retryable(error: Exception) -> bool:
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    if status in (408, 429, 500, 502, 503, 504, 529):
        return True
    name = type(error).__name__
    if name in ("APITimeoutError", "APIConnectionError", "InternalServerError"):
        return True
    msg = str(error).lower()
    return any(s in msg for s in ("overloaded", "timeout", "connection", "econnreset"))


async def _with_retry(fn: Callable[[], Awaitable[Any]], max_retries: int = 3) -> Any:
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as error:  # noqa: BLE001
            if attempt >= max_retries or not _is_retryable(error):
                raise
            delay = min(2 ** attempt, 30) + (time.time() % 1)
            logger.warning(
                "LLM call failed (%s), retry %d/%d in %.1fs",
                type(error).__name__, attempt + 1, max_retries, delay,
            )
            await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

class AgentLoop:
    """Owns one OpenAI-compatible client and runs the tool-calling loop."""

    def __init__(
        self,
        client: Any,                 # openai.AsyncOpenAI
        model: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        max_retries: int = 3,
        effective_window: int = 120_000,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_retries = max_retries
        self._effective_window = max(effective_window, 4000)

    async def run(
        self,
        *,
        system_prompt: str,
        history: List[Dict[str, Any]],
        user_input: str,
        tools: List[Tool],
        dispatch: ToolDispatch,
    ) -> Dict[str, Any]:
        """Run one user turn to completion (through any number of tool calls).

        Returns ``{"answer", "tool_calls", "messages", "usage"}``.
        """
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        tool_schemas = [tool_to_openai_schema(t) for t in tools] or None
        tool_calls_made: List[Dict[str, Any]] = []
        usage = {"input": 0, "output": 0}
        last_input_tokens = 0
        answer = ""

        for _ in range(MAX_TOOL_ITERATIONS):
            # In-turn compression: shrink/snip accumulated tool results before
            # each call once context pressure builds. No-op on the first call
            # (last_input_tokens == 0) and while utilization stays low.
            self._compress_in_turn(messages, last_input_tokens)

            resp = await _with_retry(
                lambda: self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tool_schemas,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                ),
                max_retries=self._max_retries,
            )

            if getattr(resp, "usage", None):
                last_input_tokens = getattr(resp.usage, "prompt_tokens", 0) or 0
                usage["input"] += last_input_tokens
                usage["output"] += getattr(resp.usage, "completion_tokens", 0) or 0

            msg = resp.choices[0].message
            messages.append(self._assistant_to_dict(msg))

            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                answer = msg.content or ""
                break

            for tc in tool_calls:
                if getattr(tc, "type", "function") != "function":
                    continue
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls_made.append({"name": name, "args": args})

                raw = await dispatch(name, args)
                result = persist_large_result(name, truncate_result(raw))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            # Loop exhausted without a final text answer.
            answer = answer or "(已达到最大工具调用轮数, 停止以避免死循环)"

        return {
            "answer": answer,
            "tool_calls": tool_calls_made,
            "messages": messages,
            "usage": usage,
        }

    @staticmethod
    def _assistant_to_dict(msg: Any) -> Dict[str, Any]:
        """Serialise an assistant message (with any tool_calls) back into a
        plain dict suitable for the next request."""
        out: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in tool_calls
                if getattr(tc, "type", "function") == "function"
            ]
        return out

    # ───────────────────────────── in-turn compression ─────────────────

    def _compress_in_turn(self, messages: List[Dict[str, Any]], last_input_tokens: int) -> None:
        """Budget + snip the tool-result messages accumulated this turn.

        Cheap (no API), runs before each call. Operates on OpenAI-shape
        ``{"role": "tool", "content": str}`` messages. Cross-turn history is
        already lean (no tool results), so this targets in-turn bloat from
        multi-call turns and large results."""
        if not last_input_tokens:
            return
        utilization = last_input_tokens / self._effective_window
        self._budget_tool_results(messages, utilization)
        self._snip_stale_results(messages, utilization)

    @staticmethod
    def _budget_tool_results(messages: List[Dict[str, Any]], utilization: float) -> None:
        if utilization < BUDGET_THRESHOLD:
            return
        budget = 15_000 if utilization > BUDGET_TIGHT else 30_000
        for msg in messages:
            if msg.get("role") == "tool" and isinstance(msg.get("content"), str) \
                    and len(msg["content"]) > budget:
                keep = (budget - 80) // 2
                msg["content"] = (
                    msg["content"][:keep]
                    + f"\n\n[... budgeted: {len(msg['content']) - keep * 2} chars truncated ...]\n\n"
                    + msg["content"][-keep:]
                )

    @staticmethod
    def _snip_stale_results(messages: List[Dict[str, Any]], utilization: float) -> None:
        if utilization < SNIP_THRESHOLD:
            return
        tool_idx = [
            i for i, m in enumerate(messages)
            if m.get("role") == "tool" and isinstance(m.get("content"), str)
            and m["content"] != SNIP_PLACEHOLDER
        ]
        if len(tool_idx) <= KEEP_RECENT_RESULTS:
            return
        for i in tool_idx[: len(tool_idx) - KEEP_RECENT_RESULTS]:
            messages[i]["content"] = SNIP_PLACEHOLDER

    # ───────────────────────────── summarisation ───────────────────────

    async def summarize(self, prior_summary: str, turns: List[Dict[str, Any]]) -> str:
        """One-shot summary of older turns for cross-turn auto-compact.

        Preserves the things this domain must not lose: equipment ids,
        diagnosis numbers (HI / RUL / risk), verdicts, and user decisions."""
        convo = "\n".join(
            f"{m.get('role', '?')}: {m.get('content', '')}" for m in turns
        )
        prefix = f"已有摘要:\n{prior_summary}\n\n" if prior_summary else ""
        user = (
            prefix
            + "以下是较早的对话, 请压缩成一段简洁中文摘要, 必须保留: 设备ID、"
            "诊断数值(健康指数/RUL/风险评分)、故障判定结论、用户的决定与偏好。"
            "丢弃寒暄与冗余。\n\n对话:\n" + convo
        )
        resp = await _with_retry(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "你是对话摘要器, 简洁但不丢关键事实。"},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                max_tokens=1024,
            ),
            max_retries=self._max_retries,
        )
        return resp.choices[0].message.content or ""

    async def side_query(self, system: str, user: str, max_tokens: int = 256) -> str:
        """A small auxiliary completion (no tools) — used by memory recall to
        semantically select relevant memories. Kept cheap."""
        resp = await _with_retry(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                max_tokens=max_tokens,
            ),
            max_retries=self._max_retries,
        )
        return resp.choices[0].message.content or ""
