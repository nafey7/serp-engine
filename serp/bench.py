"""Time each fetch mode on the same searches, and write the results into docs/benchmarks/.

  serp bench [--modes lite,http,hybrid,browser] [--gap 20] [--queries "a" "b" ...]

Chrome is started before the clock runs (Google is not contacted), as it would be on a
running server. Hybrid's cookies are fetched before the clock runs too (one visit to the
Google homepage, no search), as a server would keep them ready. Lite and HTTP need no warm-up.
Each search gets exactly one fetch (no retry, no fallback to another mode), so a
failure is timed as a failure. Browser and hybrid searches ask for the AI Overview, as
the production requirement does; lite and plain HTTP pages can't carry one.

Writes docs/benchmarks/<timestamp>_modes.md (tables) and .jsonl (every raw response).
"""

import json
import os
import platform
import statistics
import time
from pathlib import Path

from .config import Config
from .engine import SerpEngine
from .proxies import DIRECT, ProxyPool

DEFAULT_QUERIES = ("eczema", "best running shoes", "how to lower cholesterol")
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "benchmarks"


def run(modes: list[str], queries: list[str], gap_s: float) -> Path:
    # One fetch per search, and never a saved result.
    cfg = Config(max_attempts=1, cache_ttl_s=0, stale_ttl_s=0)
    engine = SerpEngine(cfg)
    rows: list[dict] = []
    stamp = time.strftime("%Y-%m-%d_%H%M")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUT_DIR / f"{stamp}_modes.jsonl"
    try:
        if "browser" in modes or "hybrid" in modes:
            t = time.monotonic()
            engine.browser.warm_up()
            print(f"Chrome started in {int((time.monotonic() - t) * 1000)} ms (not counted)")
        if "hybrid" in modes:
            t = time.monotonic()
            for proxy in cfg.proxies or [DIRECT]:
                engine.browser.google_session(proxy)
            print(f"Hybrid cookies ready in {int((time.monotonic() - t) * 1000)} ms (not counted)")
        with open(raw_path, "w") as raw:
            first = True
            for mode in modes:
                for q in queries:
                    if not first:
                        time.sleep(gap_s)  # longer than SERP_MIN_INTERVAL, so no pacing wait is timed
                    first = False
                    r = engine.search(q, mode=mode, ai_overview=mode in ("browser", "hybrid"), no_cache=True)
                    raw.write(json.dumps({"bench_mode": mode, **r.to_dict()}) + "\n")
                    a = r.attempts[0] if r.attempts else None
                    row = {
                        "mode": mode, "query": q, "status": r.status,
                        "outcome": a.outcome if a else r.status, "valid": r.valid,
                        "total_ms": r.elapsed_ms, "fetch_ms": a.elapsed_ms if a else 0,
                        "organic": len(r.organic),
                        "aio_chars": len(r.ai_overview.text) if r.ai_overview else 0,
                        "aio_sources": len(r.ai_overview.sources) if r.ai_overview else 0,
                        "problems": "; ".join(r.problems),
                    }
                    rows.append(row)
                    print(f"{mode:8} {q!r:32} {row['outcome']:12} valid={r.valid!s:5} {r.elapsed_ms:>6} ms  "
                          f"organic={row['organic']} aio={row['aio_chars']}/{row['aio_sources']}")
                    if r.status in ("blocked", "throttled"):
                        print("Stopping: this IP is cooling down or at its hourly limit.")
                        raise StopIteration
    except StopIteration:
        pass
    finally:
        engine.close()
    md_path = raw_path.with_suffix(".md")
    md_path.write_text(_report(rows, cfg, queries, gap_s, raw_path.name))
    return md_path


def _report(rows: list[dict], cfg: Config, queries: list[str], gap_s: float, raw_name: str) -> str:
    proxies = ", ".join(ProxyPool.label(p) for p in cfg.proxies) or "none (direct connection)"
    out = [
        f"# Fetch mode timings, {time.strftime('%Y-%m-%d %H:%M %Z')}",
        "",
        "## Conditions",
        "",
        f"- Machine: {platform.system()} {platform.machine()}, {os.cpu_count()} CPUs",
        f"- Proxies: {proxies}",
        f"- Google: hl={cfg.hl}, gl={cfg.gl}. Browser and HTTP ask for the desktop page; lite gets Google's "
        "feature-phone page, whose ranking can differ from desktop",
        f"- Chrome: `{cfg.browser_channel}`, headless={cfg.headless}, images blocked={cfg.block_images}, "
        "started before timing (warm)",
        f"- One fetch per search: no retry, no fallback, no cache. {gap_s:.0f} s between searches.",
        "- Total = everything the caller waits for: fetch, parse, link resolving, validity check.",
        "- Browser and hybrid searches ask for the AI Overview; lite and plain HTTP pages can't carry one.",
        "- Hybrid: Chrome's cookies (from one Google homepage visit, fetched before timing) reused for plain HTTP.",
        f"- Raw responses: `{raw_name}`",
        "",
        "## Summary",
        "",
        "| Mode | Searches | Fetch OK | Fully valid | Median total | Slowest total |",
        "|---|---|---|---|---|---|",
    ]
    for mode in dict.fromkeys(r["mode"] for r in rows):
        rs = [r for r in rows if r["mode"] == mode]
        ok = [r for r in rs if r["outcome"] == "ok"]
        times = [r["total_ms"] for r in ok]
        med = f"{statistics.median(times) / 1000:.1f} s" if times else "—"
        top = f"{max(times) / 1000:.1f} s" if times else "—"
        out.append(f"| {mode} | {len(rs)} | {len(ok)} | {sum(r['valid'] for r in rs)} | {med} | {top} |")
    out += [
        "",
        "Median and slowest count only fetches that got a results page. "
        f"Only {len(queries)} searches per mode: a first look, not a p95.",
        "",
        "## Every search",
        "",
        "| Mode | Query | Outcome | Valid | Total | Fetch | Organic | AI Overview (chars / sources) | Problems |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        aio = f"{r['aio_chars']} / {r['aio_sources']}" if r["aio_chars"] else "—"
        out.append(
            f"| {r['mode']} | {r['query']} | {r['outcome']} | {'yes' if r['valid'] else 'no'} | "
            f"{r['total_ms'] / 1000:.2f} s | {r['fetch_ms'] / 1000:.2f} s | {r['organic']} | {aio} | {r['problems'] or '—'} |"
        )
    return "\n".join(out) + "\n"
