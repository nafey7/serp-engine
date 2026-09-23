"""Checks that need no network: block detection, cooldown behaviour, parsing."""

import time
from pathlib import Path

import pytest

from serp.config import Config
from serp.detect import classify_block
from serp.engine import SerpEngine
from serp.fetch_http import HttpFetcher
from serp.models import Attempt, FetchResult
from serp.parser import parse_serp
from serp.proxies import DIRECT, ProxyPool

# Taken before conftest swaps it for a stub, so the redirect handling can be tested against a fake transport.
REAL_GET = HttpFetcher._get

RESULTS_PAGE = """<html><body><div id="search"><div id="rso">
<div><a href="https://example.com/shoes"><h3>Best Shoes</h3></a><div class="VwiC3b">Great shoes.</div></div>
</div></div>
<noscript><meta content="0;url=/httpservice/retry/enablejs?sei=x" http-equiv="refresh"></noscript>
</body></html>"""
JS_PAGE = '<html><noscript><meta content="0;url=/httpservice/retry/enablejs?sei=x" http-equiv="refresh"></noscript></html>'
SORRY_PAGE = '<form id="captcha-form"></form>Our systems have detected unusual traffic'
# Shape of the feature phone page, using the class names SearXNG relies on.
LITE_PAGE = """<?xml version="1.0" encoding="UTF-8"?><html><body>
<div class="zMzFAb"><a class="fuLhoc" href="/url?q=https://example.com/a&amp;sa=U&amp;ved=x"><span class="CVA68e">Result A</span></a>
<div class="taTFJ"><span class="FrIlee">About A.</span></div></div>
<div class="zMzFAb"><span>Top stories</span></div>
<div class="zMzFAb"><a class="fuLhoc" href="/url?q=https://example.org/b&amp;sa=U"><span class="CVA68e">Result B</span></a></div>
<table class="HExoMb"><tr><td><a class="ZWRArf" href="/search?q=result+c&amp;sa=X">result c</a></td></tr></table>
</body></html>"""
BOTSTUFF = """<div id="botstuff"><a href="/search?q=best+trail+shoes&amp;sa=X">best <b>trail</b> shoes</a>
<a href="/search?q=best+shoes&amp;start=10">Next</a></div>"""


def test_results_page_with_noscript_fallback_is_ok():
    assert classify_block(200, "https://www.google.com/search?q=x", RESULTS_PAGE) is None


def test_js_and_captcha_pages_are_flagged():
    assert classify_block(200, "https://www.google.com/search?q=x", JS_PAGE) == "js_required"
    assert classify_block(200, "https://www.google.com/sorry/index", SORRY_PAGE) == "captcha"


def test_parse_results_page():
    organic = parse_serp(RESULTS_PAGE).organic
    assert [(o.title, o.url, o.snippet) for o in organic] == [("Best Shoes", "https://example.com/shoes", "Great shoes.")]


def test_direct_ip_is_benched_after_a_block():
    pool = ProxyPool([], cooldown_s=60)
    assert pool.next() == DIRECT
    pool.mark_blocked(DIRECT)
    assert pool.next() is None
    assert pool.seconds_until_free() > 50


def test_blocks_from_earlier_runs_are_remembered():
    pool = ProxyPool(["http://u:p@1.2.3.4:80", "http://5.6.7.8:80"], cooldown_s=60)
    pool.seed({"1.2.3.4:80": time.time() + 50})  # free again in 50 seconds
    assert [pool.next() for _ in range(3)] == ["http://5.6.7.8:80"] * 3


def test_engine_sends_nothing_while_blocked(tmp_path, monkeypatch):
    engine = SerpEngine(Config(proxies=[], db_path=str(tmp_path / "s.db")))
    engine.proxies.mark_blocked(DIRECT)
    monkeypatch.setattr(engine.http, "fetch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent a request")))
    r = engine.search("x", mode="http")
    assert r.status == "blocked" and not r.attempts and r.note


