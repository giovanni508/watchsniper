"""Test del meccanismo di retry/backoff di BaseScraper, senza Playwright né rete."""

import pytest

from app.scraper.base import BaseScraper


class _DummyRetryScraper(BaseScraper):
    """Scraper minimale per esercitare `_with_retry` senza avviare un browser."""

    name = "retry-test"

    def __init__(self) -> None:
        super().__init__()
        # Copia isolata: evita di mutare il singleton cacheato di get_settings().
        self._settings = self._settings.model_copy()

    async def scrape(self):  # pragma: no cover - non usato in questi test
        return []

    async def rotate_identity(self) -> None:
        # Niente browser nei test: la rotazione identità è un no-op.
        return None


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    # Evita le attese reali del backoff esponenziale.
    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.scraper.base.asyncio.sleep", _instant)


async def test_with_retry_succeeds_after_transient_failures() -> None:
    scraper = _DummyRetryScraper()
    scraper._settings.scraper_max_retries = 3
    scraper._settings.scraper_retry_base_delay = 0.0
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("errore transitorio")
        return "ok"

    result = await scraper._with_retry(flaky, what="test")
    assert result == "ok"
    assert calls == 3


async def test_with_retry_raises_after_exhausting_attempts() -> None:
    scraper = _DummyRetryScraper()
    scraper._settings.scraper_max_retries = 2
    scraper._settings.scraper_retry_base_delay = 0.0
    calls = 0

    async def always_fails() -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await scraper._with_retry(always_fails, what="test")
    assert calls == 2  # esattamente max_retries tentativi
