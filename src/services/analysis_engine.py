from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict
from typing import Callable

from ..clients.llm import LLMClient
from ..clients.market import MarketClient
from ..models.analysis import Analysis, AssetRef, Sentiment
from ..models.post import XPost
from ..msgqueue.base import MessageQueue

logger = logging.getLogger(__name__)

# Accounts with known high market influence get a weight boost
HIGH_INFLUENCE_ACCOUNTS: set[str] = set()


class ImpactScorer:
    """Compute a 0–100 impact score for a post."""

    def score(self, post: XPost, sentiment: Sentiment) -> float:
        engagement = min(post.metrics.engagement_rate() * 10, 30)   # max 30
        impression_score = min(math.log10(post.metrics.impression_count + 1) * 5, 20)  # max 20
        retweet_score = min(post.metrics.retweet_count / 100, 20)   # max 20

        influence_bonus = 20 if post.author_id in HIGH_INFLUENCE_ACCOUNTS else 0

        # Uncertainty halves the score
        certainty_factor = 0.5 if sentiment == Sentiment.UNCERTAIN else 1.0

        raw = (engagement + impression_score + retweet_score + influence_bonus) * certainty_factor
        return round(min(raw, 100), 2)


class AnalysisEngine:
    def __init__(
        self,
        llm_client: LLMClient,
        market_client: MarketClient,
        queue: MessageQueue,
        scorer: ImpactScorer | None = None,
        on_analysis: "Callable[[Analysis], None] | None" = None,
    ) -> None:
        self._llm = llm_client
        self._market = market_client
        self._queue = queue
        self._scorer = scorer or ImpactScorer()
        self._on_analysis = on_analysis
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._queue.subscribe(self._handle_message)
        logger.info("AnalysisEngine consuming from queue")

    def restart(self) -> None:
        self._running = False
        self.start()

    def _handle_message(self, data: dict) -> None:
        try:
            post = XPost.from_dict(data)
            analysis = self.analyze(post)
            if self._on_analysis:
                self._on_analysis(analysis)
        except Exception:
            logger.exception("Failed to analyze post %s", data.get("post_id"))

    def analyze(self, post: XPost) -> Analysis:
        result = self._llm.analyze_post(post.author_name, post.content, fast=True)
        sentiment = self._llm.parse_sentiment(result.get("sentiment", "uncertain"))
        impact_score = self._scorer.score(post, sentiment)
        assets = self._build_asset_refs(result.get("assets", []))
        self._enrich_market_data(assets)
        analysis = Analysis(
            post=post,
            sentiment=sentiment,
            impact_score=impact_score,
            summary_zh=result.get("summary_zh", ""),
            assets=assets,
        )
        if logger.isEnabledFor(logging.INFO):
            logger.info("Analysis result:\n%s", json.dumps(asdict(analysis), ensure_ascii=False, indent=2, default=str))
        return analysis

    def _build_asset_refs(self, raw_assets: list[dict]) -> list[AssetRef]:
        refs = []
        for a in raw_assets[:5]:
            ticker = a.get("ticker", "").upper()
            if ticker:
                refs.append(AssetRef(ticker=ticker, name=a.get("name", "")))
        # Also include tickers found in the raw content (parsed by XPost)
        return refs

    def _enrich_market_data(self, assets: list[AssetRef]) -> None:
        tickers = [a.ticker for a in assets]
        if not tickers:
            return
        prices = self._market.get_prices_bulk(tickers)
        for asset in assets:
            current, change_pct = prices.get(asset.ticker, (0.0, 0.0))
            asset.current_price = current
            asset.price_change_pct = change_pct
