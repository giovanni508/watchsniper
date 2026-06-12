"""Scheduler periodico: scrape → persistenza → analisi → eventi."""

import asyncio
import logging

from app.analyzer.engine import run_analysis
from app.config import get_settings
from app.scraper.dummy import DummyWatchScraper, persist_scraped_listings

logger = logging.getLogger(__name__)


async def scrape_cycle() -> None:
    """Un singolo ciclo completo. Le eccezioni vengono loggate, mai propagate."""
    scraper = DummyWatchScraper()
    scraped = await scraper.run()
    if scraped:
        await persist_scraped_listings(scraped)
    try:
        await run_analysis()
    except Exception:
        logger.exception("Ciclo di analisi fallito")


async def scheduler_loop() -> None:
    """Esegue cicli di scrape+analisi a intervallo configurabile, per sempre."""
    interval = get_settings().scrape_interval_seconds
    logger.info("Scheduler avviato (intervallo: %ds)", interval)
    while True:
        try:
            await scrape_cycle()
        except Exception:
            # Cintura e bretelle: il loop dello scheduler non deve mai morire.
            logger.exception("Ciclo di scrape fallito, riprovo al prossimo giro")
        await asyncio.sleep(interval)
