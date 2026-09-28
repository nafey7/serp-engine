"""Time fetch modes on the same searches, and write the results into evidence/.

  serp bench [--modes hybrid,browser] [--gap 180] [--queries "a" "b" ...]

Each query runs once in every mode, one right after the other (the order alternates per
query), so the modes are compared on the same search at nearly the same moment.

Chrome is started before the clock runs (Google is not contacted), as it would be on a
running server. Hybrid's cookies are fetched before the clock runs too (one visit to the
Google homepage, no search), as a server would keep them ready. Lite and HTTP need no warm-up.
Each search gets exactly one fetch (no retry, no fallback to another mode), so a failure is
timed as a failure; with a single IP a retry would only hit the same IP again. Browser and
hybrid searches ask for the AI Overview, as the production requirement does; lite and plain
HTTP pages can't carry one.

When the IP reaches its hourly limit (SERP_MAX_PER_HOUR) the run waits for a free slot
instead of stopping; a captcha stops it (the IP is then benched for an hour or more).

Writes evidence/<timestamp>_bench/: report.md (conditions, summary, every search),
results.jsonl (every raw response) and conditions.json.
"""

import json
import time
from pathlib import Path

from .config import Config
from .engine import SerpEngine
from .envinfo import collect, to_markdown
from .proxies import DIRECT

DEFAULT_QUERIES = (
    "eczema", "best running shoes", "how to lower cholesterol", "symptoms of vitamin d deficiency",
    "how does compound interest work", "best budget laptop 2026", "how to remove a stripped screw",
    "what is a roth ira", "air fryer salmon recipe", "iphone 17 vs iphone 16", "how long to boil eggs",
    "why is the sky blue", "facebook login", "weather new york", "home depot near me",
)
EVIDENCE = Path(__file__).resolve().parent.parent / "evidence"

# Plain descriptions for readers who don't know the code.
MODE_NOTES = {
    "browser": "A real Chrome browser on our machine opens the Google results page for every search, runs "
               "Google's page code and waits for the AI Overview to finish, then the page is read.",
    "hybrid": "A real Chrome browser visits the Google homepage once (no search) and keeps the cookies Google "
              "gives it. Each search is then a single direct request that carries those cookies, so no browser "
              "window is opened per search. The AI Overview arrives inside that response and is read from it "
              "in full. When Google stops accepting the cookies, the browser fetches new ones.",
    "lite": "A direct request for the simple results page Google still serves to old feature phones. "
            "Fast, but it has no AI Overview and its ranking can differ from desktop.",
    "http": "A direct request for the desktop results page without a browser. Google now refuses these "
            "(it asks for JavaScript), so this mode fails.",
}


def run(modes: list[str], queries: list[str], gap_s: float) -> Path:
    # One fetch per search, and never a saved result.
    cfg = Config(max_attempts=1, cache_ttl_s=0, stale_ttl_s=0)
    engine = SerpEngine(cfg)
    rows: list[dict] = []
    out = EVIDENCE / f"{time.strftime('%Y-%m-%d_%H%M')}_bench"
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    env_before = env_after = None
    stop = ""
    try:
        chrome = ""
        if "browser" in modes or "hybrid" in modes:
            engine.browser.warm_up()
            chrome = engine.browser.chrome_version()
        env_before = collect(cfg, chrome)
        if "hybrid" in modes:
            for proxy in cfg.proxies or [DIRECT]:
                engine.browser.google_session(proxy)
        with open(out / "results.jsonl", "w") as raw:
            first = True
            for i, q in enumerate(queries):
                for mode in modes if i % 2 == 0 else modes[::-1]:
                    if not first:
                        time.sleep(gap_s)  # longer than SERP_MIN_INTERVAL, so no pacing wait is timed
                    first = False
                    r = _search(engine, q, mode)
                    raw.write(json.dumps({"bench_mode": mode, **r.to_dict()}) + "\n")
                    raw.flush()
                    rows.append(_row(r, mode, q))
                    row = rows[-1]
                    print(f"{row['at']} {mode:8} {q!r:36} {row['outcome']:12} valid={r.valid!s:5} "
                          f"{r.elapsed_ms:>6} ms organic={row['organic']} aio={row['aio_chars']}/{row['aio_sources']}",
                          flush=True)
                    if r.status == "blocked" or row["outcome"] == "captcha":
                        stop = (f"The run stopped at {row['at']}, when Google showed a captcha to this IP. "
                                "After a captcha the engine pauses that IP, so the remaining searches did not run.")
                        raise StopIteration
    except StopIteration:
        pass
    finally:
        try:
            env_after = collect(cfg)
        finally:
            engine.close()
    (out / "report.md").write_text(_report(rows, modes, queries, gap_s, started, env_before, env_after, stop))
    (out / "conditions.json").write_text(json.dumps({"before": env_before, "after": env_after}, indent=2))
    return out / "report.md"


