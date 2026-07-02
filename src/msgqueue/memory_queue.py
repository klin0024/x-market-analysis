from __future__ import annotations

import queue
import threading
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class MemoryQueue:
    """In-process queue backed by Python's thread-safe queue.Queue."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._q: queue.Queue[dict] = queue.Queue(maxsize=maxsize)
        self._handler: Callable[[dict], None] | None = None
        self._worker: threading.Thread | None = None

    def publish(self, msg: dict) -> None:
        try:
            self._q.put_nowait(msg)
        except queue.Full:
            logger.warning("MemoryQueue full, dropping message")

    def subscribe(self, handler: Callable[[dict], None]) -> None:
        self._handler = handler
        self._worker = threading.Thread(target=self._consume_loop, daemon=True)
        self._worker.start()

    def ack(self, msg_id: str) -> None:
        pass  # no-op for in-memory queue

    def nack(self, msg_id: str) -> None:
        pass  # no-op; failed messages are simply dropped

    def _consume_loop(self) -> None:
        while True:
            try:
                msg = self._q.get(timeout=1)
                try:
                    if self._handler:
                        self._handler(msg)
                except Exception:
                    logger.exception("Handler error for message: %s", msg.get("post_id"))
                finally:
                    self._q.task_done()
            except queue.Empty:
                continue
