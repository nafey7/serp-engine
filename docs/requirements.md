# Google SERP Scraper: Requirements

**Client:** Infatica (contact: Daniel Mercer, daniel.mercer@infatica.io)
**Lead source:** Jorge Macias, via a Slack community post (Monday, 2026-09-21, 1:12 AM)
**Referred by:** Muhammad Ali Mehboob (asked Jorge for an intro on our behalf)
**Status:** Pre-contract. No warm intro. We email the client directly, citing Jorge. Contact identity and commercial terms not yet confirmed.
**Last updated:** 2026-09-24

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

## 2. How the lead reached us

The client did not contact us. They contacted Jorge Macias's team, who passed on it.

| When | Who | What |
|---|---|---|
| Before 2026-09-21 | Client → Jorge | Two emails (below). The first is a generic vendor-screening email. The second, addressed "Hi Jorge", describes the Google SERP project. |
| Mon 2026-09-21, 1:12 AM | Jorge, Slack channel | Posted both emails as attachments: "Anyone interested, lmk, happy to pass over an intro. Seems like a crazy technical project + a little sketchy tbh." |
| Mon 2026-09-21, 1:49 AM | Muhammad Ali Mehboob → Jorge (DM) | "I know a full-stack developer turned GT[M engineer]... good fit for the project. Let me know if you can make [an intro]... deets." |
| 2026-09-24, 3:41 AM | Jorge | "yeah pass the email and i can make an intro" |
| 2026-09-24, 6:01 AM | Jorge | "nvm, included their email in the slack message" |
| 2026-09-24, 10:18 PM | Ali | "Thank youu" |

What this means for us:

- **No warm intro is coming.** Jorge's position is "here is their email, go for it". Our first email is effectively cold, so it should open by naming Jorge and the Slack thread.
- **Jorge passed on the project.** He called it a "crazy technical project" and "a little sketchy". He is a signal, not an endorsement.
- **Other vendors likely saw the same post.** The client's first email is a template, and Jorge posted it to a community channel. Expect competing bids.
- **The client has more detail they have not sent.** Their first email ends: "If relevant, I'll share our current projects and technical requirements." That document should be requested in our first reply.
- **Neither email shows a sender name** in the screenshots (both end at "Best regards,"). The Daniel Mercer identity comes from Jorge's Slack message, not the emails. Verify before sharing anything sensitive.

---

## 3. Source material (verbatim)

### Email 1: vendor screening (generic, not addressed by name)

> Hi,
>
> We are looking for an experienced engineering team for large-scale web scraping and data collection.
>
> We work with search engines, social platforms, marketplaces, and other technically challenging sources, typically at 10M+ requests/day.
>
> Could you briefly share:
>
> - Which complex websites/platforms have you already built scrapers for?
> - What was the largest sustained daily volume you handled?
> - Were these systems built and operated by your team directly?
> - Do you have experience with residential proxies, session management, browser automation and anti-bot systems?
> - Would your team be interested in taking on projects like this?
>
> If relevant, I'll share our current projects and technical requirements.

### Email 2: the Google SERP project (addressed to Jorge)

> Hi Jorge,
>
> Our current priority is a stable Google SERP scraping solution, including AI Overviews and complex queries, capable of handling 10M+ requests per day.
>
> The solution would need to run on our own infrastructure, not Apify. We are looking for a team that can build, deploy and maintain it, including adapting to changes on Google's side.
>
> Our indicative budget for ongoing support and maintenance of a stable, working solution is around $5,000–$7,000 per month. This is a maintenance budget, rather than a one-off development fee.
>
> Could you check with your team and let us know:
>
> - Whether you already have working Google SERP / AI Overviews scrapers.
> - What sustained daily volume you have handled for Google.
> - Whether you can deploy and maintain the solution on our infrastructure.
> - Your expected timeline to get a working solution ready for testing.
>
> Best regards,

---

## 4. Stated requirements

Derived from the two emails above.

### Functional
- **FR-1:** Scrape Google search results pages (SERPs).
- **FR-2:** Capture **Google AI Overviews** in the results.
- **FR-3:** Support **complex queries** (definition to be confirmed, see open questions).
- **FR-4:** Return structured data (implied by "scraping solution" and their existing API product).

### Scale and reliability
- **NFR-1:** Handle **10M+ requests per day** sustained (about 115 requests per second on average, with higher peaks).
- **NFR-2:** The solution must be **stable** and **working** (their words; the payment is framed around this).
- **NFR-3:** Adapt to changes on Google's side (layout changes, anti-bot changes) as ongoing work.

### Deployment
- **DR-1:** Runs on **the client's own infrastructure**, not Apify.
- **DR-2:** The vendor team **builds, deploys and maintains** the system.

### Commercial
- **CR-1:** Indicative budget of **$5,000 to $7,000 per month**.
- **CR-2:** Described as a **maintenance budget**, "rather than a one-off development fee", for "a stable, working solution".

### Capabilities the client screens for (email 1)
These are what they expect any vendor to already have, across all their projects:
- Residential proxies
- Session management
- Browser automation
- Anti-bot systems
- Systems built **and operated** by the vendor's own team (they ask this explicitly, so subcontracted work counts for less)

### Broader context (email 1, not current scope)
The client also works with social platforms, marketplaces and other "technically challenging sources" at 10M+ requests/day. Google SERP is described as the "current priority", so other scrapers may follow.

---

## 5. Questions the client asked, and our draft answers

We should answer both emails in one reply. Items marked TBD need real numbers before sending.

