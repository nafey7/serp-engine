"""Records every attempt so success rate, block rate and layout breakage are visible.

The same database holds the result cache, so repeated searches don't reach Google.
"""

import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    ts REAL, query TEXT, mode TEXT, proxy TEXT, outcome TEXT,
    status_code INTEGER, elapsed_ms INTEGER, n_organic INTEGER, has_ai_overview INTEGER
);
CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, ts REAL, response TEXT);
"""
# Captchas closer together than this belong to the same block (e.g. retries in one run).
SAME_BLOCK_S = 300


class Stats:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()

    def record(self, query, attempt, n_organic=0, has_ai_overview=False) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)",
                (time.time(), query, attempt.mode, attempt.proxy, attempt.outcome,
                 attempt.status_code, attempt.elapsed_ms, n_organic, int(has_ai_overview)),
            )
            self._db.commit()

    def last_seen(self, outcome: str, since_s: float, mode: str | None = None) -> dict[str, float]:
        """Latest time each proxy got `outcome` within the last `since_s` seconds."""
        sql = "SELECT proxy, MAX(ts) FROM attempts WHERE outcome = ? AND ts > ?"
        args = [outcome, time.time() - since_s]
        if mode:
            sql += " AND mode = ?"
            args.append(mode)
        with self._lock:
            return dict(self._db.execute(sql + " GROUP BY proxy", args).fetchall())

    def last_request(self, proxy_label: str) -> float:
        """Wall-clock time of the latest attempt sent through this proxy, 0 if none."""
        with self._lock:
            row = self._db.execute("SELECT MAX(ts) FROM attempts WHERE proxy = ?", (proxy_label,)).fetchone()
        return row[0] or 0.0

    def requests_since(self, proxy_label: str, since_s: float) -> int:
        """Attempts sent through this proxy in the last `since_s` seconds."""
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) FROM attempts WHERE proxy = ? AND ts > ?", (proxy_label, time.time() - since_s)
            ).fetchone()
        return row[0]

    def oldest_since(self, proxy_label: str, since_s: float) -> float:
        """Time of the oldest attempt through this proxy within the last `since_s` seconds, 0 if none."""
        with self._lock:
            row = self._db.execute(
                "SELECT MIN(ts) FROM attempts WHERE proxy = ? AND ts > ?", (proxy_label, time.time() - since_s)
            ).fetchone()
        return row[0] or 0.0

    def block_history(self, since_s: float) -> dict[str, tuple[float, int]]:
        """Per proxy: (time of latest captcha, number of separate blocks) within the last `since_s` seconds.

        A successful search clears the record: only captchas after the proxy's latest "ok" count.
        """
        with self._lock:
            rows = self._db.execute(
                """SELECT proxy, ts FROM attempts AS a
                   WHERE outcome = 'captcha' AND ts > ?
                     AND ts > COALESCE((SELECT MAX(ts) FROM attempts WHERE proxy = a.proxy AND outcome = 'ok'), 0)
                   ORDER BY ts""",
                (time.time() - since_s,),
            ).fetchall()
        history: dict[str, tuple[float, int]] = {}
        for proxy, ts in rows:
            last, n = history.get(proxy, (0.0, 0))
            history[proxy] = (ts, n + (ts - last > SAME_BLOCK_S))
        return history

    def cache_get(self, key: str, ttl_s: float) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT response FROM cache WHERE key = ? AND ts > ?", (key, time.time() - ttl_s)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, key: str, response: dict, keep_s: float) -> None:
        """Save a result, and drop saved results older than `keep_s` so the cache doesn't grow forever."""
        now = time.time()
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (key, now, json.dumps(response)))
            self._db.execute("DELETE FROM cache WHERE ts < ?", (now - keep_s,))
            self._db.commit()

    def summary(self) -> dict:
        with self._lock:
            rows = self._db.execute(
                """SELECT mode, COUNT(*), SUM(outcome = 'ok'), AVG(elapsed_ms),
                          SUM(has_ai_overview), SUM(outcome = 'empty_parse')
                   FROM attempts GROUP BY mode"""
            ).fetchall()
            outcomes = self._db.execute(
                "SELECT outcome, COUNT(*) FROM attempts GROUP BY outcome ORDER BY 2 DESC"
            ).fetchall()
            cached = self._db.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        by_mode = {
            mode: {
                "attempts": n,
                "success_rate": round(ok / n, 3) if n else 0,
                "avg_ms": int(avg or 0),
                "ai_overviews": aio or 0,
                # Page loaded fine but nothing parsed: usually means Google changed its layout.
                "layout_breaks": empty or 0,
            }
            for mode, n, ok, avg, aio, empty in rows
        }
        return {"by_mode": by_mode, "outcomes": dict(outcomes), "cached_searches": cached}
