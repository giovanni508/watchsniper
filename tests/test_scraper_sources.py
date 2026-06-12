"""Test della selezione delle fonti scraper da configurazione."""

import pytest

from app.scraper.chrono24 import Chrono24Scraper
from app.scraper.dummy import DummyWatchScraper
from app.scraper.scheduler import get_active_scrapers


@pytest.fixture
def set_sources(monkeypatch: pytest.MonkeyPatch):
    """Imposta SCRAPER_SOURCES su una copia isolata delle settings dello scheduler."""
    from app.config import get_settings
    from app.scraper import scheduler

    base = get_settings()

    def _apply(value: str):
        patched = base.model_copy(update={"scraper_sources": value})
        monkeypatch.setattr(scheduler, "get_settings", lambda: patched)

    return _apply


def test_default_dummy_source(set_sources) -> None:
    set_sources("dummy")
    assert get_active_scrapers() == [DummyWatchScraper]


def test_chrono24_source(set_sources) -> None:
    set_sources("chrono24")
    assert get_active_scrapers() == [Chrono24Scraper]


def test_multiple_sources_preserve_order_and_dedup(set_sources) -> None:
    set_sources("chrono24, dummy , chrono24")
    assert get_active_scrapers() == [Chrono24Scraper, DummyWatchScraper]


def test_unknown_source_falls_back_to_dummy(set_sources) -> None:
    set_sources("does-not-exist")
    assert get_active_scrapers() == [DummyWatchScraper]


def test_empty_sources_falls_back_to_dummy(set_sources) -> None:
    set_sources("")
    assert get_active_scrapers() == [DummyWatchScraper]
