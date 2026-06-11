"""Minimal interactive CLI for the SupervisorAgent.

Run::

    python Python/Src/Supervisor/chat_cli.py

Type a message; the supervisor decides whether to call a Tool (e.g.
``transformer_diagnosis``) or just answer directly. Multi-turn — chat
history is persisted to SQLite (``var/sessions.db`` by default) so
follow-up questions like ``"那它的 RUL 是多少?"`` work without re-running
the diagnosis.

Three layers are visible here:
  * **Tools**  — callable units the LLM invokes (``/tools`` to list).
  * **Skills** — loadable domain knowledge / SKILL.md (``/skills`` to list,
    ``/load_skill <name>`` to preview a body).
  * **Agents** — remote A2A agents, surfaced as Tools (``/register_remote``).

Commands:
  session:
    /new                  start a fresh session
    /id                   print the current session id
    /list                 list recent sessions (newest first)
    /switch <id>          switch to an existing session
    /delete <id>          delete a session (current → auto new)
    /history              dump the current session history
  tools:
    /tools                list registered tools (disabled shown as 'name [disabled]')
    /register <class_path>  hot-register a Tool class (no-arg constructor)
    /unregister <name>    remove a tool
    /enable <name>        re-enable a previously disabled tool
    /disable <name>       hide a tool from the LLM without removing it
    /load_dir <path>      scan a directory for files exporting TOOL/TOOLS
    /register_remote <url> [name]   hot-register a remote A2A agent (probes card)
    /load_remote_yaml [path]        load remote tools from YAML
  skills (prompt-style knowledge):
    /skills               list available SKILL.md skills
    /load_skill <name>    preview a skill's body
    /reload_skills        re-scan skill directories
  other:
    /quit                 exit
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.core import Supervisor
from Python.Src.Supervisor.loader import load_tools
from Python.Src.Supervisor.session import default_store


def _build_default_supervisor() -> Supervisor:
    """Construct the supervisor with whatever is declared in ``Config/tools.yaml``
    (plus remote tools from ``Config/remote_tools.yaml`` and prompt-style
    skills discovered under ``skills/``).

    New tools/skills are added by editing the YAML / dropping a SKILL.md —
    no code change here.
    """
    tools = load_tools()
    return Supervisor(tools=tools)


def _print_help() -> None:
    print(
        "session: /new  /list  /switch <id>  /delete <id>  /id  /history\n"
        "tools:   /tools  /register <class_path>  /unregister <name>  "
        "/enable <name>  /disable <name>  /load_dir <path>\n"
        "remote:  /register_remote <url> [name]  /load_remote_yaml [path]\n"
        "skills:  /skills  /load_skill <name>  /reload_skills\n"
        "other:   /quit"
    )


def _arg(line: str) -> str:
    parts = line.split(None, 1)
    return parts[1].strip() if len(parts) == 2 else ""


def main() -> int:
    # Windows GBK consoles can't print some characters Ollama emits.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=== HealthAgent Supervisor ===")
    print("正在初始化 supervisor (加载平台 registry + 编译诊断图)...")
    supervisor = _build_default_supervisor()
    session_id = supervisor.new_session()
    print(f"已创建会话: {session_id}")
    print(f"已注册工具: {supervisor.tool_names}")
    print(f"可用知识技能: {supervisor.skill_names}")
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
            target = _arg(user_input)
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
            target = _arg(user_input)
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

        # ----------------------------------------------------------- tools
        if user_input == "/tools":
            disabled = set(supervisor.disabled_tool_names)
            display = []
            for name in supervisor.all_tool_names:
                display.append(f"{name} [disabled]" if name in disabled else name)
            print(display if display else "(无)")
            continue
        if user_input.startswith("/register_remote"):
            rest = _arg(user_input)
            if not rest:
                print("用法: /register_remote <url> [name]")
                continue
            tokens = rest.split(None, 1)
            url = tokens[0]
            override_name = tokens[1].strip() if len(tokens) == 2 else None
            try:
                name = supervisor.register_remote_tool(url, name=override_name)
                print(f"已注册远程: {name}  ({url})")
            except Exception as e:  # noqa: BLE001
                print(f"[error] {e}")
            continue
        if user_input.startswith("/register"):
            class_path = _arg(user_input)
            if not class_path:
                print("用法: /register <class_path>")
                continue
            try:
                name = supervisor.register_tool_from_config(
                    {"class_path": class_path, "enabled": True}
                )
                print(f"已注册: {name}")
            except Exception as e:  # noqa: BLE001
                print(f"[error] {e}")
            continue
        if user_input.startswith("/unregister"):
            name = _arg(user_input)
            if not name:
                print("用法: /unregister <name>")
                continue
            print(f"已移除: {name}" if supervisor.unregister_tool(name)
                  else f"未找到: {name}")
            continue
        if user_input.startswith("/enable"):
            name = _arg(user_input)
            if not name:
                print("用法: /enable <name>")
                continue
            print(f"已启用: {name}" if supervisor.enable_tool(name)
                  else f"未变化 (不存在或已启用): {name}")
            continue
        if user_input.startswith("/disable"):
            name = _arg(user_input)
            if not name:
                print("用法: /disable <name>")
                continue
            print(f"已禁用: {name}" if supervisor.disable_tool(name)
                  else f"未变化 (不存在或已禁用): {name}")
            continue
        if user_input.startswith("/load_dir"):
            path = _arg(user_input)
            if not path:
                print("用法: /load_dir <path>")
                continue
            try:
                added = supervisor.register_tools_from_path(path)
                print(f"新增 {len(added)} 个 tool: {added}" if added
                      else "未发现可加载 tool (需要模块级 TOOL = ... 或 TOOLS = [...])")
            except Exception as e:  # noqa: BLE001
                print(f"[error] {e}")
            continue
        if user_input.startswith("/load_remote_yaml"):
            path = _arg(user_input) or None
            try:
                added = supervisor.register_remote_tools_from_yaml(path)
                print(f"新增 {len(added)} 个远程 tool: {added}" if added
                      else "未新增 (文件不存在 / 全部已注册 / 没有 enabled 项)")
            except Exception as e:  # noqa: BLE001
                print(f"[error] {e}")
            continue

        # ----------------------------------------------------------- skills
        if user_input == "/skills":
            reg = supervisor._skill_registry  # noqa: SLF001 — CLI introspection
            skills = reg.list()
            if not skills:
                print("(无知识技能; 在 skills/<name>/SKILL.md 添加)")
            for s in skills:
                print(f"  {s.name} — {s.description}")
            continue
        if user_input.startswith("/load_skill"):
            name = _arg(user_input)
            if not name:
                print("用法: /load_skill <name>")
                continue
            skill = supervisor._skill_registry.get(name)  # noqa: SLF001
            if skill is None:
                print(f"未找到技能 {name} (用 /skills 查)")
            else:
                print(f"--- {skill.name} ---\n{skill.body}")
            continue
        if user_input == "/reload_skills":
            names = supervisor.reload_skills()
            print(f"已重载知识技能: {names}")
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
