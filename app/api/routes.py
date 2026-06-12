"""Endpoint REST + dashboard."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.engine import compute_margin
from app.config import get_settings
from app.database import get_db_session
from app.repositories import ListingRepository, ReferenceRepository, UserRepository
from app.schemas import DealOut, FilterIn, FilterOut, ListingOut, ReferenceOut

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/api/deals", response_model=list[DealOut])
async def get_deals(
    session: SessionDep,
    max_price: Annotated[float | None, Query(gt=0)] = None,
    min_margin: Annotated[float | None, Query(ge=0)] = None,
) -> list[DealOut]:
    """Annunci attivi con margine percentuale sopra soglia (default 10%)."""
    settings = get_settings()
    threshold = min_margin if min_margin is not None else settings.deals_min_margin_percentage

    deals: list[DealOut] = []
    for listing in await ListingRepository(session).get_all_active():
        reference = listing.reference
        if reference.estimated_market_value is None:
            continue
        if max_price is not None and listing.price > max_price:
            continue
        margin = compute_margin(
            market_value=reference.estimated_market_value,
            asking_price=listing.price,
            fixed_costs=settings.estimated_fixed_costs,
        )
        if margin.percentage <= threshold:
            continue
        deals.append(
            DealOut(
                listing=ListingOut.model_validate(listing),
                reference=ReferenceOut.model_validate(reference),
                market_value=reference.estimated_market_value,
                margin=margin.absolute,
                margin_percentage=margin.percentage,
            )
        )
    deals.sort(key=lambda deal: deal.margin_percentage, reverse=True)
    return deals


@router.get("/api/references", response_model=list[ReferenceOut])
async def get_references(session: SessionDep) -> list[ReferenceOut]:
    """Referenze tracciate con il loro valore di mercato stimato."""
    references = await ReferenceRepository(session).get_all()
    return [ReferenceOut.model_validate(reference) for reference in references]


@router.post("/api/filters", response_model=FilterOut, status_code=201)
async def set_filters(payload: FilterIn, session: SessionDep) -> FilterOut:
    """Imposta i filtri di un utente dal web (stessa logica dei comandi del bot)."""
    if (
        payload.max_price is None
        and payload.min_margin_percentage is None
        and payload.target_brand is None
    ):
        raise HTTPException(status_code=422, detail="Specificare almeno un criterio di filtro")
    try:
        user_filter = await UserRepository(session).update_filter(
            payload.telegram_chat_id,
            max_price=payload.max_price,
            min_margin_percentage=payload.min_margin_percentage,
            target_brand=payload.target_brand,
        )
        await session.commit()
    except Exception:
        logger.exception("Aggiornamento filtri fallito per chat_id=%d", payload.telegram_chat_id)
        raise HTTPException(status_code=500, detail="Errore interno") from None
    return FilterOut.model_validate(user_filter)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html")
