"""Unit tests for services (no external dependencies)."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.models.post import XPost, PostMetrics
from src.models.analysis import Analysis, Sentiment, AssetRef
from src.models.alert_rule import AlertRule
from src.services.fetcher import WatchList
from src.services.analysis_engine import ImpactScorer
from src.services.alert_engine import AlertRuleEngine


def make_post(author_id="elonmusk", content="$TSLA to the moon #BTC"):
    return XPost(
        post_id="p1",
        author_id=author_id,
        author_name="Elon Musk",
        content=content,
        created_at=datetime(2025, 6, 28, tzinfo=timezone.utc),
        metrics=PostMetrics(like_count=1000, retweet_count=500, reply_count=100, impression_count=100000),
    )

def make_analysis(score=80.0, sentiment=Sentiment.BULLISH, author_id="elonmusk"):
    return Analysis(
        post=make_post(author_id=author_id),
        sentiment=sentiment,
        impact_score=score,
        summary_zh="Test summary",
    )


# ── WatchList ─────────────────────────────────────────────────────────────────

def test_watchlist_matches_account():
    wl = WatchList(accounts=["elonmusk"])
    assert wl.matches(make_post(author_id="elonmusk")) is True
    assert wl.matches(make_post(author_id="someone_else")) is False

def test_watchlist_matches_keyword():
    wl = WatchList(keywords=["interest rate"])
    assert wl.matches(make_post(content="Fed raises interest rate")) is True
    assert wl.matches(make_post(content="Nothing relevant here")) is False

def test_watchlist_matches_hashtag():
    wl = WatchList(hashtags=["BTC"])
    assert wl.matches(make_post(content="Love #BTC today")) is True
    assert wl.matches(make_post(content="No hashtags")) is False

def test_watchlist_case_insensitive_account():
    wl = WatchList(accounts=["ElonMusk"])
    assert wl.matches(make_post(author_id="elonmusk")) is True

def test_watchlist_add_remove_account():
    wl = WatchList()
    wl.add_account("user1")
    assert "user1" in wl.accounts
    wl.remove_account("user1")
    assert "user1" not in wl.accounts

def test_watchlist_build_search_queries():
    wl = WatchList(keywords=["inflation"], hashtags=["BTC"])
    queries = wl.build_search_queries()
    assert "inflation" in queries
    assert "#BTC" in queries


# ── ImpactScorer ──────────────────────────────────────────────────────────────

def test_scorer_zero_metrics():
    post = XPost("p", "u", "n", "text", datetime.now(timezone.utc),
                 PostMetrics(0, 0, 0, 0))
    score = ImpactScorer().score(post, Sentiment.BULLISH)
    assert score == 0.0

def test_scorer_uncertain_halves_score():
    post = make_post()
    scorer = ImpactScorer()
    bullish = scorer.score(post, Sentiment.BULLISH)
    uncertain = scorer.score(post, Sentiment.UNCERTAIN)
    assert uncertain == bullish * 0.5

def test_scorer_max_100():
    post = XPost("p", "u", "n", "x", datetime.now(timezone.utc),
                 PostMetrics(like_count=10**9, retweet_count=10**9,
                             reply_count=10**9, impression_count=10**9))
    score = ImpactScorer().score(post, Sentiment.BULLISH)
    assert score <= 100.0


# ── AlertRuleEngine ───────────────────────────────────────────────────────────

class FakeNotifier:
    def __init__(self):
        self.calls = []
    def push_flex(self, group_id, analysis):
        self.calls.append((group_id, analysis.impact_score))
        return True
    def push(self, group_id, text):
        self.calls.append((group_id, text))
        return True

def make_engine(rules=None, notifier=None, flood_enabled=False, flood_min_posts=3):
    if rules is None:
        rules = [AlertRule("high", 70.0, ["G1"], cooldown_sec=60, score_filter_enabled=True)]
    if notifier is None:
        notifier = FakeNotifier()
    return AlertRuleEngine(rules=rules, notifier=notifier, flood_enabled=flood_enabled, flood_min_posts=flood_min_posts), notifier

def test_alert_fires_above_threshold():
    engine, notifier = make_engine()
    engine.evaluate(make_analysis(score=75.0))
    assert len(notifier.calls) == 1

def test_alert_silent_below_threshold():
    engine, notifier = make_engine()
    engine.evaluate(make_analysis(score=65.0))
    assert len(notifier.calls) == 0

def test_alert_fires_without_score_filter():
    # score_filter_enabled=False (預設) → 低分也推送
    engine, notifier = make_engine(
        rules=[AlertRule("all", 70.0, ["G1"], cooldown_sec=60, score_filter_enabled=False)]
    )
    engine.evaluate(make_analysis(score=0.0))
    assert len(notifier.calls) == 1

def test_flood_control_blocks_second_call():
    engine, notifier = make_engine(
        rules=[AlertRule("high", 70.0, ["G1"], cooldown_sec=3600)],
        flood_enabled=True, flood_min_posts=1,
    )
    engine.evaluate(make_analysis(score=80.0))
    engine.evaluate(make_analysis(score=80.0))   # same author, within cooldown
    assert len(notifier.calls) == 1

def test_flood_control_different_author_passes():
    engine, notifier = make_engine(
        rules=[AlertRule("high", 70.0, ["G1"], cooldown_sec=3600)],
        flood_enabled=True, flood_min_posts=1,
    )
    engine.evaluate(make_analysis(score=80.0, author_id="user_a"))
    engine.evaluate(make_analysis(score=80.0, author_id="user_b"))
    assert len(notifier.calls) == 2

def test_multiple_groups_notified():
    rules = [AlertRule("high", 70.0, ["G1", "G2"], cooldown_sec=60)]
    engine, notifier = make_engine(rules=rules)
    engine.evaluate(make_analysis(score=80.0))
    groups_notified = [c[0] for c in notifier.calls]
    assert "G1" in groups_notified
    assert "G2" in groups_notified

def test_notification_callback_called():
    received = []
    notifier = FakeNotifier()
    engine = AlertRuleEngine(
        rules=[AlertRule("high", 70.0, ["G1"], cooldown_sec=60, score_filter_enabled=True)],
        notifier=notifier,
        on_notification=received.append,
        flood_enabled=False,
    )
    engine.evaluate(make_analysis(score=80.0))
    assert len(notifier.calls) == 1
    assert len(received) == 1
    assert received[0].status == "sent"

def test_flood_disabled_always_passes():
    rules = [AlertRule("high", 70.0, ["G1"], cooldown_sec=3600, score_filter_enabled=True)]
    notifier = FakeNotifier()
    engine = AlertRuleEngine(rules=rules, notifier=notifier, flood_enabled=False)
    engine.evaluate(make_analysis(score=80.0))
    engine.evaluate(make_analysis(score=80.0))
    engine.evaluate(make_analysis(score=80.0))
    assert len(notifier.calls) == 3   # 開關關閉，不受冷卻限制

def test_flood_min_posts_allows_first_n():
    rules = [AlertRule("high", 70.0, ["G1"], cooldown_sec=3600, score_filter_enabled=True)]
    notifier = FakeNotifier()
    engine = AlertRuleEngine(rules=rules, notifier=notifier, flood_enabled=True, flood_min_posts=3)
    for _ in range(3):
        engine.evaluate(make_analysis(score=80.0))   # 前 3 筆放行
    engine.evaluate(make_analysis(score=80.0))        # 第 4 筆被封鎖
    assert len(notifier.calls) == 3


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
