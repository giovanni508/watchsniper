"""Consumer dell'event bus: trasforma i DealFoundEvent in messaggi Telegram HTML."""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from app.events import event_bus
from app.models import ConditionEnum
from app.schemas import DealFoundPayload

logger = logging.getLogger(__name__)


def format_deal_message(deal: DealFoundPayload) -> str:
    condition = "Nuovo" if deal.condition is ConditionEnum.NEW else "Usato"
    box_papers = "✅" if deal.has_box_papers else "❌"
    return (
        "🎯 <b>AFFARE TROVATO!</b>\n\n"
        f"⌚ <b>{deal.brand} {deal.model}</b>\n"
        f"🔖 Referenza: <code>{deal.reference_number}</code>\n"
        f"📦 {condition} — Box &amp; Papers: {box_papers}\n\n"
        f"💰 Prezzo richiesto: <b>{deal.asking_price:,.0f}€</b>\n"
        f"📊 Valore di mercato: <b>{deal.market_value:,.0f}€</b>\n"
        f"📈 Margine stimato: <b>{deal.margin:,.0f}€ ({deal.margin_percentage:.1f}%)</b>\n\n"
        f'🔗 <a href="{deal.url}">Vai all\'annuncio</a>'
    )


async def notifier_loop(bot: Bot) -> None:
    """Consuma l'event bus per sempre e invia le notifiche."""
    logger.info("Notifier Telegram avviato")
    while True:
        event = await event_bus.consume()
        deal = event.payload
        try:
            await bot.send_message(
                chat_id=deal.chat_id,
                text=format_deal_message(deal),
                disable_web_page_preview=True,
            )
            logger.info("Alert inviato a chat %d per %s", deal.chat_id, deal.reference_number)
        except TelegramRetryAfter as exc:
            # Flood control: aspetta e reinserisce l'evento in coda.
            logger.warning("Rate limit Telegram, attendo %ds", exc.retry_after)
            await asyncio.sleep(exc.retry_after)
            await event_bus.publish(event)
        except TelegramAPIError:
            logger.exception("Invio alert fallito per chat %d", deal.chat_id)
        except Exception:
            logger.exception("Errore inatteso nel notifier")
