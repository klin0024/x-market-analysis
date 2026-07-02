from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


class MarketClient:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "Mozilla/5.0"

    def get_price_change(self, ticker: str) -> tuple[float, float]:
        """Return (current_price, change_pct). Returns (0, 0) on error."""
        try:
            url = YAHOO_QUOTE_URL.format(ticker=ticker)
            resp = self._session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            meta = data["chart"]["result"][0]["meta"]
            current = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", current) or current
            change_pct = ((current - prev_close) / prev_close * 100) if prev_close else 0
            return round(current, 4), round(change_pct, 4)
        except Exception:
            logger.warning("Failed to fetch price for %s", ticker)
            return 0.0, 0.0

    def get_prices_bulk(self, tickers: list[str]) -> dict[str, tuple[float, float]]:
        return {t: self.get_price_change(t) for t in tickers}
