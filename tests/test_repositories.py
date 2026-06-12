"""Test dei repository: upsert listing, registrazione utente, filtri, dedup alert."""

from app.database import get_session
from app.models import ConditionEnum
from app.repositories import (
    ListingRepository,
    ReferenceRepository,
    SentAlertRepository,
    UserRepository,
)
from app.schemas import ScrapedListing


def _scraped(url: str, price: float) -> ScrapedListing:
    return ScrapedListing(
        brand="Rolex",
        model="Daytona",
        reference_number="116500LN",
        price=price,
        url=url,
        condition=ConditionEnum.USED,
        has_box_papers=True,
    )


async def test_upsert_listing_creates_then_updates_price() -> None:
    async with get_session() as session:
        reference = await ReferenceRepository(session).get_or_create(
            "Rolex", "Daytona", "116500LN"
        )
        listings = ListingRepository(session)
        created = await listings.upsert_from_scrape(
            _scraped("https://x.test/1", 25000), reference.id
        )
        updated = await listings.upsert_from_scrape(
            _scraped("https://x.test/1", 24000), reference.id
        )
        assert created.id == updated.id
        assert updated.price == 24000
        assert len(await listings.get_active_for_reference(reference.id)) == 1


async def test_get_or_create_reference_is_idempotent() -> None:
    async with get_session() as session:
        references = ReferenceRepository(session)
        first = await references.get_or_create("Rolex", "Daytona", "116500LN")
        second = await references.get_or_create("Rolex", "Daytona", "116500LN")
        assert first.id == second.id
        assert await references.count() == 1


async def test_register_user_is_idempotent_and_creates_default_filter() -> None:
    async with get_session() as session:
        users = UserRepository(session)
        user = await users.register(42)
        again = await users.register(42)
        assert user.id == again.id
        assert len(user.filters) == 1
        assert user.filters[0].min_margin_percentage == 10.0


async def test_update_filter_registers_user_implicitly() -> None:
    async with get_session() as session:
        users = UserRepository(session)
        user_filter = await users.update_filter(99, max_price=15000, target_brand="Rolex")
        assert user_filter.max_price == 15000
        assert user_filter.target_brand == "Rolex"
        user = await users.get_by_chat_id(99)
        assert user is not None and user.is_active


async def test_sent_alert_dedup_pairs() -> None:
    async with get_session() as session:
        user = await UserRepository(session).register(7)
        reference = await ReferenceRepository(session).get_or_create("Omega", "Speedy", "311")
        listing = await ListingRepository(session).upsert_from_scrape(
            ScrapedListing(brand="Omega", reference_number="311", price=5000, url="https://x.test/7"),
            reference.id,
        )
        alerts = SentAlertRepository(session)
        assert await alerts.get_all_pairs() == set()
        await alerts.record(user.id, listing.id)
        assert await alerts.get_all_pairs() == {(user.id, listing.id)}
