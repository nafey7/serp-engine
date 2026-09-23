# Google SERP Scraper: Requirements

**Client:** Infatica (contact: Daniel Mercer, daniel.mercer@infatica.io)
**Introduced by:** Jorge Macias (Slack)
**Status:** Pre-contract. Contact identity and commercial terms not yet confirmed.
**Last updated:** 2026-09-23

---

## 1. Background

Infatica is a UK/Singapore web data company founded in 2019. It sells:

- **Proxies:** residential, mobile, ISP and datacenter IPs. Its residential pool (40M+ IPs) is sourced through an SDK embedded in third-party apps and browser extensions.
- **Scraper APIs:** including a public Google SERP API that already advertises AI Overview support (`mode="render"`).
- **Datasets:** pre-collected data from LinkedIn, Amazon, TikTok and similar sources.

The requested system is most likely the engine behind (or a replacement for) their SERP API product. They want it running on their own infrastructure instead of Apify.

Public SERP API pricing, for context on business value:

| Tier | Price per 1k requests | ~Monthly revenue at 10M/day |
|---|---|---|
| Basic (datacenter) | $0.08 to $0.10 | ~$24k to $30k |
| Pro (residential + rendering) | $0.63 to $0.78 | ~$190k to $234k |

---

## 2. Stated requirements (from client emails)

These come directly from the client's two emails.

### Functional
- **FR-1:** Scrape Google search results pages (SERPs).
- **FR-2:** Capture **Google AI Overviews** in the results.
- **FR-3:** Support **complex queries** (definition to be confirmed, see open questions).
- **FR-4:** Return structured data (implied by "scraping solution" and their existing API product).

### Scale and reliability
- **NFR-1:** Handle **10M+ requests per day** sustained (about 115 requests per second on average, with higher peaks).
- **NFR-2:** The solution must be **stable**.
- **NFR-3:** Adapt to changes on Google's side (layout changes, anti-bot changes) as ongoing work.

### Deployment
- **DR-1:** Runs on **the client's own infrastructure**, not Apify.
- **DR-2:** The vendor team **builds, deploys and maintains** the system.

### Commercial
- **CR-1:** Indicative budget of **$5,000 to $7,000 per month**.
- **CR-2:** Described as a **maintenance budget**, "rather than a one-off development fee", for "a stable, working solution".

### Information the client asked for
1. Do we already have working Google SERP / AI Overview scrapers?
2. What sustained daily volume have we handled for Google?
3. Can we deploy and maintain the solution on their infrastructure?
4. What is our expected timeline to a working solution ready for testing?

### Broader context (first email, not current scope)
The client also works with social platforms, marketplaces and other "technically challenging sources" at 10M+ requests/day. They asked about experience with residential proxies, session management, browser automation and anti-bot systems. Other scrapers may become future projects.

---

## 3. Scope

### In scope
- One Google SERP scraper with two fetch modes:
  - **Fast mode:** plain HTTP requests for standard results.
  - **Render mode:** headless browser for AI Overviews and JavaScript-dependent content.
- A parser that turns SERP HTML into structured JSON.
- A job queue with retries and failure handling.
- Integration with the client's proxy network.
- Deployment on client servers.
- Monitoring, alerting and ongoing maintenance.

### Out of scope (unless agreed later)
- Scrapers for non-Google sources.
- Proxy sourcing or proxy infrastructure.
- Infrastructure and proxy costs (assumed client-paid, to be confirmed).
- Customer-facing API, billing or dashboard (assumed they already have these).

---

## 4. Proposed architecture (high level)

```
 Client API / job source
          │
          ▼
    ┌───────────┐
    │ Job queue │  (Redis / Kafka) retries, priorities, rate control
    └─────┬─────┘
          │
   ┌──────┴────────┐
   ▼               ▼
Fast workers    Render workers
(HTTP client)   (Playwright / headless Chrome)
   │               │
   └──────┬────────┘
          ▼
   Proxy layer (client's residential / datacenter pool)
          │
          ▼
       Google
          │
          ▼
    Parser → structured JSON → client storage / API response
          │
          ▼
 Monitoring: success rate, block/CAPTCHA rate, latency, cost per 1k,
 parser-break alerts
```

### Components
| Component | Purpose |
|---|---|
| Job queue | Holds search jobs, distributes to workers, handles retries |
| Fast workers | Cheap, high-throughput fetching of standard SERPs |
| Render workers | Real browser sessions for AI Overviews and complex pages |
| Session manager | Keeps cookies, headers and browser profiles consistent per session |
| Proxy router | Picks proxy type and location per request, rotates on failure |
| Parser | Extracts organic results, ads, AI Overview, People Also Ask, etc. |
| Parser tests | Snapshot tests that flag when Google changes its page layout |
| Monitoring | Dashboards and alerts on success rate, blocks, latency, cost |

### Rough sizing
- 10M/day ≈ 115 req/s average. Plan for 2 to 3x peaks.
- Render mode is far more expensive than fast mode. The share of queries needing render mode drives server count (roughly 50 to 200 servers).

---

## 5. Open questions for the client

### Commercial
1. Is there a separate fee for the initial build, or does the monthly fee start from day one?
2. When does the $5k to $7k monthly payment begin?
3. Contract length and notice period?

### Infrastructure
4. Does the client pay all server and proxy costs?
5. Can we use their residential proxy network, and are there bandwidth limits?
6. What infrastructure do they run (cloud provider, Kubernetes, bare metal)?

### Technical
7. Is there an existing system to take over, or is this a fresh build?
8. What counts as a "complex query"?
9. Which SERP elements must be parsed (organic, ads, AI Overview, PAA, shopping, local, news, images)?
10. Which countries, languages and devices (desktop / mobile)?
11. What share of the 10M/day needs AI Overviews (render mode)?
12. Required output format and delivery method (API response, queue, storage bucket)?
13. Latency requirements (real time vs batch)?

### Stability / SLA
14. How is "stable" defined? Target success rate, uptime, max CAPTCHA rate?
15. Expected response time when Google changes break the scraper?
16. On-call expectations (hours, time zones)?

---

## 6. Risks

| Risk | Notes |
|---|---|
| Unpaid build phase | Budget is framed as maintenance only. Build work may be unpaid unless negotiated. |
| Low budget vs value | $5k to $7k/month is small relative to the revenue this engine supports. |
| Contact verification | Introducer noted the website was down and called it "sketchy". Verify the contact is a real Infatica employee before sharing anything sensitive. |
| Google Terms of Service | Scraping Google violates its ToS. Legal gray area, common in the industry. |
| Constant breakage | Google changes layouts and anti-bot measures often. Maintenance load is ongoing. |
| AI Overview variability | AI Overviews load dynamically and do not appear on every query. They are harder to capture reliably. |

---

## 7. Next steps
1. Verify Daniel Mercer's identity through LinkedIn or Infatica's official contact channel.
2. Send reply email with experience details and the open questions above.
3. Get answers on build fee, infrastructure costs and the "stable" definition in writing.
4. Refine scope, timeline and pricing based on answers.
