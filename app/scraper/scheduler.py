"""Scheduler periodico: scrape → persistenza → analisi → eventi.

Le fonti attive si scelgono via configurazione (`SCRAPER_SOURCES` in `.env`,
es. "dummy", "chrono24" o "dummy,chrono24"). Per aggiungere una nuova fonte:
implementa una sottoclasse di `BaseScraper` e registrala in `SCRAPER_REGISTRY`.
"""

import asyncio
import logging

from app.analyzer.engine import run_analysis
from app.config import get_settings
from app.scraper.base import BaseScraper
from app.scraper.chrono24 import Chrono24Scraper
from app.scraper.dummy import DummyWatchScraper
from app.scraper.persistence import persist_scraped_listings

logger = logging.getLogger(__name__)

# Fonti disponibili, indicizzate per nome (quello usato in SCRAPER_SOURCES).
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "dummy": DummyWatchScraper,
    "chrono24": Chrono24Scraper,
}


def get_active_scrapers() -> list[type[BaseScraper]]:
    """Risolve le fonti configurate in classi scraper, con fallback sul dummy."""
    active: list[type[BaseScraper]] = []
    for name in get_settings().scraper_source_list:
        scraper_cls = SCRAPER_REGISTRY.get(name)
        if scraper_cls is None:
            logger.warning(
                "Fonte scraper sconosciuta: %r (disponibili: %s)",
                name,
                ", ".join(SCRAPER_REGISTRY),
            )
            continue
        active.append(scraper_cls)
    if not active:
        logger.warning("Nessuna fonte valida configurata, uso il DummyWatchScraper")
        active.append(DummyWatchScraper)
    return active


async def scrape_cycle() -> None:
    """Un singolo ciclo completo su tutte le fonti. Le eccezioni vengono loggate, mai propagate."""
    for scraper_cls in get_active_scrapers():
        scraper = scraper_cls()
        scraped = await scraper.run()  # non solleva: errori già loggati dallo scraper
        if scraped:
            await persist_scraped_listings(scraped)
    try:
        await run_analysis()
    except Exception:
        logger.exception("Ciclo di analisi fallito")


async def scheduler_loop() -> None:
    """Esegue cicli di scrape+analisi a intervallo configurabile, per sempre."""
    settings = get_settings()
    active = get_active_scrapers()
    logger.info(
        "Scheduler avviato (intervallo: %ds, fonti: %s)",
        settings.scrape_interval_seconds,
        ", ".join(s.name for s in active),
    )
    while True:
        try:
            await scrape_cycle()
        except Exception:
            # Cintura e bretelle: il loop dello scheduler non deve mai morire.
            logger.exception("Ciclo di scrape fallito, riprovo al prossimo giro")
        await asyncio.sleep(settings.scrape_interval_seconds)
