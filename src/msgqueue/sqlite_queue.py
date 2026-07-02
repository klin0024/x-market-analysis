from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    msg        TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
"""


class SQLiteQueue:
    """Persistent queue backed by SQLite. Survives process restarts."""

    def __init__(self, db_path: str | Path = "xmarket.db", poll_interval: float = 1.0) -> None:
        self._path = str(db_path)
        self._poll_interval = poll_interval
        self._handler: Callable[[dict], None] | None = None
        self._running = False
        self._consumer_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_QUEUE_SCHEMA)

    def publish(self, msg: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO queue (msg) VALUES (?)",
                (json.dumps(msg, ensure_ascii=False),),
            )
        logger.debug("SQLiteQueue: published post_id=%s", msg.get("post_id"))

    def subscribe(self, handler: Callable[[dict], None]) -> None:
        self._handler = handler
        self._running = True
        self._consumer_thread = threading.Thread(target=self._consume_loop, daemon=True)
        self._consumer_thread.start()

    def is_alive(self) -> bool:
        t = getattr(self, "_consumer_thread", None)
        return self._running and t is not None and t.is_alive()

    def ack(self, msg_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE queue SET status='done', updated_at=datetime('now') WHERE id=?",
                (msg_id,),
            )

    def nack(self, msg_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE queue SET status='failed', updated_at=datetime('now') WHERE id=?",
                (msg_id,),
            )

    def _consume_loop(self) -> None:
        # On startup, reset any stuck 'processing' rows back to 'pending'
        with self._connect() as conn:
            conn.execute(
                "UPDATE queue SET status='pending', updated_at=datetime('now') WHERE status='processing'"
            )
        while self._running:
            self._process_next()
            time.sleep(self._poll_interval)

    def _process_next(self) -> None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, msg FROM queue WHERE status='pending' ORDER BY id LIMIT 1"
                ).fetchone()
                if not row:
                    return
                conn.execute(
                    "UPDATE queue SET status='processing', updated_at=datetime('now') WHERE id=?",
                    (row["id"],),
                )

        msg_id = str(row["id"])
        try:
            msg = json.loads(row["msg"])
            if self._handler:
                self._handler(msg)
            self.ack(msg_id)
        except Exception:
            logger.exception("SQLiteQueue handler error for id=%s post_id=%s", msg_id, row["msg"][:50])
            self.nack(msg_id)

    def pending_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM queue WHERE status='pending'").fetchone()[0]
