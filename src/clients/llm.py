"""
LLM client — 組合 analysis_agent 與 report_agent，加上 rate limiting。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

from ..agents.analysis_agent import PostAnalysisOutput, build_analysis_agent
from ..agents.report_agent import DailyReportOutput, build_report_agent
from ..models.analysis import Sentiment

logger = logging.getLogger(__name__)


# ── Rate limiter ───────────────────────────────────────────────────────────────

class _RateLimiter:
    """Sliding-window rate limiter. Default: 12 calls / 60 s (stays under free-tier 15/min)."""

    def __init__(self, max_calls: int = 12, window_sec: float = 60.0) -> None:
        self._max = max_calls
        self._window = window_sec
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._timestamps and self._timestamps[0] < now - self._window:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max:
                    self._timestamps.append(now)
                    return
                wait = self._window - (now - self._timestamps[0])
            logger.info("Rate limit: waiting %.1f s before next LLM call", wait)
            time.sleep(max(wait, 0.1))


_rate_limiter = _RateLimiter(max_calls=12, window_sec=60.0)
_RETRY_DELAY_SEC = 3


# ── LLMClient ─────────────────────────────────────────────────────────────────

class LLMClient:
    def __init__(
        self,
        fast_model: str = "google_genai:gemini-3.1-flash-lite",
        slow_model: str = "google_genai:gemini-3.1-flash-lite",
        max_retries: int = 2,
    ) -> None:
        self._analysis_agent = build_analysis_agent(fast_model)
        self._report_agent = build_report_agent(slow_model)
        self._max_retries = max_retries

    def analyze_post(self, author: str, content: str, fast: bool = True) -> dict:
        prompt = f"貼文作者：{author}\n貼文內容：{content}"
        for attempt in range(self._max_retries + 1):
            try:
                _rate_limiter.acquire()
                raw = self._analysis_agent.invoke({"messages": prompt})
                result: PostAnalysisOutput = raw["structured_response"]
                return {
                    "sentiment": result.sentiment,
                    "summary_zh": result.summary_zh,
                    "assets": [a.model_dump() for a in result.assets],
                    "reasoning": result.reasoning,
                    "error": False,
                }
            except Exception:
                logger.warning("DeepAgent analysis failed (attempt %d/%d)", attempt + 1, self._max_retries + 1)
                if attempt < self._max_retries:
                    time.sleep(_RETRY_DELAY_SEC)
        logger.error("DeepAgent analysis failed after %d attempts", self._max_retries + 1)
        return {
            "sentiment": "error",
            "summary_zh": "分析失敗",
            "assets": [],
            "reasoning": "LLM error",
            "error": True,
        }

    def generate_daily_report(self, analyses_summary: str) -> str:
        prompt = f"今日市場訊號彙整：\n\n{analyses_summary}"
        try:
            _rate_limiter.acquire()
            raw = self._report_agent.invoke({"messages": prompt})
            result: DailyReportOutput = raw["structured_response"]
            return result.report
        except Exception:
            logger.exception("DeepAgent daily report failed")
            return "每日報告生成失敗，請檢查日誌。"

    def parse_sentiment(self, value: str) -> Sentiment:
        mapping = {
            "bullish": Sentiment.BULLISH,
            "bearish": Sentiment.BEARISH,
            "neutral": Sentiment.NEUTRAL,
        }
        return mapping.get(value.lower(), Sentiment.UNCERTAIN)
