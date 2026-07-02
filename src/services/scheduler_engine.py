from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from config.settings import Settings
from src.clients.llm import LLMClient
from src.db.sqlite_repository import SQLiteRepository
from src.services.line_notifier import LineNotifier

logger = logging.getLogger(__name__)


class SchedulerEngine:
    def __init__(
        self,
        repo: SQLiteRepository,
        llm: LLMClient,
        notifier: LineNotifier,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._notifier = notifier
        self._settings = settings
        self._scheduler = BackgroundScheduler()

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def get_jobs(self):
        return self._scheduler.get_jobs()

    def start(self) -> None:
        if self._scheduler.running:
            return
        hour, minute = map(int, self._settings.DAILY_REPORT_TIME.split(":"))
        self._scheduler.add_job(
            self._run_daily_report,
            trigger="cron",
            hour=hour,
            minute=minute,
        )
        self._scheduler.start()
        logger.info("SchedulerEngine started (daily report at %s)", self._settings.DAILY_REPORT_TIME)

    def shutdown(self, wait: bool = False) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    def _run_daily_report(self) -> None:
        logger.info("Generating daily market report")
        rows = self._repo.get_daily_analyses(min_score=0)
        if not rows:
            logger.info("No analyses today, skipping report")
            return

        lines = [
            f"[{(r['sentiment'] or 'unknown').upper()}] @{r['author_name'] or 'unknown'}: {r['summary_zh'] or ''}"
            for r in rows[:20]
        ]
        report = self._llm.generate_daily_report("\n".join(lines))
        msg = f"📊 每日市場影響報告\n\n{report}"
        logger.info("Daily report:\n%s", msg)
        for group_id in self._settings.LINE_GROUP_IDS.values():
            self._notifier.push(group_id, msg)
        logger.info("Daily report sent to %d groups", len(self._settings.LINE_GROUP_IDS))
