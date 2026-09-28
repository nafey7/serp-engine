"""Browser mode: a real Chrome driven by patchright (Playwright with automation traces removed).

Slower and costlier than HTTP mode, but it runs JavaScript, so it can get past
the "turn on JavaScript" page and capture the AI Overview, which loads late.

Each proxy keeps its own cookies between requests (a "session"), so every
proxy looks like one consistent person rather than a fresh visitor each time.
Sessions are saved to SERP_SESSION_DIR (owner-only permissions) and survive restarts.

Each proxy also keeps one open tab between searches, so a search skips setting up
a fresh browser window. A tab that hits a captcha or breaks is closed and replaced.

Coded /goto links start resolving as soon as they appear on the page, so most are
done by the time the AI Overview has finished loading.

Playwright's sync API must stay on the thread that started it, so all browser
work runs on one dedicated worker thread.
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode, urlsplit

from .config import Config
from .fetch_http import CONSENT_COOKIES, search_params
from .models import FetchResult
from .proxies import DIRECT, ProxyPool
from .resolve import start_resolving

# Filled with the real browser version: a user agent that disagrees with the browser is a bot signal.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{version} Safari/537.36"
)


# True when an AI Overview is on its way. Google sends the start of the overview with the page,
# under a hidden screen-reader heading "AI Mode replied:", so the heading is there as soon as the
# results are (checked on live searches, 2026-09-29: present at results time on every overview
# search, never present on searches without one). A visible "AI Overview" heading also counts, for
# older layouts without the hidden one. Hidden "AI Overview is not available" placeholders on pages
# without an overview are not visible, so they don't count.
_AIO_COMING_JS = """() => {
  if ([...document.querySelectorAll('h3')].some(e => e.textContent.includes('AI Mode replied'))) return true;
  return [...document.querySelectorAll('div, span, h1, h2, strong')].some(
    e => e.textContent.trim() === 'AI Overview' && e.getClientRects().length > 0);
}"""
# How long to keep checking for the heading after the results appear. It was always there at once in
# testing; this only covers a heading that arrives a moment late.
AIO_SIGNAL_WAIT_MS = 500

# True once the AI Overview holds its full source list, which Google adds when the answer is complete.
_AIO_DONE_JS = """() => {
  const label = [...document.querySelectorAll('h3')].find(e => e.textContent.includes('AI Mode replied'));
  const root = label ? label.parentElement : document;
  return !!root.querySelector('[role=dialog] li, [aria-label="Show less related results"]');
}"""


def _playwright_proxy(proxy: str) -> dict | None:
    if proxy == DIRECT:
        return None
    p = urlsplit(proxy)
    out = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        out |= {"username": p.username, "password": p.password or ""}
    return out


class BrowserFetcher:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
        self._pw = None
        self._browser = None
        self._sessions: dict[str, dict] = {}  # proxy -> saved cookies/storage
        self._tabs: dict[str, object] = {}  # proxy -> open tab, kept between searches
        self._google: dict[str, dict] = {}  # proxy -> cookies + user agent for hybrid mode
        self._stale_google: set[str] = set()  # proxies whose cookies Google stopped accepting
        self._dir = cfg.session_dir
        os.makedirs(self._dir, mode=0o700, exist_ok=True)
        os.chmod(self._dir, 0o700)

    def _session_path(self, proxy: str) -> str:
        return os.path.join(self._dir, re.sub(r"[^A-Za-z0-9._-]", "_", ProxyPool.label(proxy)) + ".json")

    def _load_session(self, proxy: str) -> dict | None:
        if proxy not in self._sessions:
            try:
                with open(self._session_path(proxy)) as f:
                    self._sessions[proxy] = json.load(f)
            except (OSError, ValueError):
                return None
        return self._sessions[proxy]

    def _save_session(self, proxy: str, state: dict | None) -> None:
        path = self._session_path(proxy)
        if state is None:
            self._sessions.pop(proxy, None)
            if os.path.exists(path):
                os.remove(path)
            return
        self._sessions[proxy] = state
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)

    def fetch(self, query: str, proxy: str, want_ai_overview: bool, start: int = 0, tbs: str = "") -> FetchResult:
        return self._worker.submit(self._fetch, query, proxy, want_ai_overview, start, tbs).result()

    def close(self) -> None:
        def _close():
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()

        self._worker.submit(_close).result()
        self._worker.shutdown()

    def google_session(self, proxy: str, fresh: bool = False) -> dict:
        """Cookies and user agent of this proxy's Chrome tab after it has passed Google's
        JavaScript check, for hybrid mode to reuse in fast HTTP requests.

        Opening the Google homepage is enough to get them: no search is sent. `fresh` throws
        the old cookies away first (Google stopped accepting them).
        """
        cached = self._google.get(proxy)
        if cached and not fresh:
            return cached
        session = self._worker.submit(self._new_google_session, proxy, fresh).result()
        self._google[proxy] = session
        return session

    def forget_google_session(self, proxy: str) -> None:
        self._google.pop(proxy, None)
        self._stale_google.add(proxy)

    def _new_google_session(self, proxy: str, fresh: bool) -> dict:
        page = self._tab(proxy)
        ctx = page.context
        if fresh or proxy in self._stale_google:
            ctx.clear_cookies()
            ctx.add_cookies(
                [{"name": k, "value": v, "domain": ".google.com", "path": "/"} for k, v in CONSENT_COOKIES.items()]
            )
            self._stale_google.discard(proxy)
        cookies = lambda: {c["name"]: c["value"] for c in ctx.cookies("https://www.google.com")}
        if "AEC" not in cookies():
            page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=self.cfg.timeout_s * 1000)
            for _ in range(50):  # Google's script sets the cookies shortly after the page loads
                if "AEC" in cookies():
                    break
                page.wait_for_timeout(100)
        self._save_session(proxy, ctx.storage_state())
        return {"user_agent": page.evaluate("navigator.userAgent"), "cookies": cookies(), "created": time.time()}

    def capture(self, proxy: str, png_path: str, html_path: str) -> None:
        """Save what this proxy's tab shows right now (the page of its latest search): a
        full-page screenshot and the page's HTML. The AI Overview is opened out first
        ("Show more"), so the screenshot shows all of it; the parsed result is not affected."""
        def _capture():
            page = self._tabs[proxy]
            try:
                more = page.get_by_role("button", name="Show more").first
                if more.is_visible():
                    more.click(timeout=2_000)
                    page.wait_for_timeout(800)
            except Exception:
                pass
            page.screenshot(path=png_path, full_page=True)
            with open(html_path, "w") as f:
                f.write(page.content())

        self._worker.submit(_capture).result()

    def chrome_version(self) -> str:
        return self._worker.submit(lambda: self._ensure_browser().version).result()

    def warm_up(self) -> None:
        """Start Chrome now, so the first search doesn't pay for it. Google is not contacted."""
        self._worker.submit(self._ensure_browser).result()

    def _ensure_browser(self):
        if self._browser is None:
            from patchright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=self.cfg.headless,
                channel=self.cfg.browser_channel,
                # Images are not needed for the text and links; skipping them makes the page load faster.
                # Chrome's own switch, so no request has to be intercepted.
                args=["--blink-settings=imagesEnabled=false"] if self.cfg.block_images else [],
            )
        return self._browser

    def _tab(self, proxy: str):
        """The open tab for this proxy, created on first use and kept for the next search."""
        tab = self._tabs.get(proxy)
        if tab and not tab.is_closed():
            return tab
        browser = self._ensure_browser()
        ctx = browser.new_context(
            # Headless Chrome announces itself as "HeadlessChrome"; a visible one needs no override.
            user_agent=USER_AGENT.format(version=browser.version) if self.cfg.headless else None,
            locale=f"{self.cfg.hl}-{self.cfg.gl.upper()}",
            viewport={"width": 1366, "height": 900},
            proxy=_playwright_proxy(proxy),
            storage_state=self._load_session(proxy),
        )
        if proxy not in self._sessions:
            ctx.add_cookies(
                [{"name": k, "value": v, "domain": ".google.com", "path": "/"} for k, v in CONSENT_COOKIES.items()]
            )
        self._tabs[proxy] = tab = ctx.new_page()
        return tab

    def _drop_tab(self, proxy: str) -> None:
        tab = self._tabs.pop(proxy, None)
        if tab:
            try:
                tab.context.close()
            except Exception:
                pass

    def _fetch(self, query: str, proxy: str, want_ai_overview: bool, start: int, tbs: str) -> FetchResult:
        t0 = time.monotonic()
        links: dict = {}  # coded link -> its resolution, started as soon as the link appears
        try:
            page = self._tab(proxy)
            params = urlencode(search_params(self.cfg, query, start, tbs))
            resp = page.goto(
                f"https://www.google.com/search?{params}",
                wait_until="domcontentloaded",
                timeout=self.cfg.timeout_s * 1000,
            )
            try:
                page.wait_for_selector("#search, #rso, #captcha-form, form[action*='sorry']", timeout=10_000)
            except Exception:
                pass
            status = resp.status if resp else 0
            if "/sorry/" in page.url and self.cfg.manual_captcha_s and not self.cfg.headless:
                status = self._wait_for_human(page) or status
            blocked = "/sorry/" in page.url
            if not blocked:
                self._start_resolving(page, proxy, links)  # organic links resolve while the overview loads
            aio_shown = aio_complete = None
            if want_ai_overview and not blocked:
                aio_shown, aio_complete = self._expand_ai_overview(page, lambda: self._start_resolving(page, proxy, links))
            html = page.content()
            if not blocked:
                self._start_resolving(page, proxy, links)
                self._save_session(proxy, page.context.storage_state())
            else:
                self._save_session(proxy, None)  # burned session, start fresh next time
                self._drop_tab(proxy)
            return FetchResult(
                status_code=status,
                final_url=page.url,
                html=html,
                elapsed_ms=int((time.monotonic() - t0) * 1000),
                aio_shown=aio_shown,
                aio_complete=aio_complete,
                links=links,
            )
        except Exception:
            self._drop_tab(proxy)  # a crashed or stuck tab is not reused
            raise

    @staticmethod
    def _start_resolving(page, proxy: str, links: dict) -> None:
        """Start resolving every coded link now on the page that isn't being resolved yet."""
        try:
            hrefs = page.eval_on_selector_all("a[href^='/goto?']", "els => els.map(e => e.getAttribute('href'))")
        except Exception:
            return
        for href in hrefs:
            url = "https://www.google.com" + href
            if url not in links:
                links[url] = start_resolving(url, proxy)

    def _wait_for_human(self, page) -> int | None:
        """Give the person at the keyboard a chance to solve the captcha in the visible window."""
        print(f"Google is showing a captcha in the Chrome window. Solve it within "
              f"{self.cfg.manual_captcha_s}s to continue.", file=sys.stderr, flush=True)
        try:
            page.wait_for_url(lambda url: "/sorry/" not in url, timeout=self.cfg.manual_captcha_s * 1000)
            page.wait_for_selector("#search, #rso", timeout=10_000)
            return 200
        except Exception:
            return None

    @staticmethod
    def _expand_ai_overview(page, on_tick=lambda: None) -> tuple[bool, bool]:
        """Wait for the AI Overview to finish. Returns (shown, complete).

        Whether one is coming is read from the page right after the results appear
        (_AIO_COMING_JS), so a search without an overview returns within AIO_SIGNAL_WAIT_MS
        instead of waiting out a timeout for a heading that never appears.

        The overview keeps streaming in after the page loads, in chunks up to a second apart,
        so "the page stopped changing" is not a safe sign that it is done. Google adds the full
        source list (and its "Show less related results" button) only once the answer is
        complete, so that is what is waited for. The page already holds the whole text even
        where Google collapses it behind "Show more", so nothing is clicked.
        """
        for waited in range(0, AIO_SIGNAL_WAIT_MS + 1, 100):
            try:
                if page.evaluate(_AIO_COMING_JS):
                    break
            except Exception:
                return False, False
            if waited < AIO_SIGNAL_WAIT_MS:
                page.wait_for_timeout(100)
        else:
            return False, False  # no overview on this page
        for _ in range(50):  # up to ~5 s
            try:
                if page.evaluate(_AIO_DONE_JS):
                    return True, True
            except Exception:
                break
            on_tick()
            page.wait_for_timeout(100)
        return True, False
