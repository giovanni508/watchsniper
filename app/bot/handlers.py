"""Handler dei comandi del bot (aiogram v3 Router)."""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.database import get_session
from app.repositories import UserRepository

logger = logging.getLogger(__name__)

router = Router(name="watchsniper")

HELP_TEXT = (
    "<b>⌚ WatchSniper</b>\n\n"
    "Ti avviso quando trovo orologi sotto il prezzo di mercato.\n\n"
    "<b>Comandi:</b>\n"
    "/start — registrati per ricevere gli alert\n"
    "/filtra prezzo &lt;max&gt; — es. <code>/filtra prezzo 15000</code>\n"
    "/filtra margine &lt;min %&gt; — es. <code>/filtra margine 12</code>"
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user is None:
        return
    try:
        async with get_session() as session:
            await UserRepository(session).register(message.chat.id)
        await message.answer(
            f"✅ Registrato! Riceverai gli alert sui deal.\n\n{HELP_TEXT}"
        )
        logger.info("Utente registrato: chat_id=%d", message.chat.id)
    except Exception:
        logger.exception("Registrazione fallita per chat_id=%d", message.chat.id)
        await message.answer("⚠️ Errore durante la registrazione, riprova più tardi.")


@router.message(Command("filtra"))
async def cmd_filtra(message: Message, command: CommandObject) -> None:
    """`/filtra prezzo <max>` oppure `/filtra margine <min>`."""
    usage = (
        "Uso:\n<code>/filtra prezzo 15000</code>\n<code>/filtra margine 12</code>"
    )
    args = (command.args or "").split()
    if len(args) != 2:
        await message.answer(usage)
        return

    kind, raw_value = args[0].lower(), args[1].replace(",", ".")
    try:
        value = float(raw_value)
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer(f"❌ <code>{raw_value}</code> non è un numero valido.\n\n{usage}")
        return

    try:
        async with get_session() as session:
            users = UserRepository(session)
            if kind == "prezzo":
                await users.update_filter(message.chat.id, max_price=value)
                await message.answer(f"✅ Filtro aggiornato: prezzo massimo <b>{value:,.0f}€</b>")
            elif kind == "margine":
                await users.update_filter(message.chat.id, min_margin_percentage=value)
                await message.answer(f"✅ Filtro aggiornato: margine minimo <b>{value:g}%</b>")
            else:
                await message.answer(usage)
                return
        logger.info("Filtro aggiornato per chat_id=%d: %s=%s", message.chat.id, kind, value)
    except Exception:
        logger.exception("Aggiornamento filtro fallito per chat_id=%d", message.chat.id)
        await message.answer("⚠️ Errore durante l'aggiornamento del filtro, riprova più tardi.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
