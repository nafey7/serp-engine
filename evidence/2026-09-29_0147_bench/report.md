# Fetch mode test, 2026-09-29

## Test conditions

- Measured: 2026-09-29 01:47:05 PKT (UTC+0500)
- Location: Lahore, Punjab, PK (network: AS17557 Pakistan Telecommunication Company Limited, IP 39.45.x.x)
- Proxies: none (direct connection)
- Google: hl=en, gl=us
- Network to Google (5 probes of generate_204, median): round trip 42 ms, new secure connection 205 ms, reply 253 ms; served by 142.251.151.119, 142.251.152.119, 142.251.154.119, 142.251.155.119, 142.251.156.119
- Download speed: 32.3 Mbit/s (10 MB from speed.cloudflare.com)
- Machine: Darwin 24.5.0, Apple M2, 8 CPUs, 8 GB RAM
- Software: Python 3.11.9, Chrome 153.0.8010.54, patchright 1.63.0, curl_cffi 0.16.3
- Browser: chrome, headless=False, images blocked=True
- Run: 01:47 to 03:16 PKT, 29 searches, 180 s between searches (plus waits for the hourly limit).
- Each query ran once in every mode, back to back, alternating which mode went first.
- One fetch per search: no retry, no fallback, no cache. With one IP a retry only asks the same IP again, so retries could not be measured here.
- Total = everything the caller waits for: fetch, parse, link resolving, validity check.
- Browser and hybrid ask for the AI Overview. Chrome and hybrid's cookies were ready before timing began.
- Both modes ask for Google's desktop results page.
- Network re-measured after the run: round trip 46 ms, new secure connection 261 ms, download 20.9 Mbit/s.

**The run stopped at 03:15:50, when Google showed a captcha to this IP. After a captcha the engine pauses that IP, so the 30th search (browser, "home depot near me") did not run.**

## What the modes mean

- **hybrid**: A real Chrome browser visits the Google homepage once (no search) and keeps the cookies Google gives it. Each search is then a single direct request that carries those cookies, so no browser window is opened per search. The AI Overview arrives inside that response and is read from it in full. When Google stops accepting the cookies, the browser fetches new ones.
- **browser**: A real Chrome browser on our machine opens the Google results page for every search, runs Google's page code and waits for the AI Overview to finish, then the page is read.

## Summary

| Mode | Searches | Got a results page | Fully valid | Valid rate | With AI Overview | p50 | p95 | Slowest |
|---|---|---|---|---|---|---|---|---|
| hybrid | 15 | 14 | 14 | 93% | 11 | 2.1 s | 3.2 s | 3.2 s |
| browser | 14 | 14 | 14 | 100% | 11 | 3.4 s | 8.3 s | 8.3 s |

p50 / p95: half / 95% of searches finished within this time, failures included. With 15 searches per mode the p95 is close to the slowest search, not a stable figure.

## Notes on the results

- **Captcha:** it came on the 29th search, about 1.5 hours and 31 Google searches into the session on this one home IP (29 test searches plus 2 proof searches just before). A single IP is expected to reach this point; production spreads searches across a pool of residential proxies.
- **Browser mode's three slowest searches** (7.7–8.3 s: "air fryer salmon recipe", "facebook login", "weather new york") are the three searches without an AI Overview. In browser mode the engine waited up to 6 s for an overview that Google never showed. A fix is in progress. Hybrid mode is not affected: the same three searches took 1.8–2.2 s.
- **Same answers in both modes:** for all 14 queries that ran in both modes, the AI Overview text and its sources were identical. The organic results were identical for 10 of the 14. For the other 4, Google ranked some results differently between the two requests, which were made about 3 minutes apart.
- **Sample size:** with 15 searches per mode, the p95 is close to the slowest single search, not yet a stable figure.

## Every search

