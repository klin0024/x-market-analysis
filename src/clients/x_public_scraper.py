"""
Playwright scraper for X.com — no login required.

Uses real Chrome (channel='chrome') to avoid bot detection.
Extracts tweet cards from <article> elements visible to logged-out users;
parses innerText since data-testid attributes are absent on public pages.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timezone

from concurrent.futures import ThreadPoolExecutor, as_completed

from playwright.sync_api import Browser, Page, sync_playwright

from ..models.post import PostMetrics, XPost

logger = logging.getLogger(__name__)

POST_ID_RE = re.compile(r"/status/(\d+)")

_EXTRACT_JS = """
() => {
    const results = [];
    const seen = new Set();
    const articles = Array.from(document.querySelectorAll('article'));
    for (const article of articles) {
        // Find status permalink (first link with /status/NNN)
        const statusLink = Array.from(article.querySelectorAll('a[href*="/status/"]'))
            .find(a => /\\/status\\/\\d+$/.test(a.getAttribute('href') || ''));
        if (!statusLink) continue;
        const href = statusLink.getAttribute('href') || '';
        const m = href.match(/\\/status\\/(\\d+)/);
        if (!m || seen.has(m[1])) continue;
        seen.add(m[1]);
        const postId = m[1];
        const pathParts = href.split('/').filter(Boolean);
        const username = (pathParts[0] || '').toLowerCase();
        const rawText = (article.innerText || '').trim();
        results.push({ post_id: postId, username, raw_text: rawText });
    }
    return results;
}
"""


# Twitter epoch: 2006-03-21T20:50:14Z = 1288834974657 ms since Unix epoch
_TWITTER_EPOCH_MS = 1288834974657

def _snowflake_to_datetime(post_id: str) -> datetime:
    """Decode creation time from Twitter Snowflake ID."""
    try:
        ts_ms = (int(post_id) >> 22) + _TWITTER_EPOCH_MS
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except (ValueError, OverflowError):
        return datetime.now(timezone.utc)


def _parse_raw_text(raw: str, username: str) -> tuple[str, str, str]:
    """
    Parse article innerText into (author_name, author_handle, tweet_content).

    Structure (logged-out X.com):
      [optional emoji/icon line]
      Author Display Name
      @handle
      [date line]
      Tweet text (may be multi-line)
    """
    lines = [l for l in raw.split("\n") if l.strip()]
    # Find @handle line
    handle_idx = next(
        (i for i, l in enumerate(lines) if l.strip().startswith("@")), -1
    )
    if handle_idx == -1:
        return username, username, raw

    author_name = lines[handle_idx - 1].strip() if handle_idx > 0 else username
    author_handle = lines[handle_idx].strip().lstrip("@")

    # Next line is the date/timestamp — skip it
    content_start = handle_idx + 2
    tweet_content = "\n".join(lines[content_start:]).strip()
    return author_name, author_handle, tweet_content


class XPublicScraper:
    """Scrape X.com without any login session."""

    def __init__(self, headless: bool = True, max_workers: int = 2) -> None:
        self._headless = headless
        self._max_workers = max_workers

    def scrape_user_timeline(
        self, username: str, max_posts: int = 10, since: datetime | None = None
    ) -> list[XPost]:
        return self._scrape(f"https://x.com/{username}", max_posts, since=since)

    def scrape_search(
        self, query: str, max_posts: int = 15, since: datetime | None = None
    ) -> list[XPost]:
        url = f"https://x.com/search?q={urllib.parse.quote(query)}&f=live"
        return self._scrape(url, max_posts, since=since)

    def scrape_many(
        self,
        tasks: list[tuple[str, int, "datetime | None"]],
    ) -> list[XPost]:
        """Scrape multiple URLs concurrently."""
        posts: list[XPost] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as ex:
            futs = {
                ex.submit(self._scrape, url, max_p, since): url
                for url, max_p, since in tasks
            }
            for fut in as_completed(futs):
                try:
                    posts.extend(fut.result())
                except Exception:
                    logger.exception("scrape_many task failed: %s", futs[fut])
        return posts

    # ── internals ────────────────────────────────────────────────────────

    def _scrape(self, url: str, max_posts: int, since: datetime | None = None) -> list[XPost]:
        posts: list[XPost] = []
        seen: set[str] = set()

        with sync_playwright() as p:
            # Real Chrome avoids X.com's headless Chromium detection
            try:
                browser: Browser = p.chromium.launch(
                    channel="chrome", headless=self._headless
                )
            except Exception:
                logger.warning("Chrome channel unavailable, falling back to Chromium")
                browser = p.chromium.launch(headless=self._headless)

            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page: Page = ctx.new_page()

            try:
                page.goto(url, wait_until="commit", timeout=45000)
                page.wait_for_timeout(5000)

                for _ in range(5):
                    raw_list: list[dict] = page.evaluate(_EXTRACT_JS)
                    for data in raw_list:
                        if data["post_id"] in seen:
                            continue
                        post = self._build_post(data)
                        if post:
                            if since and post.created_at <= since:
                                continue
                            seen.add(post.post_id)
                            posts.append(post)
                    if len(posts) >= max_posts:
                        break
                    page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                    page.wait_for_timeout(2000)

            except Exception:
                logger.exception("Failed to scrape %s", url)
            finally:
                browser.close()

        logger.info("Public scrape: %d posts from %s", len(posts), url)
        return posts[:max_posts]

    @staticmethod
    def _build_post(data: dict) -> XPost | None:
        try:
            post_id = data["post_id"]
            username = data.get("username", "")
            raw_text = data.get("raw_text", "")
            author_name, author_handle, content = _parse_raw_text(raw_text, username)
            if not content:
                return None
            return XPost(
                post_id=post_id,
                author_id=author_handle or username,
                author_name=author_name,
                content=content,
                created_at=_snowflake_to_datetime(post_id),
                metrics=PostMetrics(
                    reply_count=0,
                    retweet_count=0,
                    like_count=0,
                    impression_count=0,
                ),
            )
        except Exception:
            logger.exception("Failed to build XPost")
            return None
