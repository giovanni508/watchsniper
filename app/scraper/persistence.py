"""Persistenza generica dei risultati di scrape (repository pattern).

Usata da qualunque scraper: i DTO `ScrapedListing` vengono convertiti in
referenze e annunci tramite i repository, indipendentemente dalla fonte.
"""

import logging

from app.database import get_session
from app.repositories import ListingRepository, ReferenceRepository
from app.schemas import ScrapedListing

logger = logging.getLogger(__name__)


async def persist_scraped_listings(scraped: list[ScrapedListing]) -> int:
    """Salva i risultati dello scrape nel DB. Restituisce il numero di annunci persistiti."""
    saved = 0
    async with get_session() as session:
        references = ReferenceRepository(session)
        listings = ListingRepository(session)
        for item in scraped:
            try:
                reference = await references.get_or_create(
                    brand=item.brand,
                    model=item.model,
                    reference_number=item.reference_number,
                )
                await listings.upsert_from_scrape(item, reference.id)
                saved += 1
            except Exception:
                logger.exception("Persistenza fallita per %s", item.url)
    logger.info("Persistiti %d/%d annunci", saved, len(scraped))
    return saved
