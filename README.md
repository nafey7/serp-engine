# SERP Engine

A Google search results (SERP) scraper. It tries fast, cheap HTTP requests first and falls back to a real browser when needed, for example to capture Google AI Overviews.

## Features

- **Four fetch modes:** `lite` (feature-phone page), `http` (desktop page), `browser` (real Chrome via Patchright), and `auto` (tries them in that order).
- **AI Overview capture** with `--aio` / `aio=true` (uses the browser).
- **Structured output:** organic results, AI Overview text and sources, People Also Ask, related searches.
- **Block handling:** detects captchas, benches the IP or proxy with a growing cooldown, and paces requests per IP.
- **Proxy rotation** from an env var or a file.
- **Caching:** repeat searches are served locally; stale results are returned when Google can't be reached.
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
```

### HTTP API

```bash
uvicorn serp.api:app --port 8000
```

- `GET /search?q=...&mode=auto&aio=true&start=0&tbs=qdr:w&no_cache=false`
- `GET /stats`
- `GET /` — demo dashboard

## Configuration

All settings are environment variables (see [serp/config.py](serp/config.py)).

| Variable | Default | What it does |
|---|---|---|
| `SERP_HL` / `SERP_GL` | `en` / `us` | Results language and country |
| `SERP_PROXIES` | — | Comma-separated proxy URLs, e.g. `http://user:pass@host:port` |
| `SERP_PROXY_FILE` | — | File with one proxy URL per line |
| `SERP_BROWSER_CHANNEL` | `chrome` | `chrome` (installed) or `chromium` (bundled) |
| `SERP_HEADLESS` | `false` | Headless browser (Google flags it more often) |
| `SERP_TIMEOUT` | `25` | Request timeout in seconds |
| `SERP_MAX_ATTEMPTS` | `3` | Attempts per search |
| `SERP_MIN_INTERVAL` | `8` | Minimum seconds between requests from one IP |
| `SERP_MAX_PER_HOUR` | `20` | Max requests per IP per rolling hour (`0` = no limit) |
| `SERP_BLOCK_COOLDOWN` | `3600` | Seconds to rest an IP after a captcha |
| `SERP_MAX_COOLDOWN` | `21600` | Upper limit for the growing cooldown |
| `SERP_CACHE_TTL` | `3600` | Seconds to reuse a cached result (`0` = off) |
| `SERP_STALE_TTL` | `604800` | Max age of a stale fallback result (`0` = off) |
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
