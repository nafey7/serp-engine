from dataclasses import asdict, dataclass, field


@dataclass
class OrganicResult:
    position: int
    title: str
    # The real page URL. Newer desktop pages only carry a coded https://www.google.com/goto?url=...
    # link; the engine follows it to the real page. One left as /goto could not be resolved,
    # and the response then lists it under `problems`.
    url: str
    snippet: str = ""
    domain: str = ""  # e.g. "runrepeat.com"; empty when Google shows only a site name (Reddit, YouTube)
    source: str = ""  # site name as Google shows it, e.g. "RunRepeat" or "Reddit · r/running"
    display_url: str = ""  # breadcrumb as shown, e.g. "https://runrepeat.com › guides › best-running-shoes"


@dataclass
class AIOverview:
    # The answer only: one line per paragraph, heading or list item ("- "). Citation chips,
    # product prices, video cards, the source panel and buttons are left out.
    text: str
    # Every cited page, in Google's order: {"title", "site", "url"}.
    sources: list[dict] = field(default_factory=list)


@dataclass
class ParsedSerp:
    organic: list[OrganicResult] = field(default_factory=list)
    people_also_ask: list[str] = field(default_factory=list)
    related_searches: list[str] = field(default_factory=list)
    ai_overview: AIOverview | None = None
    ai_overview_complete: bool = False  # the overview's full source list is on the page


@dataclass
class FetchResult:
    status_code: int
    final_url: str
    html: str
    elapsed_ms: int
    # Browser mode only: True if Google visibly showed an AI Overview, None if not checked.
    aio_shown: bool | None = None
    # Browser mode only: True if the overview finished loading before the wait ran out.
    aio_complete: bool | None = None
    # Browser mode only: coded /goto link -> its resolution (a Future), started while the page loaded.
    links: dict = field(default_factory=dict)


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
    # True only when the result is complete: organic results with real URLs, and (when asked
    # for and shown by Google) the AI Overview text with every source resolved. Partial = False.
    valid: bool = False
    problems: list[str] = field(default_factory=list)  # why valid is False, e.g. "unresolved_links: 2"
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
