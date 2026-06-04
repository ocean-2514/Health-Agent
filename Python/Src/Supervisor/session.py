"""SQLite-backed chat session store + diagnosis record log.

Ported (and trimmed) from the earlier multi-agent project at
``D:/code/AI/project/agent``. Two concerns live here:

  * **chat sessions** — ``create_session`` / ``save_message`` /
    ``get_history``. The supervisor loads history before each turn (as
    LangChain ``HumanMessage`` / ``AIMessage``) and appends the new
    exchange afterwards. Follow-up references like "那它的 RUL 是多少"
    therefore work by replay alone — no extra lookup needed.

  * **diagnosis records** — ``save_diagnosis_record`` /
    ``get_diagnosis_records``. Each ``transformer_diagnosis`` invocation
    writes a structured row keyed by ``equipment_id`` so the
    ``history_lookup`` skill can answer "tr01 之前诊断过吗 / 上次结果如何 /
    HI 趋势" without re-running anything.

Diagnosis records are deliberately session-independent (queried by
equipment, not by chat thread) — a user who reconnects in a new session
can still ask about historical state.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

                CREATE TABLE IF NOT EXISTS diagnosis_records (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    equipment_id        TEXT NOT NULL,
                    substation          TEXT,
                    run_timestamp       INTEGER DEFAULT (strftime('%s','now') * 1000),
                    health_index        REAL,
                    predicted_rul_years REAL,
                    fusion_verdict_cn   TEXT,
                    fusion_confidence   REAL,
                    dga_risk_score      REAL,
                    primary_threat      TEXT,
                    forced_override     TEXT,
                    session_id          TEXT,
                    extras_json         TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_diagnosis_equipment
                    ON diagnosis_records(equipment_id);
                CREATE INDEX IF NOT EXISTS idx_diagnosis_timestamp
                    ON diagnosis_records(run_timestamp);
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

    def session_exists(self, session_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ? LIMIT 1", (session_id,)
            )
            return cur.fetchone() is not None

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Recent sessions, newest first.

        Returns ``[{session_id, created_at, last_active, message_count}, ...]``
        with timestamps formatted as ``YYYY-MM-DD HH:MM:SS`` for display.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT session_id, created_at, last_active, message_count "
                "FROM sessions ORDER BY last_active DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()

        def _fmt(ts_ms: Optional[int]) -> str:
            if not ts_ms:
                return ""
            return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")

        return [
            {
                "session_id": r["session_id"],
                "created_at": _fmt(r["created_at"]),
                "last_active": _fmt(r["last_active"]),
                "message_count": r["message_count"],
            }
            for r in rows
        ]

    # ------------------------------------------------------ diagnosis records

    def save_diagnosis_record(
        self,
        equipment_id: str,
        *,
        substation: Optional[str] = None,
        health_index: Optional[float] = None,
        predicted_rul_years: Optional[float] = None,
        fusion_verdict_cn: Optional[str] = None,
        fusion_confidence: Optional[float] = None,
        dga_risk_score: Optional[float] = None,
        primary_threat: Optional[str] = None,
        forced_override: Optional[str] = None,
        session_id: Optional[str] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Persist one transformer-diagnosis run; returns the new row id.

        Called by the ``transformer_diagnosis`` Skill at the end of a
        successful run, so the ``history_lookup`` Skill can answer
        historical questions later (possibly in a different chat session).
        """
        ts = int(datetime.now().timestamp() * 1000)
        extras_json = json.dumps(extras, ensure_ascii=False) if extras else None
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO diagnosis_records "
                "(equipment_id, substation, run_timestamp, health_index, "
                " predicted_rul_years, fusion_verdict_cn, fusion_confidence, "
                " dga_risk_score, primary_threat, forced_override, "
                " session_id, extras_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    equipment_id, substation, ts, health_index,
                    predicted_rul_years, fusion_verdict_cn, fusion_confidence,
                    dga_risk_score, primary_threat, forced_override,
                    session_id, extras_json,
                ),
            )
            return cur.lastrowid or 0

    def get_diagnosis_records(
        self, equipment_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Return up to ``limit`` most recent diagnosis records for an
        equipment id, in **newest-first** order."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM diagnosis_records WHERE equipment_id = ? "
                "ORDER BY run_timestamp DESC LIMIT ?",
                (equipment_id, limit),
            )
            rows = cursor.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            extras = None
            if r["extras_json"]:
                try:
                    extras = json.loads(r["extras_json"])
                except json.JSONDecodeError:
                    extras = None
            out.append(
                {
                    "id": r["id"],
                    "equipment_id": r["equipment_id"],
                    "substation": r["substation"],
                    "run_at": datetime.fromtimestamp(
                        r["run_timestamp"] / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "health_index": r["health_index"],
                    "predicted_rul_years": r["predicted_rul_years"],
                    "fusion_verdict_cn": r["fusion_verdict_cn"],
                    "fusion_confidence": r["fusion_confidence"],
                    "dga_risk_score": r["dga_risk_score"],
                    "primary_threat": r["primary_threat"],
                    "forced_override": r["forced_override"],
                    "session_id": r["session_id"],
                    "extras": extras,
                }
            )
        return out


# Convenience module-level default — most callers only need one store.
default_store = SessionStore()
