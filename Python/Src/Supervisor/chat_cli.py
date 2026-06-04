"""Minimal interactive CLI for the SupervisorAgent.

Run::

    python Python/Src/Supervisor/chat_cli.py

Type a message; the supervisor decides whether to call a Skill (e.g.
``transformer_diagnosis``) or just answer directly. Multi-turn — chat
history is persisted to SQLite (``var/sessions.db`` by default) so
follow-up questions like ``"那它的 RUL 是多少?"`` work without re-running
the diagnosis.

Commands:
  /new      start a fresh session
  /id       print the current session id
  /history  dump the current session history
  /skills   list registered skills
  /quit     exit
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.core import Supervisor
from Python.Src.Supervisor.session import default_store
from Python.Src.Supervisor.skills.transformer_diagnosis import SKILL as DIAGNOSIS_SKILL


def _build_default_supervisor() -> Supervisor:
    """Construct the supervisor with the currently bundled Skills.

    Phase 6 MVP ships just ``transformer_diagnosis``. Future Phase 6.x
    additions (knowledge_qa, history_lookup, remote A2A skills) get plugged
    in here.
    """
    return Supervisor(skills=[DIAGNOSIS_SKILL])


def _print_help() -> None:
    print("commands: /new  /id  /history  /skills  /quit")


def main() -> int:
    # Windows GBK consoles can't print some characters Ollama emits.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=== HealthAgent Supervisor (Phase 6 MVP) ===")
    print("正在初始化 supervisor (加载平台 registry + 编译诊断图)...")
    supervisor = _build_default_supervisor()
    session_id = supervisor.new_session()
    print(f"已创建会话: {session_id}")
    print(f"已注册技能: {supervisor.skill_names}")
    _print_help()

    while True:
        try:
            user_input = input(f"\n[{session_id}] you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not user_input:
            continue
        if user_input in ("/quit", "/exit"):
            return 0
        if user_input == "/new":
            session_id = supervisor.new_session()
            print(f"新会话: {session_id}")
            continue
        if user_input == "/id":
            print(session_id)
            continue
        if user_input == "/history":
            for row in default_store.get_history(session_id):
                print(f"  [{row['role']:>9}] {row['content']}")
            continue
        if user_input == "/skills":
            print(supervisor.skill_names)
            continue
        if user_input.startswith("/"):
            _print_help()
            continue

        try:
            answer = supervisor.chat(session_id, user_input)
        except Exception as e:  # noqa: BLE001
            print(f"[error] {e}")
            continue
        print(f"\nassistant> {answer}")


if __name__ == "__main__":
    raise SystemExit(main())
