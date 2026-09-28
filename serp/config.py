import os
from dataclasses import dataclass, field
from pathlib import Path


def _proxies_from_env() -> list[str]:
    proxies = [p.strip() for p in os.getenv("SERP_PROXIES", "").split(",") if p.strip()]
    path = os.getenv("SERP_PROXY_FILE")
    if path and Path(path).exists():
        proxies += [
            line.strip()
            for line in Path(path).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    return proxies


@dataclass
class Config:
    # Language and country of the Google results.
    hl: str = field(default_factory=lambda: os.getenv("SERP_HL", "en"))
    gl: str = field(default_factory=lambda: os.getenv("SERP_GL", "us"))
    # Proxy URLs like http://user:pass@host:port. Empty means direct connection.
    proxies: list[str] = field(default_factory=_proxies_from_env)
    # "chrome" (installed Google Chrome, hardest for Google to spot) or "chromium" (bundled).
    browser_channel: str = field(default_factory=lambda: os.getenv("SERP_BROWSER_CHANNEL", "chrome"))
    # Google shows headless Chrome a captcha almost every time, so a visible window is the default.
    headless: bool = field(default_factory=lambda: os.getenv("SERP_HEADLESS", "false").lower() == "true")
    # Don't load images in browser mode: faster, and the text and links don't need them.
    block_images: bool = field(default_factory=lambda: os.getenv("SERP_BLOCK_IMAGES", "true").lower() == "true")
    timeout_s: int = field(default_factory=lambda: int(os.getenv("SERP_TIMEOUT", "25")))
    max_attempts: int = field(default_factory=lambda: int(os.getenv("SERP_MAX_ATTEMPTS", "3")))
    # After a captcha, leave that IP (or proxy) alone this long. Retrying sooner only extends the block.
    # Each further block within 24 hours doubles the wait, up to max_cooldown_s.
    # One hour matches SearXNG's default suspension for a Google captcha.
    block_cooldown_s: int = field(default_factory=lambda: int(os.getenv("SERP_BLOCK_COOLDOWN", "3600")))
    max_cooldown_s: int = field(default_factory=lambda: int(os.getenv("SERP_MAX_COOLDOWN", "21600")))
    # Minimum seconds between two requests from the same IP (randomized +/-30%). Bursts get flagged fast.
    min_interval_s: float = field(default_factory=lambda: float(os.getenv("SERP_MIN_INTERVAL", "8")))
    # Most requests one IP may send to Google in any rolling hour. A single IP without proxies
    # typically gets a captcha after 20 to 50 searches, so stop well before that. 0 = no limit.
    max_per_hour: int = field(default_factory=lambda: int(os.getenv("SERP_MAX_PER_HOUR", "20")))
    # Serve a repeated search from the local cache for this many seconds. 0 = off (the default:
    # every search asks Google and no result is stored).
    cache_ttl_s: int = field(default_factory=lambda: int(os.getenv("SERP_CACHE_TTL", "0")))
    # When Google can't be asked (blocked, over the hourly limit, or failing), return a saved result
    # up to this old instead of nothing, marked stale. 0 = off (the default).
    stale_ttl_s: int = field(default_factory=lambda: int(os.getenv("SERP_STALE_TTL", "0")))
    # Browser cookies per proxy, kept between runs so each IP looks like a returning visitor.
    # Holds Google session cookies: the folder is created readable by you only.
    session_dir: str = field(
        default_factory=lambda: os.getenv("SERP_SESSION_DIR", str(Path.home() / ".serp-engine" / "sessions"))
    )
    # With a visible browser, wait up to this many seconds for you to solve a captcha by hand. 0 = off.
    manual_captcha_s: int = field(default_factory=lambda: int(os.getenv("SERP_MANUAL_CAPTCHA", "0")))
    # Folder to save every fetched page into, for building offline test fixtures. Empty = off.
    save_html_dir: str = field(default_factory=lambda: os.getenv("SERP_SAVE_HTML", ""))
    db_path: str = field(default_factory=lambda: os.getenv("SERP_DB", "serp_stats.db"))
