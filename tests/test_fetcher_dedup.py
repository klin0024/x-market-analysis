"""Tests for XFetcherService dedup and poll logic (no Playwright)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.models.post import XPost, PostMetrics
from src.services.fetcher import XFetcherService, WatchList
from src.clients.x_public_scraper import XPublicScraper


def make_post(post_id="p1", author_id="elonmusk", content="$TSLA #BTC"):
    return XPost(
        post_id=post_id,
        author_id=author_id,
        author_name="Elon Musk",
        content=content,
        created_at=datetime.now(timezone.utc),
        metrics=PostMetrics(0, 0, 0, 0),
    )


def make_fetcher(repo=None):
    queue = MagicMock()
    scraper = MagicMock()
    watch = WatchList(accounts=["elonmusk"])
    return XFetcherService(
        scraper=scraper,
        queue=queue,
        watch_list=watch,
        repo=repo,
        poll_interval_sec=60,
        lookback_hours=1,
    ), queue


def make_fetcher_with_public_scraper(lookback_hours=1):
    queue = MagicMock()
    scraper = MagicMock(spec=XPublicScraper)
    scraper.scrape_many.return_value = []
    watch = WatchList(accounts=["elonmusk"])
    return XFetcherService(
        scraper=scraper,
        queue=queue,
        watch_list=watch,
        repo=None,
        poll_interval_sec=60,
        lookback_hours=lookback_hours,
    )


# ── dedup behavior ────────────────────────────────────────────────────────────

def test_is_duplicate_db_check():
    repo = MagicMock()
    repo.post_exists.return_value = True
    fetcher, queue = make_fetcher(repo=repo)
    fetcher._handle(make_post())
    queue.publish.assert_not_called()


def test_handle_skips_non_matching():
    fetcher, queue = make_fetcher()
    fetcher._handle(make_post(author_id="nobody"))
    queue.publish.assert_not_called()


def test_handle_skips_duplicate():
    fetcher, queue = make_fetcher()
    post = make_post()
    fetcher._handle(post)           # first: published
    fetcher._handle(post)           # second: duplicate
    assert queue.publish.call_count == 1


def test_handle_publishes_new_post():
    fetcher, queue = make_fetcher()
    post = make_post()
    fetcher._handle(post)
    queue.publish.assert_called_once()
    assert queue.publish.call_args[0][0]["post_id"] == post.post_id


# ── poll window ───────────────────────────────────────────────────────────────

def test_first_poll_uses_lookback():
    fetcher = make_fetcher_with_public_scraper(lookback_hours=2)

    before = datetime.now(timezone.utc)
    fetcher._run_once()
    after = datetime.now(timezone.utc)

    tasks = fetcher._scraper.scrape_many.call_args[0][0]
    since = tasks[0][2]
    assert before - timedelta(hours=2, seconds=1) <= since <= after
