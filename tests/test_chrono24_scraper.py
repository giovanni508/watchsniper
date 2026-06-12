"""Test del Chrono24Scraper: parsing di card mockate e pulizia del prezzo.

Nessuna chiamata di rete: si verifica direttamente la logica di estrazione su
HTML statico che riproduce la struttura tipica di una card Chrono24.
"""

import pytest

from app.models import ConditionEnum
from app.scraper.chrono24 import Chrono24Scraper, map_condition, parse_price

# Blocco HTML che imita due card di risultato Chrono24 + una "Prezzo su richiesta".
MOCK_HTML = """
<html><body>
  <div class="article-item-container">
    <a class="article-item" href="/rolex/daytona--id12345678.htm">
      <div class="article-title text-bold">Rolex Daytona 116500LN</div>
      <div class="article-price">€ 28.500</div>
      <div class="article-condition">Unworn</div>
      <div class="article-bottom-text">Box, Original papers (2023)</div>
    </a>
  </div>
  <div class="article-item-container">
    <a class="article-item" href="https://www.chrono24.com/rolex/daytona--id87654321.htm">
      <div class="article-title text-bold">Rolex Daytona 116500LN</div>
      <div class="article-price">€ 26.900</div>
      <div class="article-condition">Pre-owned</div>
      <div class="article-bottom-text">Original papers only</div>
    </a>
  </div>
  <div class="article-item-container">
    <a class="article-item" href="/rolex/daytona--id99999999.htm">
      <div class="article-title text-bold">Rolex Daytona 116500LN</div>
      <div class="article-price">Price on request</div>
      <div class="article-condition">Used</div>
    </a>
  </div>
</body></html>
"""


def test_parse_extracts_listings_from_cards() -> None:
    scraper = Chrono24Scraper(targets=[("Rolex", "116500LN")])
    listings = scraper._parse(MOCK_HTML, brand="Rolex", reference_number="116500LN")

    # La terza card ("Price on request") viene scartata: nessun prezzo numerico.
    assert len(listings) == 2

    first = listings[0]
    assert first.brand == "Rolex"
    assert first.reference_number == "116500LN"
    assert first.price == 28500.0
    assert first.condition is ConditionEnum.NEW  # "Unworn"
    assert first.has_box_papers is True  # box + papers presenti
    assert first.url == "https://www.chrono24.com/rolex/daytona--id12345678.htm"

    second = listings[1]
    assert second.price == 26900.0
    assert second.condition is ConditionEnum.USED  # "Pre-owned"
    assert second.has_box_papers is False  # solo papers, manca la scatola
    # Gli href assoluti vengono preservati così come sono.
    assert second.url == "https://www.chrono24.com/rolex/daytona--id87654321.htm"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("€ 28.000", 28000.0),
        ("28,500 USD", 28500.0),
        ("€ 6.500,00", 6500.0),
        ("$12,500.00", 12500.0),
        ("1.234.567", 1234567.0),
        ("€ 99,99", 99.99),
        ("EUR 13500", 13500.0),
    ],
)
def test_parse_price_handles_currencies_and_separators(raw: str, expected: float) -> None:
    assert parse_price(raw) == expected


@pytest.mark.parametrize("raw", ["Price on request", "Prezzo su richiesta", "—", ""])
def test_parse_price_rejects_non_numeric(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_price(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Unworn", ConditionEnum.NEW),
        ("New", ConditionEnum.NEW),
        ("Nuovo", ConditionEnum.NEW),
        ("Pre-owned", ConditionEnum.USED),
        ("Used", ConditionEnum.USED),
        ("Very good", ConditionEnum.USED),
    ],
)
def test_map_condition(raw: str, expected: ConditionEnum) -> None:
    assert map_condition(raw) == expected


def test_build_search_url_encodes_query() -> None:
    scraper = Chrono24Scraper(targets=[])
    url = scraper.build_search_url("Rolex", "116500LN")
    assert url == "https://www.chrono24.com/search/index.htm?query=Rolex+116500LN&dosearch=true"


def test_build_search_url_adds_page_for_pagination() -> None:
    scraper = Chrono24Scraper(targets=[])
    assert scraper.build_search_url("Rolex", "116500LN", page=1).endswith("&dosearch=true")
    assert scraper.build_search_url("Rolex", "116500LN", page=3).endswith("&showpage=3")


@pytest.mark.parametrize(
    "html",
    [
        "<html><head><title>Just a moment...</title></head><body></body></html>",
        "<html><body>Please enable JS, powered by DataDome</body></html>",
        "<html><body><div id='cf-challenge'>Checking your browser</div></body></html>",
        "<html><body>Access Denied</body></html>",
    ],
)
def test_is_blocked_detects_challenge_pages(html: str) -> None:
    scraper = Chrono24Scraper(targets=[])
    assert scraper._is_blocked(html) is True


def test_is_blocked_false_on_normal_results() -> None:
    scraper = Chrono24Scraper(targets=[])
    assert scraper._is_blocked(MOCK_HTML) is False


def test_has_next_page_detects_pagination_controls() -> None:
    scraper = Chrono24Scraper(targets=[])
    with_next = "<html><body><a class='pagination-next' href='?showpage=2'>Next</a></body></html>"
    rel_next = "<html><head><link rel='next' href='?showpage=2'></head><body></body></html>"
    disabled = "<html><body><a class='pagination-next disabled'>Next</a></body></html>"
    assert scraper._has_next_page(with_next) is True
    assert scraper._has_next_page(rel_next) is True
    assert scraper._has_next_page(disabled) is False
    assert scraper._has_next_page(MOCK_HTML) is False


def test_extract_price_prefers_data_price_attribute() -> None:
    from bs4 import BeautifulSoup

    scraper = Chrono24Scraper(targets=[])
    card = BeautifulSoup(
        '<div class="article-item-container">'
        '<span class="article-price" data-price="28500">circa € 28.500</span></div>',
        "html.parser",
    ).select_one("div.article-item-container")
    assert scraper._extract_price(card) == 28500.0


def test_parse_handles_alternative_card_selector() -> None:
    """Fallback su <article class='article-item'> quando manca il container classico."""
    html = """
    <html><body>
      <article class="article-item">
        <a href="/rolex/x--id1.htm">link</a>
        <span class="article-price">€ 19.900</span>
        <span class="article-condition">New</span>
      </article>
    </body></html>
    """
    scraper = Chrono24Scraper(targets=[])
    listings = scraper._parse(html, brand="Rolex", reference_number="126710BLRO")
    assert len(listings) == 1
    assert listings[0].price == 19900.0
    assert listings[0].condition is ConditionEnum.NEW
