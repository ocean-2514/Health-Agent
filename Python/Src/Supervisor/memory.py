"""Cross-session memory — file-based, 4-type, with MEMORY.md index +
semantic recall. Ported from the ``claude-code-from-scratch`` reference and
adapted to our platform.

Key adaptation: we are not a coding agent and have no ``write_file`` tool, so
memories are saved through a built-in :class:`SaveMemoryTool` the LLM calls
(name / description / type / content). Recall is semantic — a side-query to
the same backend (DeepSeek / Ollama) picks which memories are relevant to the
current question, rather than keyword matching.

Only save what cannot be derived from current project / diagnosis state:
  * **user**      — who the user is (role, preferences, expertise)
  * **feedback**  — corrections / confirmations about how to behave (+ why)
  * **project**   — ongoing goals, decisions, deadlines (absolute dates)
  * **reference** — pointers to external systems (dashboards, tickets)

The MEMORY.md index is loaded into the system prompt every turn, so it must
stay one-line-per-entry; full bodies are pulled in on demand by recall.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.tool import ToolCard

VALID_TYPES = {"user", "feedback", "project", "reference"}
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25_000
MAX_MEMORY_BYTES_PER_FILE = 4096
MAX_SESSION_MEMORY_BYTES = 60 * 1024   # cumulative recall budget per session
MAX_RECALL = 5

# A side-query callable: async (system, user) -> str
SideQueryFn = Callable[[str, str], Awaitable[str]]


# ─── paths ──────────────────────────────────────────────────────────────

def get_memory_dir() -> Path:
    d = Path(project_root) / "var" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path() -> Path:
    return get_memory_dir() / "MEMORY.md"


def _slugify(text: str) -> str:
    # Keep unicode word chars so Chinese names don't all collapse to the same
    # slug (which would make same-type memories overwrite each other).
    s = re.sub(r"[^\w]+", "_", text.strip().lower(), flags=re.UNICODE).strip("_")
    if not s:
        s = "mem_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return s[:40]


# ─── frontmatter (simple key: value) ────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[Dict[str, str], str]:
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, content
    end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end == -1:
        return {}, content
    meta: Dict[str, str] = {}
    for i in range(1, end):
        if ":" in lines[i]:
            k, _, v = lines[i].partition(":")
            if k.strip():
                meta[k.strip()] = v.strip().strip("'\"")
    return meta, "\n".join(lines[end + 1:]).strip()


def format_frontmatter(meta: Dict[str, str], body: str) -> str:
    out = ["---"]
    out.extend(f"{k}: {v}" for k, v in meta.items())
    out.append("---")
    out.append("")
    out.append(body)
    return "\n".join(out)


# ─── entries / CRUD ─────────────────────────────────────────────────────

class MemoryEntry:
    __slots__ = ("name", "description", "type", "filename", "content")

    def __init__(self, name, description, type, filename, content):
        self.name = name
        self.description = description
        self.type = type
        self.filename = filename
        self.content = content


def list_memories() -> List[MemoryEntry]:
    d = get_memory_dir()
    entries: List[MemoryEntry] = []
    for f in sorted(d.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        try:
            meta, body = parse_frontmatter(f.read_text(encoding="utf-8"))
            if not meta.get("name") or not meta.get("type"):
                continue
            t = meta["type"] if meta["type"] in VALID_TYPES else "project"
            entries.append(MemoryEntry(meta["name"], meta.get("description", ""),
                                       t, f.name, body))
        except Exception:
            pass
    entries.sort(key=lambda e: (d / e.filename).stat().st_mtime, reverse=True)
    return entries


def save_memory(name: str, description: str, type: str, content: str) -> str:
    if type not in VALID_TYPES:
        type = "project"
    d = get_memory_dir()
    filename = f"{type}_{_slugify(name)}.md"
    text = format_frontmatter(
        {"name": name, "description": description, "type": type}, content
    )
    (d / filename).write_text(text, encoding="utf-8")
    _update_index()
    return filename


def delete_memory(filename: str) -> bool:
    fp = get_memory_dir() / filename
    if not fp.exists():
        return False
    fp.unlink()
    _update_index()
    return True


def _update_index() -> None:
    lines = ["# Memory Index", ""]
    for m in list_memories():
        lines.append(f"- [{m.name}]({m.filename}) ({m.type}) — {m.description}")
    _index_path().write_text("\n".join(lines), encoding="utf-8")


def load_memory_index() -> str:
    p = _index_path()
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8")
    lines = content.split("\n")
    if len(lines) > MAX_INDEX_LINES:
        content = "\n".join(lines[:MAX_INDEX_LINES]) + "\n\n[... 索引过长已截断 ...]"
    if len(content.encode("utf-8")) > MAX_INDEX_BYTES:
        content = content[:MAX_INDEX_BYTES] + "\n\n[... 索引过大已截断 ...]"
    return content


# ─── headers / freshness ────────────────────────────────────────────────

class MemoryHeader:
    __slots__ = ("filename", "file_path", "mtime_ms", "description", "type")

    def __init__(self, filename, file_path, mtime_ms, description, type):
        self.filename = filename
        self.file_path = file_path
        self.mtime_ms = mtime_ms
        self.description = description
        self.type = type


def scan_memory_headers() -> List[MemoryHeader]:
    d = get_memory_dir()
    headers: List[MemoryHeader] = []
    for f in d.glob("*.md"):
        if f.name == "MEMORY.md":
            continue
        try:
            stat = f.stat()
            first30 = "\n".join(f.read_text(encoding="utf-8").split("\n")[:30])
            meta, _ = parse_frontmatter(first30)
            t = meta.get("type")
            headers.append(MemoryHeader(
                f.name, str(f), stat.st_mtime * 1000,
                meta.get("description"), t if t in VALID_TYPES else None,
            ))
        except Exception:
            pass
    headers.sort(key=lambda h: h.mtime_ms, reverse=True)
    return headers


def format_memory_manifest(headers: List[MemoryHeader]) -> str:
    lines = []
    for h in headers:
        tag = f"[{h.type}] " if h.type else ""
        ts = datetime.fromtimestamp(h.mtime_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        desc = f": {h.description}" if h.description else ""
        lines.append(f"- {tag}{h.filename} ({ts}){desc}")
    return "\n".join(lines)


def memory_age(mtime_ms: float) -> str:
    days = max(0, int((time.time() * 1000 - mtime_ms) / 86_400_000))
    return "今天" if days == 0 else ("昨天" if days == 1 else f"{days} 天前")


def memory_freshness_warning(mtime_ms: float) -> str:
    days = max(0, int((time.time() * 1000 - mtime_ms) / 86_400_000))
    if days <= 1:
        return ""
    return (f"这条记忆是 {days} 天前的, 是时间切片而非实时状态, "
            "断言前请对照当前代码/数据核实。")


# ─── semantic recall ────────────────────────────────────────────────────

class RelevantMemory:
    __slots__ = ("path", "content", "mtime_ms", "header")

    def __init__(self, path, content, mtime_ms, header):
        self.path = path
        self.content = content
        self.mtime_ms = mtime_ms
        self.header = header


_SELECT_PROMPT = (
    "你在为一个变压器健康管控助理挑选与用户当前问题相关的记忆。给你用户问题和"
    "可用记忆清单(文件名+描述)。返回一个 JSON 对象, 含 \"selected_memories\" "
    "数组(最多 5 个文件名), 只选你确信有用的; 不确定就不选; 都无关就返回空数组。"
)


async def select_relevant_memories(
    query: str,
    side_query: SideQueryFn,
    already_surfaced: set[str],
) -> List[RelevantMemory]:
    headers = scan_memory_headers()
    if not headers:
        return []
    candidates = [h for h in headers if h.file_path not in already_surfaced]
    if not candidates:
        return []
    manifest = format_memory_manifest(candidates)
    try:
        text = await side_query(
            _SELECT_PROMPT, f"用户问题: {query}\n\n可用记忆:\n{manifest}"
        )
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return []
        selected = set(json.loads(match.group(0)).get("selected_memories", []))
        chosen = [h for h in candidates if h.filename in selected][:MAX_RECALL]
        out: List[RelevantMemory] = []
        for h in chosen:
            content = Path(h.file_path).read_text(encoding="utf-8")
            if len(content.encode("utf-8")) > MAX_MEMORY_BYTES_PER_FILE:
                content = content[:MAX_MEMORY_BYTES_PER_FILE] + "\n\n[... 记忆过大已截断 ...]"
            fresh = memory_freshness_warning(h.mtime_ms)
            header = (f"{fresh}\n\n记忆: {h.file_path}:" if fresh
                      else f"记忆 (存于 {memory_age(h.mtime_ms)}): {h.file_path}:")
            out.append(RelevantMemory(h.file_path, content, h.mtime_ms, header))
        return out
    except Exception as e:  # noqa: BLE001 — recall must never break a turn
        return []


def format_memories_for_injection(memories: List[RelevantMemory]) -> str:
    return "\n\n".join(
        f"<system-reminder>\n{m.header}\n\n{m.content}\n</system-reminder>"
        for m in memories
    )


# ─── system-prompt section ──────────────────────────────────────────────

def build_memory_prompt_section() -> str:
    index = load_memory_index()
    body = (
        "# 记忆系统\n\n"
        "你有一个跨会话的文件式记忆。用内置工具 save_memory 保存, 用 4 种类型:\n"
        "- user: 用户身份/偏好/背景\n"
        "- feedback: 对你行为的纠正或肯定 (正文写明 Why + 如何应用)\n"
        "- project: 进行中的目标/决策/截止日期 (相对日期转绝对)\n"
        "- reference: 外部系统的定位 (看板/工单/URL)\n\n"
        "不要保存: 能从代码/诊断数据/历史推导的东西; 一次性任务细节。\n"
        "相关记忆会在需要时通过 <system-reminder> 自动注入, 你不必主动检索。\n"
    )
    if index:
        body += "\n## 当前记忆索引\n" + index
    else:
        body += "\n(暂无记忆)"
    return body


# ─── SaveMemoryTool (built-in) ──────────────────────────────────────────

class SaveMemoryInput(BaseModel):
    name: str = Field(..., description="记忆的简短名称")
    description: str = Field(..., description="一句话描述 (会进索引)")
    type: str = Field(..., description="user | feedback | project | reference")
    content: str = Field(..., description="记忆正文; feedback/project 请写明 Why 与如何应用")


class SaveMemoryOutput(BaseModel):
    saved: bool
    filename: str = ""
    error: Optional[str] = None


class SaveMemoryTool:
    """Built-in Tool the LLM calls to persist a cross-session memory."""

    card = ToolCard(
        name="save_memory",
        description=(
            "保存一条跨会话记忆 (user/feedback/project/reference 四类之一). "
            "用于: 了解到用户身份偏好、收到行为纠正/肯定、项目决策或外部系统定位时. "
            "不要保存能从代码/诊断数据推导的内容。"
        ),
        input_model=SaveMemoryInput,
        output_model=SaveMemoryOutput,
    )

    def run(self, **kwargs: Any) -> SaveMemoryOutput:
        inp = SaveMemoryInput(**kwargs)
        if inp.type not in VALID_TYPES:
            return SaveMemoryOutput(
                saved=False, error=f"type 必须是 {sorted(VALID_TYPES)} 之一"
            )
        try:
            fname = save_memory(inp.name, inp.description, inp.type, inp.content)
            return SaveMemoryOutput(saved=True, filename=fname)
        except Exception as e:  # noqa: BLE001
            return SaveMemoryOutput(saved=False, error=str(e))
