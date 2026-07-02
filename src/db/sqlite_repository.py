from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..models.analysis import Analysis
from ..models.notification import Notification
from ..models.post import XPost

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    x_post_id   TEXT    UNIQUE NOT NULL,
    author_id   TEXT    NOT NULL,
    author_name TEXT,
    content     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    fetched_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_posts_author  ON posts(author_id);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at);

CREATE TABLE IF NOT EXISTS analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id   TEXT    UNIQUE NOT NULL,
    post_id       INTEGER NOT NULL UNIQUE REFERENCES posts(id) ON DELETE CASCADE,
    sentiment     TEXT    NOT NULL,
    impact_score  REAL    NOT NULL,
    summary_zh    TEXT,
    reasoning     TEXT,
    error_msg     TEXT,
    analyzed_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_analyses_sentiment   ON analyses(sentiment);
CREATE INDEX IF NOT EXISTS idx_analyses_analyzed_at ON analyses(analyzed_at);

CREATE TABLE IF NOT EXISTS assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    symbol      TEXT    NOT NULL,
    asset_type  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_symbol ON assets(symbol);

CREATE TABLE IF NOT EXISTS notifications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    notif_id      TEXT    UNIQUE NOT NULL,
    analysis_id   INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    group_id      TEXT    NOT NULL,
    sent_at       TEXT,
    status        TEXT    NOT NULL,
    retry_count   INTEGER NOT NULL DEFAULT 0,
    error_msg     TEXT
);

CREATE TABLE IF NOT EXISTS queue (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    msg        TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
"""


class SQLiteRepository:
    def __init__(self, db_path: str | Path = "xmarket.db") -> None:
        self._path = str(db_path)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    # ── Posts ─────────────────────────────────────────────────────────────
    def save_post(self, post: XPost) -> int:
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO posts (x_post_id, author_id, author_name, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (post.post_id, post.author_id, post.author_name,
             post.content, post.created_at.isoformat()),
        )
        self._conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = self._conn.execute(
            "SELECT id FROM posts WHERE x_post_id = ?", (post.post_id,)
        ).fetchone()
        return row["id"] if row else 0

    # ── Analyses ──────────────────────────────────────────────────────────
    def save_analysis(self, analysis: Analysis, post_db_id: int) -> int:
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO analyses
                    (analysis_id, post_id, sentiment, impact_score,
                     summary_zh, reasoning, error_msg, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.analysis_id,
                    post_db_id,
                    analysis.sentiment.value,
                    analysis.impact_score,
                    analysis.summary_zh,
                    getattr(analysis, "reasoning", None),
                    getattr(analysis, "error_msg", None),
                    analysis.analyzed_at.isoformat(),
                ),
            )
            analysis_db_id = cur.lastrowid or 0
            if analysis_db_id and analysis.assets:
                self._conn.executemany(
                    "INSERT INTO assets (analysis_id, symbol, asset_type) VALUES (?, ?, ?)",
                    [(analysis_db_id, a.ticker, "stock") for a in analysis.assets],
                )
        return analysis_db_id

    def get_analysis_db_id(self, analysis_uuid: str) -> int:
        row = self._conn.execute(
            "SELECT id FROM analyses WHERE analysis_id = ?", (analysis_uuid,)
        ).fetchone()
        return row["id"] if row else 0

    def post_exists(self, x_post_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM posts WHERE x_post_id = ?", (x_post_id,)
        ).fetchone()
        return row is not None

    def analysis_exists_for_post(self, x_post_id: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1 FROM analyses a
            JOIN posts p ON p.id = a.post_id
            WHERE p.x_post_id = ?
            """,
            (x_post_id,),
        ).fetchone()
        return row is not None

    def get_daily_analyses(self, min_score: float = 30.0) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT a.*, p.author_name, p.content, p.created_at AS post_created_at
            FROM analyses a
            JOIN posts p ON p.id = a.post_id
            WHERE datetime(p.created_at) >= datetime('now', '-24 hours')
              AND a.impact_score >= ?
            ORDER BY p.created_at DESC
            """,
            (min_score,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Notifications ─────────────────────────────────────────────────────
    def save_notification(self, notif: Notification, analysis_db_id: int) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO notifications (notif_id, analysis_id, group_id, sent_at, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                notif.notif_id,
                analysis_db_id,
                notif.group_id,
                notif.sent_at.isoformat() if notif.sent_at else None,
                notif.status,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
