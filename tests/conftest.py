"""Fixture condivise: DB SQLite temporaneo isolato e schema pulito per ogni test.

La variabile d'ambiente DATABASE_URL viene impostata PRIMA di importare `app.*`,
perché engine e settings sono creati a import time.
"""

import asyncio
import os
import tempfile

_db_fd, _db_path = tempfile.mkstemp(prefix="watchsniper_test_", suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_path}"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["ESTIMATED_FIXED_COSTS"] = "300.0"

import pytest  # noqa: E402

from app import models  # noqa: E402, F401 — registra i modelli sul metadata
from app.database import Base, engine  # noqa: E402
from app.events import event_bus  # noqa: E402


def _drain_event_bus() -> list:
    events = []
    while True:
        try:
            events.append(event_bus._queue.get_nowait())
        except asyncio.QueueEmpty:
            return events


@pytest.fixture(autouse=True)
async def clean_db():
    """Schema vuoto e event bus svuotato per ogni test; dispose dell'engine a fine test
    per non riusare connessioni legate a un event loop precedente."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    _drain_event_bus()
    yield
    await engine.dispose()


@pytest.fixture
def drain_events():
    return _drain_event_bus
