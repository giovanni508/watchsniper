"""Scheduler periodico: scrape → persistenza → analisi → eventi.

Per aggiungere una nuova fonte è sufficiente implementare una sottoclasse di
`BaseScraper` e registrarla in `SCRAPERS`: lo scheduler la eseguirà a ogni ciclo.
"""

import asyncio
import logging

from app.analyzer.engine import run_analysis
from app.config import get_settings
from app.scraper.base import BaseScraper
from app.scraper.chrono24 import Chrono24Scraper
from app.scraper.dummy import DummyWatchScraper  # noqa: F401 — fonte demo, vedi SCRAPERS
from app.scraper.persistence import persist_scraped_listings

logger = logging.getLogger(__name__)

# Registro delle fonti attive. Per aggiungere una fonte: sottoclasse di
# BaseScraper + voce qui sotto.
# DummyWatchScraper è temporaneamente disattivato per testare lo scraper reale.
SCRAPERS: tuple[type[BaseScraper], ...] = (
    Chrono24Scraper,
    # DummyWatchScraper,
)


async def scrape_cycle() -> None:
    """Un singolo ciclo completo su tutte le fonti. Le eccezioni vengono loggate, mai propagate."""
    for scraper_cls in SCRAPERS:
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
    interval = get_settings().scrape_interval_seconds
    logger.info("Scheduler avviato (intervallo: %ds, fonti: %d)", interval, len(SCRAPERS))
    while True:
        try:
            await scrape_cycle()
        except Exception:
            # Cintura e bretelle: il loop dello scheduler non deve mai morire.
            logger.exception("Ciclo di scrape fallito, riprovo al prossimo giro")
        await asyncio.sleep(interval)
