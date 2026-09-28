"""Turn Google's coded /goto links into the real page URLs.

Desktop result pages no longer carry the destination URL: each link is
https://www.google.com/goto?url=<encrypted token>, and the token can't be decoded.
Google answers a request for that link with a plain 302 redirect to the real page,
so the redirect is read (not followed) and the page itself is never loaded.

All links of one search are asked for at the same time, through the same proxy as
the search, so resolving a full page costs about one round trip (~0.5 s). In browser
mode they start while the page is still loading, which hides most of that time.
"""

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

from curl_cffi import requests

from .proxies import DIRECT

GOTO_PREFIX = "https://www.google.com/goto?"
_pool = ThreadPoolExecutor(max_workers=32, thread_name_prefix="resolve")
# Each worker thread keeps its own open connection per proxy, so a link after the first
# skips the ~0.2 s it costs to open a secure connection to Google.
_local = threading.local()


def _http_get(url: str, *, proxy: str, **kwargs):
    sessions = _local.__dict__.setdefault("sessions", {})
    session = sessions.get(proxy) or sessions.setdefault(proxy, requests.Session())
    return session.get(url, proxies=None if proxy == DIRECT else {"http": proxy, "https": proxy}, **kwargs)


def is_goto(url: str) -> bool:
    return url.startswith(GOTO_PREFIX)


def start_resolving(url: str, proxy: str, timeout_s: float = 5.0) -> Future:
    """Begin resolving one link in the background; the future gives the real URL or None."""
    return _pool.submit(_resolve_one, url, proxy, timeout_s)


def resolve_links(urls: list[str], proxy: str, started: dict[str, Future] | None = None,
                  timeout_s: float = 5.0) -> dict[str, str]:
    """Real URL for each /goto link, keyed by that link. Links that failed twice are left out.

    `started` holds links already being resolved (the browser starts them as they appear on
    the page); only the rest are started here.
    """
    todo = list(dict.fromkeys(u for u in urls if is_goto(u)))
    started = started or {}
    futures = {u: started.get(u) or start_resolving(u, proxy, timeout_s) for u in todo}
    found = {u: real for u, f in futures.items() if (real := f.result())}
    # One retry for links that timed out or answered oddly.
    retry = {u: start_resolving(u, proxy, timeout_s) for u in todo if u not in found}
    found |= {u: real for u, f in retry.items() if (real := f.result())}
    return found


def _resolve_one(url: str, proxy: str, timeout_s: float) -> str | None:
    try:
        resp = _http_get(url, proxy=proxy, impersonate="chrome", allow_redirects=False, timeout=timeout_s)
    except Exception:
        return None
    location = resp.headers.get("location", "")
    if not (300 <= resp.status_code < 400 and location):
        return None
    real = urljoin(url, location)
    # A redirect back to Google search or its captcha page is not the destination.
    # (Other Google sites, such as support.google.com, are real destinations.)
    if urlsplit(real).hostname == "www.google.com" or "/sorry/" in real:
        return None
    return real
