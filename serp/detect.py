def is_block_redirect(url: str) -> bool:
    """True if Google redirected to its captcha or consent page instead of the results."""
    return "/sorry/" in url or "sorry.google." in url or "consent.google." in url


def classify_block(status_code: int, final_url: str, html: str) -> str | None:
    """Return why a Google response is unusable, or None if it looks like a real results page."""
    low = html.lower()
    if status_code == 429 or "/sorry/" in final_url or "sorry.google." in final_url or 'id="captcha-form"' in low or "unusual traffic" in low:
        return "captcha"
    if len(html) < 2000 and "/sorry/" in low:
        # A tiny page that only points at the captcha (meta refresh or JS redirect).
        return "captcha"
    if "consent.google." in final_url or 'action="https://consent.google' in low:
        return "consent"
    if status_code >= 400:
        return f"http_{status_code}"
    if 'id="search"' in low or 'id="rso"' in low or "zmzfab" in low:
        # Real results pages also carry an "enablejs" redirect inside <noscript>, so
        # the results container has to win over that marker. "zMzFAb" wraps each
        # result on the lite (feature phone) page.
        return None
    if "enablejs" in low or "/httpservice/retry/" in low:
        # Google served the "turn on JavaScript" page: plain HTTP is not enough for this request.
        return "js_required"
    return "no_results_container"
