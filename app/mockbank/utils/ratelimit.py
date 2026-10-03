import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """In-process limiter: at most `limit` calls per `window_seconds` per key.

    Counts reset when the process restarts, which is acceptable for a single-instance mock.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            calls = self._calls[key]
            while calls and now - calls[0] >= self.window:
                calls.popleft()
            if len(calls) >= self.limit:
                return False
            calls.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()
