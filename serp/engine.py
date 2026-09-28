"""One entry point, three modes.

mode="auto" (default):
  0. If the same search was done within SERP_CACHE_TTL, return the saved result
     without contacting Google (pass no_cache=True to skip this).
  1. Try lite mode first: the feature-phone page, one cheap request, no JavaScript.
  2. Then plain HTTP mode (the desktop page, also about 1 second).
  3. Then browser mode for the remaining attempts.
  A mode that failed in a way that will keep failing (e.g. Google asking plain HTTP
  for JavaScript) is skipped for a few hours instead of costing a request each time.
  If the caller wants the AI Overview, go straight to the browser, because the
  overview only appears after JavaScript runs.

Every attempt rotates to the next proxy, and requests through the same IP are
spaced at least SERP_MIN_INTERVAL seconds apart, one at a time, and capped at
SERP_MAX_PER_HOUR per rolling hour. A proxy (or your own IP) that hits a captcha is
benched for SERP_BLOCK_COOLDOWN seconds, doubled for each further block within
24 hours (up to SERP_MAX_COOLDOWN), and that is remembered across runs. When every IP
is benched the search returns status="blocked" (or "throttled" when over the hourly
cap) without contacting Google.

After a successful fetch, every coded /goto link is followed to its real page (all at
once, through the same proxy), and the result is checked: valid=True only when it is
complete (see _problems). Each search is recorded once, apart from its attempts, so the
stats can report searches, valid rate, first-try rate and p95 time separately.

Caching is off by default (SERP_CACHE_TTL=0, SERP_STALE_TTL=0): every search asks Google.
When turned on, a saved result up to SERP_STALE_TTL old is returned if Google can't be
asked, marked stale=True, and identical searches running at the same time share one request.
"""

import json
import os
import random
import threading
import time
from urllib.parse import urlencode, urlsplit

from .config import Config
from .detect import classify_block
from .fetch_browser import BrowserFetcher
from .fetch_http import HttpFetcher, search_params
from .models import Attempt, FetchResult, SerpResponse
from .parser import parse_serp
from .proxies import DIRECT, ProxyPool
from .resolve import is_goto, resolve_links
from .stats import Stats

MODES = ("auto", "lite", "http", "hybrid", "browser")
MODE_RECHECK_S = 6 * 3600
BLOCK_MEMORY_S = 24 * 3600
# Outcomes that mean a mode is broken for us right now, not just unlucky once.
MODE_BROKEN = {"http": ("js_required",), "lite": ("no_results_container", "empty_parse", "http_403")}