def _engine(tmp_path, **cfg):
    return SerpEngine(Config(proxies=[], db_path=str(tmp_path / "s.db"), min_interval_s=0, **cfg))


def _fake(html, status=200, url="https://www.google.com/search?q=x"):
    return lambda *a, **k: FetchResult(status_code=status, final_url=url, html=html, elapsed_ms=1)


def _never(*a, **k):
    raise AssertionError("sent a request")


def test_lite_page_is_recognised_and_parsed():
    assert classify_block(200, "https://www.google.com/wml/search?q=x", LITE_PAGE) is None
    parsed = parse_serp(LITE_PAGE)
    assert [(o.title, o.url, o.snippet) for o in parsed.organic] == [
        ("Result A", "https://example.com/a", "About A."),
        ("Result B", "https://example.org/b", ""),
    ]
    assert parsed.related_searches == ["result c"]


def test_tiny_sorry_redirect_page_is_a_captcha():
    page = '<meta http-equiv="refresh" content="0;url=https://www.google.com/sorry/index?continue=x">'
    assert classify_block(200, "https://www.google.com/search?q=x", page) == "captcha"


def test_related_searches_skip_pagination():
    assert parse_serp(RESULTS_PAGE + BOTSTUFF).related_searches == ["best trail shoes"]


def test_auto_tries_lite_first_and_caches(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setattr(engine.http, "fetch_lite", _fake(LITE_PAGE))
    monkeypatch.setattr(engine.http, "fetch", _never)
    r = engine.search("x")
    assert r.status == "ok" and r.mode == "lite" and not r.cached and len(r.organic) == 2

    monkeypatch.setattr(engine.http, "fetch_lite", _never)
    again = engine.search("x")
    assert again.cached and again.organic == r.organic and again.related_searches == ["result c"]
    fresh = engine.search("x", no_cache=True)  # skipping the cache really asks Google
    assert "sent a request" in fresh.attempts[0].detail
    assert [a.mode for a in fresh.attempts] == ["lite", "http", "browser"]
    assert "must not contact Google" in fresh.attempts[2].detail
    # Every mode failed, so the saved copy comes back, flagged as stale, with the real status.
    assert fresh.stale and fresh.status == "failed" and fresh.organic == r.organic and "saved result" in fresh.note


def test_auto_falls_back_from_lite_to_http(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setattr(engine.http, "fetch_lite", _fake("<html>odd page</html>"))
    monkeypatch.setattr(engine.http, "fetch", _fake(RESULTS_PAGE))
    r = engine.search("x")
    assert [a.mode for a in r.attempts] == ["lite", "http"] and r.status == "ok"
    # Lite failed and has not worked since, so the next search skips it.
    assert engine._plan("auto", False) == ["http", "browser"]


def test_failed_searches_are_not_cached(tmp_path, monkeypatch):
    engine = _engine(tmp_path, max_attempts=1)
    monkeypatch.setattr(engine.http, "fetch_lite", _fake(JS_PAGE))
    assert engine.search("x").status == "failed"
    assert engine.stats.cache_get('x', 3600) is None and engine.stats.summary()["cached_searches"] == 0


def test_repeat_blocks_double_the_cooldown(tmp_path, monkeypatch):
    engine = _engine(tmp_path, block_cooldown_s=100, max_cooldown_s=350)
    assert [engine._cooldown(n) for n in (1, 2, 3, 4)] == [100, 200, 350, 350]
    now = time.time()
    rows = [now - 1000, now - 990, now - 600, now - 5]  # the first two are one burst
    for ts in rows:
        engine.stats._db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)", (ts, "x", "browser", DIRECT, "captcha", 200, 1, 0, 0))
    engine.stats._db.commit()
    assert engine.stats.block_history(3600) == {DIRECT: (rows[-1], 3)}
    # A fresh engine remembers: 3 blocks -> 350s (capped), counted from the last captcha.
    later = _engine(tmp_path, block_cooldown_s=100, max_cooldown_s=350)
    assert later.proxies.next() is None and 330 < later.proxies.seconds_until_free() <= 345


def test_requests_through_one_ip_are_spaced(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    engine.cfg.min_interval_s = 10
    engine.stats._db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)", (time.time() - 4, "x", "lite", DIRECT, "ok", 200, 1, 1, 0))
    slept = []
    monkeypatch.setattr("serp.engine.time.sleep", slept.append)
    engine._pace(DIRECT)
    assert slept and 2 < slept[0] < 10


def test_real_desktop_page_2026_09():
    # Saved from a live browser-mode run. Links are coded /goto redirects.
    html = (Path(__file__).parent / "fixtures" / "desktop_2026-09_running_shoes.html").read_text()
    assert classify_block(200, "https://www.google.com/search?q=best+running+shoes", html) is None
    r = parse_serp(html)
    assert len(r.organic) == 8
    first = r.organic[0]
    assert first.title == "7 Best Running Shoes in 2026" and first.domain == "runrepeat.com"
    assert first.url.startswith("https://www.google.com/goto?url=") and first.snippet
    assert r.organic[2].source.startswith("Reddit") and not r.organic[2].domain
    assert r.ai_overview.text.startswith("The best running shoes for daily training")
    assert "What are the best shoes for running?" in r.people_also_ask


def test_success_clears_earlier_blocks(tmp_path):
    from serp.models import Attempt
    from serp.stats import Stats

    stats = Stats(str(tmp_path / "s.db"))
    stats.record("q", Attempt(mode="browser", proxy=DIRECT, outcome="captcha", status_code=200, elapsed_ms=1))
    assert DIRECT in stats.block_history(3600)
    stats.record("q", Attempt(mode="browser", proxy=DIRECT, outcome="ok", status_code=200, elapsed_ms=1))
    assert stats.block_history(3600) == {}


def test_related_searches_on_real_desktop_page():
    from pathlib import Path

    html = (Path(__file__).parent / "fixtures" / "desktop_2026-09_running_shoes.html").read_text()
    related = parse_serp(html).related_searches
    assert len(related) == 8 and related[0] == "Best running shoes men"


@pytest.mark.parametrize("name, opening, n_sources", [
    ("hello_world_aio", 'A "Hello, World!" program is a simple computer code', 8),
    ("running_shoes", "The best running shoes for daily training", 3),
    ("sourdough", "To make basic sourdough bread", 8),
])
def test_ai_overview_on_real_pages(name, opening, n_sources):
    # Since 2026 the overview body sits under a hidden "AI Mode replied:" label, next to hidden
    # "not available" messages and Google's internal state strings; none of those may leak in.
    html = (Path(__file__).parent / "fixtures" / f"desktop_2026-09_{name}.html").read_text()
    aio = parse_serp(html).ai_overview
    assert aio.text.startswith(opening) and len(aio.text) > 1000
    for junk in ("AI Mode replied", "not available", "|", "/HugV6", "Go to product viewer"):
        assert junk not in aio.text
    assert len(aio.sources) == n_sources
    assert all(s["title"] and s["url"].startswith("https://www.google.com/goto?url=") for s in aio.sources)


def test_page_without_overview_text_has_no_ai_overview():
    # Only the hidden placeholders: Google offered no overview for this search.
    html = """<div><div>AI Overview</div><span>An AI Overview is not available for this search</span>
    <span>Can't generate an AI overview right now. Try again later.</span></div>"""
    assert parse_serp(html).ai_overview is None


def test_old_cache_rows_are_dropped(tmp_path):
    from serp.stats import Stats

    stats = Stats(str(tmp_path / "s.db"))
    stats.cache_put("old", {"q": 1}, keep_s=60)
    stats._db.execute("UPDATE cache SET ts = ts - 120 WHERE key = 'old'")
    stats.cache_put("new", {"q": 2}, keep_s=60)
    assert [k for (k,) in stats._db.execute("SELECT key FROM cache")] == ["new"]


class _Resp:
    def __init__(self, status, url, location="", text=""):
        self.status_code, self.url, self.text, self.headers = status, url, text, {"location": location}


def test_captcha_redirect_is_not_followed(monkeypatch):
    calls = []

    def fake_get(url, **k):
        calls.append(url)
        return _Resp(302, "https://www.google.com/wml/search?q=x", location="https://www.google.com/sorry/index?continue=x")

    monkeypatch.setattr("serp.fetch_http.requests.get", fake_get)
    got = REAL_GET(HttpFetcher(Config()), "https://www.google.com/wml/search", {"q": "x"}, DIRECT, "chrome")
    assert len(calls) == 1  # the sorry page itself was never loaded
    assert classify_block(got.status_code, got.final_url, got.html) == "captcha"


def test_other_redirects_are_followed(monkeypatch):
    replies = [_Resp(301, "https://google.com/search?q=x", location="/search?q=x"),
               _Resp(200, "https://www.google.com/search?q=x", text=RESULTS_PAGE)]
    monkeypatch.setattr("serp.fetch_http.requests.get", lambda url, **k: replies.pop(0))
    got = REAL_GET(HttpFetcher(Config()), "https://google.com/search", {"q": "x"}, DIRECT, "chrome")
    assert got.status_code == 200 and classify_block(got.status_code, got.final_url, got.html) is None


def _log(engine, n, outcome="ok", age_s=60):
    for _ in range(n):
        engine.stats.record("q", Attempt(mode="lite", proxy=DIRECT, outcome=outcome, status_code=200, elapsed_ms=1))
    engine.stats._db.execute("UPDATE attempts SET ts = ts - ?", (age_s,))
    engine.stats._db.commit()


def test_hourly_limit_stops_requests(tmp_path, monkeypatch):
    engine = _engine(tmp_path, max_per_hour=3)
    _log(engine, 3, age_s=600)  # three requests ten minutes ago
    monkeypatch.setattr(engine.http, "fetch_lite", _never)
    r = engine.search("x", mode="lite")
    assert r.status == "throttled" and not r.attempts and "~50 min" in r.note


def test_hourly_limit_frees_up_after_an_hour(tmp_path, monkeypatch):
    engine = _engine(tmp_path, max_per_hour=3)
    _log(engine, 3, age_s=3700)
    monkeypatch.setattr(engine.http, "fetch_lite", _fake(LITE_PAGE))
    assert engine.search("x", mode="lite").status == "ok"


def test_stale_copy_is_served_while_blocked(tmp_path, monkeypatch):
    engine = _engine(tmp_path, cache_ttl_s=60)
    monkeypatch.setattr(engine.http, "fetch_lite", _fake(LITE_PAGE))
    first = engine.search("x", mode="lite")
    engine.stats._db.execute("UPDATE cache SET ts = ts - 7200")  # now past the normal cache time
    engine.stats._db.commit()
    engine.proxies.mark_blocked(DIRECT)
    monkeypatch.setattr(engine.http, "fetch_lite", _never)
    r = engine.search("x", mode="lite")
    assert r.status == "blocked" and r.stale and r.cached and r.organic == first.organic and not r.attempts
    assert "flagged every available IP" in r.note

    engine.cfg.stale_ttl_s = 0  # turned off: a blocked search returns nothing
    assert not engine.search("x", mode="lite").organic


def test_duplicate_searches_at_once_send_one_request(tmp_path, monkeypatch):
    import threading

    engine = _engine(tmp_path)
    calls, gate = [], threading.Event()

    def slow_lite(*a, **k):
        calls.append(1)
        gate.wait(2)
        return _fake(LITE_PAGE)()

    monkeypatch.setattr(engine.http, "fetch_lite", slow_lite)
    results = []
    threads = [threading.Thread(target=lambda: results.append(engine.search("x", mode="lite"))) for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in threads:
        t.join()
    assert len(calls) == 1 and sorted(r.cached for r in results) == [False, True, True]
