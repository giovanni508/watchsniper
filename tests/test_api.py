"""Test degli endpoint FastAPI con httpx (ASGITransport, nessun server reale)."""

import httpx
import pytest

from app.api.app import create_app
from app.database import get_session
from app.repositories import ListingRepository, ReferenceRepository
from app.schemas import ScrapedListing


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed(prices: list[float], market_value: float) -> None:
    async with get_session() as session:
        references = ReferenceRepository(session)
        reference = await references.get_or_create("Rolex", "Daytona", "116500LN")
        await references.update_market_value(reference, market_value)
        listings = ListingRepository(session)
        for index, price in enumerate(prices):
            await listings.upsert_from_scrape(
                ScrapedListing(
                    brand="Rolex",
                    reference_number="116500LN",
                    price=price,
                    url=f"https://x.test/{index}",
                ),
                reference.id,
            )


async def test_get_references(client: httpx.AsyncClient) -> None:
    await _seed([25000], market_value=28000)
    response = await client.get("/api/references")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["reference_number"] == "116500LN"
    assert body[0]["estimated_market_value"] == 28000


async def test_get_deals_filters_by_margin_and_price(client: httpx.AsyncClient) -> None:
    # Con mercato 28000 e costi fissi 300: 20000 → 38.5%, 27000 → 2.6%
    await _seed([20000, 27000], market_value=28000)

    response = await client.get("/api/deals")
    assert response.status_code == 200
    deals = response.json()
    assert len(deals) == 1
    assert deals[0]["listing"]["price"] == 20000
    assert deals[0]["margin_percentage"] == 38.5

    # max_price sotto il deal: nessun risultato.
    response = await client.get("/api/deals", params={"max_price": 15000})
    assert response.json() == []


async def test_post_filters_creates_user_filter(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/filters",
        json={"telegram_chat_id": 555, "max_price": 30000, "min_margin_percentage": 12},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["max_price"] == 30000
    assert body["min_margin_percentage"] == 12


async def test_post_filters_requires_at_least_one_criterion(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/filters", json={"telegram_chat_id": 555})
    assert response.status_code == 422