class SerpEngine:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.proxies = ProxyPool(self.cfg.proxies, cooldown_s=self.cfg.block_cooldown_s)
        self.stats = Stats(self.cfg.db_path)
        # Blocks outlive the process: remember captchas from earlier runs.
        self.proxies.seed({
            label: ts + self._cooldown(n) for label, (ts, n) in self.stats.block_history(BLOCK_MEMORY_S).items()
        })
        self.http = HttpFetcher(self.cfg)
        self._browser: BrowserFetcher | None = None  # started only when first needed
        # One request at a time per IP, so parallel API calls can't burst past the pacing.
        self._ip_locks: dict[str, threading.Lock] = {}
        # The same search always takes the same lock: a duplicate waits, then finds the first one's result in the cache.
        self._search_locks = [threading.Lock() for _ in range(64)]

    @property
    def browser(self) -> BrowserFetcher:
        if self._browser is None:
            self._browser = BrowserFetcher(self.cfg)
        return self._browser

    def close(self) -> None:
        if self._browser:
            self._browser.close()

    def _cooldown(self, blocks: int) -> float:
        """Bench time after the n-th separate block in 24 hours: 1x, 2x, 4x ... the base, capped."""
        return min(self.cfg.block_cooldown_s * 2 ** max(blocks - 1, 0), self.cfg.max_cooldown_s)

    def _plan(self, mode: str, ai_overview: bool) -> list[str]:
        """Modes to try, in order. The last one is repeated for any remaining attempts."""
        if mode != "auto":
            return [mode]
        if ai_overview:
            # Hybrid returns the complete overview in one fast request when Google accepts the
            # reused cookies; if not, or if the overview came back incomplete, the browser takes over.
            return ["hybrid", "browser"]
        return [m for m in ("lite", "http", "hybrid", "browser") if not self._looks_broken(m)]

    def _looks_broken(self, mode: str) -> bool:
        """True if this mode's latest result in the last few hours was a lasting failure, not a success."""
        latest = lambda outcome: max(self.stats.last_seen(outcome, MODE_RECHECK_S, mode=mode).values(), default=0)
        failed = max((latest(o) for o in MODE_BROKEN.get(mode, ())), default=0)
        return failed > latest("ok")

    def _next_proxy(self) -> tuple[str | None, str]:
        """Next proxy that is neither benched nor over its hourly cap, else (None, "blocked" or "throttled")."""
        for _ in range(max(len(self.cfg.proxies), 1)):
            proxy = self.proxies.next()
            if proxy is None:
                return None, "blocked"
            if not self.cfg.max_per_hour or self.stats.requests_since(ProxyPool.label(proxy), 3600) < self.cfg.max_per_hour:
                return proxy, ""
        return None, "throttled"

    def _throttled_for_s(self) -> int:
        """Seconds until the first IP drops back under its hourly cap."""
        oldest = min(self.stats.oldest_since(ProxyPool.label(p), 3600) for p in (self.cfg.proxies or [DIRECT]))
        return max(0, int(oldest + 3600 - time.time()))

    def _pace(self, proxy: str) -> None:
        wait = self.cfg.min_interval_s * random.uniform(0.7, 1.3) - (
            time.time() - self.stats.last_request(ProxyPool.label(proxy))
        )
        if wait > 0:
            time.sleep(wait)

    def _save_html(self, html: str, mode: str, outcome: str) -> None:
        if not self.cfg.save_html_dir:
            return
        os.makedirs(self.cfg.save_html_dir, exist_ok=True)
        name = f"{time.strftime('%Y%m%d-%H%M%S')}_{mode}_{outcome}.html"
        with open(os.path.join(self.cfg.save_html_dir, name), "w") as f:
            f.write(html)

    def search(
        self,
        query: str,
        mode: str = "auto",
        ai_overview: bool = False,
        start: int = 0,
        tbs: str = "",
        no_cache: bool = False,
    ) -> SerpResponse:
        """`start` is the result offset (10 = page 2); `tbs` is Google's filter, e.g. "qdr:w" = past week."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        params = search_params(self.cfg, query, start, tbs)
        cache_key = json.dumps([params, mode, ai_overview])
        with self._search_locks[hash(cache_key) % len(self._search_locks)]:
            response = self._search(query, mode, ai_overview, params, cache_key, start, tbs, no_cache)
        if not response.cached or response.stale:
            self.stats.record_search(response, ai_overview)
        return response

    def _search(self, query, mode, ai_overview, params, cache_key, start, tbs, no_cache) -> SerpResponse:
        begin = time.monotonic()
        if self.cfg.cache_ttl_s and not no_cache:
            hit = self.stats.cache_get(cache_key, self.cfg.cache_ttl_s)
            if hit:
                response = SerpResponse.from_dict(hit)
                response.cached = True
                response.elapsed_ms = int((time.monotonic() - begin) * 1000)
                return response

        plan = self._plan(mode, ai_overview)
        response = SerpResponse(
            query=query, status="failed", mode=None,
            google_url="https://www.google.com/search?" + urlencode(params),
        )

        for i in range(self.cfg.max_attempts):
            current = plan[min(i, len(plan) - 1)]
            proxy, why = self._next_proxy()
            if why == "blocked":
                response.status = "blocked"
                response.note = (
                    f"Google flagged every available IP. Waiting ~{self.proxies.seconds_until_free() // 60 + 1} min "
                    "before trying again (SERP_BLOCK_COOLDOWN); add proxies with SERP_PROXIES to keep going."
                )
                break
            if why == "throttled":
                response.status = "throttled"
                response.note = (
                    f"Hourly limit of {self.cfg.max_per_hour} requests per IP reached (SERP_MAX_PER_HOUR). "
                    f"Next slot in ~{self._throttled_for_s() // 60 + 1} min; Google was not contacted."
                )
                break
            with self._ip_locks.setdefault(ProxyPool.label(proxy), threading.Lock()):
                attempt, parsed, fetched = self._attempt(query, current, proxy, ai_overview, start, tbs)
            response.attempts.append(attempt)
            if attempt.outcome == "ok":
                response.status, response.mode = "ok", current
                response.organic = parsed.organic
                response.people_also_ask = parsed.people_also_ask
                response.related_searches = parsed.related_searches
                response.ai_overview = parsed.ai_overview
                self._resolve(response, proxy, fetched.links)
                response.problems = self._problems(response, ai_overview, fetched, parsed)
                response.valid = not response.problems
                break

            if attempt.outcome == "captcha":
                _, blocks = self.stats.block_history(BLOCK_MEMORY_S).get(attempt.proxy, (0, 1))
                self.proxies.mark_blocked(proxy, self._cooldown(blocks))

        if response.status == "ok":
            response.created_at = time.time()
            if self.cfg.cache_ttl_s:
                # Keep rows as long as the stale fallback may still use them.
                self.stats.cache_put(cache_key, response.to_dict(), max(self.cfg.cache_ttl_s, self.cfg.stale_ttl_s))
        elif self.cfg.stale_ttl_s and (old := self.stats.cache_get(cache_key, self.cfg.stale_ttl_s)):
            # Better an older answer than none while Google is off limits.
            stale = SerpResponse.from_dict(old)
            stale.cached = stale.stale = True
            stale.valid, stale.problems = False, ["stale"]
            # The status still says what happened this time; stale=True says the results are older.
            stale.status, stale.attempts, stale.note = response.status, response.attempts, (
                f"Showing a saved result from {time.strftime('%Y-%m-%d %H:%M', time.localtime(stale.created_at))} "
                f"because this search came back {response.status!r}. {response.note}"
            ).strip()
            response = stale
        response.elapsed_ms = int((time.monotonic() - begin) * 1000)
        return response

    def _resolve(self, response: SerpResponse, proxy: str, started: dict) -> None:
        """Replace coded /goto links with the real page URLs."""
        sources = response.ai_overview.sources if response.ai_overview else []
        found = resolve_links([o.url for o in response.organic] + [s["url"] for s in sources], proxy, started)
        for o in response.organic:
            o.url = found.get(o.url, o.url)
            if not o.domain and not is_goto(o.url):
                o.domain = (urlsplit(o.url).hostname or "").removeprefix("www.")
        if response.ai_overview:
            # Two coded links can lead to the same page: keep the first.
            unique: dict[str, dict] = {}
            for s in sources:
                s["url"] = found.get(s["url"], s["url"])
                unique.setdefault(s["url"], s)
            response.ai_overview.sources = list(unique.values())

    @staticmethod
    def _problems(response: SerpResponse, ai_overview: bool, fetched: FetchResult, parsed) -> list[str]:
        """Why a fetched result is not complete. Empty means valid."""
        problems = []
        if not response.organic:
            problems.append("no_organic_results")
        unresolved = sum(is_goto(o.url) for o in response.organic)
        if response.ai_overview:
            unresolved += sum(is_goto(s["url"]) for s in response.ai_overview.sources)
            if not response.ai_overview.sources:
                problems.append("ai_overview_without_sources")
        if unresolved:
            problems.append(f"unresolved_links: {unresolved}")
        if any(not o.title for o in response.organic):
            problems.append("organic_result_without_title")
        if ai_overview and fetched.aio_shown and not response.ai_overview:
            problems.append("ai_overview_shown_but_not_extracted")
        elif ai_overview and response.ai_overview and (fetched.aio_complete is False or not parsed.ai_overview_complete):
            # Google was still writing the answer (or its source list is missing): the text may be cut off.
            problems.append("ai_overview_incomplete")
        return problems

    def _attempt(self, query, mode, proxy, ai_overview, start, tbs):
        """Pace, send one request, classify and parse it, and record the attempt."""
        self._pace(proxy)
        attempt = Attempt(mode=mode, proxy=ProxyPool.label(proxy), outcome="ok", status_code=0, elapsed_ms=0)
        parsed, fetched = None, None
        try:
            if mode == "lite":
                fetched = self.http.fetch_lite(query, proxy, start, tbs)
            elif mode == "http":
                fetched = self.http.fetch(query, proxy, start, tbs)
            elif mode == "hybrid":
                session = self.browser.google_session(proxy)
                fetched = self.http.fetch_hybrid(query, proxy, session, start, tbs)
            else:
                fetched = self.browser.fetch(query, proxy, want_ai_overview=ai_overview, start=start, tbs=tbs)
            attempt.status_code, attempt.elapsed_ms = fetched.status_code, fetched.elapsed_ms
            block = classify_block(fetched.status_code, fetched.final_url, fetched.html)
            self._save_html(fetched.html, mode, block or "ok")
            if block:
                attempt.outcome = block
                if mode == "hybrid":
                    self.browser.forget_google_session(proxy)  # get new cookies next time
            else:
                parsed = parse_serp(fetched.html, fill_deferred=(mode == "hybrid"))
                if not parsed.organic and not parsed.ai_overview:
                    attempt.outcome = "empty_parse"
                elif mode == "hybrid" and ai_overview and parsed.ai_overview and not parsed.ai_overview_complete:
                    # The page was fine but the overview is cut off: let the browser finish it.
                    attempt.outcome = "aio_incomplete"
        except Exception as e:  # network errors, timeouts, browser crashes
            attempt.outcome, attempt.detail = "error", f"{type(e).__name__}: {e}"[:300]
        self.stats.record(
            query, attempt,
            n_organic=len(parsed.organic) if parsed else 0,
            has_ai_overview=bool(parsed and parsed.ai_overview),
        )
        return attempt, parsed, fetched
