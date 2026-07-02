"""Unit tests for SQLiteRepository."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.db.sqlite_repository import SQLiteRepository
from src.models.post import XPost, PostMetrics
from src.models.analysis import Analysis, Sentiment, AssetRef
from src.models.notification import Notification


def make_post(post_id="p1"):
    return XPost(
        post_id=post_id,
        author_id="elonmusk",
        author_name="Elon Musk",
        content="$TSLA moon #BTC",
        created_at=datetime(2025, 6, 28, 10, 0, tzinfo=timezone.utc),
        metrics=PostMetrics(like_count=500, retweet_count=100, reply_count=20, impression_count=10000),
    )

def make_analysis(post):
    return Analysis(
        post=post,
        sentiment=Sentiment.BULLISH,
        impact_score=80.0,
        summary_zh="Tesla looks very bullish",
        assets=[AssetRef(ticker="TSLA", price_change_pct=3.5)],
        analyzed_at=datetime(2025, 6, 28, 10, 5, tzinfo=timezone.utc),
    )

def fresh_repo():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return SQLiteRepository(db_path=f.name)


def test_save_and_retrieve_post():
    repo = fresh_repo()
    post = make_post()
    row_id = repo.save_post(post)
    assert row_id > 0

def test_save_post_idempotent():
    repo = fresh_repo()
    post = make_post()
    id1 = repo.save_post(post)
    id2 = repo.save_post(post)   # same post_id → INSERT OR IGNORE
    assert id1 > 0
    assert id2 == id1   # returns same id

def test_save_analysis():
    repo = fresh_repo()
    post = make_post()
    post_id = repo.save_post(post)
    analysis = make_analysis(post)
    a_id = repo.save_analysis(analysis, post_id)
    assert a_id > 0

def test_get_daily_analyses_returns_results():
    repo = fresh_repo()
    post = make_post()
    post_id = repo.save_post(post)
    analysis = make_analysis(post)
    repo.save_analysis(analysis, post_id)
    # Override post created_at to now so the 24h filter matches
    repo._conn.execute(
        "UPDATE posts SET created_at = datetime('now') WHERE x_post_id = ?",
        (post.post_id,)
    )
    repo._conn.commit()
    rows = repo.get_daily_analyses(min_score=0)
    assert len(rows) == 1
    assert rows[0]["sentiment"] == "bullish"

def test_get_daily_analyses_score_filter():
    repo = fresh_repo()
    post = make_post()
    post_id = repo.save_post(post)
    analysis = make_analysis(post)
    repo.save_analysis(analysis, post_id)
    repo._conn.execute(
        "UPDATE posts SET created_at = datetime('now') WHERE x_post_id = ?",
        (post.post_id,)
    )
    repo._conn.commit()
    rows = repo.get_daily_analyses(min_score=90)   # score=80 should be excluded
    assert len(rows) == 0

def test_save_notification():
    repo = fresh_repo()
    post = make_post()
    post_id = repo.save_post(post)
    analysis = make_analysis(post)
    a_id = repo.save_analysis(analysis, post_id)
    notif = Notification(analysis=analysis, group_id="G1", status="sent",
                         sent_at=datetime(2025, 6, 28, 10, 6, tzinfo=timezone.utc))
    repo.save_notification(notif, a_id)   # should not raise

def test_post_exists_true():
    repo = fresh_repo()
    post = make_post()
    repo.save_post(post)
    assert repo.post_exists(post.post_id) is True

def test_post_exists_false():
    repo = fresh_repo()
    assert repo.post_exists("nonexistent") is False

def test_analysis_exists_for_post():
    repo = fresh_repo()
    post = make_post()
    post_id = repo.save_post(post)
    assert repo.analysis_exists_for_post(post.post_id) is False
    repo.save_analysis(make_analysis(post), post_id)
    assert repo.analysis_exists_for_post(post.post_id) is True


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
