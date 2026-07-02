"""
Playwright-based X (Twitter) scraper.

Scrapes the logged-in X timeline or a user's profile page.
Requires a saved auth state (cookies) via `save_auth()` on first run.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

from ..models.post import PostMetrics, XPost

logger = logging.getLogger(__name__)

AUTH_STATE_PATH = Path("auth_state.json")
X_HOME = "https://x.com/home"
POST_ID_RE = re.compile(r"/status/(\d+)")
TICKER_RE = re.compile(r"\$([A-Z]{1,5})")


class XScraper:
    """
    Scrapes X posts via Playwright browser automation.

    First-time setup:
        scraper = XScraper()
        scraper.save_auth()   # opens browser for manual login, then saves cookies
    """

    def __init__(self, auth_state: Path = AUTH_STATE_PATH, headless: bool = True) -> None:
        self._auth_state = auth_state
        self._headless = headless

    # ── Public API ────────────────────────────────────────────────────────

    def save_auth(self) -> None:
        """Open a visible browser, let the user log in, then save cookies."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto("https://x.com/login")
            print("Please log in to X, then press Enter here to save the session...")
            input()
            ctx.storage_state(path=str(self._auth_state))
            browser.close()
            print(f"Auth state saved to {self._auth_state}")

    def scrape_home_timeline(self, max_posts: int = 20) -> list[XPost]:
        """Scrape the home timeline (For You / Following)."""
        return self._scrape_page(X_HOME, max_posts)

    def scrape_user_timeline(
        self, username: str, max_posts: int = 10, since: datetime | None = None
    ) -> list[XPost]:
        """Scrape a specific user's profile timeline."""
        return self._scrape_page(f"https://x.com/{username}", max_posts, since=since)

    def scrape_search(
        self, query: str, max_posts: int = 20, since: datetime | None = None
    ) -> list[XPost]:
        """Scrape search results for a query (e.g. '$AAPL' or '#BTC')."""
        import urllib.parse
        url = f"https://x.com/search?q={urllib.parse.quote(query)}&f=live"
        return self._scrape_page(url, max_posts, since=since)

    # ── Internal ──────────────────────────────────────────────────────────

    def _scrape_page(self, url: str, max_posts: int, since: datetime | None = None) -> list[XPost]:
        if not self._auth_state.exists():
            raise RuntimeError(
                f"Auth state not found at {self._auth_state}. Run save_auth() first."
            )

        posts: list[XPost] = []
        seen_ids: set[str] = set()

        with sync_playwright() as p:
            browser: Browser = p.chromium.launch(headless=self._headless)
            ctx = browser.new_context(storage_state=str(self._auth_state))
            page: Page = ctx.new_page()

            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            attempts = 0
            while len(posts) < max_posts and attempts < 15:
                articles = page.query_selector_all('article[data-testid="tweet"]')
                for article in articles:
                    post = self._parse_article(article, page)
                    if post and post.post_id not in seen_ids:
                        if since and post.created_at <= since:
                            continue
                        seen_ids.add(post.post_id)
                        posts.append(post)
                        if len(posts) >= max_posts:
                            break

                if len(posts) < max_posts:
                    page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                    page.wait_for_timeout(2000)
                attempts += 1

            browser.close()

        logger.info("Scraped %d posts from %s", len(posts), url)
        return posts

    def _parse_article(self, article, page: Page) -> XPost | None:
        try:
            # Post ID from the permalink <a> tag
            link = article.query_selector('a[href*="/status/"]')
            if not link:
                return None
            href = link.get_attribute("href") or ""
            m = POST_ID_RE.search(href)
            if not m:
                return None
            post_id = m.group(1)

            # Author
            author_el = article.query_selector('[data-testid="User-Name"]')
            author_name = ""
            author_handle = ""
            if author_el:
                spans = author_el.query_selector_all("span")
                texts = [s.inner_text().strip() for s in spans if s.inner_text().strip()]
                author_name = texts[0] if texts else ""
                author_handle = next(
                    (t.lstrip("@") for t in texts if t.startswith("@")), author_name
                )

            # Content
            text_el = article.query_selector('[data-testid="tweetText"]')
            content = text_el.inner_text().strip() if text_el else ""

            # Timestamp
            time_el = article.query_selector("time")
            created_at = datetime.now(timezone.utc)
            if time_el:
                dt_str = time_el.get_attribute("datetime") or ""
                try:
                    created_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Metrics (aria-label on stat groups)
            metrics = self._parse_metrics(article)

            return XPost(
                post_id=post_id,
                author_id=author_handle,
                author_name=author_name,
                content=content,
                created_at=created_at,
                metrics=metrics,
            )
        except Exception:
            logger.exception("Failed to parse article")
            return None

    @staticmethod
    def _parse_metrics(article) -> PostMetrics:
        """Parse like / retweet / reply counts from aria-labels."""
        def _extract(testid: str) -> int:
            el = article.query_selector(f'[data-testid="{testid}"]')
            if not el:
                return 0
            label = el.get_attribute("aria-label") or ""
            nums = re.findall(r"[\d,]+", label)
            if nums:
                return int(nums[0].replace(",", ""))
            text = el.inner_text().strip().replace(",", "").replace("K", "000")
            try:
                return int(text) if text.isdigit() else 0
            except ValueError:
                return 0

        return PostMetrics(
            reply_count=_extract("reply"),
            retweet_count=_extract("retweet"),
            like_count=_extract("like"),
            impression_count=0,  # X hides impressions on others' posts
        )
