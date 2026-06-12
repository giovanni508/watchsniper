"""Engine asincrono, session factory e base dichiarativa SQLAlchemy 2.0."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(
    get_settings().database_url,
    echo=False,
    # SQLite: necessario quando più task condividono lo stesso engine.
    connect_args={"check_same_thread": False},
)

session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Context manager con commit/rollback automatico, per scraper/analyzer/bot."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Errore durante la transazione DB, eseguito rollback")
            raise


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Dependency FastAPI."""
    async with get_session() as session:
        yield session


async def init_db() -> None:
    """Crea le tabelle in sviluppo. In produzione usare Alembic (`alembic upgrade head`)."""
    from app import models  # noqa: F401 — registra i modelli sul metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database inizializzato (%s)", get_settings().database_url)
