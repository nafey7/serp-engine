"""Records every search and every attempt, so the numbers that matter are visible.

A search is one logical query from a caller. It may take several attempts (fetches
from Google): a retry after a captcha, or a fallback to another mode. Both are kept
apart: search-level numbers (valid rate, first-try rate, p95 time including retries)
come from the searches table, fetch-level numbers from the attempts table.

The same database holds the optional result cache (off by default).
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
CREATE TABLE IF NOT EXISTS searches (
    ts REAL, query TEXT, status TEXT, valid INTEGER, n_attempts INTEGER, elapsed_ms INTEGER,
    aio_requested INTEGER, has_ai_overview INTEGER, n_sources INTEGER, problems TEXT
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

    def record_search(self, response, aio_requested: bool) -> None:
        aio = response.ai_overview
        with self._lock:
            self._db.execute(
                "INSERT INTO searches VALUES (?,?,?,?,?,?,?,?,?,?)",
                (time.time(), response.query, response.status, int(response.valid), len(response.attempts),
                 response.elapsed_ms, int(aio_requested), int(bool(aio)), len(aio.sources) if aio else 0,
                 "; ".join(response.problems)),
            )
            self._db.commit()

    def search_summary(self, since_s: float | None = None) -> dict:
        """Search-level numbers. Searches answered without contacting Google (every IP
        blocked or at its hourly cap) count as searches and as not valid, but not toward speed."""
        where, args = ("WHERE ts > ?", [time.time() - since_s]) if since_s else ("", [])
        with self._lock:
            rows = self._db.execute(
                f"SELECT valid, n_attempts, elapsed_ms, aio_requested, has_ai_overview, problems FROM searches {where}",
                args,
            ).fetchall()
        n = len(rows)
        times = sorted(ms for _, tries, ms, *_ in rows if tries)
        pct = lambda p: times[min(len(times) - 1, int(p * len(times)))] if times else 0
        rate = lambda k: round(k / n, 3) if n else 0
        aio_rows = [r for r in rows if r[3]]
        return {
            "searches": n,
            "valid_rate": rate(sum(r[0] for r in rows)),
            # Valid on the very first fetch: no retry, no fallback to another mode.
            "first_try_valid_rate": rate(sum(1 for r in rows if r[0] and r[1] == 1)),
            "fetch_attempts": sum(r[1] for r in rows),
            "p50_ms": pct(0.50),
            "p95_ms": pct(0.95),
            "ai_overview": {
                "searches_asking": len(aio_rows),
                "found": sum(r[4] for r in aio_rows),
                # Google showed an overview but the parser got nothing: a layout change to fix.
                "shown_but_not_extracted": sum("ai_overview_shown_but_not_extracted" in r[5] for r in aio_rows),
            },
        }

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
        return {
            "searches": self.search_summary(),
            "by_mode": by_mode, "outcomes": dict(outcomes), "cached_searches": cached,
        }
