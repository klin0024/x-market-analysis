from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PostMetrics:
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    impression_count: int = 0

    def engagement_rate(self) -> float:
        if self.impression_count == 0:
            return 0.0
        interactions = self.like_count + self.retweet_count + self.reply_count
        return round(interactions / self.impression_count * 100, 4)


_TICKER_RE = re.compile(r"\$([A-Z]{1,5})", re.ASCII)
_HASHTAG_RE = re.compile(r"#([A-Za-z0-9]+)")


@dataclass
class XPost:
    post_id: str
    author_id: str
    author_name: str
    content: str
    created_at: datetime
    metrics: PostMetrics = field(default_factory=PostMetrics)

    def get_tickers(self) -> list[str]:
        return list({m.group(1) for m in _TICKER_RE.finditer(self.content)})

    def get_hashtags(self) -> list[str]:
        return list({m.group(1).lower() for m in _HASHTAG_RE.finditer(self.content)})

    def to_dict(self) -> dict:
        return {
            "post_id": self.post_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "metrics": {
                "like_count": self.metrics.like_count,
                "retweet_count": self.metrics.retweet_count,
                "reply_count": self.metrics.reply_count,
                "impression_count": self.metrics.impression_count,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "XPost":
        m = data.get("metrics", {})
        return cls(
            post_id=data["post_id"],
            author_id=data["author_id"],
            author_name=data["author_name"],
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metrics=PostMetrics(
                like_count=m.get("like_count", 0),
                retweet_count=m.get("retweet_count", 0),
                reply_count=m.get("reply_count", 0),
                impression_count=m.get("impression_count", 0),
            ),
        )
