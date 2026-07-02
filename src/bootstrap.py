from __future__ import annotations

import json
import logging

from config.settings import Settings
from src.models.alert_rule import AlertRule
from src.services.fetcher import WatchList

logger = logging.getLogger(__name__)


def validate_settings(settings: Settings) -> None:
    errors = []
    if not settings.LINE_CHANNEL_ACCESS_TOKEN:
        errors.append("LINE_CHANNEL_ACCESS_TOKEN is not set")
    if not settings.LINE_GROUP_IDS:
        errors.append("LINE_GROUP_IDS is empty — notifications will never be sent")
    if not settings.WATCH_ACCOUNTS:
        errors.append("WATCH_ACCOUNTS is empty — at least one account is required")
    if not settings.GOOGLE_API_KEY and "google_genai" in settings.LLM_FAST_MODEL:
        errors.append("GOOGLE_API_KEY is not set but LLM_FAST_MODEL uses google_genai")
    if not settings.GOOGLE_API_KEY and "google_genai" in settings.LLM_SLOW_MODEL:
        errors.append("GOOGLE_API_KEY is not set but LLM_SLOW_MODEL uses google_genai")
    parts = settings.DAILY_REPORT_TIME.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        errors.append(f"DAILY_REPORT_TIME must be HH:MM format, got: '{settings.DAILY_REPORT_TIME}'")
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        raise SystemExit("Aborting: fix the above config errors in .env")


def build_watch_list(settings: Settings) -> WatchList:
    return WatchList(
        accounts=settings.WATCH_ACCOUNTS,
        keywords=settings.WATCH_KEYWORDS,
        hashtags=settings.WATCH_HASHTAGS,
    )


def build_alert_rules(settings: Settings) -> list[AlertRule]:
    score_filter = settings.SCORE_FILTER_ENABLED
    if settings.ALERT_RULES_JSON:
        raw = json.loads(settings.ALERT_RULES_JSON)
        return [AlertRule(**r) for r in raw]

    all_groups = list(settings.LINE_GROUP_IDS.values())
    cooldown = settings.FLOOD_COOLDOWN_SEC
    return [
        AlertRule(name="high_impact",   score_threshold=70.0, target_groups=all_groups, cooldown_sec=cooldown, score_filter_enabled=score_filter),
        AlertRule(name="medium_impact", score_threshold=40.0, target_groups=all_groups, cooldown_sec=cooldown, score_filter_enabled=score_filter),
    ]
