"""Unit tests for MemoryQueue."""
import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.msgqueue.memory_queue import MemoryQueue


def test_publish_subscribe_roundtrip():
    q = MemoryQueue()
    received = []
    q.subscribe(lambda msg: received.append(msg))
    q.publish({"post_id": "abc"})
    time.sleep(0.2)
    assert received == [{"post_id": "abc"}]

def test_multiple_messages_in_order():
    q = MemoryQueue()
    received = []
    q.subscribe(lambda msg: received.append(msg["n"]))
    for i in range(5):
        q.publish({"n": i})
    time.sleep(0.3)
    assert received == [0, 1, 2, 3, 4]

def test_full_queue_drops_message():
    q = MemoryQueue(maxsize=2)
    received = []
    q.subscribe(received.append)
    q.publish({"n": 1})
    q.publish({"n": 2})
    q.publish({"n": 3})   # dropped silently — consumer still works
    time.sleep(0.3)
    assert len(received) == 2   # only 2 delivered (3rd was dropped)

def test_handler_exception_does_not_kill_consumer():
    q = MemoryQueue()
    results = []

    def flaky(msg):
        if msg["n"] == 1:
            raise ValueError("intentional error")
        results.append(msg["n"])

    q.subscribe(flaky)
    q.publish({"n": 0})
    q.publish({"n": 1})   # will raise
    q.publish({"n": 2})
    time.sleep(0.4)
    assert results == [0, 2]   # consumer survived and processed n=2


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
