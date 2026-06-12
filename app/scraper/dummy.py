"""Scraper di esempio: genera un marketplace fittizio e lo parsa con BeautifulSoup.

Dimostra la pipeline completa (HTML → parsing → DTO → repository) senza colpire
siti reali e senza richiedere un browser installato: `run()` è ridefinito per
saltare l'avvio di Playwright. Uno scraper reale erediterebbe da BaseScraper
usando `fetch_html()` e lo stesso parsing BS4 di questo modulo.
"""

import logging
import random

from bs4 import BeautifulSoup, Tag

from app.database import get_session
from app.models import ConditionEnum
from app.repositories import ListingRepository, ReferenceRepository
from app.schemas import ScrapedListing
from app.scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# Catalogo fittizio: (brand, model, reference, prezzo base di mercato)
CATALOG: tuple[tuple[str, str, str, float], ...] = (
    ("Rolex", "Daytona", "116500LN", 28000.0),
    ("Rolex", "Submariner Date", "126610LN", 13500.0),
    ("Rolex", "GMT-Master II", "126710BLRO", 19000.0),
    ("Omega", "Speedmaster Moonwatch", "310.30.42.50.01.001", 6500.0),
    ("Patek Philippe", "Nautilus", "5711/1A-010", 95000.0),
    ("Audemars Piguet", "Royal Oak", "15500ST.OO.1220ST.01", 45000.0),
)


def _build_fake_marketplace_html(rng: random.Random) -> str:
    """Genera l'HTML di un finto marketplace con prezzi che oscillano attorno al base.

    Circa un annuncio su sei esce molto sotto mercato, così l'analyzer ha
    periodicamente dei "deal" da segnalare.
    """
    cards: list[str] = []
    for brand, model, reference, base_price in CATALOG:
        for _ in range(rng.randint(2, 5)):
            if rng.random() < 0.17:
                factor = rng.uniform(0.70, 0.85)  # sottoprezzo: potenziale affare
            else:
                factor = rng.uniform(0.92, 1.12)
            price = round(base_price * factor, -1)
            listing_id = rng.randint(100000, 999999)
            condition = rng.choice(["new", "used"])
            box_papers = rng.choice(["yes", "no"])
            cards.append(
                f"""
                <div class="listing-card" data-condition="{condition}"
                     data-box-papers="{box_papers}">
                  <span class="brand">{brand}</span>
                  <span class="model">{model}</span>
                  <span class="reference">{reference}</span>
                  <span class="price">EUR {price:,.0f}</span>
                  <a class="link" href="https://dummy-watch-market.example/listing/{listing_id}">
                    Vedi annuncio
                  </a>
                </div>
                """
            )
    return f"<html><body><div id='results'>{''.join(cards)}</div></body></html>"


class DummyWatchScraper(BaseScraper):
    name = "dummy-watch-market"

    def __init__(self, seed: int | None = None) -> None:
        super().__init__()
        self._rng = random.Random(seed)

    async def scrape(self) -> list[ScrapedListing]:
        html = _build_fake_marketplace_html(self._rng)
        return self._parse(html)

    def _parse(self, html: str) -> list[ScrapedListing]:
        soup = BeautifulSoup(html, "html.parser")
        listings: list[ScrapedListing] = []
        for card in soup.select("div.listing-card"):
            try:
                listings.append(self._parse_card(card))
            except Exception:
                # Una card malformata non deve interrompere l'intero scrape.
                logger.exception("[%s] Card non parsabile, ignorata", self.name)
        return listings

    def _parse_card(self, card: Tag) -> ScrapedListing:
        def text_of(selector: str) -> str:
            node = card.select_one(selector)
            if node is None:
                raise ValueError(f"selettore mancante: {selector}")
            return node.get_text(strip=True)

        link = card.select_one("a.link")
        if link is None or not link.get("href"):
            raise ValueError("link annuncio mancante")

        price_raw = text_of("span.price").replace("EUR", "").replace(",", "").strip()
        return ScrapedListing(
            brand=text_of("span.brand"),
            model=text_of("span.model"),
            reference_number=text_of("span.reference"),
            price=float(price_raw),
            url=str(link["href"]),
            condition=ConditionEnum(card.get("data-condition", "used")),
            has_box_papers=card.get("data-box-papers") == "yes",
        )

    async def run(self) -> list[ScrapedListing]:
        """Il dummy non naviga: niente Playwright, solo generazione+parsing."""
        try:
            listings = await self.scrape()
            logger.info("[%s] Scrape completato: %d annunci", self.name, len(listings))
            return listings
        except Exception:
            logger.exception("[%s] Scrape fallito", self.name)
            return []


async def persist_scraped_listings(scraped: list[ScrapedListing]) -> int:
    """Salva i risultati dello scrape nel DB tramite il repository pattern."""
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
