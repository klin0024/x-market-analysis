from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import urllib.parse
from typing import Union
from ..clients.x_scraper import XScraper
from ..clients.x_public_scraper import XPublicScraper

AnyScraper = Union[XScraper, XPublicScraper]
from ..models.post import XPost
from ..msgqueue.base import MessageQueue

logger = logging.getLogger(__name__)

DEDUP_MAX_SIZE = 10_000   # keep last N post IDs in memory


@dataclass
class WatchList:
    accounts: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._accounts_lower: set[str] = {a.lower() for a in self.accounts}
        self._keywords_lower: list[str] = [k.lower() for k in self.keywords]
        self._hashtags_lower: list[str] = [h.lower() for h in self.hashtags]

    def add_account(self, username: str) -> None:
        if username not in self.accounts:
            self.accounts.append(username)
            self._accounts_lower.add(username.lower())

    def remove_account(self, username: str) -> None:
        self.accounts = [a for a in self.accounts if a != username]
        self._accounts_lower = {a.lower() for a in self.accounts}

    def build_search_queries(self) -> list[str]:
        queries: list[str] = []
        for kw in self.keywords:
            queries.append(kw)
        for ht in self.hashtags:
            queries.append(f"#{ht}")
        return queries

    def matches(self, post: XPost) -> bool:
        if post.author_id.lower() in self._accounts_lower:
            return True
        content_lower = post.content.lower()
        if any(kw in content_lower for kw in self._keywords_lower):
            return True
        post_tags = post.get_hashtags()
        if any(ht in post_tags for ht in self._hashtags_lower):
            return True
        return False


class XFetcherService:
    """
    Polls X via Playwright scraping.

    Three sources:
      1. Each watched account's profile timeline
      2. Search results for keywords / hashtags
      3. Home timeline (optional, broad coverage)
    """

    def __init__(
        self,
        scraper: AnyScraper,
        queue: MessageQueue,
        watch_list: WatchList,
        repo=None,
        poll_home: bool = False,
        poll_interval_sec: int = 60,
        lookback_hours: int = 1,
    ) -> None:
        self._scraper = scraper
        self._queue = queue
        self._watch = watch_list
        self._repo = repo
        self._poll_home = poll_home
        self._poll_interval = poll_interval_sec
        self._lookback_hours = lookback_hours
        self._running = False
        self._thread: threading.Thread | None = None
        self._seen_ids: set[str] = set()
        self._seen_order: list[str] = []   # FIFO eviction for dedup set
        self._last_poll_at: datetime | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("XFetcherService started (Playwright polling every %ds)", self._poll_interval)

    def stop(self) -> None:
        self._running = False

    def is_alive(self) -> bool:
        t = getattr(self, "_thread", None)
        return self._running and t is not None and t.is_alive()

    def _poll_loop(self) -> None:
        while self._running:
            self._run_once()
            time.sleep(self._poll_interval)

    def _run_once(self) -> None:
        posts: list[XPost] = []
        poll_start = datetime.now(timezone.utc)

        # 首次 poll 用回溯視窗；後續 poll 用上次 poll 時間
        if self._last_poll_at is not None:
            since = self._last_poll_at
        elif self._lookback_hours > 0:
            since = poll_start - timedelta(hours=self._lookback_hours)
        else:
            since = None

        # 1 & 2. Account timelines + keyword searches
        if isinstance(self._scraper, XPublicScraper):
            tasks = []
            for username in self._watch.accounts:
                tasks.append((f"https://x.com/{username}", 10, since))
            for query in self._watch.build_search_queries():
                url = f"https://x.com/search?q={urllib.parse.quote(query)}&f=live"
                tasks.append((url, 15, since))
            if tasks:
                posts += self._scraper.scrape_many(tasks)
        else:
            for username in self._watch.accounts:
                try:
                    posts += self._scraper.scrape_user_timeline(username, max_posts=10, since=since)
                except Exception:
                    logger.exception("Failed to scrape user: %s", username)
            for query in self._watch.build_search_queries():
                try:
                    posts += self._scraper.scrape_search(query, max_posts=15, since=since)
                except Exception:
                    logger.exception("Failed to scrape search: %s", query)

        # 3. Home timeline (optional, only available when logged in)
        if self._poll_home and hasattr(self._scraper, "scrape_home_timeline"):
            try:
                posts += self._scraper.scrape_home_timeline(max_posts=20)
            except Exception:
                logger.exception("Failed to scrape home timeline")

        for post in posts:
            self._handle(post)

        self._last_poll_at = poll_start

    def _handle(self, post: XPost) -> None:
        if not self._watch.matches(post):
            return
        if self._is_duplicate(post.post_id):
            return
        self._queue.publish(post.to_dict())
        logger.info("Enqueued post %s by @%s", post.post_id, post.author_id)

    def _register(self, post_id: str) -> None:
        self._seen_ids.add(post_id)
        self._seen_order.append(post_id)
        while len(self._seen_order) > DEDUP_MAX_SIZE:
            old = self._seen_order.pop(0)
            self._seen_ids.discard(old)

    def _is_duplicate(self, post_id: str) -> bool:
        if post_id in self._seen_ids:
            return True
        if self._repo and self._repo.post_exists(post_id):
            self._register(post_id)
            return True
        self._register(post_id)
        return False
