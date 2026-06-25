"""Offline smoke test for P3 cross-session memory.

No network. Scripted side-query drives semantic recall. Uses a temp memory
dir so it doesn't touch real memories.

Run::

    python -m Python.Src.Supervisor._memory_smoke
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import Python.Src.Supervisor.memory as memory


def main() -> int:
    print("=== P3 memory smoke test ===\n")

    tmp = Path(tempfile.mkdtemp(prefix="ha_mem_"))
    with patch.object(memory, "get_memory_dir", lambda: tmp):

        print("[1] save_memory + index")
        f1 = memory.save_memory("用户偏好简洁", "用户要简短回答", "feedback",
                                "用户说回答要简短。\n**Why:** 省时间。\n**如何应用:** 直接给结论。")
        f2 = memory.save_memory("tr01 检修窗口", "tr01 计划 2026-09 停电检修", "project",
                                "tr01 定于 2026-09 停电检修, 在此之前只做带电监测。")
        assert f1.startswith("feedback_") and f2.startswith("project_")
        idx = memory.load_memory_index()
        print(idx)
        assert "用户偏好简洁" in idx and "tr01 检修窗口" in idx

        print("\n[2] list_memories")
        mems = memory.list_memories()
        assert {m.type for m in mems} == {"feedback", "project"}
        print(f"  ok, {len(mems)} memories")

        print("\n[3] build_memory_prompt_section includes index + instructions")
        section = memory.build_memory_prompt_section()
        assert "# 记忆系统" in section and "save_memory" in section and "tr01 检修窗口" in section
        print("  ok")

        print("\n[4] semantic recall (scripted side-query picks the project memory)")
        async def fake_side_query(system, user):
            # pretend the model selected the project file
            return '{"selected_memories": ["' + f2 + '"]}'

        recalled = asyncio.run(memory.select_relevant_memories(
            "tr01 什么时候检修?", fake_side_query, set()))
        assert len(recalled) == 1 and "2026-09" in recalled[0].content
        injection = memory.format_memories_for_injection(recalled)
        assert "<system-reminder>" in injection and "tr01" in injection
        print(f"  ok, recalled 1 memory, injection has system-reminder")

        print("\n[5] SaveMemoryTool (the built-in tool the LLM calls)")
        out = memory.SaveMemoryTool().run(
            name="变电站联系人", description="station1 负责人是张工",
            type="reference", content="station1 运维负责人: 张工, 分机 8021。")
        assert out.saved and out.filename.startswith("reference_")
        bad = memory.SaveMemoryTool().run(
            name="x", description="y", type="not_a_type", content="z")
        assert not bad.saved and bad.error
        print(f"  ok, saved={out.filename}; bad type rejected")

        print("\n[6] freshness warning (>1 day) vs fresh (today)")
        now_ms = __import__("time").time() * 1000
        assert memory.memory_freshness_warning(now_ms) == ""
        old = memory.memory_freshness_warning(now_ms - 5 * 86_400_000)
        assert "5 天前" in old
        print(f"  ok, old warning: {old[:30]}...")

    print("\n=== OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
