"""Minimal interactive CLI for the SupervisorAgent.

Run::

    python Python/Src/Supervisor/chat_cli.py

Type a message; the supervisor decides whether to call a Skill (e.g.
``transformer_diagnosis``) or just answer directly. Multi-turn — chat
history is persisted to SQLite (``var/sessions.db`` by default) so
follow-up questions like ``"那它的 RUL 是多少?"`` work without re-running
the diagnosis.

Commands:
  /new                 start a fresh session
  /id                  print the current session id
  /list                list recent sessions (newest first)
  /switch <id>         switch to an existing session
  /delete <id>         delete a session (if it's the current one, auto-creates a new one)
  /history             dump the current session history
  /skills              list registered skills
  /quit                exit
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.core import Supervisor
from Python.Src.Supervisor.loader import load_skills
from Python.Src.Supervisor.session import default_store


def _build_default_supervisor() -> Supervisor:
    """Construct the supervisor with whatever is declared in ``Config/skills.yaml``.

    New skills (knowledge_qa, remote A2A skills, ...) are added by editing
    the YAML — no code change here.
    """
    skills = load_skills()
    return Supervisor(skills=skills)


def _print_help() -> None:
    print(
        "commands: /new  /list  /switch <id>  /delete <id>  "
        "/id  /history  /skills  /quit"
    )


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
        if user_input == "/list":
            rows = default_store.list_sessions(limit=20)
            if not rows:
                print("(无会话)")
            for s in rows:
                mark = " *" if s["session_id"] == session_id else "  "
                print(
                    f"{mark} {s['session_id']}  last_active={s['last_active']}  "
                    f"msgs={s['message_count']}"
                )
            continue
        if user_input.startswith("/switch"):
            parts = user_input.split(None, 1)
            target = parts[1].strip() if len(parts) == 2 else ""
            if not target:
                print("用法: /switch <session_id>")
            elif target == session_id:
                print(f"已在会话 {target}")
            elif not default_store.session_exists(target):
                print(f"未找到会话 {target} (用 /list 查可用 id)")
            else:
                session_id = target
                print(f"切到会话: {session_id}")
            continue
        if user_input.startswith("/delete"):
            parts = user_input.split(None, 1)
            target = parts[1].strip() if len(parts) == 2 else ""
            if not target:
                print("用法: /delete <session_id>")
                continue
            if not default_store.session_exists(target):
                print(f"未找到会话 {target}")
                continue
            default_store.delete_session(target)
            if target == session_id:
                session_id = supervisor.new_session()
                print(f"已删除当前会话 {target}, 自动切到新会话: {session_id}")
            else:
                print(f"已删除会话: {target}")
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
