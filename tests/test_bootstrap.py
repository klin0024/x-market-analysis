"""Unit tests for src/bootstrap.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("WATCH_ACCOUNTS", '["elonmusk"]')
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "token")
os.environ.setdefault("LINE_GROUP_IDS", '{"stock":"G1"}')
os.environ.setdefault("GOOGLE_API_KEY", "key")
os.environ.setdefault("LLM_FAST_MODEL", "google_genai:gemini-3.1-flash-lite")
os.environ.setdefault("LLM_SLOW_MODEL", "google_genai:gemini-3.1-flash-lite")

from config.settings import Settings
from src.bootstrap import build_watch_list, build_alert_rules, validate_settings


def make_settings(**overrides):
    s = Settings()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ── build_watch_list ───────────────────────────────────────────────────────────

def test_build_watch_list_accounts():
    s = make_settings(WATCH_ACCOUNTS=["elonmusk", "POTUS"], WATCH_KEYWORDS=[], WATCH_HASHTAGS=[])
    wl = build_watch_list(s)
    assert "elonmusk" in wl.accounts
    assert "POTUS" in wl.accounts

def test_build_watch_list_keywords():
    s = make_settings(WATCH_ACCOUNTS=["x"], WATCH_KEYWORDS=["inflation", "tariff"], WATCH_HASHTAGS=[])
    wl = build_watch_list(s)
    assert "inflation" in wl.keywords

def test_build_watch_list_hashtags():
    s = make_settings(WATCH_ACCOUNTS=["x"], WATCH_KEYWORDS=[], WATCH_HASHTAGS=["BTC", "ETH"])
    wl = build_watch_list(s)
    assert "BTC" in wl.hashtags


# ── build_alert_rules ─────────────────────────────────────────────────────────

def test_build_alert_rules_default():
    s = make_settings(
        LINE_GROUP_IDS={"stock": "G1"},
        ALERT_RULES_JSON="",
        SCORE_FILTER_ENABLED=False,
    )
    rules = build_alert_rules(s)
    assert len(rules) == 2
    names = {r.name for r in rules}
    assert "high_impact" in names
    assert "medium_impact" in names

def test_build_alert_rules_score_filter_off():
    s = make_settings(
        LINE_GROUP_IDS={"stock": "G1"},
        ALERT_RULES_JSON="",
        SCORE_FILTER_ENABLED=False,
    )
    rules = build_alert_rules(s)
    assert all(not r.score_filter_enabled for r in rules)

def test_build_alert_rules_score_filter_on():
    s = make_settings(
        LINE_GROUP_IDS={"stock": "G1"},
        ALERT_RULES_JSON="",
        SCORE_FILTER_ENABLED=True,
    )
    rules = build_alert_rules(s)
    assert all(r.score_filter_enabled for r in rules)

def test_build_alert_rules_from_json():
    import json
    custom = [{"name": "custom", "score_threshold": 50.0, "target_groups": ["G2"], "cooldown_sec": 900}]
    s = make_settings(
        LINE_GROUP_IDS={"stock": "G1"},
        ALERT_RULES_JSON=json.dumps(custom),
        SCORE_FILTER_ENABLED=False,
    )
    rules = build_alert_rules(s)
    assert len(rules) == 1
    assert rules[0].name == "custom"
    assert rules[0].score_threshold == 50.0

def test_build_alert_rules_target_groups():
    s = make_settings(
        LINE_GROUP_IDS={"stock": "G1", "crypto": "G2"},
        ALERT_RULES_JSON="",
        SCORE_FILTER_ENABLED=False,
    )
    rules = build_alert_rules(s)
    for rule in rules:
        assert "G1" in rule.target_groups
        assert "G2" in rule.target_groups


# ── validate_settings ─────────────────────────────────────────────────────────

def _capture_validate(settings):
    import logging
    logged = []
    class _Capture(logging.Handler):
        def emit(self, record):
            logged.append(record.getMessage())
    h = _Capture()
    logging.getLogger("src.bootstrap").addHandler(h)
    try:
        validate_settings(settings)
        return []
    except SystemExit:
        return logged
    finally:
        logging.getLogger("src.bootstrap").removeHandler(h)

def test_validate_passes():
    s = make_settings(
        WATCH_ACCOUNTS=["elonmusk"],
        LINE_CHANNEL_ACCESS_TOKEN="token",
        LINE_GROUP_IDS={"stock": "G1"},
        GOOGLE_API_KEY="key",
        LLM_FAST_MODEL="google_genai:x",
        LLM_SLOW_MODEL="google_genai:x",
        DAILY_REPORT_TIME="09:00",
    )
    assert _capture_validate(s) == []

def test_validate_missing_token():
    s = make_settings(
        WATCH_ACCOUNTS=["elonmusk"],
        LINE_CHANNEL_ACCESS_TOKEN="",
        LINE_GROUP_IDS={"stock": "G1"},
        GOOGLE_API_KEY="key",
        LLM_FAST_MODEL="google_genai:x",
        LLM_SLOW_MODEL="google_genai:x",
        DAILY_REPORT_TIME="09:00",
    )
    assert _capture_validate(s) != []

def test_validate_bad_time_format():
    s = make_settings(
        WATCH_ACCOUNTS=["elonmusk"],
        LINE_CHANNEL_ACCESS_TOKEN="token",
        LINE_GROUP_IDS={"stock": "G1"},
        GOOGLE_API_KEY="key",
        LLM_FAST_MODEL="google_genai:x",
        LLM_SLOW_MODEL="google_genai:x",
        DAILY_REPORT_TIME="9am",
    )
    assert _capture_validate(s) != []


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
