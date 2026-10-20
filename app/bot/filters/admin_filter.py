"""Telegram filter restricting commands strictly to configured administrators."""

from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.config import settings


class IsAdmin(BaseFilter):
    """Filter that matches only if message sender is the bot owner / admin."""

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return settings.is_admin(message.from_user.id)
