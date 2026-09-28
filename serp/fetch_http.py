"""Fast modes: one plain HTTP request, no browser.

curl_cffi copies Chrome's network fingerprint, so the request looks like a real
browser at the connection level. It cannot run JavaScript.

- "http" asks for the normal desktop page. Google now often answers with a
  "turn on JavaScript" page instead; the engine then moves on to another mode.
- "hybrid" asks for the normal desktop page too, but with the cookies and user agent
  of a Chrome tab that has passed Google's JavaScript check (fetch_browser.google_session),
  so Google serves the real results. The parts Google's scripts would insert later
  (the rest of the AI Overview) are filled in by the parser.
- "lite" asks for the page Google still serves to old feature phones
  (/wml/search with a Nokia user agent). It needs no JavaScript, so it usually
  works where "http" doesn't. SearXNG uses the same trick. It has no
  AI Overview and no "People also ask".
"""

import random
import re
import threading
import time
from urllib.parse import urljoin

from curl_cffi import requests

from .config import Config
from .detect import is_block_redirect
from .models import FetchResult
from .proxies import DIRECT
from .resolve import start_resolving

# One open connection per (proxy, fingerprint), reused between searches: a new secure
# connection to Google costs ~0.2 s (measured from Lahore, 2026-09-29). The engine sends one
# request at a time per proxy, so a session is never used by two threads at once.
_sessions: dict[tuple[str, str], requests.Session] = {}
_sessions_lock = threading.Lock()
# A coded result link, as it appears in the page and inside Google's escaped scripts.
_GOTO_TOKEN = re.compile(rb"/goto\?url=([A-Za-z0-9_-]+)")


def _http_get(url: str, *, proxy: str, impersonate: str, **kwargs):
    with _sessions_lock:
        session = _sessions.get((proxy, impersonate))
        if session is None:
            session = _sessions[(proxy, impersonate)] = requests.Session()
    return session.get(
        url, impersonate=impersonate,
        proxies=None if proxy == DIRECT else {"http": proxy, "https": proxy}, **kwargs,
    )

# Pre-accepts the cookie consent screen shown in some regions.
CONSENT_COOKIES = {"SOCS": "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg", "CONSENT": "YES+"}

# Old Nokia phones: Google answers them with a simple page that needs no JavaScript.
NOKIA_USER_AGENTS = (
    "Nokia7610/2.0 (5.0509.0) SymbianOS/7.0s Series60/2.1 Profile/MIDP-2.0 Configuration/CLDC-1.0",
    "Nokia7610/2.0 (7.0642.0) SymbianOS/7.0s Series60/2.1 Profile/MIDP-2.0 Configuration/CLDC-1.0",
    "Nokia6230/2.0 (05.50) Profile/MIDP-2.0 Configuration/CLDC-1.1",
    "Nokia6230i/2.0 (03.80) Profile/MIDP-2.0 Configuration/CLDC-1.1",
    "Nokia6280/2.0 (03.60) Profile/MIDP-2.0 Configuration/CLDC-1.1",
    "NokiaN72/2.0617.1.0.3 Series60/2.8 Profile/MIDP-2.0 Configuration/CLDC-1.1",
)


def search_params(cfg: Config, query: str, start: int = 0, tbs: str = "") -> dict:
    """Query string shared by every mode. `start` is the result offset (10 = page 2); `tbs` e.g. "qdr:d" = past day."""
    params = {"q": query, "hl": cfg.hl, "gl": cfg.gl, "pws": 0}
    if start:
        params["start"] = start
    if tbs:
        params["tbs"] = tbs
    return params


class HttpFetcher:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def fetch(self, query: str, proxy: str, start: int = 0, tbs: str = "") -> FetchResult:
        return self._get(
            "https://www.google.com/search",
            {**search_params(self.cfg, query, start, tbs), "num": 10},
            proxy,
            impersonate="chrome",
        )

    def fetch_hybrid(self, query: str, proxy: str, session: dict, start: int = 0, tbs: str = "") -> FetchResult:
        """Read the page as it streams in, and start resolving each result link as soon as it
        appears, so most links are done by the time Google finishes the AI Overview."""
        t0 = time.monotonic()
        resp = _http_get(
            "https://www.google.com/search", proxy=proxy, impersonate="chrome",
            params=search_params(self.cfg, query, start, tbs),
            headers={"User-Agent": session["user_agent"]}, cookies=session["cookies"],
            allow_redirects=False, timeout=self.cfg.timeout_s, stream=True,
        )
        links: dict = {}
        body, scanned = bytearray(), 0
        def scan(final: bool) -> int:
            # Look again at the last few bytes too: a link can be split across two chunks, so
            # one that touches the end of what has arrived waits for the next chunk.
            for m in _GOTO_TOKEN.finditer(body, max(0, scanned - 200)):
                if m.end() == len(body) and not final:
                    break
                url = "https://www.google.com/goto?url=" + m.group(1).decode()
                if url not in links:
                    links[url] = start_resolving(url, proxy)
            return len(body)

        try:
            for chunk in resp.iter_content():
                body += chunk
                scanned = scan(final=False)
            scan(final=True)
        finally:
            resp.close()
        final_url = str(resp.url)
        if 300 <= resp.status_code < 400:
            final_url = urljoin(final_url, resp.headers.get("location", ""))  # e.g. the captcha page
        return FetchResult(
            status_code=resp.status_code,
            final_url=final_url,
            html=body.decode(resp.encoding or "utf-8", "replace"),
            elapsed_ms=int((time.monotonic() - t0) * 1000),
            links=links,
        )

    def fetch_lite(self, query: str, proxy: str, start: int = 0, tbs: str = "") -> FetchResult:
        return self._get(
            "https://www.google.com/wml/search",
            # Without sca_esv=1 Google answers this page with 403 Forbidden (tested 2026-09-28;
            # SearXNG sends it too). It does not narrow the results, unlike SearXNG's lr/cr.
            {**search_params(self.cfg, query, start, tbs), "sca_esv": "1", "ie": "utf8", "oe": "utf8"},
            proxy,
            impersonate="chrome99_android",
            headers={"User-Agent": random.choice(NOKIA_USER_AGENTS), "Accept": "*/*"},
        )

    def _get(self, url: str, params: dict, proxy: str, impersonate: str, headers: dict | None = None,
             cookies: dict | None = None) -> FetchResult:
        start = time.monotonic()
        kwargs = dict(
            proxy=proxy,
            impersonate=impersonate,
            headers=headers,
            cookies=cookies or CONSENT_COOKIES,
            timeout=self.cfg.timeout_s,
        )
        # Redirects are not followed blindly: a redirect to the captcha page is already
        # the answer, and loading that page would be one more request from a flagged IP.
        resp = _http_get(url, params=params, allow_redirects=False, **kwargs)
        final_url = str(resp.url)
        if 300 <= resp.status_code < 400:
            final_url = urljoin(final_url, resp.headers.get("location", ""))
            if not is_block_redirect(final_url):
                resp = _http_get(final_url, allow_redirects=True, **kwargs)
                final_url = str(resp.url)
        return FetchResult(
            status_code=resp.status_code,
            final_url=final_url,
            html=resp.text,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
