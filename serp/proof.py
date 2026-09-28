"""A proof package for one search: the raw result next to the Google page it came from.

  serp proof "eczema" ["another query" ...]

For each query, one browser-mode search with the AI Overview (the mode that can show the page),
then, from the same tab and without loading anything again:
  result.json   the API response, exactly as POST /serp returns it
  page.png      full-page screenshot of that Google page (AI Overview opened out)
  page.html     that page's HTML
  summary.md    the result in readable form, with timings and problems
and once per run, conditions.md / conditions.json (location, network, machine, versions).

Written to evidence/<date>_<time>_proof/.
"""

import json
import re
import time
from pathlib import Path

from .config import Config
from .engine import SerpEngine
from .envinfo import collect, to_markdown
from .proxies import DIRECT, ProxyPool

EVIDENCE = Path(__file__).resolve().parent.parent / "evidence"


def run(queries: list[str]) -> Path:
    # Images on, so the screenshot looks like the real page. No cache, no stored result.
    cfg = Config(cache_ttl_s=0, stale_ttl_s=0, block_images=False)
    out = EVIDENCE / f"{time.strftime('%Y-%m-%d_%H%M')}_proof"
    out.mkdir(parents=True, exist_ok=True)
    engine = SerpEngine(cfg)
    try:
        engine.browser.warm_up()
        env = collect(cfg, engine.browser.chrome_version())
        (out / "conditions.json").write_text(json.dumps(env, indent=2))
        (out / "conditions.md").write_text("# Test conditions\n\n" + to_markdown(env) + "\n")
        for i, q in enumerate(queries):
            if i:
                time.sleep(max(cfg.min_interval_s * 2, 20))
            r = engine.search(q, mode="browser", ai_overview=True, no_cache=True)
            folder = out / re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")
            folder.mkdir(exist_ok=True)
            (folder / "result.json").write_text(json.dumps(r.to_dict(), indent=2, ensure_ascii=False))
            if r.attempts and r.attempts[-1].outcome == "ok":
                label = r.attempts[-1].proxy
                proxy = next((p for p in cfg.proxies if ProxyPool.label(p) == label), DIRECT)
                engine.browser.capture(proxy, str(folder / "page.png"), str(folder / "page.html"))
            (folder / "summary.md").write_text(_summary(r))
            print(f"{q!r}: status={r.status} valid={r.valid} {r.elapsed_ms} ms -> {folder}")
    finally:
        engine.close()
    return out


def _summary(r) -> str:
    lines = [
        f"# {r.query}",
        "",
        f"- Status: {r.status}, valid: {'yes' if r.valid else 'no'}"
        + (f" (problems: {'; '.join(r.problems)})" if r.problems else ""),
        f"- Total time: {r.elapsed_ms / 1000:.2f} s (what the caller waits for: fetch, parse, link resolving)",
        "- Attempts: " + (" -> ".join(f"{a.mode} {a.outcome} {a.elapsed_ms / 1000:.2f} s via {a.proxy}"
                                        for a in r.attempts) or "none"),
        f"- Google page: {r.google_url}",
        "",
        f"## Organic results ({len(r.organic)})",
        "",
    ]
    lines += [f"{o.position}. {o.title}  \n   {o.url}" for o in r.organic]
    if r.ai_overview:
        lines += ["", f"## AI Overview ({len(r.ai_overview.text)} characters)", "", "```text",
                  r.ai_overview.text, "```", "", f"### Sources ({len(r.ai_overview.sources)})", ""]
        lines += [f"{i}. {s['site'] + ' — ' if s['site'] else ''}{s['title']}  \n   {s['url']}"
                  for i, s in enumerate(r.ai_overview.sources, 1)]
    else:
        lines += ["", "## AI Overview", "", "None shown for this search."]
    return "\n".join(lines) + "\n"
