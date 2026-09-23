"""Turn a Google results page into structured data.

Google renames its CSS classes often, so this leans on structure that has stayed
stable for years (a result is a link wrapping an <h3>; "People also ask" items
carry a data-q attribute; the AI Overview has a visible "AI Overview" heading)
and only uses class names as optional hints.

The lite (feature phone) page has no <h3> titles, so it is read with the class
names SearXNG uses for it. If Google renames them, lite mode reports
"empty_parse" and the engine falls back to the other modes.
"""

import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from .models import AIOverview, OrganicResult, ParsedSerp

SNIPPET_HINTS = ("VwiC3b", "IsZvec", "lEBKkf")
# Hidden messages and labels Google keeps inside the overview block; not part of the answer.
AIO_PLACEHOLDERS = (
    "not available for this search", "can't generate an ai overview", "ai mode replied",
    "go to product viewer dialog",
)


def parse_serp(html: str) -> ParsedSerp:
    if html.lstrip().startswith("<?xml"):
        html = html.split("?>", 1)[-1]
    soup = BeautifulSoup(html, "lxml")
    return ParsedSerp(
        organic=_organic(soup) or _organic_lite(soup),
        people_also_ask=_people_also_ask(soup),
        related_searches=_related_searches(soup),
        ai_overview=_ai_overview(soup),
    )


def _clean_url(href: str) -> str | None:
    # The no-JavaScript page wraps links as /url?q=<real url>.
    if href.startswith("/url?"):
        href = parse_qs(urlsplit(href).query).get("q", [""])[0]
    if not href.startswith("http"):
        return None
    host = urlsplit(href).hostname or ""
    if host.endswith("google.com") or host.endswith("googleusercontent.com"):
        return None
    return href


def _organic(soup: BeautifulSoup) -> list[OrganicResult]:
    root = soup.select_one("#rso") or soup.select_one("#search") or soup
    results, seen = [], set()
    for h3 in root.find_all("h3"):
        link = h3.find_parent("a", href=True)
        if not link:
            continue
        href = link["href"]
        # Newer pages hide the target behind a coded /goto link; keep it (it redirects when opened).
        url = urljoin("https://www.google.com", href) if href.startswith("/goto?") else _clean_url(href)
        if not url or url in seen:
            continue
        seen.add(url)
        display_url, domain, source = _site_for(link)
        results.append(
            OrganicResult(
                position=len(results) + 1,
                title=h3.get_text(" ", strip=True),
                url=url,
                snippet=_snippet_for(link),
                domain=domain or _host(url),
                source=source,
                display_url=display_url,
            )
        )
    return results


def _host(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return "" if host.endswith("google.com") else host.removeprefix("www.")


def _site_for(link: Tag) -> tuple[str, str, str]:
    """(breadcrumb, domain, site name) from the lines Google shows under a result's title."""
    cite = link.find("cite")
    crumb = cite.get_text(" ", strip=True) if cite else ""
    domain = ""
    if crumb.startswith("http"):
        domain = _host(crumb.split("\u203a")[0].strip())
    else:
        crumb = ""  # a video or forum line ("270K+ views · 3 months ago"), not a URL
    names = [s.get_text(" ", strip=True) for s in link.find_all("span") if s.get_text(strip=True)]
    source = names[0].replace("\xa0", " ") if names else ""
    return crumb, domain, source


def _organic_lite(soup: BeautifulSoup) -> list[OrganicResult]:
    results, seen = [], set()
    for block in soup.select("div.zMzFAb"):
        link = block.select_one("a.fuLhoc[href]")
        title = link.select_one("span.CVA68e") if link else None
        if not title:
            continue  # not a normal result (e.g. a "Top stories" section)
        url = _clean_url(link["href"])
        if not url or url in seen:
            continue
        seen.add(url)
        snippet = block.select_one("div.taTFJ span.FrIlee")
        results.append(
            OrganicResult(
                position=len(results) + 1,
                title=title.get_text(" ", strip=True),
                url=url,
                snippet=snippet.get_text(" ", strip=True) if snippet else "",
            )
        )
    return results


def _snippet_for(link: Tag) -> str:
    # Walk up from the link to the result's block, then look for the snippet text.
    node = link
    for _ in range(6):
        node = node.parent
        if node is None:
            return ""
        el = node.find(attrs={"data-sncf": True}) or node.find(
            class_=lambda c: c and any(h in c for h in SNIPPET_HINTS)
        )
        if el:
            return el.get_text(" ", strip=True)
    return ""


def _people_also_ask(soup: BeautifulSoup) -> list[str]:
    questions = []
    for el in soup.select("[data-q]"):
        q = el["data-q"].strip()
        if q and q not in questions:
            questions.append(q)
    return questions


def _related_searches(soup: BeautifulSoup) -> list[str]:
    # Desktop: links to other searches at the bottom of the page (#botstuff).
    # Lite: the suggestion table. Pagination links carry start= and are skipped.
    links = soup.select("#botstuff a[href^='/search?']") + soup.select("table.HExoMb a.ZWRArf")
    related = []
    for a in links:
        args = parse_qs(urlsplit(a.get("href", "")).query)
        if "start" in args:
            continue
        q = (args.get("q") or [a.get_text(" ", strip=True)])[0].strip()
        if q and q not in related:
            related.append(q)
    return related


def _ai_overview(soup: BeautifulSoup) -> AIOverview | None:
    # Since 2026 the overview's body sits under a hidden "AI Mode replied:" heading (a
    # screen-reader label). Next to it Google keeps hidden "not available" messages,
    # which _aio_text drops, so a page without an overview yields too little text.
    label = soup.find(lambda t: t.name == "h3" and "AI Mode replied" in t.get_text())
    container = label.parent if label else _aio_container_by_heading(soup)
    if container is None:
        return None
    text = _aio_text(container).replace("AI Overview", "", 1).strip()
    if len(text) < 40:
        return None
    titles: dict[str, str] = {}  # url -> title, in page order
    for a in container.find_all("a", href=True):
        href = a["href"]
        # Citations are coded /goto links (they redirect to the page when opened).
        url = urljoin("https://www.google.com", href) if href.startswith("/goto?") else _clean_url(href)
        if url and not titles.get(url):
            # An image link has no text; a later link to the same page may supply the name.
            titles[url] = (a.get("aria-label") or a.get_text(" ", strip=True))[:200]
    sources = [{"title": title, "url": url} for url, title in titles.items()]
    return AIOverview(text=text, sources=sources)


def _aio_container_by_heading(soup: BeautifulSoup) -> Tag | None:
    """Older layout: climb from the visible "AI Overview" heading until the block holds the body."""
    heading = soup.find(
        lambda t: t.name in ("h1", "h2", "div", "span", "strong")
        and t.get_text(strip=True) == "AI Overview"
    )
    if not heading:
        return None
    container = heading
    for _ in range(8):
        if container.parent is None:
            break
        container = container.parent
        if len(_aio_text(container)) > 300:
            break
    return container


# Google's internal state strings ("qkimaf z6ekjd_a/HugV6", "TgQPHd|...||[[...]]"): never shown to people.
_STATE_STRING = re.compile(r"\w_\w+/\w|\|")


def _aio_text(el: Tag) -> str:
    parts = (
        t.strip() for t in el.find_all(string=True)
        if t.parent.name not in ("script", "style") and not _STATE_STRING.search(t)
    )
    return " ".join(t for t in parts if t and not any(p in t.lower() for p in AIO_PLACEHOLDERS))
