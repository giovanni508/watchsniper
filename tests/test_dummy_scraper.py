"""Test del DummyWatchScraper: generazione, parsing BS4 e persistenza."""

from app.database import get_session
from app.models import ConditionEnum
from app.repositories import ListingRepository, ReferenceRepository
from app.scraper.dummy import CATALOG, DummyWatchScraper
from app.scraper.persistence import persist_scraped_listings


async def test_scrape_returns_valid_listings() -> None:
    scraper = DummyWatchScraper(seed=42)
    listings = await scraper.run()
    assert listings, "lo scrape dummy deve produrre annunci"
    known_references = {ref for _, _, ref, _ in CATALOG}
    for item in listings:
        assert item.reference_number in known_references
        assert item.price > 0
        assert item.url.startswith("https://dummy-watch-market.example/")
        assert item.condition in (ConditionEnum.NEW, ConditionEnum.USED)


async def test_persist_creates_references_and_listings() -> None:
    scraper = DummyWatchScraper(seed=42)
    scraped = await scraper.run()
    saved = await persist_scraped_listings(scraped)
    assert saved == len(scraped)
    async with get_session() as session:
        assert await ReferenceRepository(session).count() == len(CATALOG)
        active = await ListingRepository(session).get_all_active()
        # Gli URL sono unici: upsert, non duplicazione.
        assert len(active) == len({item.url for item in scraped})


def test_parse_skips_malformed_cards() -> None:
    scraper = DummyWatchScraper()
    html = """
    <html><body>
      <div class="listing-card" data-condition="used" data-box-papers="yes">
        <span class="brand">Rolex</span><span class="model">Daytona</span>
        <span class="reference">116500LN</span><span class="price">EUR 25,000</span>
        <a class="link" href="https://x.test/ok">ok</a>
      </div>
      <div class="listing-card"><span class="brand">Broken</span></div>
    </body></html>
    """
    listings = scraper._parse(html)
    assert len(listings) == 1
    assert listings[0].price == 25000
    assert listings[0].has_box_papers is True
