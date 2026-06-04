"""SQLite-backed chat session store.

Ported (and trimmed) from the earlier multi-agent project at
``D:/code/AI/project/agent`` — only the bits the Phase 6 supervisor needs:
``create_session`` / ``save_message`` / ``get_history`` / ``delete_session``.

Each session keeps an ordered list of role/content messages. The supervisor
loads the history before each turn (as LangChain ``HumanMessage`` /
``AIMessage``) and appends the new exchange afterwards. Follow-up
references like "那它的 RUL 是多少" therefore work by replay: the previous
assistant turn — which already mentioned the indicators — is in the chat
context, so the LLM can answer without re-invoking the tool.
"""
from __future__ import annotations

import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

DEFAULT_DB_PATH = Path(project_root) / "var" / "sessions.db"


class SessionStore:
    """Minimal SQLite store for multi-turn chat sessions."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------- schema

    def _init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id   TEXT PRIMARY KEY,
                    created_at   INTEGER DEFAULT (strftime('%s','now') * 1000),
                    last_active  INTEGER DEFAULT (strftime('%s','now') * 1000),
                    message_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    timestamp   INTEGER DEFAULT (strftime('%s','now') * 1000),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                                                          ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session_id
                    ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                    ON messages(timestamp);
                """
            )

    # ------------------------------------------------------------- CRUD

    def create_session(self) -> str:
        """Create a fresh session; returns a short (8-char) session id."""
        session_id = uuid.uuid4().hex[:8]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sessions (session_id) VALUES (?)", (session_id,)
            )
        return session_id

    def save_message(self, session_id: str, role: str, content: str) -> None:
        """Append a message to a session. Auto-creates the session if absent."""
        ts = int(datetime.now().timestamp() * 1000)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
                (session_id,),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, ts),
            )
            conn.execute(
                "UPDATE sessions SET last_active = ?, "
                "message_count = message_count + 1 WHERE session_id = ?",
                (ts, session_id),
            )

    def get_history(self, session_id: str, limit: int = 50) -> List[Dict[str, str]]:
        """Return up to ``limit`` most recent messages in chronological order."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            )
            rows = cursor.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def delete_session(self, session_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


# Convenience module-level default — most callers only need one store.
default_store = SessionStore()
