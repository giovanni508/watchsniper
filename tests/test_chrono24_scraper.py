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
