from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from .post import XPost

# ── 顏色常數 ──────────────────────────────────────────────────────────────────
COLOR_BULLISH   = "#e74c3c"   # 紅（看漲）
COLOR_BEARISH   = "#27ae60"   # 綠（看跌）
COLOR_NEUTRAL   = "#95a5a6"   # 灰（持平）
COLOR_UNCERTAIN = "#95a5a6"   # 灰（不確定）
COLOR_AUTHOR    = "#1DA1F2"   # 藍（作者名）
COLOR_TEXT      = "#333333"   # 深灰（摘要）
COLOR_LABEL     = "#888888"   # 淺灰（標籤）
COLOR_TIME      = "#aaaaaa"   # 極淺灰（時間）
COLOR_ASSET     = "#555555"   # 中灰（資產名）
COLOR_NA        = "#95a5a6"   # 灰（查無資料）
COLOR_UP        = "#e74c3c"   # 紅（漲）
COLOR_DOWN      = "#27ae60"   # 綠（跌）


class Sentiment(Enum):
    BULLISH   = "bullish"
    BEARISH   = "bearish"
    NEUTRAL   = "neutral"
    UNCERTAIN = "uncertain"
    ERROR     = "error"

    @property
    def emoji(self) -> str:
        return {
            Sentiment.BULLISH:   "📈 看漲",
            Sentiment.BEARISH:   "📉 看跌",
            Sentiment.NEUTRAL:   "➡️ 持平",
            Sentiment.UNCERTAIN: "❓ 不確定",
            Sentiment.ERROR:     "❌ 錯誤",
        }[self]


_SENTIMENT_COLOR: dict = {
    Sentiment.BULLISH:   COLOR_BULLISH,
    Sentiment.BEARISH:   COLOR_BEARISH,
    Sentiment.NEUTRAL:   COLOR_NEUTRAL,
    Sentiment.UNCERTAIN: COLOR_UNCERTAIN,
}


@dataclass
class AssetRef:
    ticker: str
    name: str = ""
    price_change_pct: float = 0.0
    current_price: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "price_change_pct": self.price_change_pct,
            "current_price": self.current_price,
        }


@dataclass
class Analysis:
    post: XPost
    sentiment: Sentiment
    impact_score: float
    summary_zh: str
    assets: list[AssetRef] = field(default_factory=list)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def is_high_impact(self) -> bool:
        return self.impact_score >= 70.0

    def to_line_flex_message(self) -> dict:
        header_color = _SENTIMENT_COLOR.get(self.sentiment, COLOR_UNCERTAIN)

        asset_rows = [
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": asset.name or f"${asset.ticker}", "size": "sm", "color": COLOR_ASSET, "flex": 2},
                    {
                        "type": "text",
                        "text": "N/A" if asset.current_price == 0 else f"{'+' if asset.price_change_pct >= 0 else ''}{asset.price_change_pct:.2f}%",
                        "size": "sm",
                        "color": COLOR_NA if asset.current_price == 0 else (COLOR_DOWN if asset.price_change_pct < 0 else COLOR_UP),
                        "flex": 1,
                        "align": "end",
                    },
                ],
            }
            for asset in self.assets[:5]
        ]

        return {
            "type": "flex",
            "altText": f"{self.sentiment.emoji} {self.post.author_name}: {self.summary_zh[:40]}",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": header_color,
                    "contents": [
                        {
                            "type": "text",
                            "text": f"市場評價: {self.sentiment.emoji}",
                            "color": "#ffffff",
                            "weight": "bold",
                            "size": "sm",
                        },
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": self.post.author_name,
                            "weight": "bold",
                            "size": "sm",
                            "color": COLOR_AUTHOR,
                        },
                        {
                            "type": "text",
                            "text": self.summary_zh,
                            "wrap": True,
                            "size": "sm",
                            "color": COLOR_TEXT,
                        },
                        *(
                            [
                                {
                                    "type": "text",
                                    "text": "關注資產:",
                                    "size": "xs",
                                    "color": COLOR_LABEL,
                                    "weight": "bold",
                                },
                                *asset_rows,
                            ]
                            if asset_rows else []
                        ),
                        {
                            "type": "text",
                            "text": self.post.created_at.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M +08"),
                            "size": "xxs",
                            "color": COLOR_TIME,
                        },
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "link",
                            "height": "sm",
                            "action": {
                                "type": "uri",
                                "label": "查看貼文",
                                "uri": f"https://x.com/i/web/status/{self.post.post_id}",
                            },
                        }
                    ],
                },
            },
        }
