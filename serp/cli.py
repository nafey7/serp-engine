"""Command line.

  serp search "best running shoes" [--mode auto|lite|http|browser] [--aio] [--page 2] [--tbs qdr:w] [--no-cache] [--json]
  serp batch queries.txt [--delay 30] [--mode auto] [--aio] [--no-cache] [--out results.jsonl]
  serp stats
"""

import argparse
import json
import random
import sys
import time

from .engine import MODES, SerpEngine


def _print_human(r) -> None:
    trail = " -> ".join(f"{a.mode}:{a.outcome}({a.elapsed_ms}ms)" for a in r.attempts)
    print(f"\n[{r.status}] {r.query!r}  mode={r.mode}  total={r.elapsed_ms}ms" + ("  (stale)" if r.stale else "  (cached)" if r.cached else ""))
    if r.attempts and (not r.cached or r.stale):
        print(f"  attempts: {trail}")
    if r.note:
        print(f"  note: {r.note}")
    if r.ai_overview:
        print(f"  AI Overview ({len(r.ai_overview.sources)} sources): {r.ai_overview.text[:300]}...")
    for o in r.organic[:10]:
        where = o.display_url or o.domain or o.source
        print(f"  {o.position:>2}. {o.title}\n      {where if o.url.startswith('https://www.google.com/goto') else o.url}")
    if r.people_also_ask:
        print("  People also ask: " + " | ".join(r.people_also_ask[:4]))
    if r.related_searches:
        print("  Related: " + " | ".join(r.related_searches[:6]))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="serp")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--mode", choices=MODES, default="auto")
    s.add_argument("--aio", action="store_true", help="capture the AI Overview (uses the browser)")
    s.add_argument("--page", type=int, default=1, help="results page (1 = first ten results)")
    s.add_argument("--tbs", default="", help='Google time filter, e.g. "qdr:d" (past day), "qdr:w", "qdr:m", "qdr:y"')
    s.add_argument("--no-cache", action="store_true", help="always ask Google, even for a recent repeat search")
    s.add_argument("--json", action="store_true")

    b = sub.add_parser("batch")
    b.add_argument("file")
    b.add_argument("--mode", choices=MODES, default="auto")
    b.add_argument("--aio", action="store_true")
    b.add_argument("--no-cache", action="store_true")
    # A single IP gets a captcha after a handful of quick searches, so pace them.
    b.add_argument("--delay", type=float, default=30.0, help="average seconds between queries (randomized +/-30%%)")
    b.add_argument("--out", default="results.jsonl")

    sub.add_parser("stats")
    args = ap.parse_args(argv)

    engine = SerpEngine()
    try:
        if args.cmd == "search":
            r = engine.search(
                args.query, mode=args.mode, ai_overview=args.aio,
                start=10 * (max(args.page, 1) - 1), tbs=args.tbs, no_cache=args.no_cache,
            )
            print(json.dumps(r.to_dict(), indent=2)) if args.json else _print_human(r)
            sys.exit(0 if r.status == "ok" else 1)

        if args.cmd == "batch":
            queries = [q.strip() for q in open(args.file) if q.strip() and not q.startswith("#")]
            with open(args.out, "a") as out:
                for i, q in enumerate(queries):
                    r = engine.search(q, mode=args.mode, ai_overview=args.aio, no_cache=args.no_cache)
                    out.write(json.dumps(r.to_dict()) + "\n")
                    _print_human(r)
                    if r.status in ("blocked", "throttled"):
                        print("\nStopping the batch: every IP is cooling down or at its hourly limit.")
                        break
                    if not r.cached and i < len(queries) - 1:
                        time.sleep(args.delay * random.uniform(0.7, 1.3))
            print(f"\nSaved to {args.out}")

        print("\n" + json.dumps(engine.stats.summary(), indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
