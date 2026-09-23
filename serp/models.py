from dataclasses import asdict, dataclass, field


@dataclass
class OrganicResult:
    position: int
    title: str
    # The real page URL when Google puts it in the page. Newer desktop pages only carry a
    # coded https://www.google.com/goto?url=... link, which still redirects to the page when opened.
    url: str
    snippet: str = ""
    domain: str = ""  # e.g. "runrepeat.com"; empty when Google shows only a site name (Reddit, YouTube)
    source: str = ""  # site name as Google shows it, e.g. "RunRepeat" or "Reddit · r/running"
    display_url: str = ""  # breadcrumb as shown, e.g. "https://runrepeat.com › guides › best-running-shoes"


@dataclass
class AIOverview:
    text: str
    sources: list[dict] = field(default_factory=list)


@dataclass
class ParsedSerp:
    organic: list[OrganicResult] = field(default_factory=list)
    people_also_ask: list[str] = field(default_factory=list)
    related_searches: list[str] = field(default_factory=list)
    ai_overview: AIOverview | None = None


@dataclass
class FetchResult:
    status_code: int
    final_url: str
    html: str
    elapsed_ms: int


@dataclass
class Attempt:
    mode: str  # "lite", "http" or "browser"
    proxy: str
    outcome: str  # "ok", "captcha", "js_required", "consent", "empty_parse", "error", ...
    status_code: int
    elapsed_ms: int
    detail: str = ""


@dataclass
class SerpResponse:
    query: str
    # "ok", "failed", "blocked" (every IP is cooling down) or "throttled" (every IP is at its
    # hourly limit). Nothing is sent to Google for "blocked" or "throttled".
    status: str
    mode: str | None  # mode that produced the final result
    organic: list[OrganicResult] = field(default_factory=list)
    people_also_ask: list[str] = field(default_factory=list)
    related_searches: list[str] = field(default_factory=list)
    ai_overview: AIOverview | None = None
    attempts: list[Attempt] = field(default_factory=list)
    elapsed_ms: int = 0
    note: str = ""
    google_url: str = ""
    # True when served from the local cache: Google was not contacted.
    cached: bool = False
    # True when Google couldn't be asked and an older saved result (past SERP_CACHE_TTL) was returned instead.
    stale: bool = False
    created_at: float = 0.0  # unix time the results were fetched from Google

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SerpResponse":
        d = dict(d)
        d["organic"] = [OrganicResult(**o) for o in d.get("organic", [])]
        d["attempts"] = [Attempt(**a) for a in d.get("attempts", [])]
        if d.get("ai_overview"):
            d["ai_overview"] = AIOverview(**d["ai_overview"])
        return cls(**d)
