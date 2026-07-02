"""Unit tests for _validate_settings."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch env before importing settings
os.environ.setdefault("WATCH_ACCOUNTS", '["elonmusk"]')
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "token")
os.environ.setdefault("LINE_GROUP_IDS", '{"stock":"G1"}')
os.environ.setdefault("GOOGLE_API_KEY", "key")
os.environ.setdefault("LLM_FAST_MODEL", "google_genai:gemini-3.1-flash-lite")
os.environ.setdefault("LLM_SLOW_MODEL", "google_genai:gemini-3.1-flash-lite")

import json
from unittest.mock import patch
from config.settings import Settings


def make_settings(**overrides):
    s = Settings()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def run_validate(settings):
    """Returns list of error strings logged, or [] if validation passed."""
    from src.bootstrap import validate_settings
    logged = []
    import logging
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


def test_valid_config_passes():
    s = make_settings(
        WATCH_ACCOUNTS=["elonmusk"],
        WATCH_KEYWORDS=[],
        WATCH_HASHTAGS=[],
        LINE_CHANNEL_ACCESS_TOKEN="token",
        LINE_GROUP_IDS={"stock": "G1"},
        GOOGLE_API_KEY="key",
        LLM_FAST_MODEL="google_genai:x",
        LLM_SLOW_MODEL="google_genai:x",
        DAILY_REPORT_TIME="10:00",
    )
    assert run_validate(s) == []

def test_empty_keywords_and_hashtags_ok():
    s = make_settings(
        WATCH_ACCOUNTS=["elonmusk"],
        WATCH_KEYWORDS=[],      # empty — should be fine
        WATCH_HASHTAGS=[],      # empty — should be fine
        LINE_CHANNEL_ACCESS_TOKEN="token",
        LINE_GROUP_IDS={"stock": "G1"},
        GOOGLE_API_KEY="key",
        LLM_FAST_MODEL="google_genai:x",
        LLM_SLOW_MODEL="google_genai:x",
        DAILY_REPORT_TIME="10:00",
    )
    assert run_validate(s) == []

def test_empty_accounts_fails():
    s = make_settings(
        WATCH_ACCOUNTS=[],
        WATCH_KEYWORDS=["inflation"],
        WATCH_HASHTAGS=["BTC"],
        LINE_CHANNEL_ACCESS_TOKEN="token",
        LINE_GROUP_IDS={"stock": "G1"},
        GOOGLE_API_KEY="key",
        LLM_FAST_MODEL="google_genai:x",
        LLM_SLOW_MODEL="google_genai:x",
        DAILY_REPORT_TIME="10:00",
    )
    errors = run_validate(s)
    assert errors != []
    assert "WATCH_ACCOUNTS" in errors[0]

def test_missing_line_token_fails():
    s = make_settings(
        WATCH_ACCOUNTS=["elonmusk"],
        WATCH_KEYWORDS=[], WATCH_HASHTAGS=[],
        LINE_CHANNEL_ACCESS_TOKEN="",
        LINE_GROUP_IDS={"stock": "G1"},
        GOOGLE_API_KEY="key",
        LLM_FAST_MODEL="google_genai:x",
        LLM_SLOW_MODEL="google_genai:x",
        DAILY_REPORT_TIME="10:00",
    )
    assert run_validate(s) != []

def test_bad_daily_report_time_fails():
    s = make_settings(
        WATCH_ACCOUNTS=["elonmusk"],
        WATCH_KEYWORDS=[], WATCH_HASHTAGS=[],
        LINE_CHANNEL_ACCESS_TOKEN="token",
        LINE_GROUP_IDS={"stock": "G1"},
        GOOGLE_API_KEY="key",
        LLM_FAST_MODEL="google_genai:x",
        LLM_SLOW_MODEL="google_genai:x",
        DAILY_REPORT_TIME="1000",   # wrong format
    )
    assert run_validate(s) != []


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
