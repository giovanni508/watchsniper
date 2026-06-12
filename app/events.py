"""Event bus in-process basato su asyncio.Queue.

Disaccoppia l'analyzer (producer di DealFoundEvent) dal notifier Telegram
(consumer). In un deployment distribuito può essere sostituito da Redis/RabbitMQ
mantenendo la stessa interfaccia publish/subscribe.
"""

import asyncio
import logging
from dataclasses import dataclass

from app.schemas import DealFoundPayload

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DealFoundEvent:
    payload: DealFoundPayload


class EventBus:
    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[DealFoundEvent] = asyncio.Queue(maxsize=maxsize)

    async def publish(self, event: DealFoundEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Meglio perdere un alert che bloccare il ciclo di analisi.
            logger.warning("Event bus pieno: evento scartato (%s)", event.payload.url)

    async def consume(self) -> DealFoundEvent:
        return await self._queue.get()


event_bus = EventBus()
