from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Generator

import requests

from ..models.post import XPost, PostMetrics

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twitter.com/2"
TWEET_FIELDS = "id,text,author_id,created_at,public_metrics"
EXPANSIONS = "author_id"
USER_FIELDS = "name,username"


class XApiClient:
    def __init__(self, bearer_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {bearer_token}"}
        self._session = requests.Session()
        self._session.headers.update(self._headers)

    def stream_filtered(self) -> Generator[XPost, None, None]:
        url = f"{BASE_URL}/tweets/search/stream"
        params = {
            "tweet.fields": TWEET_FIELDS,
            "expansions": EXPANSIONS,
            "user.fields": USER_FIELDS,
        }
        while True:
            try:
                with self._session.get(url, params=params, stream=True, timeout=90) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        import json
                        data = json.loads(line)
                        post = self._parse_tweet(data)
                        if post:
                            yield post
            except Exception:
                logger.exception("Stream disconnected, reconnecting in 5s")
                time.sleep(5)

    def poll_user_timeline(self, user_id: str, since_id: str | None = None) -> list[XPost]:
        url = f"{BASE_URL}/users/{user_id}/tweets"
        params: dict = {
            "tweet.fields": TWEET_FIELDS,
            "max_results": 10,
        }
        if since_id:
            params["since_id"] = since_id
        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        posts = []
        for tweet in data.get("data", []):
            post = self._parse_tweet({"data": tweet})
            if post:
                posts.append(post)
        return posts

    def set_filter_rules(self, rules: list[dict]) -> None:
        # Delete existing rules first
        existing = self._session.get(f"{BASE_URL}/tweets/search/stream/rules", timeout=30)
        existing.raise_for_status()
        ids = [r["id"] for r in existing.json().get("data", [])]
        if ids:
            self._session.post(
                f"{BASE_URL}/tweets/search/stream/rules",
                json={"delete": {"ids": ids}},
                timeout=30,
            ).raise_for_status()

        if rules:
            self._session.post(
                f"{BASE_URL}/tweets/search/stream/rules",
                json={"add": rules},
                timeout=30,
            ).raise_for_status()

    def _parse_tweet(self, payload: dict) -> XPost | None:
        try:
            tweet = payload.get("data", payload)
            m = tweet.get("public_metrics", {})
            return XPost(
                post_id=tweet["id"],
                author_id=tweet.get("author_id", ""),
                author_name=tweet.get("author_id", ""),  # enriched separately
                content=tweet["text"],
                created_at=datetime.fromisoformat(
                    tweet.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")
                ),
                metrics=PostMetrics(
                    like_count=m.get("like_count", 0),
                    retweet_count=m.get("retweet_count", 0),
                    reply_count=m.get("reply_count", 0),
                    impression_count=m.get("impression_count", 0),
                ),
            )
        except Exception:
            logger.exception("Failed to parse tweet payload")
            return None
