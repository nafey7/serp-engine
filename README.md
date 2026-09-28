# SERP Engine

A Google search results (SERP) scraper. It tries fast, cheap HTTP requests first and falls back to a real browser when needed, for example to capture Google AI Overviews.

## Features

- **Five fetch modes:** `lite` (feature-phone page), `http` (desktop page), `hybrid` (desktop page over plain HTTP, reusing a Chrome tab's Google cookies; the rest of the AI Overview is filled in from the page's scripts), `browser` (real Chrome via Patchright), and `auto`. With the AI Overview wanted, `auto` tries hybrid, then the browser.
- **AI Overview capture** with `--aio` / `aio=true` (uses the browser).
- **Structured output:** organic results, AI Overview text and sources, People Also Ask, related searches.
- **Block handling:** detects captchas, benches the IP or proxy with a growing cooldown, and paces requests per IP.
- **Proxy rotation** from an env var or a file.
- **Real URLs:** Google's coded `/goto` links are followed to the real pages, all at once (~0.5 s per search).
- **Strict validity:** each result says `valid: true` only when complete; otherwise `problems` says what is missing.
- **Honest stats:** searches are counted apart from fetch attempts, with valid rate, first-try rate and p95 time.
- **Optional caching** (off by default): repeat searches served locally, stale results when Google can't be reached.
- **CLI, HTTP API, and a small demo dashboard.**

## Requirements

- Python 3.10+
- Google Chrome installed (for browser mode), or set `SERP_BROWSER_CHANNEL=chromium`

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
patchright install chromium   # only needed if you use the bundled Chromium
```

## Usage

### CLI

```bash
serp search "best running shoes"
serp search "how does sourdough work" --aio --json
serp search "news" --page 2 --tbs qdr:w --no-cache
serp batch queries.txt --delay 30 --out results.jsonl
serp stats
serp bench --modes hybrid,browser   # timings written to docs/benchmarks/
```

### HTTP API

```bash
serp serve   # http://127.0.0.1:8765
```

- `POST /serp` with `{"q": "eczema"}`: runs the search while you wait and returns the full result in the same response. No queue, nothing stored. Optional fields: `aio` (default `true`), `mode`, `start`, `tbs`.
- `GET /search?q=...&mode=auto&aio=true&start=0&tbs=qdr:w&no_cache=false`
- `GET /stats`
- `GET /` — demo dashboard

## Configuration

All settings are environment variables (see [serp/config.py](serp/config.py)).

| Variable | Default | What it does |
|---|---|---|
| `SERP_PORT` / `SERP_HOST` | `8765` / `127.0.0.1` | Where `serp serve` listens (8765 avoids ports used by other local projects) |
| `SERP_HL` / `SERP_GL` | `en` / `us` | Results language and country |
| `SERP_PROXIES` | — | Comma-separated proxy URLs, e.g. `http://user:pass@host:port` |
| `SERP_PROXY_FILE` | — | File with one proxy URL per line |
| `SERP_BROWSER_CHANNEL` | `chrome` | `chrome` (installed) or `chromium` (bundled) |
| `SERP_BLOCK_IMAGES` | `true` | Don't load images in browser mode (faster; text and links don't need them) |
| `SERP_HEADLESS` | `false` | Headless browser (Google flags it more often) |
| `SERP_TIMEOUT` | `25` | Request timeout in seconds |
| `SERP_MAX_ATTEMPTS` | `3` | Attempts per search |
| `SERP_MIN_INTERVAL` | `8` | Minimum seconds between requests from one IP |
| `SERP_MAX_PER_HOUR` | `20` | Max requests per IP per rolling hour (`0` = no limit) |
| `SERP_BLOCK_COOLDOWN` | `3600` | Seconds to rest an IP after a captcha |
| `SERP_MAX_COOLDOWN` | `21600` | Upper limit for the growing cooldown |
| `SERP_CACHE_TTL` | `0` | Seconds to reuse a cached result (`0` = off) |
| `SERP_STALE_TTL` | `0` | Max age of a stale fallback result (`0` = off) |
| `SERP_SESSION_DIR` | `~/.serp-engine/sessions` | Saved browser cookies per proxy |
| `SERP_MANUAL_CAPTCHA` | `0` | Seconds to wait for a manual captcha solve (visible browser) |
| `SERP_SAVE_HTML` | — | Folder to save fetched pages (for test fixtures) |
| `SERP_DB` | `serp_stats.db` | SQLite file for stats and cache |

## Project layout

```
serp/
  engine.py         mode selection, retries, cache, cooldowns
  fetch_http.py     lite and desktop HTTP fetchers (curl_cffi)
  fetch_browser.py  browser fetcher (Patchright)
  parser.py         HTML -> structured results
  resolve.py        Google /goto links -> real page URLs
  detect.py         captcha / block detection
  proxies.py        proxy pool and per-IP pacing
  stats.py          SQLite stats and cache
  api.py            FastAPI app and dashboard
  cli.py            command line
tests/              offline tests with saved SERP fixtures
docs/               requirements
```

## Tests

The tests need no network.

```bash
pip install pytest
pytest
```
