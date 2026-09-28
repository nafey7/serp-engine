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

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from .models import AIOverview, OrganicResult, ParsedSerp

SNIPPET_HINTS = ("VwiC3b", "IsZvec", "lEBKkf")
# Hidden messages and labels Google keeps inside the overview block; not part of the answer.
AIO_PLACEHOLDERS = (
    "not available for this search", "can't generate an ai overview", "ai mode replied",
    "go to product viewer dialog",
)


def parse_serp(html: str, fill_deferred: bool = False) -> ParsedSerp:
    """`fill_deferred`: the page came over plain HTTP, so Google's scripts never ran; put the
    parts they would have inserted (the rest of the AI Overview) in place first."""
    if html.lstrip().startswith("<?xml"):
        html = html.split("?>", 1)[-1]
    soup = BeautifulSoup(html, "lxml")
    if fill_deferred:
        _fill_deferred(soup, html)
    aio_container = _aio_container(soup)
    return ParsedSerp(
        organic=_organic(soup) or _organic_lite(soup),
        people_also_ask=_people_also_ask(soup),
        related_searches=_related_searches(soup),
        ai_overview=_ai_overview(aio_container),
        # Google adds the overview's full source list only once the answer is complete.
        ai_overview_complete=bool(aio_container and aio_container.select_one(_AIO_DONE)),
    )


# Google sends part of the page as HTML inside scripts, and its JavaScript inserts each piece
# into the element with the given id: [{id:'sdh_...'},function(){jsl.dh(this.id,"\x3cdiv ...")}].
# The AI Overview arrives this way in chunks ("sdh" = streamed deferred HTML).
_DEFERRED = re.compile(r"""\{id:'([^']+)'\},function\(\)\{(?:window\.)?jsl\.dh\(this\.id,(["'])((?:\\.|(?!\2)[^\\])*)\2\)""", re.S)
_JS_ESCAPE = re.compile(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|.)", re.S)
_AIO_DONE = '[role=dialog] li, [aria-label="Show less related results"]'


def _js_unescape(s: str) -> str:
    def one(m):
        e = m.group(1)
        if e[0] in "xu" and len(e) > 1:
            return chr(int(e[1:], 16))
        return {"n": "\n", "t": "\t", "r": "\r"}.get(e, e)
    return _JS_ESCAPE.sub(one, s)


def _fill_deferred(soup: BeautifulSoup, html: str) -> None:
    pieces = [(m.group(1), _js_unescape(m.group(3))) for m in _DEFERRED.finditer(html)]
    for _ in range(3):  # a piece can target an element that another piece creates
        waiting = []
        for el_id, fragment in pieces:
            el = soup.find(id=el_id)
            if el is None:
                waiting.append((el_id, fragment))
                continue
            el.clear()
            el.append(BeautifulSoup(fragment, "html.parser"))
        if not waiting or len(waiting) == len(pieces):
            break
        pieces = waiting


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
        url = _link_url(href)
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


def _aio_container(soup: BeautifulSoup) -> Tag | None:
    # Since 2026 the overview's body sits under a hidden "AI Mode replied:" heading (a
    # screen-reader label). Next to it Google keeps hidden "not available" messages,
    # which are dropped, so a page without an overview yields too little text.
    label = soup.find(lambda t: t.name == "h3" and "AI Mode replied" in t.get_text())
    return label.parent if label else _aio_container_by_heading(soup)


def _ai_overview(container: Tag | None) -> AIOverview | None:
    if container is None:
        return None
    text = _aio_answer(container)
    if text.startswith("AI Overview"):
        text = text.removeprefix("AI Overview").lstrip()
    if len(text) < 40:
        return None
    return AIOverview(text=text, sources=_aio_sources(container))


def _link_url(href: str) -> str | None:
    # Newer pages hide the target behind a coded /goto link; the engine follows it to the real page.
    return urljoin("https://www.google.com", href) if href.startswith("/goto?") else _clean_url(href)


# Google marks the parts of the overview that are not the answer in ways that survive its class
# renames: the source panel and video cards carry data-ignore-copy (Google leaves them out when
# you copy the answer), and citation chips and "Show more" are buttons.
_AIO_SKIP = "script, style, svg, button, [data-ignore-copy], [role=dialog]"
_BLOCK_TAGS = {"div", "p", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "pre", "blockquote"}


def _aio_answer(container: Tag) -> str:
    """The overview's answer as plain text: one line per paragraph, heading or list item ("- ")."""
    body = BeautifulSoup(str(container), "lxml")
    for el in body.select(_AIO_SKIP):
        el.decompose()
    for card in body.select("[role=button]"):
        img = card.find("img", alt=True)
        name = img["alt"].strip() if img else ""
        if img:
            img.decompose()
        if name and card.get_text(strip=True):
            # A product card: keep the product's name, drop price, rating and "Add to list".
            card.replace_with(body.new_tag("div", string=name))
        elif card.name == "a" and not name:
            card.unwrap()  # a clickable term inside a sentence ("sourdough bread")
        else:
            card.decompose()  # a source's thumbnail, or a control such as "Show more"
    lines: list[str] = []
    _walk(body.body or body, lines, [], inline=False)
    return "\n".join(lines)


def _walk(el: Tag, lines: list[str], cur: list[str], inline: bool) -> None:
    for child in el.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            if not _STATE_STRING.search(child) and not any(p in child.lower() for p in AIO_PLACEHOLDERS):
                cur.append(str(child))
            continue
        # A block nested inside inline text (a product name mid-sentence) stays in the sentence.
        if inline or child.name not in _BLOCK_TAGS:
            _walk(child, lines, cur, inline=True)
            continue
        _flush(lines, cur)
        start = len(lines)
        _walk(child, lines, cur, inline=False)
        _flush(lines, cur)
        if child.name == "li" and len(lines) > start:
            lines[start] = "- " + lines[start]


def _flush(lines: list[str], cur: list[str]) -> None:
    line = re.sub(r"\s+", " ", "".join(cur)).strip()
    # Spaces the markup leaves before punctuation ("works properly .").
    line = re.sub(r" ([.,;:!?])(?=\s|$)", r"\1", line)
    if line:
        lines.append(line)
    cur.clear()


def _aio_sources(container: Tag) -> list[dict]:
    """Every page the overview cites, in the order of Google's full source list ("Show all")."""
    sources, seen = [], set()
    panel = container.select_one("[role=dialog]")
    for item in panel.select("li") if panel else []:
        a = item.find("a", href=True)
        url = _link_url(a["href"]) if a else None
        if not url or url in seen:
            continue  # e.g. a Google Shopping card, which links to no page
        seen.add(url)
        label = a.get("aria-label", "")
        title = re.sub(r"(\. Opens in new tab\.|, Video, watch on .*)$", "", label).strip() or a.get_text(" ", strip=True)
        text = item.get_text(" ", strip=True)
        site = text.split(title, 1)[0].strip() if title and title in text else ""
        sources.append({"title": title[:200], "site": site[:100], "url": url})
    # Links in the answer itself that the list lacks (and older layouts without the list).
    for a in container.find_all("a", href=True):
        url = _link_url(a["href"])
        if url and url not in seen:
            seen.add(url)
            name = (a.get("aria-label") or a.get_text(" ", strip=True))[:200]
            sources.append({"title": name, "site": "", "url": url})
    return sources


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
