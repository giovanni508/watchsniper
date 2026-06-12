"""Repository per Listing."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Listing, ListingStatusEnum
from app.schemas import ScrapedListing


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_url(self, url: str) -> Listing | None:
        return await self._session.scalar(select(Listing).where(Listing.url == url))

    async def upsert_from_scrape(self, scraped: ScrapedListing, reference_id: int) -> Listing:
        """Crea il listing se nuovo, altrimenti ne aggiorna il prezzo."""
        existing = await self.get_by_url(scraped.url)
        if existing is not None:
            existing.price = scraped.price
            await self._session.flush()
            return existing
        listing = Listing(
            reference_id=reference_id,
            url=scraped.url,
            price=scraped.price,
            condition=scraped.condition,
            has_box_papers=scraped.has_box_papers,
            status=ListingStatusEnum.ACTIVE,
        )
        self._session.add(listing)
        await self._session.flush()
        return listing

    async def get_active_for_reference(self, reference_id: int) -> list[Listing]:
        result = await self._session.scalars(
            select(Listing).where(
                Listing.reference_id == reference_id,
                Listing.status == ListingStatusEnum.ACTIVE,
            )
        )
        return list(result)

    async def get_all_active(self) -> list[Listing]:
        result = await self._session.scalars(
            select(Listing)
            .where(Listing.status == ListingStatusEnum.ACTIVE)
            .options(selectinload(Listing.reference))
        )
        return list(result)

    async def mark_sold(self, listing: Listing) -> None:
        listing.status = ListingStatusEnum.SOLD
        await self._session.flush()
