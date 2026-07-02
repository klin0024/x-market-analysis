from __future__ import annotations

import json
import os
from pathlib import Path


class Settings:
    # Playwright / X scraper
    X_AUTH_STATE_PATH: str = os.getenv("X_AUTH_STATE_PATH", "auth_state.json")
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"

    # DeepAgents model strings (格式：provider:model-name)
    LLM_FAST_MODEL: str = os.getenv("LLM_FAST_MODEL", "google_genai:gemini-3.1-flash-lite")
    LLM_SLOW_MODEL: str = os.getenv("LLM_SLOW_MODEL", "openai:gpt-4o-mini")
    # API keys — LangChain 也會直接從環境變數讀取，此處統一管理
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

    # LINE Messaging API
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    LINE_GROUP_IDS: dict[str, str] = json.loads(os.getenv("LINE_GROUP_IDS", "{}"))

    # SQLite — 指定目錄，檔名固定為 xmarket.db
    _sqlite_dir: str = os.getenv("SQLITE_DIR", "data")
    SQLITE_PATH: str = str(Path(_sqlite_dir) / "xmarket.db")
    Path(_sqlite_dir).mkdir(parents=True, exist_ok=True)

    # Alert rules (JSON override)
    ALERT_RULES_JSON: str = os.getenv("ALERT_RULES_JSON", "")
    # impact_score 過濾開關（true = 必須達到閾值才推送，false = 所有貼文都推送）
    SCORE_FILTER_ENABLED: bool = os.getenv("SCORE_FILTER_ENABLED", "false").lower() == "true"

    # Fetcher poll 間隔（秒）
    POLL_INTERVAL_SEC: int = int(os.getenv("POLL_INTERVAL_SEC", "600"))
    # 首次啟動回溯時間（小時，0 = 不限）
    FETCH_LOOKBACK_HOURS: int = int(os.getenv("FETCH_LOOKBACK_HOURS", "24"))
    # Watchdog 檢查間隔（秒）
    WATCHDOG_INTERVAL_SEC: int = int(os.getenv("WATCHDOG_INTERVAL_SEC", "600"))
    # 公開爬蟲並行數（XPublicScraper）
    SCRAPER_MAX_WORKERS: int = int(os.getenv("SCRAPER_MAX_WORKERS", "2"))

    # LLM 分析失敗重試次數
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # Flood control
    FLOOD_CONTROL_ENABLED: bool = os.getenv("FLOOD_CONTROL_ENABLED", "false").lower() == "true"
    FLOOD_MIN_POSTS: int = int(os.getenv("FLOOD_MIN_POSTS", "3"))   # 推送 N 筆後才啟動 flood
    FLOOD_COOLDOWN_SEC: int = int(os.getenv("FLOOD_COOLDOWN_SEC", "1800"))

    # Watch list
    WATCH_ACCOUNTS: list[str] = json.loads(os.getenv("WATCH_ACCOUNTS", "[]"))
    WATCH_KEYWORDS: list[str] = json.loads(os.getenv("WATCH_KEYWORDS", "[]"))
    WATCH_HASHTAGS: list[str] = json.loads(os.getenv("WATCH_HASHTAGS", "[]"))

    # Daily report schedule (UTC HH:MM)
    DAILY_REPORT_TIME: str = os.getenv("DAILY_REPORT_TIME", "10:00")