| Time | Mode | Query | Outcome | Valid | Total | Fetch | Organic | AI Overview (chars / sources) | Problems |
|---|---|---|---|---|---|---|---|---|---|
| 01:47:16 | hybrid | eczema | ok | yes | 1.85 s | 1.51 s | 7 | 1615 / 11 | — |
| 01:50:19 | browser | eczema | ok | yes | 3.95 s | 3.22 s | 7 | 1615 / 11 | — |
| 01:53:23 | browser | best running shoes | ok | yes | 3.33 s | 3.17 s | 8 | 1198 / 3 | — |
| 01:56:26 | hybrid | best running shoes | ok | yes | 2.81 s | 2.25 s | 8 | 1198 / 3 | — |
| 01:59:28 | hybrid | how to lower cholesterol | ok | yes | 2.32 s | 2.00 s | 8 | 1518 / 11 | — |
| 02:02:31 | browser | how to lower cholesterol | ok | yes | 3.33 s | 2.97 s | 8 | 1518 / 11 | — |
| 02:05:35 | browser | symptoms of vitamin d deficiency | ok | yes | 3.38 s | 3.04 s | 9 | 1151 / 12 | — |
| 02:08:37 | hybrid | symptoms of vitamin d deficiency | ok | yes | 1.86 s | 1.44 s | 9 | 1151 / 12 | — |
| 02:11:39 | hybrid | how does compound interest work | ok | yes | 2.14 s | 1.64 s | 7 | 1881 / 10 | — |
| 02:14:43 | browser | how does compound interest work | ok | yes | 4.21 s | 3.80 s | 7 | 1881 / 10 | — |
| 02:17:46 | browser | best budget laptop 2026 | ok | yes | 3.24 s | 2.88 s | 8 | 1241 / 5 | — |
| 02:20:48 | hybrid | best budget laptop 2026 | ok | yes | 1.97 s | 1.55 s | 8 | 1241 / 5 | — |
| 02:23:50 | hybrid | how to remove a stripped screw | ok | yes | 1.96 s | 1.58 s | 6 | 1693 / 9 | — |
| 02:26:54 | browser | how to remove a stripped screw | ok | yes | 3.60 s | 3.24 s | 6 | 1693 / 9 | — |
| 02:31:21 | browser | what is a roth ira | ok | yes | 3.14 s | 2.78 s | 7 | 1391 / 11 | — |
| 02:34:23 | hybrid | what is a roth ira | ok | yes | 2.77 s | 2.41 s | 7 | 1391 / 11 | — |
| 02:37:25 | hybrid | air fryer salmon recipe | ok | yes | 1.83 s | 1.64 s | 8 | — | — |
| 02:40:34 | browser | air fryer salmon recipe | ok | yes | 8.26 s | 8.20 s | 8 | — | — |
| 02:45:13 | browser | iphone 17 vs iphone 16 | ok | yes | 3.40 s | 3.23 s | 6 | 1630 / 8 | — |
| 02:48:16 | hybrid | iphone 17 vs iphone 16 | ok | yes | 3.15 s | 2.57 s | 6 | 1630 / 8 | — |
| 02:51:19 | hybrid | how long to boil eggs | ok | yes | 3.09 s | 2.54 s | 6 | 1425 / 9 | — |
| 02:54:23 | browser | how long to boil eggs | ok | yes | 4.09 s | 3.71 s | 5 | 1425 / 9 | — |
| 02:57:27 | browser | why is the sky blue | ok | yes | 3.20 s | 2.86 s | 5 | 986 / 6 | — |
| 03:00:29 | hybrid | why is the sky blue | ok | yes | 2.40 s | 2.07 s | 5 | 986 / 6 | — |
| 03:03:31 | hybrid | facebook login | ok | yes | 2.19 s | 2.09 s | 7 | — | — |
| 03:06:39 | browser | facebook login | ok | yes | 7.69 s | 7.64 s | 7 | — | — |
| 03:09:47 | browser | weather new york | ok | yes | 8.15 s | 8.04 s | 9 | — | — |
| 03:12:49 | hybrid | weather new york | ok | yes | 1.83 s | 1.57 s | 9 | — | — |
| 03:15:50 | hybrid | home depot near me | captcha | no | 0.91 s | 0.90 s | 0 | — | — |