| # | Client question | Draft answer / evidence |
|---|---|---|
| 1 | Which complex websites/platforms have you built scrapers for? | TBD: list prior targets. Google SERP is covered by this repo. |
| 2 | Largest sustained daily volume handled? | TBD: honest number. Do not claim 10M/day for Google unless it is true. |
| 3 | Built and operated by your team directly? | Yes for this engine (see `README.md`). TBD for anything else listed. |
| 4 | Experience with residential proxies, session management, browser automation, anti-bot? | Yes. This engine has proxy rotation, per-proxy saved browser sessions, Patchright browser mode, captcha detection with IP cooldowns. |
| 5 | Interested in projects like this? | Yes, Google SERP first. |
| 6 | Working Google SERP / AI Overview scrapers already? | Yes. Four fetch modes (lite, http, browser, auto), AI Overview capture via browser mode, structured JSON output (organic, AI Overview text and sources, People Also Ask, related searches). |
| 7 | Sustained daily volume handled for Google? | TBD: current engine is tuned for low per-IP rates (default 20 req/IP/hour). Volume at 10M/day depends on their proxy pool size. |
| 8 | Deploy and maintain on their infrastructure? | Yes, subject to answers on cloud provider, access and proxy bandwidth. |
| 9 | Timeline to a solution ready for testing? | TBD: propose a phased plan (single-node test build, then scale-out) rather than one date. |

Also ask for: the "current projects and technical requirements" document they offered in email 1.

---

## 6. Scope

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
- Scrapers for non-Google sources (social platforms, marketplaces).
- Proxy sourcing or proxy infrastructure.
- Infrastructure and proxy costs (assumed client-paid, to be confirmed).
- Customer-facing API, billing or dashboard (assumed they already have these).

---

## 7. Proposed architecture (high level)

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
| Component | Purpose | Status in this repo |
|---|---|---|
| Job queue | Holds search jobs, distributes to workers, handles retries | Not built (single-process CLI/API today) |
| Fast workers | Cheap, high-throughput fetching of standard SERPs | `lite` and `http` modes exist |
| Render workers | Real browser sessions for AI Overviews and complex pages | `browser` mode exists (Patchright) |
| Session manager | Keeps cookies, headers and browser profiles consistent per session | Per-proxy session dir exists |
| Proxy router | Picks proxy type and location per request, rotates on failure | Basic rotation and cooldown exist |
| Parser | Extracts organic results, ads, AI Overview, People Also Ask, etc. | Organic, AIO, PAA, related searches exist; ads and other blocks not yet |
| Parser tests | Snapshot tests that flag when Google changes its page layout | Partial (`tests/`, HTML fixture saving) |
| Monitoring | Dashboards and alerts on success rate, blocks, latency, cost | Local SQLite stats and demo dashboard only |

### Rough sizing
- 10M/day ≈ 115 req/s average. Plan for 2 to 3x peaks.
- Render mode is far more expensive than fast mode. The share of queries needing render mode drives server count (roughly 50 to 200 servers).

---

## 8. Open questions for the client

### Commercial
1. Is there a separate fee for the initial build, or does the monthly fee start from day one?
2. When does the $5k to $7k monthly payment begin? On delivery of a "stable, working solution", or earlier?
3. Contract length and notice period?
4. Are other vendors being evaluated, and on what timeline?

### Infrastructure
5. Does the client pay all server and proxy costs?
6. Can we use their residential proxy network, and are there bandwidth limits?
7. What infrastructure do they run (cloud provider, Kubernetes, bare metal)?

### Technical
8. Can they send the "current projects and technical requirements" document mentioned in their first email?
9. Is there an existing system to take over (their current Apify-based setup?), or is this a fresh build?
10. What counts as a "complex query"?
11. Which SERP elements must be parsed (organic, ads, AI Overview, PAA, shopping, local, news, images)?
12. Which countries, languages and devices (desktop / mobile)?
13. What share of the 10M/day needs AI Overviews (render mode)?
14. Required output format and delivery method (API response, queue, storage bucket)?
15. Latency requirements (real time vs batch)?

### Stability / SLA
16. How is "stable" defined? Target success rate, uptime, max CAPTCHA rate?
17. Expected response time when Google changes break the scraper?
18. On-call expectations (hours, time zones)?

---

## 9. Risks

| Risk | Notes |
|---|---|
| Unpaid build phase | Budget is framed as maintenance only. Build work may be unpaid unless negotiated. Payment appears tied to a "stable, working solution", so the build is at our risk. |
| Low budget vs value | $5k to $7k/month is small relative to the revenue this engine supports and to 50 to 200 servers of ops load. |
| Contact verification | Jorge called the lead "a little sketchy tbh" and passed on it. The emails shown are unsigned. Earlier notes also record the website being down. Verify the contact is a real Infatica employee before sharing anything sensitive. |
| Competing bids | The screening email is a template and was posted to a community channel. Assume several vendors replied. |
| Cold outreach | No intro from Jorge. Our email must establish credibility on its own. |
| Google Terms of Service | Scraping Google violates its ToS. Legal gray area, common in the industry. |
| Constant breakage | Google changes layouts and anti-bot measures often. Maintenance load is ongoing. |
| AI Overview variability | AI Overviews load dynamically and do not appear on every query. They are harder to capture reliably. |
| Gap between prototype and 10M/day | This repo is a working single-node engine. Queue, scale-out, and monitoring are not built yet. Do not overstate readiness. |

---

## 10. Next steps
1. Verify Daniel Mercer's identity through LinkedIn or Infatica's official contact channel.
2. Fill in the TBD answers in section 5 with real numbers.
3. Send one reply covering both emails: name Jorge and the Slack thread, answer their nine questions, ask for the technical requirements doc, and attach the open questions above.
4. Get answers on build fee, infrastructure costs and the "stable" definition in writing.
5. Refine scope, timeline and pricing based on answers.
