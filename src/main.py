"""Entry point: wires all services together and runs the pipeline."""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_env(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env()

from apscheduler.schedulers.background import BackgroundScheduler

from config.settings import Settings
from src.bootstrap import build_alert_rules, build_watch_list, validate_settings
from src.models.analysis import Sentiment
from src.clients.llm import LLMClient
from src.clients.market import MarketClient
from src.clients.x_public_scraper import XPublicScraper
from src.clients.x_scraper import XScraper
from src.db.sqlite_repository import SQLiteRepository
from src.models.analysis import Analysis
from src.models.notification import Notification
from src.msgqueue.sqlite_queue import SQLiteQueue
from src.services.scheduler_engine import SchedulerEngine
from src.services.alert_engine import AlertRuleEngine
from src.services.analysis_engine import AnalysisEngine, ImpactScorer
from src.services.fetcher import XFetcherService
from src.services.line_notifier import LineNotifier
from src.health import run_health_check

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings()
    validate_settings(settings)

    repo = SQLiteRepository(db_path=settings.SQLITE_PATH)
    queue = SQLiteQueue(db_path=settings.SQLITE_PATH)

    auth_path = Path(settings.X_AUTH_STATE_PATH)
    if auth_path.exists():
        logger.info("Using authenticated scraper (%s)", auth_path)
        scraper = XScraper(auth_state=auth_path, headless=settings.PLAYWRIGHT_HEADLESS)
    else:
        logger.info("auth_state.json not found — using public (no-login) scraper")
        scraper = XPublicScraper(headless=settings.PLAYWRIGHT_HEADLESS, max_workers=settings.SCRAPER_MAX_WORKERS)

    llm_client = LLMClient(fast_model=settings.LLM_FAST_MODEL, slow_model=settings.LLM_SLOW_MODEL, max_retries=settings.LLM_MAX_RETRIES)
    market_client = MarketClient()
    notifier = LineNotifier(settings.LINE_CHANNEL_ACCESS_TOKEN, settings.LINE_GROUP_IDS)

    watch_list = build_watch_list(settings)
    alert_rules = build_alert_rules(settings)

    def on_notification(notif: Notification) -> None:
        analysis_db_id = repo.get_analysis_db_id(notif.analysis.analysis_id)
        if analysis_db_id:
            repo.save_notification(notif, analysis_db_id)

    alert_engine = AlertRuleEngine(
        rules=alert_rules,
        notifier=notifier,
        on_notification=on_notification,
        flood_enabled=settings.FLOOD_CONTROL_ENABLED,
        flood_min_posts=settings.FLOOD_MIN_POSTS,
    )

    def on_analysis(analysis: Analysis) -> None:
        post_db_id = repo.save_post(analysis.post)
        if repo.analysis_exists_for_post(analysis.post.post_id):
            logger.info("Skipping duplicate analysis for post %s", analysis.post.post_id)
            return
        repo.save_analysis(analysis, post_db_id)
        if analysis.sentiment != Sentiment.ERROR:
            alert_engine.evaluate(analysis)

    analysis_engine = AnalysisEngine(
        llm_client=llm_client,
        market_client=market_client,
        queue=queue,
        scorer=ImpactScorer(),
        on_analysis=on_analysis,
    )

    fetcher = XFetcherService(scraper=scraper, queue=queue, watch_list=watch_list, repo=repo, poll_interval_sec=settings.POLL_INTERVAL_SEC, lookback_hours=settings.FETCH_LOOKBACK_HOURS)

    scheduler = SchedulerEngine(repo, llm_client, notifier, settings)
    

    analysis_engine.start()
    fetcher.start()
    scheduler.start()

    run_health_check(settings, fetcher=fetcher, queue=queue, scheduler=scheduler).print()

    logger.info("System running. Press Ctrl+C to stop.")

    def _shutdown(sig, frame):  # noqa: ANN001
        logger.info("Shutting down...")
        fetcher.stop()
        scheduler.shutdown()
        repo.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Watchdog loop — 定期檢查 thread 是否存活，自動重啟
    WATCHDOG_INTERVAL = settings.WATCHDOG_INTERVAL_SEC
    last_check = time.time()
    while True:
        time.sleep(1)
        if time.time() - last_check >= WATCHDOG_INTERVAL:
            last_check = time.time()
            if not fetcher.is_alive():
                logger.warning("Fetcher thread dead — restarting")
                fetcher.start()
            if not queue.is_alive():
                logger.warning("Queue consumer thread dead — restarting")
                analysis_engine.restart()
            if not scheduler.running:
                logger.warning("Scheduler stopped — restarting")
                scheduler.start()


if __name__ == "__main__":
    main()
