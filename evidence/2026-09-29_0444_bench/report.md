# Fetch mode test, 2026-09-29

## Test conditions

- Measured: 2026-09-29 04:44:24 PKT (UTC+0500)
- Location: Lahore, Punjab, PK (network: AS17557 Pakistan Telecommunication Company Limited, IP 39.45.x.x)
- Proxies: none (direct connection)
- Google: hl=en, gl=us
- Network to Google (5 probes of generate_204, median): round trip 47 ms, new secure connection 207 ms, reply 252 ms; served by 142.251.150.119, 142.251.152.119, 142.251.154.119, 142.251.155.119, 142.251.156.119
- Download speed: 43.0 Mbit/s (10 MB from speed.cloudflare.com)
- Machine: Darwin 24.5.0, Apple M2, 8 CPUs, 8 GB RAM
- Software: Python 3.11.9, Chrome 153.0.8010.54, patchright 1.63.0, curl_cffi 0.16.3
- Browser: chrome, headless=False, images blocked=True
- Run: 04:44 to 04:49 PKT, 6 searches, 60 s between searches (plus waits for the hourly limit).
- Each query ran once in every mode, back to back, alternating which mode went first.
- One fetch per search: no retry, no fallback, no cache. With one IP a retry only asks the same IP again, so retries could not be measured here.
- Total = everything the caller waits for: fetch, parse, link resolving, validity check.
- Browser and hybrid ask for the AI Overview. Chrome and hybrid's cookies were ready before timing began.

## What the modes mean

- **browser**: A real Chrome browser on our machine opens the Google results page for every search, runs Google's page code and waits for the AI Overview to finish, then the page is read.

## More on the conditions

- Network re-measured after the run: round trip 43 ms, new secure connection 206 ms, download 31.6 Mbit/s.

## Summary

| Mode | Searches | Got a results page | Fully valid | Valid rate | With AI Overview | p50 | p95 | Slowest |
|---|---|---|---|---|---|---|---|---|
| browser | 6 | 6 | 6 | 100% | 2 | 2.1 s | 3.5 s | 3.5 s |

p50 / p95: half / 95% of searches finished within this time, failures included. With 6 searches per mode the p95 is close to the slowest search, not a stable figure.

## Every search

| Time | Mode | Query | Outcome | Valid | Total | Fetch | Organic | AI Overview (chars / sources) | Problems |
|---|---|---|---|---|---|---|---|---|---|
| 04:44:33 | browser | air fryer salmon recipe | ok | yes | 2.06 s | 2.01 s | 6 | — | — |
| 04:45:34 | browser | facebook login | ok | yes | 1.45 s | 1.43 s | 7 | — | — |
| 04:46:36 | browser | weather new york | ok | yes | 2.07 s | 2.03 s | 9 | — | — |
| 04:47:38 | browser | home depot near me | ok | yes | 2.00 s | 1.96 s | 9 | — | — |
| 04:48:41 | browser | eczema | ok | yes | 2.50 s | 2.39 s | 7 | 1615 / 11 | — |
| 04:49:44 | browser | why is the sky blue | ok | yes | 3.46 s | 3.13 s | 5 | 994 / 9 | — |