def _search(engine: SerpEngine, q: str, mode: str):
    while True:
        r = engine.search(q, mode=mode, ai_overview=mode in ("browser", "hybrid"), no_cache=True)
        if r.status != "throttled":
            return r
        wait = engine._throttled_for_s() + 5
        print(f"{time.strftime('%H:%M:%S')} hourly limit reached; waiting {wait} s", flush=True)
        time.sleep(wait)


def _row(r, mode: str, q: str) -> dict:
    a = r.attempts[0] if r.attempts else None
    return {
        "mode": mode, "query": q, "status": r.status,
        "outcome": a.outcome if a else r.status, "valid": r.valid,
        "total_ms": r.elapsed_ms, "fetch_ms": a.elapsed_ms if a else 0,
        "organic": len(r.organic),
        "aio_chars": len(r.ai_overview.text) if r.ai_overview else 0,
        "aio_sources": len(r.ai_overview.sources) if r.ai_overview else 0,
        "problems": "; ".join(r.problems),
        "at": time.strftime("%H:%M:%S"),
    }


def _pct(values: list[int], p: float) -> str:
    """Nearest rank: the time that a share p of the searches finished within."""
    if not values:
        return "—"
    v = sorted(values)
    return f"{v[min(len(v) - 1, max(0, -(-int(p * 100) * len(v) // 100) - 1))] / 1000:.1f} s"


def _report(rows, modes, queries, gap_s, started, env_before, env_after, stop) -> str:
    ended = time.time()
    out = [
        f"# Fetch mode test, {time.strftime('%Y-%m-%d', time.localtime(started))}",
        "",
        "## Test conditions",
        "",
        to_markdown(env_before) if env_before else "- (not measured)",
        f"- Run: {time.strftime('%H:%M', time.localtime(started))} to {time.strftime('%H:%M %Z', time.localtime(ended))}, "
        f"{len(rows)} searches, {gap_s:.0f} s between searches (plus waits for the hourly limit).",
        "- Each query ran once in every mode, back to back, alternating which mode went first.",
        "- One fetch per search: no retry, no fallback, no cache. With one IP a retry only asks the same IP again, "
        "so retries could not be measured here.",
        "- Total = everything the caller waits for: fetch, parse, link resolving, validity check.",
        "- Browser and hybrid ask for the AI Overview. Chrome and hybrid's cookies were ready before timing began.",
    ]
    if "lite" in modes:
        out.append("- Lite gets Google's feature-phone page, whose ranking can differ from desktop.")
    out += ["", "## What the modes mean", ""]
    out += [f"- **{m}**: {MODE_NOTES[m]}" for m in modes if m in MODE_NOTES]
    out += ["", "## More on the conditions", ""]
    if env_after and env_after.get("network_to_google", {}).get("samples"):
        n = env_after["network_to_google"]
        out.append(f"- Network re-measured after the run: round trip {n['tcp_connect_ms']} ms, "
                   f"new secure connection {n['tls_ready_ms']} ms, download "
                   f"{env_after['download_speed'].get('mbps', '?')} Mbit/s.")
    if stop:
        out += ["", f"**{stop}**"]
    out += [
        "",
        "## Summary",
        "",
        "| Mode | Searches | Got a results page | Fully valid | Valid rate | With AI Overview | p50 | p95 | Slowest |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for mode in modes:
        rs = [r for r in rows if r["mode"] == mode]
        if not rs:
            continue
        ok = [r for r in rs if r["outcome"] == "ok"]
        valid = sum(r["valid"] for r in rs)
        times = [r["total_ms"] for r in rs]
        out.append(
            f"| {mode} | {len(rs)} | {len(ok)} | {valid} | {valid / len(rs):.0%} | "
            f"{sum(1 for r in rs if r['aio_chars'])} | {_pct(times, 0.5)} | {_pct(times, 0.95)} | "
            f"{max(times) / 1000:.1f} s |"
        )
    out += [
        "",
        "p50 / p95: half / 95% of searches finished within this time, failures included. "
        f"With {len(queries)} searches per mode the p95 is close to the slowest search, not a stable figure.",
        "",
        "## Every search",
        "",
        "| Time | Mode | Query | Outcome | Valid | Total | Fetch | Organic | AI Overview (chars / sources) | Problems |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        aio = f"{r['aio_chars']} / {r['aio_sources']}" if r["aio_chars"] else "—"
        out.append(
            f"| {r['at']} | {r['mode']} | {r['query']} | {r['outcome']} | {'yes' if r['valid'] else 'no'} | "
            f"{r['total_ms'] / 1000:.2f} s | {r['fetch_ms'] / 1000:.2f} s | {r['organic']} | {aio} | {r['problems'] or '—'} |"
        )
    return "\n".join(out) + "\n"
