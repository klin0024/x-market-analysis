from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from ..models.analysis import Analysis
from ..models.notification import Notification
from ..models.post import XPost

logger = logging.getLogger(__name__)


class Repository:
    def __init__(self, dsn: str) -> None:
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False

    # ── Posts ────────────────────────────────────────────────────────────
    def save_post(self, post: XPost) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO posts (x_post_id, author_id, author_name, content, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (x_post_id) DO NOTHING
                RETURNING id
                """,
                (post.post_id, post.author_id, post.author_name, post.content, post.created_at),
            )
            row = cur.fetchone()
            self._conn.commit()
            return row[0] if row else 0

    # ── Analyses ─────────────────────────────────────────────────────────
    def save_analysis(self, analysis: Analysis, post_db_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analyses (analysis_id, post_id, sentiment, impact_score, assets, summary_zh, analyzed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (analysis_id) DO NOTHING
                """,
                (
                    analysis.analysis_id,
                    post_db_id,
                    analysis.sentiment.value,
                    analysis.impact_score,
                    json.dumps([a.to_dict() for a in analysis.assets]),
                    analysis.summary_zh,
                    analysis.analyzed_at,
                ),
            )
            self._conn.commit()

    def get_daily_analyses(self, min_score: float = 30.0) -> list[dict]:
        today = datetime.now(timezone.utc).date()
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.*, p.author_name, p.content
                FROM analyses a
                JOIN posts p ON p.id = a.post_id
                WHERE a.analyzed_at::date = %s AND a.impact_score >= %s
                ORDER BY a.impact_score DESC
                """,
                (today, min_score),
            )
            return [dict(row) for row in cur.fetchall()]

    # ── Notifications ─────────────────────────────────────────────────────
    def save_notification(self, notif: Notification, analysis_db_id: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notifications (notif_id, analysis_id, group_id, sent_at, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (notif_id) DO NOTHING
                """,
                (notif.notif_id, analysis_db_id, notif.group_id, notif.sent_at, notif.status),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()
