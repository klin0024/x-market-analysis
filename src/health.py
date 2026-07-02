"""
Health check — 驗證所有外部依賴是否可用，並檢查內部 thread 存活狀態。
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    elapsed_ms: int = 0


@dataclass
class HealthReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return all(r.ok for r in self.results)

    def print(self) -> None:
        print("\n─── Health Check ───────────────────────────────")
        for r in self.results:
            icon = "✅" if r.ok else "❌"
            print(f"  {icon}  {r.name:<22} {r.detail}  ({r.elapsed_ms}ms)")
        status = "ALL OK" if self.healthy else "DEGRADED"
        print(f"──────────────────────────────────── {status}\n")


def _check(name: str, fn) -> CheckResult:
    t0 = time.monotonic()
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"exception: {e}"
    elapsed = int((time.monotonic() - t0) * 1000)
    return CheckResult(name=name, ok=ok, detail=detail, elapsed_ms=elapsed)


# ── External service checks ───────────────────────────────────────────────────

def check_sqlite(db_path: str) -> CheckResult:
    def _fn():
        conn = sqlite3.connect(db_path, timeout=3)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        required = {"posts", "analyses", "notifications", "queue"}
        missing = required - tables
        if missing:
            return False, f"missing tables: {missing}"
        return True, f"{len(tables)} tables OK"
    return _check("SQLite", _fn)


def check_queue(db_path: str) -> CheckResult:
    def _fn():
        conn = sqlite3.connect(db_path, timeout=3)
        row = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE status='pending'"
        ).fetchone()
        conn.close()
        pending = row[0] if row else 0
        if pending > 1000:
            return False, f"queue backlog too large: {pending}"
        return True, f"pending={pending}"
    return _check("Queue", _fn)


def check_line(token: str, group_ids: dict) -> CheckResult:
    def _fn():
        if not token:
            return False, "LINE_CHANNEL_ACCESS_TOKEN not set"
        resp = requests.get(
            "https://api.line.me/v2/bot/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        name = resp.json().get("displayName", "unknown")
        return True, f"bot={name}, groups={len(group_ids)}"
    return _check("LINE API", _fn)


def check_google_api(api_key: str) -> CheckResult:
    def _fn():
        if not api_key:
            return False, "GOOGLE_API_KEY not set"
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=5,
        )
        if resp.status_code == 200:
            return True, "key valid"
        return False, f"HTTP {resp.status_code}"
    return _check("Google Gemini", _fn)


def check_yahoo_finance() -> CheckResult:
    def _fn():
        resp = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/SPY",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        price = resp.json()["chart"]["result"][0]["meta"].get("regularMarketPrice", 0)
        return True, f"SPY={price}"
    return _check("Yahoo Finance", _fn)


# ── Internal component checks ────────────────────────────────────────────────

def check_fetcher(fetcher) -> CheckResult:
    def _fn():
        if fetcher is None:
            return False, "not initialized"
        if fetcher.is_alive():
            return True, "thread alive"
        return False, "thread dead"
    return _check("Fetcher", _fn)


def check_queue_consumer(queue) -> CheckResult:
    def _fn():
        if queue is None:
            return False, "not initialized"
        if queue.is_alive():
            return True, "consumer alive"
        return False, "consumer dead"
    return _check("Queue consumer", _fn)


def check_scheduler(scheduler) -> CheckResult:
    def _fn():
        if scheduler is None:
            return False, "not initialized"
        if not scheduler.running:
            return False, "scheduler stopped"
        jobs = scheduler.get_jobs()
        return True, f"{len(jobs)} job(s) scheduled"
    return _check("Scheduler", _fn)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_health_check(settings, fetcher=None, queue=None, scheduler=None) -> HealthReport:
    report = HealthReport()
    report.results.append(check_sqlite(settings.SQLITE_PATH))
    report.results.append(check_queue(settings.SQLITE_PATH))
    report.results.append(check_line(settings.LINE_CHANNEL_ACCESS_TOKEN, settings.LINE_GROUP_IDS))
    report.results.append(check_google_api(settings.GOOGLE_API_KEY))
    report.results.append(check_yahoo_finance())
    if fetcher is not None:
        report.results.append(check_fetcher(fetcher))
    if queue is not None:
        report.results.append(check_queue_consumer(queue))
    if scheduler is not None:
        report.results.append(check_scheduler(scheduler))
    return report
