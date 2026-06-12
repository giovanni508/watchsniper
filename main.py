"""Entrypoint: avvia FastAPI, bot Telegram (polling) e scheduler nello stesso event loop.

    uv run python main.py
"""

import asyncio
import logging

import uvicorn

from app.api.app import create_app
from app.bot.notifier import notifier_loop
from app.bot.runner import create_bot, run_polling
from app.config import get_settings
from app.database import get_session, init_db
from app.logging_config import setup_logging
from app.repositories import ReferenceRepository
from app.scraper.dummy import CATALOG

logger = logging.getLogger("watchsniper")


async def seed_references() -> None:
    """Popola le referenze tracciate al primo avvio (idempotente)."""
    async with get_session() as session:
        references = ReferenceRepository(session)
        if await references.count() > 0:
            return
        for brand, model, reference_number, _ in CATALOG:
            await references.get_or_create(
                brand=brand, model=model, reference_number=reference_number
            )
    logger.info("Seed iniziale: %d referenze tracciate", len(CATALOG))


async def run_api() -> None:
    settings = get_settings()
    config = uvicorn.Config(
        create_app(),
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,  # usa il logging già configurato
    )
    server = uvicorn.Server(config)
    logger.info("API su http://%s:%d", settings.api_host, settings.api_port)
    await server.serve()


async def run_drain_events() -> None:
    """Senza bot configurato, svuota l'event bus loggando i deal trovati."""
    from app.events import event_bus

    while True:
        event = await event_bus.consume()
        deal = event.payload
        logger.info(
            "[no-telegram] Deal per chat %d: %s %s a %.0f€ (margine %.1f%%) — %s",
            deal.chat_id,
            deal.brand,
            deal.reference_number,
            deal.asking_price,
            deal.margin_percentage,
            deal.url,
        )


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Avvio WatchSniper…")

    await init_db()
    await seed_references()

    # Import dopo init_db così un errore di bootstrap emerge subito e chiaro.
    from app.scraper.scheduler import scheduler_loop

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(run_api(), name="api")
            group.create_task(scheduler_loop(), name="scheduler")
            if settings.telegram_enabled:
                bot = create_bot()
                group.create_task(run_polling(bot), name="telegram-polling")
                group.create_task(notifier_loop(bot), name="telegram-notifier")
            else:
                logger.warning(
                    "TELEGRAM_BOT_TOKEN non configurato: bot disabilitato, "
                    "i deal saranno solo loggati e visibili sulla dashboard"
                )
                group.create_task(run_drain_events(), name="event-drain")
    except* Exception as group_errors:
        for exc in group_errors.exceptions:
            logger.exception("Task terminato con errore", exc_info=exc)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arresto richiesto dall'utente, bye 👋")
