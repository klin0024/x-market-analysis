"""Tests for AnalysisEngine (LLM + market client mocked)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.models.post import XPost, PostMetrics
from src.models.analysis import Analysis, Sentiment
from src.services.analysis_engine import AnalysisEngine, ImpactScorer


def make_post(content="$TSLA is going up"):
    return XPost(
        post_id="p1",
        author_id="elonmusk",
        author_name="Elon Musk",
        content=content,
        created_at=datetime.now(timezone.utc),
        metrics=PostMetrics(0, 0, 0, 0),
    )


def make_engine(llm_result=None, on_analysis=None):
    llm = MagicMock()
    llm.analyze_post.return_value = llm_result or {
        "sentiment": "bullish",
        "summary_zh": "測試摘要",
        "assets": [{"ticker": "TSLA", "name": "Tesla"}],
    }
    llm.parse_sentiment.side_effect = lambda s: Sentiment(s) if s in Sentiment._value2member_map_ else Sentiment.UNCERTAIN

    market = MagicMock()
    market.get_prices_bulk.return_value = {"TSLA": (250.0, 3.5)}

    queue = MagicMock()
    queue.is_alive.return_value = False

    return AnalysisEngine(
        llm_client=llm,
        market_client=market,
        queue=queue,
        scorer=ImpactScorer(),
        on_analysis=on_analysis,
    ), llm, market, queue


# ── analyze() ────────────────────────────────────────────────────────────────

def test_analyze_returns_analysis():
    engine, _, _, _ = make_engine()
    result = engine.analyze(make_post())
    assert isinstance(result, Analysis)


def test_analyze_uses_llm_result():
    engine, llm, _, _ = make_engine(llm_result={
        "sentiment": "bearish",
        "summary_zh": "市場看跌",
        "assets": [],
    })
    result = engine.analyze(make_post())
    assert result.sentiment == Sentiment.BEARISH
    assert result.summary_zh == "市場看跌"


def test_analyze_handles_missing_assets():
    engine, _, _, _ = make_engine(llm_result={
        "sentiment": "neutral",
        "summary_zh": "無影響",
        "assets": [],
    })
    result = engine.analyze(make_post())
    assert result.assets == []


def test_analyze_limits_assets_to_5():
    assets_6 = [{"ticker": f"T{i}", "name": f"Stock{i}"} for i in range(6)]
    engine, _, market, _ = make_engine(llm_result={
        "sentiment": "bullish",
        "summary_zh": "多資產",
        "assets": assets_6,
    })
    market.get_prices_bulk.return_value = {}
    result = engine.analyze(make_post())
    assert len(result.assets) == 5


def test_analyze_filters_empty_ticker():
    engine, _, market, _ = make_engine(llm_result={
        "sentiment": "bullish",
        "summary_zh": "空 ticker",
        "assets": [{"ticker": "", "name": "Invalid"}, {"ticker": "AAPL", "name": "Apple"}],
    })
    market.get_prices_bulk.return_value = {"AAPL": (180.0, 1.2)}
    result = engine.analyze(make_post())
    tickers = [a.ticker for a in result.assets]
    assert "" not in tickers
    assert "AAPL" in tickers


def test_enrich_market_data_updates_assets():
    engine, _, market, _ = make_engine()
    market.get_prices_bulk.return_value = {"TSLA": (300.0, 5.0)}
    result = engine.analyze(make_post())
    tsla = next(a for a in result.assets if a.ticker == "TSLA")
    assert tsla.current_price == 300.0
    assert tsla.price_change_pct == 5.0


def test_enrich_market_data_handles_missing_ticker():
    engine, _, market, _ = make_engine()
    market.get_prices_bulk.return_value = {}   # no price data
    result = engine.analyze(make_post())
    tsla = next((a for a in result.assets if a.ticker == "TSLA"), None)
    if tsla:
        assert tsla.current_price == 0.0
        assert tsla.price_change_pct == 0.0


