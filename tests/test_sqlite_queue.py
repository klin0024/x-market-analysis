"""Tests for SQLiteQueue."""
import sys, os, tempfile, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.msgqueue.sqlite_queue import SQLiteQueue


def fresh_queue():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return SQLiteQueue(db_path=f.name, poll_interval=0.05)


def test_publish_stores_pending():
    q = fresh_queue()
    q.publish({"post_id": "p1"})
    assert q.pending_count() == 1


def test_pending_count_zero_initially():
    q = fresh_queue()
    assert q.pending_count() == 0


def test_is_alive_false_before_subscribe():
    q = fresh_queue()
    assert q.is_alive() is False


def test_subscribe_starts_consumer():
    q = fresh_queue()
    q.subscribe(lambda msg: None)
    time.sleep(0.1)
    assert q.is_alive() is True


def test_handler_called_with_message():
    q = fresh_queue()
    received = []
    q.subscribe(received.append)
    q.publish({"post_id": "p1", "content": "hello"})
    time.sleep(0.3)
    assert len(received) == 1
    assert received[0]["post_id"] == "p1"


def test_multiple_messages_delivered_in_order():
    q = fresh_queue()
    received = []
    q.subscribe(received.append)
    for i in range(3):
        q.publish({"seq": i})
    time.sleep(0.5)
    assert len(received) == 3
    assert [r["seq"] for r in received] == [0, 1, 2]


def test_handler_exception_doesnt_kill_consumer():
    q = fresh_queue()
    results = []

    def flaky_handler(msg):
        if msg.get("fail"):
            raise RuntimeError("boom")
        results.append(msg)

    q.subscribe(flaky_handler)
    q.publish({"fail": True})
    q.publish({"post_id": "ok"})
    time.sleep(0.5)
    assert len(results) == 1
    assert results[0]["post_id"] == "ok"
    assert q.is_alive() is True


def test_processing_reset_on_startup():
    # Simulate a stuck 'processing' row from a prior crash
    q = fresh_queue()
    import sqlite3
    conn = sqlite3.connect(q._path)
    conn.execute("INSERT INTO queue (msg, status) VALUES ('{\"x\":1}', 'processing')")
    conn.commit()
    conn.close()

    received = []
    q2 = SQLiteQueue(db_path=q._path, poll_interval=0.05)
    q2.subscribe(received.append)
    time.sleep(0.3)
    assert len(received) == 1
