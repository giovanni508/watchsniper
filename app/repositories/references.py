"""Repository per WatchReference."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WatchReference


class ReferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> list[WatchReference]:
        result = await self._session.scalars(select(WatchReference))
        return list(result)

    async def get_by_reference_number(self, reference_number: str) -> WatchReference | None:
        return await self._session.scalar(
            select(WatchReference).where(WatchReference.reference_number == reference_number)
        )

    async def get_or_create(
        self, brand: str, model: str, reference_number: str
    ) -> WatchReference:
        existing = await self.get_by_reference_number(reference_number)
        if existing is not None:
            return existing
        reference = WatchReference(brand=brand, model=model, reference_number=reference_number)
        self._session.add(reference)
        await self._session.flush()
        return reference

    async def update_market_value(self, reference: WatchReference, value: float) -> None:
        reference.estimated_market_value = value
        await self._session.flush()

    async def count(self) -> int:
        result = await self._session.scalars(select(WatchReference.id))
        return len(list(result))
