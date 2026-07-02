from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable

from ..models.alert_rule import AlertRule
from ..models.analysis import Analysis
from ..models.notification import Notification
from .line_notifier import LineNotifier

logger = logging.getLogger(__name__)


class AlertRuleEngine:
    def __init__(
        self,
        rules: list[AlertRule],
        notifier: LineNotifier,
        on_notification: Callable[[Notification], None] | None = None,
        flood_enabled: bool = False,
        flood_min_posts: int = 3,
    ) -> None:
        self._rules = sorted(rules, key=lambda r: r.priority(), reverse=True)
        self._notifier = notifier
        self._on_notification = on_notification
        self._flood_enabled = flood_enabled
        self._flood_min_posts = flood_min_posts
        self._flood_expiry: dict[str, float] = {}
        self._send_count: dict[str, int] = {}

    def evaluate(self, analysis: Analysis) -> None:
        for rule in self._rules:
            if not rule.matches(analysis):
                continue
            if self._is_flood(rule, analysis):
                logger.info(
                    "Flood guard: skipping rule '%s' for post %s",
                    rule.name, analysis.post.post_id,
                )
                continue

            for group_id in self._get_target_groups(rule, analysis):
                notif = self._send(analysis, group_id)
                if self._on_notification:
                    self._on_notification(notif)

            self._record_sent(rule, analysis)
            break  # first matching rule wins

    def _is_flood(self, rule: AlertRule, analysis: Analysis) -> bool:
        if not self._flood_enabled:
            return False
        key = rule.flood_key(analysis)
        if self._send_count.get(key, 0) < self._flood_min_posts:
            return False
        return time.monotonic() < self._flood_expiry.get(key, 0)

    def _record_sent(self, rule: AlertRule, analysis: Analysis) -> None:
        key = rule.flood_key(analysis)
        self._send_count[key] = self._send_count.get(key, 0) + 1
        self._flood_expiry[key] = time.monotonic() + rule.cooldown_sec

    def _get_target_groups(self, rule: AlertRule, analysis: Analysis) -> list[str]:
        return rule.target_groups

    def _send(self, analysis: Analysis, group_id: str) -> Notification:
        notif = Notification(analysis=analysis, group_id=group_id)
        success = self._notifier.push_flex(group_id, analysis)
        notif.status = "sent" if success else "failed"
        notif.sent_at = datetime.utcnow()
        logger.info(
            "Notification %s to group %s: %s (score=%.1f)",
            notif.notif_id, group_id, notif.status, analysis.impact_score,
        )
        return notif
