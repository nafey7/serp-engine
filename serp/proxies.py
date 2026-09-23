import threading
import time
from urllib.parse import urlsplit

DIRECT = "direct"


class ProxyPool:
    """Round-robin proxy rotation. A proxy that gets blocked sits out for a cooldown."""

    def __init__(self, proxies: list[str], cooldown_s: float = 60.0):
        self._proxies = proxies or [DIRECT]
        self._cooldown_s = cooldown_s
        self._benched_until: dict[str, float] = {}
        self._i = 0
        self._lock = threading.Lock()

    def next(self) -> str | None:
        """Next usable proxy, or None when every one is cooling down after a block."""
        with self._lock:
            now = time.monotonic()
            for _ in range(len(self._proxies)):
                proxy = self._proxies[self._i % len(self._proxies)]
                self._i += 1
                if self._benched_until.get(self.label(proxy), 0) <= now:
                    return proxy
            return None

    def mark_blocked(self, proxy: str, cooldown_s: float | None = None) -> None:
        # The direct connection is benched too: hitting Google again from a flagged IP extends the block.
        with self._lock:
            self._benched_until[self.label(proxy)] = time.monotonic() + (cooldown_s or self._cooldown_s)

    def seed(self, free_at: dict[str, float]) -> None:
        """Bench proxies (by label) that were blocked in earlier runs. `free_at` holds wall-clock times."""
        with self._lock:
            for label, ts in free_at.items():
                self._benched_until[label] = time.monotonic() + (ts - time.time())

    def seconds_until_free(self) -> int:
        with self._lock:
            now = time.monotonic()
            return max(0, int(min(self._benched_until.get(self.label(p), 0) for p in self._proxies) - now))

    @staticmethod
    def label(proxy: str) -> str:
        """Proxy name safe for logs (no credentials)."""
        if proxy == DIRECT:
            return DIRECT
        parts = urlsplit(proxy)
        return f"{parts.hostname}:{parts.port}"
