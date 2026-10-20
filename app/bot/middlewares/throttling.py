"""Rate limiting middleware to prevent spamming and abuse."""

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """In-memory sliding window rate limiter per Telegram user."""

    def __init__(self, limit: int = 10, window_seconds: float = 60.0):
        super().__init__()
        self.limit = limit
        self.window_seconds = window_seconds
        self._user_requests: Dict[int, list[float]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            # Bypass rate limiting for bot owner
            if settings.is_admin(user_id):
                return await handler(event, data)

            now = time.time()
            timestamps = self._user_requests.setdefault(user_id, [])
            # Purge timestamps older than window
            self._user_requests[user_id] = [t for t in timestamps if now - t < self.window_seconds]

            if len(self._user_requests[user_id]) >= self.limit:
                logger.warning(f"User {user_id} exceeded rate limit ({self.limit} req / {self.window_seconds}s)")
                if isinstance(event, Message):
                    await event.answer(
                        "⚠️ <b>Terlalu banyak permintaan.</b>\n"
                        "Mohon tunggu sejenak sebelum mengirim pesan atau perintah lagi.",
                        parse_mode="HTML",
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Terlalu banyak klik. Mohon tunggu beberapa detik.", show_alert=True)
                return None

            self._user_requests[user_id].append(now)

        return await handler(event, data)
