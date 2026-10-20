"""Middleware ensuring Telegram users are recorded in the database."""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.database.repository import UserRepository
from app.database.session import get_db_session


class UserTrackerMiddleware(BaseMiddleware):
    """Guarantees every active user has a database profile record."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if tg_user and not tg_user.is_bot:
            async with get_db_session() as session:
                user = await UserRepository.get_or_create(
                    session=session,
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                )
                data["db_user"] = user

        return await handler(event, data)
