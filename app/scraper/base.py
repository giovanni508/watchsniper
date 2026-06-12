"""Scraper base asincrono con Playwright e contromisure anti-bot basilari.

Le contromisure (rotazione User-Agent/viewport, ritardi casuali) servono a
rendere il traffico simile a quello umano sui siti che si è autorizzati a
scrappare. Rispettare sempre i Termini di Servizio e il robots.txt dei target.
"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from app.config import get_settings
from app.schemas import ScrapedListing

logger = logging.getLogger(__name__)

USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
)

VIEWPORTS: tuple[dict[str, int], ...] = (
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
)


class BaseScraper(ABC):
    """Gestisce il ciclo di vita di Playwright; le sottoclassi implementano `scrape()`."""

    name: str = "base"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> Self:
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._settings.scraper_headless
            )
            self._context = await self._new_context()
        except Exception:
            logger.exception("[%s] Avvio di Playwright fallito", self.name)
            await self.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:
                    logger.exception("[%s] Errore in chiusura risorsa Playwright", self.name)
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                logger.exception("[%s] Errore nello stop di Playwright", self.name)
        self._playwright = self._browser = self._context = None

    async def _new_context(self) -> BrowserContext:
        """Crea un contesto browser con User-Agent e viewport ruotati casualmente."""
        assert self._browser is not None
        user_agent = random.choice(USER_AGENTS)
        viewport = random.choice(VIEWPORTS)
        logger.debug("[%s] Nuovo contesto: UA=%s viewport=%s", self.name, user_agent, viewport)
        return await self._browser.new_context(
            user_agent=user_agent,
            viewport=viewport,  # type: ignore[arg-type]
            locale="it-IT",
        )

    async def rotate_identity(self) -> None:
        """Sostituisce il contesto corrente con uno con nuova identità."""
        if self._context is not None:
            await self._context.close()
        self._context = await self._new_context()

    async def new_page(self) -> Page:
        assert self._context is not None, "Scraper non avviato: usare `async with`"
        return await self._context.new_page()

    async def random_delay(self) -> None:
        """Pausa casuale (default 2–7s) per eludere rate-limiter e sistemi anti-bot."""
        delay = random.uniform(self._settings.scraper_min_delay, self._settings.scraper_max_delay)
        logger.debug("[%s] Attesa anti-bot di %.1fs", self.name, delay)
        await asyncio.sleep(delay)

    async def fetch_html(self, url: str, *, wait_until: str = "domcontentloaded") -> str:
        """Naviga a `url` con una pagina temporanea e restituisce l'HTML renderizzato."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until=wait_until)  # type: ignore[arg-type]
            await self.random_delay()
            return await page.content()
        finally:
            await page.close()

    @abstractmethod
    async def scrape(self) -> list[ScrapedListing]:
        """Estrae gli annunci dal target. Implementato dalle sottoclassi."""

    async def run(self) -> list[ScrapedListing]:
        """Esegue uno scrape completo con gestione errori; non solleva mai."""
        try:
            async with self:
                listings = await self.scrape()
                logger.info("[%s] Scrape completato: %d annunci", self.name, len(listings))
                return listings
        except Exception:
            logger.exception("[%s] Scrape fallito", self.name)
            return []
