"""DTO Pydantic v2 per API, scraper e analyzer."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ConditionEnum, ListingStatusEnum


class ScrapedListing(BaseModel):
    """Risultato grezzo prodotto da uno scraper, prima della persistenza."""

    brand: str
    reference_number: str
    model: str = ""
    price: float = Field(gt=0)
    url: str
    condition: ConditionEnum = ConditionEnum.USED
    has_box_papers: bool = False


class ReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand: str
    model: str
    reference_number: str
    estimated_market_value: float | None
    updated_at: datetime


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    price: float
    condition: ConditionEnum
    has_box_papers: bool
    status: ListingStatusEnum
    discovered_at: datetime


class DealOut(BaseModel):
    """Annuncio attivo arricchito con i dati di margine calcolati dall'analyzer."""

    listing: ListingOut
    reference: ReferenceOut
    market_value: float
    margin: float
    margin_percentage: float


class FilterIn(BaseModel):
    """Body di POST /api/filters — stessa semantica dei comandi del bot."""

    telegram_chat_id: int
    max_price: float | None = Field(default=None, gt=0)
    min_margin_percentage: float | None = Field(default=None, ge=0)
    target_brand: str | None = None


class FilterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    max_price: float | None
    min_margin_percentage: float
    target_brand: str | None


class DealFoundPayload(BaseModel):
    """Dati del deal trasportati da un DealFoundEvent."""

    chat_id: int
    brand: str
    model: str
    reference_number: str
    asking_price: float
    market_value: float
    margin: float
    margin_percentage: float
    url: str
    condition: ConditionEnum
    has_box_papers: bool
