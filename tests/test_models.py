"""Unit tests for models."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.models.post import XPost, PostMetrics
from src.models.analysis import Analysis, Sentiment, AssetRef
from src.models.alert_rule import AlertRule
from src.models.notification import Notification


def make_post(**kwargs):
    defaults = dict(
        post_id="123",
        author_id="elonmusk",
        author_name="Elon Musk",
        content="$TSLA is going to the moon! #BTC",
        created_at=datetime(2025, 6, 28, 10, 0, tzinfo=timezone.utc),
        metrics=PostMetrics(like_count=1000, retweet_count=200, reply_count=50, impression_count=50000),
    )
    defaults.update(kwargs)
    return XPost(**defaults)


def make_analysis(**kwargs):
    post = make_post()
    defaults = dict(
        post=post,
        sentiment=Sentiment.BULLISH,
        impact_score=75.0,
        summary_zh="特斯拉股價看漲",
        assets=[AssetRef(ticker="TSLA", name="Tesla", price_change_pct=3.5, current_price=250.0)],
    )
    defaults.update(kwargs)
    return Analysis(**defaults)


# ── PostMetrics ────────────────────────────────────────────────────────────────

def test_engagement_rate_normal():
    m = PostMetrics(like_count=100, retweet_count=50, reply_count=10, impression_count=1000)
    assert m.engagement_rate() == 16.0

def test_engagement_rate_zero_impressions():
    m = PostMetrics()
    assert m.engagement_rate() == 0.0


# ── XPost ─────────────────────────────────────────────────────────────────────

def test_get_tickers():
    post = make_post(content="Buy $AAPL and $TSLA now!")
    tickers = post.get_tickers()
    assert set(tickers) == {"AAPL", "TSLA"}

def test_get_tickers_empty():
    post = make_post(content="Just a regular tweet")
    assert post.get_tickers() == []

def test_get_hashtags():
    post = make_post(content="Big move #BTC #ETH coming")
    tags = post.get_hashtags()
    assert set(tags) == {"btc", "eth"}

def test_get_hashtags_lowercase():
    post = make_post(content="#Bitcoin #BITCOIN")
    tags = post.get_hashtags()
    assert tags.count("bitcoin") == 1   # deduplicated

def test_to_dict_roundtrip():
    post = make_post()
    d = post.to_dict()
    restored = XPost.from_dict(d)
    assert restored.post_id == post.post_id
    assert restored.content == post.content
    assert restored.metrics.like_count == post.metrics.like_count


# ── Analysis ──────────────────────────────────────────────────────────────────

def test_is_high_impact_true():
    a = make_analysis(impact_score=70.0)
    assert a.is_high_impact() is True

def test_is_high_impact_false():
    a = make_analysis(impact_score=69.9)
    assert a.is_high_impact() is False

def test_to_line_flex_message_structure():
    a = make_analysis()
    msg = a.to_line_flex_message()
    assert msg["type"] == "flex"
    assert "altText" in msg
    assert msg["contents"]["type"] == "bubble"

    # Collect all text values recursively
    def collect_texts(obj):
        texts = []
        if isinstance(obj, dict):
            if "text" in obj:
                texts.append(obj["text"])
            for v in obj.values():
                texts.extend(collect_texts(v))
        elif isinstance(obj, list):
            for item in obj:
                texts.extend(collect_texts(item))
        return texts

    all_texts = collect_texts(msg["contents"]["body"])
    assert any("Tesla" in t for t in all_texts)

def test_sentiment_emoji():
    assert Sentiment.BULLISH.emoji.startswith("📈")
    assert Sentiment.BEARISH.emoji.startswith("📉")


# ── AlertRule ─────────────────────────────────────────────────────────────────

def test_alert_rule_matches():
    # score_filter_enabled=False (預設) → 所有分析都通過
    rule = AlertRule(name="high", score_threshold=70.0, target_groups=["G1"])
    assert rule.matches(make_analysis(impact_score=70.0)) is True
    assert rule.matches(make_analysis(impact_score=69.9)) is True

    # score_filter_enabled=True → 必須達到閾值
    rule_strict = AlertRule(name="high", score_threshold=70.0, target_groups=["G1"], score_filter_enabled=True)
    assert rule_strict.matches(make_analysis(impact_score=70.0)) is True
    assert rule_strict.matches(make_analysis(impact_score=69.9)) is False

def test_alert_rule_flood_key():
    rule = AlertRule(name="high", score_threshold=70.0, target_groups=["G1"])
    a = make_analysis()
    assert rule.flood_key(a) == "flood:high:elonmusk"

def test_alert_rule_priority():
    rule = AlertRule(name="high", score_threshold=70.0, target_groups=[])
    assert rule.priority() == 70


# ── Notification ──────────────────────────────────────────────────────────────

def test_notification_defaults():
    n = Notification(analysis=make_analysis(), group_id="G1")
    assert n.status == "pending"
    assert n.sent_at is None
    assert len(n.notif_id) == 36   # UUID format


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
