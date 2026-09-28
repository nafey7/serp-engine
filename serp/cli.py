"""Command line.

  serp search "best running shoes" [--mode auto|lite|http|browser] [--aio] [--page 2] [--tbs qdr:w] [--no-cache] [--json]
  serp batch queries.txt [--delay 30] [--mode auto] [--aio] [--no-cache] [--out results.jsonl]
  serp stats
  serp serve [--host 127.0.0.1] [--port 8765]
  serp bench [--modes hybrid,browser] [--gap 180] [--queries "a" "b" ...]
  serp proof "eczema" ["another query" ...]
"""

import argparse
import json
import os
import random
import sys
import time

from .engine import MODES, SerpEngine


def _print_human(r) -> None:
    trail = " -> ".join(f"{a.mode}:{a.outcome}({a.elapsed_ms}ms)" for a in r.attempts)
    print(f"\n[{r.status}] {r.query!r}  mode={r.mode}  total={r.elapsed_ms}ms" + ("  (stale)" if r.stale else "  (cached)" if r.cached else ""))
    if r.attempts and (not r.cached or r.stale):
        print(f"  attempts: {trail}")
    if r.status == "ok":
        print(f"  valid: {r.valid}" + (f"  problems: {'; '.join(r.problems)}" if r.problems else ""))
    if r.note:
        print(f"  note: {r.note}")
    if r.ai_overview:
        print(f"  AI Overview ({len(r.ai_overview.sources)} sources): {r.ai_overview.text[:300]}...")
    for o in r.organic[:10]:
        print(f"  {o.position:>2}. {o.title}\n      {o.url}")
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

    # 8765 is unused by the other local projects (grona-code, relevic-v2, Nature Treats).
    sv = sub.add_parser("serve", help="run the HTTP API and dashboard")
    sv.add_argument("--host", default=os.getenv("SERP_HOST", "127.0.0.1"))
    sv.add_argument("--port", type=int, default=int(os.getenv("SERP_PORT", "8765")))
    bn = sub.add_parser("bench", help="time each fetch mode on the same searches; results go to evidence/")
    bn.add_argument("--modes", default="hybrid,browser")
    bn.add_argument("--gap", type=float, default=180.0, help="seconds between searches (180 = 20 an hour)")
    bn.add_argument("--queries", nargs="+")
    pf = sub.add_parser("proof", help="save result JSON + screenshot + page HTML per query into evidence/")
    pf.add_argument("queries", nargs="+")
    args = ap.parse_args(argv)

    if args.cmd == "proof":
        from .proof import run as run_proof

        print(f"\nWrote {run_proof(args.queries)}")
        return

    if args.cmd == "bench":
        from .bench import DEFAULT_QUERIES, run

        modes = [m.strip() for m in args.modes.split(",") if m.strip()]
        if not set(modes) <= {"lite", "http", "hybrid", "browser"}:
            ap.error("--modes takes lite, http, hybrid and browser")
        print(f"\nWrote {run(modes, args.queries or list(DEFAULT_QUERIES), args.gap)}")
        return

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("serp.api:app", host=args.host, port=args.port)
        return

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
