"""Test della pipeline di analisi: mediana, matching filtri, eventi e dedup persistente."""

from app.analyzer.engine import evaluate_listings, recalculate_market_values
from app.database import get_session
from app.repositories import ListingRepository, ReferenceRepository, UserRepository
from app.schemas import ScrapedListing


async def _seed_market(prices: list[float], reference_number: str = "116500LN") -> None:
    async with get_session() as session:
        reference = await ReferenceRepository(session).get_or_create(
            "Rolex", "Daytona", reference_number
        )
        listings = ListingRepository(session)
        for index, price in enumerate(prices):
            await listings.upsert_from_scrape(
                ScrapedListing(
                    brand="Rolex",
                    reference_number=reference_number,
                    price=price,
                    url=f"https://x.test/{reference_number}/{index}",
                ),
                reference.id,
            )


async def test_market_value_is_median_of_active_listings() -> None:
    await _seed_market([20000, 28000, 30000])
    await recalculate_market_values()
    async with get_session() as session:
        reference = await ReferenceRepository(session).get_by_reference_number("116500LN")
        assert reference is not None
        assert reference.estimated_market_value == 28000


async def test_deal_event_published_when_margin_beats_filter(drain_events) -> None:
    # Mediana 28000; il listing a 20000 ha margine (28000-20000)-300 = 7700 → 38.5%
    await _seed_market([20000, 28000, 30000])
    async with get_session() as session:
        await UserRepository(session).update_filter(123, min_margin_percentage=20)

    await recalculate_market_values()
    deals = await evaluate_listings()

    assert deals == 1
    events = drain_events()
    assert len(events) == 1
    payload = events[0].payload
    assert payload.chat_id == 123
    assert payload.asking_price == 20000
    assert payload.market_value == 28000
    assert payload.margin == 7700
    assert payload.margin_percentage == 38.5


async def test_dedup_no_duplicate_alerts_on_second_run(drain_events) -> None:
    await _seed_market([20000, 28000, 30000])
    async with get_session() as session:
        await UserRepository(session).update_filter(123, min_margin_percentage=20)

    await recalculate_market_values()
    assert await evaluate_listings() == 1
    # Secondo giro: stesso annuncio, nessun nuovo alert (dedup su sent_alerts).
    assert await evaluate_listings() == 0
    assert len(drain_events()) == 1


async def test_filters_exclude_wrong_brand_and_price(drain_events) -> None:
    await _seed_market([20000, 28000, 30000])
    async with get_session() as session:
        users = UserRepository(session)
        # Brand diverso: mai notificato.
        await users.update_filter(1, min_margin_percentage=5, target_brand="Patek Philippe")
        # Prezzo massimo sotto l'annuncio conveniente: mai notificato.
        await users.update_filter(2, min_margin_percentage=5, max_price=15000)
        # Margine minimo irraggiungibile: mai notificato.
        await users.update_filter(3, min_margin_percentage=90)

    await recalculate_market_values()
    assert await evaluate_listings() == 0
    assert drain_events() == []
