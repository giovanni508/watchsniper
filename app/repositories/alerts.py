"""Repository per SentAlert (deduplicazione persistente delle notifiche)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SentAlert


class SentAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_pairs(self) -> set[tuple[int, int]]:
        """Coppie (user_id, listing_id) già notificate."""
        result = await self._session.execute(select(SentAlert.user_id, SentAlert.listing_id))
        return {(row.user_id, row.listing_id) for row in result}

    async def record(self, user_id: int, listing_id: int) -> None:
        self._session.add(SentAlert(user_id=user_id, listing_id=listing_id))
        await self._session.flush()
