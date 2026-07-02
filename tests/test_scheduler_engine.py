"""Tests for SchedulerEngine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch


def make_settings(groups=None, report_time="08:00"):
    s = MagicMock()
    s.DAILY_REPORT_TIME = report_time
    s.LINE_GROUP_IDS = groups or {"g1": "G1", "g2": "G2"}
    return s


def make_engine(rows=None, groups=None):
    from src.services.scheduler_engine import SchedulerEngine

    repo = MagicMock()
    repo.get_daily_analyses.return_value = rows if rows is not None else []
    llm = MagicMock()
    llm.generate_daily_report.return_value = "Market summary"
    notifier = MagicMock()
    settings = make_settings(groups=groups)

    engine = SchedulerEngine(repo=repo, llm=llm, notifier=notifier, settings=settings)
    return engine, repo, llm, notifier


# ── start / shutdown ──────────────────────────────────────────────────────────

def test_start_registers_job():
    engine, _, _, _ = make_engine()
    engine.start()
    assert len(engine.get_jobs()) == 1
    engine.shutdown()


def test_start_idempotent():
    engine, _, _, _ = make_engine()
    engine.start()
    engine.start()
    assert len(engine.get_jobs()) == 1
    engine.shutdown()


def test_shutdown_stops_scheduler():
    engine, _, _, _ = make_engine()
    engine.start()
    assert engine.running is True
    engine.shutdown()
    assert engine.running is False


# ── _run_daily_report ─────────────────────────────────────────────────────────

def make_row(sentiment="bullish", author="elonmusk", summary="Tesla up"):
    return {"sentiment": sentiment, "author_name": author, "summary_zh": summary}


def test_daily_report_skips_empty():
    engine, _, llm, notifier = make_engine(rows=[])
    engine._run_daily_report()
    llm.generate_daily_report.assert_not_called()
    notifier.push.assert_not_called()


def test_daily_report_sends_to_groups():
    engine, _, llm, notifier = make_engine(rows=[make_row()], groups={"g1": "G1", "g2": "G2"})
    engine._run_daily_report()
    assert notifier.push.call_count == 2
    group_ids = [c[0][0] for c in notifier.push.call_args_list]
    assert set(group_ids) == {"G1", "G2"}


def test_daily_report_null_sentiment():
    engine, _, _, notifier = make_engine(rows=[make_row(sentiment=None)])
    engine._run_daily_report()   # should not raise
    assert notifier.push.call_count >= 1
