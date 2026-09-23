import pytest

from serp.fetch_browser import BrowserFetcher
from serp.fetch_http import HttpFetcher


def _offline(*a, **k):
    raise RuntimeError("tests must not contact Google")


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    """Any fetch a test didn't replace with a fake fails instead of reaching Google."""
    monkeypatch.setattr(HttpFetcher, "_get", _offline)
    monkeypatch.setattr(BrowserFetcher, "fetch", _offline)
    monkeypatch.setenv("SERP_SESSION_DIR", str(tmp_path / "sessions"))
