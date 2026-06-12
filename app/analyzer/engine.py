"""Logica di business: valore di mercato, margini e generazione DealFoundEvent.

Formula del margine (dalla specifica):
    Margine = (Valore_di_Mercato - Prezzo_Annuncio) - Costi_Fissi_Stimati
    Margine % = Margine / Prezzo_Annuncio * 100
"""

import logging
import statistics
from typing import NamedTuple

from app.config import get_settings
from app.database import get_session
from app.events import DealFoundEvent, event_bus
from app.models import Listing, User, WatchReference
from app.repositories import (
    ListingRepository,
    ReferenceRepository,
    SentAlertRepository,
    UserRepository,
)
from app.schemas import DealFoundPayload

logger = logging.getLogger(__name__)


class Margin(NamedTuple):
    absolute: float
    percentage: float


def compute_margin(market_value: float, asking_price: float, fixed_costs: float) -> Margin:
    absolute = (market_value - asking_price) - fixed_costs
    percentage = (absolute / asking_price * 100) if asking_price > 0 else 0.0
    return Margin(absolute=round(absolute, 2), percentage=round(percentage, 2))


async def recalculate_market_values() -> None:
    """Aggiorna l'estimated_market_value di ogni referenza con la mediana dei prezzi attivi."""
    async with get_session() as session:
        references = ReferenceRepository(session)
        listings = ListingRepository(session)
        for reference in await references.get_all():
            active = await listings.get_active_for_reference(reference.id)
            if not active:
                continue
            median_price = statistics.median(listing.price for listing in active)
            await references.update_market_value(reference, round(median_price, 2))
            logger.debug(
                "Mercato %s %s: %.2f€ (su %d annunci)",
                reference.brand,
                reference.reference_number,
                median_price,
                len(active),
            )
    logger.info("Valori di mercato ricalcolati")


def _matches_filters(
    user: User, listing: Listing, reference: WatchReference, margin: Margin
) -> bool:
    """True se almeno un filtro dell'utente accetta il deal."""
    for user_filter in user.filters:
        if user_filter.max_price is not None and listing.price > user_filter.max_price:
            continue
        if margin.percentage < user_filter.min_margin_percentage:
            continue
        if (
            user_filter.target_brand
            and user_filter.target_brand.lower() != reference.brand.lower()
        ):
            continue
        return True
    return False


async def evaluate_listings() -> int:
    """Valuta ogni annuncio attivo contro i filtri utente e pubblica i DealFoundEvent."""
    settings = get_settings()
    deals_found = 0
    async with get_session() as session:
        listings = ListingRepository(session)
        users = UserRepository(session)
        alerts = SentAlertRepository(session)
        active_listings = await listings.get_all_active()
        active_users = await users.get_active_with_filters()
        already_notified = await alerts.get_all_pairs()

        for listing in active_listings:
            reference = listing.reference
            if reference.estimated_market_value is None:
                continue
            margin = compute_margin(
                market_value=reference.estimated_market_value,
                asking_price=listing.price,
                fixed_costs=settings.estimated_fixed_costs,
            )
            if margin.absolute <= 0:
                continue

            for user in active_users:
                key = (user.id, listing.id)
                if key in already_notified:
                    continue
                if not _matches_filters(user, listing, reference, margin):
                    continue
                payload = DealFoundPayload(
                    chat_id=user.telegram_chat_id,
                    brand=reference.brand,
                    model=reference.model,
                    reference_number=reference.reference_number,
                    asking_price=listing.price,
                    market_value=reference.estimated_market_value,
                    margin=margin.absolute,
                    margin_percentage=margin.percentage,
                    url=listing.url,
                    condition=listing.condition,
                    has_box_papers=listing.has_box_papers,
                )
                await event_bus.publish(DealFoundEvent(payload=payload))
                await alerts.record(user.id, listing.id)
                already_notified.add(key)
                deals_found += 1
                logger.info(
                    "DEAL: %s %s a %.0f€ (mercato %.0f€, margine %.1f%%) per chat %d",
                    reference.brand,
                    reference.reference_number,
                    listing.price,
                    reference.estimated_market_value,
                    margin.percentage,
                    user.telegram_chat_id,
                )
    return deals_found


async def run_analysis() -> None:
    """Pipeline completa di analisi: market value → valutazione → eventi."""
    try:
        await recalculate_market_values()
        deals = await evaluate_listings()
        logger.info("Analisi completata: %d nuovi deal", deals)
    except Exception:
        logger.exception("Errore durante l'analisi")
        raise
