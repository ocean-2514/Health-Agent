"""Skill — loadable prompt / domain knowledge (the *real* skill).

This is the prompt-style notion of a Skill (as in the Claude Agent SDK /
CodeWhale ``SKILL.md`` convention), **not** a callable. A Skill is a
folder containing a ``SKILL.md``:

    skills/
      dga-interpretation/
        SKILL.md        ← YAML frontmatter (name, description) + markdown body
        ...             ← optional companion files

The body is domain expertise — "how to read DGA ratios", "how to write a
maintenance recommendation", standards procedures — that the LLM loads
into context *on demand*, not a function it executes.

Two-step disclosure (progressive disclosure, to spare the prompt budget):

  1. The Supervisor injects a one-line **catalogue** (name + description)
     of every Skill into the system prompt, so the LLM knows what exists.
  2. When the LLM judges a Skill relevant it calls the ``load_skill`` Tool
     (see :class:`LoadSkillTool`), which returns the full body as the tool
     result — i.e. injected into the next turn's context.

Contrast with ``tool.py``: a *Tool* is something the LLM calls to *act*;
a *Skill* is knowledge the LLM loads to *know how to act*.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.tool import ToolCard

MAX_DESCRIPTION_CHARS = 280
MAX_DISCOVERY_DEPTH = 6
SKILL_MEMORY_FILENAME = "SKILL.memory.md"
MAX_SKILL_MEMORY_CHARS = 4000   # cap surfaced per-skill memory


# ---------------------------------------------------------------------------
# Skill data + registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Skill:
    """A parsed ``SKILL.md`` definition."""

    name: str
    description: str
    body: str
    path: Path
    companion_files: List[Path] = field(default_factory=list)


def default_skill_dirs(workspace: Optional[Path] = None) -> List[Path]:
    """Directories searched for ``SKILL.md``, highest precedence first.

    Project-level under the repo, then a user-global location — mirrors the
    CodeWhale / agentskills layout so skills authored for other Claude-
    compatible tools are picked up too."""
    root = Path(workspace or project_root)
    dirs = [
        root / "skills",
        root / ".agents" / "skills",
    ]
    home = Path.home()
    dirs.append(home / ".healthagent" / "skills")
    dirs.append(home / ".claude" / "skills")
    return dirs


def _parse_skill_md(path: Path, content: str) -> Optional[Skill]:
    """Parse a ``SKILL.md`` with simple ``--- yaml --- body`` frontmatter.

    Returns ``None`` (caller skips) if there's no frontmatter or no name.
    """
    if not content.lstrip().startswith("---"):
        return None
    stripped = content.lstrip()
    # split off the first frontmatter block
    rest = stripped[3:]
    end = rest.find("\n---")
    if end == -1:
        return None
    front = rest[:end]
    body = rest[end + 4:].lstrip("\n")

    meta: Dict[str, str] = {}
    for line in front.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip("'\"")

    name = meta.get("name")
    if not name:
        return None
    description = meta.get("description", "")[:MAX_DESCRIPTION_CHARS]

    companions = []
    skill_dir = path.parent
    for sibling in sorted(skill_dir.iterdir()):
        if sibling.is_file() and sibling.name != "SKILL.md":
            companions.append(sibling)

    return Skill(
        name=name,
        description=description,
        body=body,
        path=path,
        companion_files=companions,
    )


# ---------------------------------------------------------------------------
# Skill-level memory (MUSE-style): each skill carries a SKILL.memory.md next
# to its SKILL.md, accumulating lessons / caveats / corrections across tasks.
# Surfaced alongside the skill body on load, so the agent benefits from
# previously-learned experience without re-deriving it.
# ---------------------------------------------------------------------------

def skill_memory_path(skill: "Skill") -> Path:
    return skill.path.parent / SKILL_MEMORY_FILENAME


def read_skill_memory(skill: "Skill") -> str:
    p = skill_memory_path(skill)
    if not p.is_file():
        return ""
    try:
        text = p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if len(text) > MAX_SKILL_MEMORY_CHARS:
        text = text[-MAX_SKILL_MEMORY_CHARS:]  # keep the most recent lessons
    return text


def append_skill_memory(skill: "Skill", note: str) -> bool:
    """Append a dated lesson to the skill's memory file (create if missing).
    Returns False if the location is not writable (e.g. a read-only global
    skill dir)."""
    note = note.strip()
    if not note:
        return False
    p = skill_memory_path(skill)
    header = f"# {skill.name} — 经验记忆\n\n" if not p.exists() else ""
    entry = f"- [{date.today().isoformat()}] {note}\n"
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(header + entry)
        return True
    except OSError:
        return False


class SkillRegistry:
    """In-memory registry of discovered ``SKILL.md`` skills."""

    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    # -------------------------------------------------------- discovery

    @classmethod
    def discover(cls, dirs: Optional[List[Path]] = None) -> "SkillRegistry":
        reg = cls()
        for d in dirs or default_skill_dirs():
            if d.is_dir():
                reg._scan(d, depth=0)
        return reg

    def _scan(self, directory: Path, depth: int) -> None:
        if depth > MAX_DISCOVERY_DEPTH:
            return
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if skill_md.is_file():
                try:
                    skill = _parse_skill_md(skill_md, skill_md.read_text(encoding="utf-8"))
                except OSError:
                    skill = None
                if skill and skill.name not in self._skills:
                    # first-wins precedence (earlier dirs = higher priority)
                    self._skills[skill.name] = skill
                # a dir that IS a skill is not descended into
                continue
            self._scan(entry, depth + 1)

    # -------------------------------------------------------- access

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list(self) -> List[Skill]:
        return list(self._skills.values())

    @property
    def names(self) -> List[str]:
        return list(self._skills.keys())

    def catalogue_text(self) -> str:
        """One line per skill (name + description) for the system prompt.

        Returns "" when no skills are installed so the caller can omit the
        whole ``## Skills`` section."""
        skills = self.list()
        if not skills:
            return ""
        lines = [
            f"- `{s.name}` — {s.description}" for s in skills
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# load_skill — the built-in Tool that injects a skill body into context
# ---------------------------------------------------------------------------

class LoadSkillInput(BaseModel):
    name: str = Field(
        ...,
        description="技能 id (系统提示 `## 可用知识技能` 列表里的 name).",
    )


class LoadSkillOutput(BaseModel):
    name: str
    found: bool
    body: str = ""
    memory: str = Field(
        "", description="该技能跨任务累积的经验记忆 (失败模式/纠正/注意事项), 可能为空"
    )
    companion_files: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class LoadSkillTool:
    """Built-in Tool: load a Skill's ``SKILL.md`` body into the next turn.

    Always registered by the Supervisor when at least one Skill exists.
    Returns the full body as the tool result so the LLM gains the domain
    knowledge it needs for the current task. One call — no separate
    list_dir / read_file dance.
    """

    card = ToolCard(
        name="load_skill",
        description=(
            "加载一个领域知识技能(SKILL.md 正文)到上下文. 当用户点名某技能, "
            "或任务明显匹配系统提示 `## 可用知识技能` 里列出的某条时调用. "
            "返回该技能的完整指导正文供你据此作答."
        ),
        input_model=LoadSkillInput,
        output_model=LoadSkillOutput,
    )

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def run(self, **kwargs: Any) -> LoadSkillOutput:
        inp = LoadSkillInput(**kwargs)
        skill = self._registry.get(inp.name)
        if skill is None:
            avail = ", ".join(self._registry.names) or "(无)"
            return LoadSkillOutput(
                name=inp.name,
                found=False,
                error=f"未找到技能 '{inp.name}'. 可用: {avail}",
            )
        return LoadSkillOutput(
            name=skill.name,
            found=True,
            body=skill.body,
            memory=read_skill_memory(skill),
            companion_files=[str(p) for p in skill.companion_files],
        )


# ---------------------------------------------------------------------------
# append_skill_memory — built-in Tool to record a per-skill lesson
# ---------------------------------------------------------------------------

class AppendSkillMemoryInput(BaseModel):
    skill_name: str = Field(..., description="要记录经验的技能 id")
    note: str = Field(
        ...,
        description="一条经验/教训/注意事项 (如: 失败模式、输入格式坑、专家纠正)。简洁一句。",
    )


class AppendSkillMemoryOutput(BaseModel):
    saved: bool
    skill_name: str
    error: Optional[str] = None


class AppendSkillMemoryTool:
    """Built-in Tool: append a lesson to a skill's memory.

    Call when you learn something durable about a skill — a correction the
    user gave, a failure mode, an input quirk — so future loads of that skill
    surface the lesson. Do NOT record one-off task details."""

    card = ToolCard(
        name="append_skill_memory",
        description=(
            "给某个知识技能追加一条经验记忆 (失败模式/输入坑/用户纠正). "
            "当你在使用某技能时学到可复用的教训时调用; 下次加载该技能会自动带出. "
            "不要记一次性任务细节。"
        ),
        input_model=AppendSkillMemoryInput,
        output_model=AppendSkillMemoryOutput,
    )

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def run(self, **kwargs: Any) -> AppendSkillMemoryOutput:
        inp = AppendSkillMemoryInput(**kwargs)
        skill = self._registry.get(inp.skill_name)
        if skill is None:
            avail = ", ".join(self._registry.names) or "(无)"
            return AppendSkillMemoryOutput(
                saved=False, skill_name=inp.skill_name,
                error=f"未找到技能 '{inp.skill_name}'. 可用: {avail}",
            )
        ok = append_skill_memory(skill, inp.note)
        return AppendSkillMemoryOutput(
            saved=ok, skill_name=inp.skill_name,
            error=None if ok else "记忆文件不可写 (可能是只读的全局技能目录)",
        )
