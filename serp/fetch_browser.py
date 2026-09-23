"""Browser mode: a real Chrome driven by patchright (Playwright with automation traces removed).

Slower and costlier than HTTP mode, but it runs JavaScript, so it can get past
the "turn on JavaScript" page and capture the AI Overview, which loads late.

Each proxy keeps its own cookies between requests (a "session"), so every
proxy looks like one consistent person rather than a fresh visitor each time.
Sessions are saved to SERP_SESSION_DIR (owner-only permissions) and survive restarts.

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

# Filled with the real browser version: a user agent that disagrees with the browser is a bot signal.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{version} Safari/537.36"
)


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

    def _ensure_browser(self):
        if self._browser is None:
            from patchright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=self.cfg.headless,
                channel=self.cfg.browser_channel,
            )
        return self._browser

    def _fetch(self, query: str, proxy: str, want_ai_overview: bool, start: int, tbs: str) -> FetchResult:
        start = time.monotonic()
        browser = self._ensure_browser()
        ctx = browser.new_context(
            # Headless Chrome announces itself as "HeadlessChrome"; a visible one needs no override.
            user_agent=USER_AGENT.format(version=browser.version) if self.cfg.headless else None,
            locale=f"{self.cfg.hl}-{self.cfg.gl.upper()}",
            viewport={"width": 1366, "height": 900},
            proxy=_playwright_proxy(proxy),
            storage_state=self._load_session(proxy),
        )
        try:
            if proxy not in self._sessions:
                ctx.add_cookies(
                    [{"name": k, "value": v, "domain": ".google.com", "path": "/"} for k, v in CONSENT_COOKIES.items()]
                )
            page = ctx.new_page()
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
            if want_ai_overview:
                self._expand_ai_overview(page)
            html = page.content()
            if "/sorry/" not in page.url:
                self._save_session(proxy, ctx.storage_state())
            else:
                self._save_session(proxy, None)  # burned session, start fresh next time
            return FetchResult(
                status_code=status,
                final_url=page.url,
                html=html,
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )
        finally:
            ctx.close()

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
    def _expand_ai_overview(page) -> None:
        # The AI Overview streams in after the page loads, and is often cut off behind "Show more".
        try:
            page.get_by_text("AI Overview", exact=True).first.wait_for(timeout=6_000)
        except Exception:
            return  # Google did not show one for this query
        try:
            page.get_by_role("button", name="Show more").first.click(timeout=2_000)
            page.wait_for_timeout(1_000)
        except Exception:
            pass
