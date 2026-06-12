"""Scraper reale per Chrono24.

Chrono24 protegge le pagine con DataDome/Cloudflare, quindi questo scraper
applica tecniche stealth a Playwright: la libreria `playwright-stealth` (se
disponibile) più un'iniezione manuale di script che maschera i segnali di
automazione più comuni (`navigator.webdriver`, plugin, lingue, runtime Chrome).

Nota legale: prima di eseguirlo verifica i Termini di Servizio e il robots.txt
di Chrono24 e rispetta i rate limit. Il default `SCRAPE_INTERVAL_SECONDS` e i
ritardi casuali di `BaseScraper` servono proprio a non sovraccaricare il target.
"""

import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag
from playwright.async_api import BrowserContext

from app.database import get_session
from app.models import ConditionEnum
from app.repositories import ReferenceRepository
from app.schemas import ScrapedListing
from app.scraper.base import BaseScraper

logger = logging.getLogger(__name__)

try:  # potenziamento opzionale: assente non blocca lo scraper
    from playwright_stealth import Stealth

    _STEALTH_AVAILABLE = True
except ImportError:  # pragma: no cover - dipende dall'ambiente
    _STEALTH_AVAILABLE = False


BASE_URL = "https://www.chrono24.com"

# User-Agent Chrome coerente con lo spoofing stealth (che assume un browser Chromium).
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Hardening manuale: nasconde i marker di automazione più controllati da DataDome.
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['it-IT', 'it', 'en-US'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters)
);
"""

# Token usati nei badge per riconoscere scatola e documenti.
_BOX_TOKENS = ("box", "scatola")
_PAPERS_TOKENS = ("papers", "paper", "documenti", "documents", "warranty card")
# Condizioni che indicano un orologio nuovo/mai indossato.
_NEW_TOKENS = ("new", "unworn", "nuovo", "mai indossato")


def parse_price(raw: str) -> float:
    """Converte una stringa prezzo in float, ignorando valuta e separatori.

    Gestisce formato europeo e anglosassone:
      "€ 28.000"     -> 28000.0
      "28,500 USD"   -> 28500.0
      "€ 6.500,00"   -> 6500.0
      "$12,500.00"   -> 12500.0
    Solleva ValueError per stringhe senza cifre (es. "Prezzo su richiesta").
    """
    cleaned = re.sub(r"[^\d.,]", "", raw)
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        raise ValueError(f"prezzo non numerico: {raw!r}")

    # Un separatore finale seguito da 1-2 cifre è decimale; tutto il resto è migliaia.
    decimal_match = re.search(r"[.,](\d{1,2})$", cleaned)
    if decimal_match:
        integer_part = re.sub(r"[.,]", "", cleaned[: decimal_match.start()])
        return float(f"{integer_part or '0'}.{decimal_match.group(1)}")
    return float(re.sub(r"[.,]", "", cleaned))


def map_condition(raw: str) -> ConditionEnum:
    text = raw.strip().lower()
    return ConditionEnum.NEW if any(token in text for token in _NEW_TOKENS) else ConditionEnum.USED


class Chrono24Scraper(BaseScraper):
    name = "chrono24"

    def __init__(self, targets: list[tuple[str, str]] | None = None) -> None:
        """`targets`: lista (brand, reference_number). Se None, vengono letti dal DB."""
        super().__init__()
        self._targets = targets
        self._stealth = Stealth() if _STEALTH_AVAILABLE else None

    # --- Anti-bot --------------------------------------------------------------

    async def _new_context(self) -> BrowserContext:
        """Contesto Chromium-coerente con stealth (libreria + script manuale)."""
        assert self._browser is not None
        context = await self._browser.new_context(
            user_agent=CHROME_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="it-IT",
            extra_http_headers={"Accept-Language": "it-IT,it;q=0.9,en;q=0.8"},
            ignore_https_errors=self._settings.scraper_ignore_https_errors,
        )
        await context.add_init_script(STEALTH_INIT_SCRIPT)
        if self._stealth is not None:
            try:
                await self._stealth.apply_stealth_async(context)
            except Exception:
                logger.exception("[%s] playwright-stealth non applicato", self.name)
        else:
            logger.warning(
                "[%s] playwright-stealth non disponibile: uso solo l'hardening manuale",
                self.name,
            )
        return context

    # --- Targeting -------------------------------------------------------------

    def build_search_url(self, brand: str, reference_number: str) -> str:
        """URL della ricerca Chrono24 per una marca e referenza."""
        query = quote_plus(f"{brand} {reference_number}".strip())
        return f"{BASE_URL}/search/index.htm?query={query}&dosearch=true"

    async def _resolve_targets(self) -> list[tuple[str, str]]:
        if self._targets is not None:
            return self._targets
        async with get_session() as session:
            references = await ReferenceRepository(session).get_all()
            return [(ref.brand, ref.reference_number) for ref in references]

    # --- Scraping --------------------------------------------------------------

    async def scrape(self) -> list[ScrapedListing]:
        targets = await self._resolve_targets()
        results: list[ScrapedListing] = []
        for brand, reference_number in targets:
            url = self.build_search_url(brand, reference_number)
            logger.info("[%s] Ricerca %s %s", self.name, brand, reference_number)
            try:
                html = await self.fetch_html(url, wait_until="domcontentloaded")
            except Exception:
                logger.exception("[%s] Fetch fallito per %s", self.name, url)
                continue
            page_listings = self._parse(html, brand=brand, reference_number=reference_number)
            logger.info(
                "[%s] %s %s: %d annunci estratti",
                self.name,
                brand,
                reference_number,
                len(page_listings),
            )
            results.extend(page_listings)
            await self.rotate_identity()  # nuova identità tra una referenza e l'altra
        return results

    # --- Parsing ---------------------------------------------------------------

    def _parse(self, html: str, *, brand: str, reference_number: str) -> list[ScrapedListing]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.article-item-container")
        listings: list[ScrapedListing] = []
        for card in cards:
            try:
                listing = self._parse_card(card, brand=brand, reference_number=reference_number)
            except Exception:
                # Una card malformata o "Prezzo su richiesta" non interrompe il parsing.
                logger.debug("[%s] Card non parsabile, ignorata", self.name, exc_info=True)
                continue
            if listing is not None:
                listings.append(listing)
        return listings

    def _parse_card(
        self, card: Tag, *, brand: str, reference_number: str
    ) -> ScrapedListing | None:
        anchor = card.select_one("a[href]")
        if anchor is None or not anchor.get("href"):
            return None
        href = str(anchor["href"])
        url = href if href.startswith("http") else f"{BASE_URL}{href}"

        price_node = card.select_one(".article-price, .text-bold strong, [class*=price]")
        if price_node is None:
            return None
        price = parse_price(price_node.get_text(strip=True))

        condition_node = card.select_one(".article-condition, [class*=condition]")
        condition = (
            map_condition(condition_node.get_text(strip=True))
            if condition_node is not None
            else ConditionEnum.USED
        )

        card_text = card.get_text(" ", strip=True).lower()
        has_box = any(token in card_text for token in _BOX_TOKENS)
        has_papers = any(token in card_text for token in _PAPERS_TOKENS)

        title_node = card.select_one(".article-title, .text-bold")
        model = title_node.get_text(strip=True) if title_node is not None else brand

        return ScrapedListing(
            brand=brand,
            reference_number=reference_number,
            model=model,
            price=price,
            url=url,
            condition=condition,
            has_box_papers=has_box and has_papers,
        )
