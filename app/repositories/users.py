"""Repository per User e UserFilter."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User, UserFilter


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_chat_id(self, telegram_chat_id: int) -> User | None:
        return await self._session.scalar(
            select(User)
            .where(User.telegram_chat_id == telegram_chat_id)
            .options(selectinload(User.filters))
        )

    async def register(self, telegram_chat_id: int) -> User:
        """Registra l'utente (idempotente) e gli assegna un filtro di default."""
        user = await self.get_by_chat_id(telegram_chat_id)
        if user is not None:
            user.is_active = True
            await self._session.flush()
            return user
        user = User(telegram_chat_id=telegram_chat_id, is_active=True)
        user.filters.append(UserFilter(min_margin_percentage=10.0))
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_active_with_filters(self) -> list[User]:
        result = await self._session.scalars(
            select(User).where(User.is_active.is_(True)).options(selectinload(User.filters))
        )
        return list(result)

    async def update_filter(
        self,
        telegram_chat_id: int,
        *,
        max_price: float | None = None,
        min_margin_percentage: float | None = None,
        target_brand: str | None = None,
    ) -> UserFilter:
        """Aggiorna (o crea) il filtro principale dell'utente.

        Logica condivisa tra il comando /filtra del bot e POST /api/filters.
        L'utente viene registrato implicitamente se non esiste.
        """
        user = await self.register(telegram_chat_id)
        user_filter = user.filters[0] if user.filters else None
        if user_filter is None:
            user_filter = UserFilter(user_id=user.id, min_margin_percentage=10.0)
            self._session.add(user_filter)

        if max_price is not None:
            user_filter.max_price = max_price
        if min_margin_percentage is not None:
            user_filter.min_margin_percentage = min_margin_percentage
        if target_brand is not None:
            user_filter.target_brand = target_brand

        await self._session.flush()
        return user_filter
