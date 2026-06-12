"""Setup di Bot e Dispatcher aiogram v3 e avvio del polling come coroutine."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import router
from app.config import get_settings

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    settings = get_settings()
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def run_polling(bot: Bot) -> None:
    """Avvia il long polling; pensata per girare come task nello stesso event loop."""
    dispatcher = create_dispatcher()
    logger.info("Bot Telegram in polling")
    try:
        await dispatcher.start_polling(bot, handle_signals=False)
    except Exception:
        logger.exception("Polling Telegram terminato con errore")
        raise
