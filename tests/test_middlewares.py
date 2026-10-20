"""Tests for Telegram bot middlewares (throttling and rate-limiting)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, User as TgUser

from app.bot.middlewares.throttling import ThrottlingMiddleware


@pytest.mark.asyncio
class TestMiddlewares:
    """Middlewares behavior tests."""

    # 18. Rate limiting works
    async def test_throttling_middleware_rate_limiting(self):
        # Configure middleware with limit of 3 requests per 60 seconds
        middleware = ThrottlingMiddleware(limit=3, window_seconds=60.0)

        dummy_handler = AsyncMock(return_value="OK")

        # Fake Telegram message
        message = MagicMock(spec=Message)
        message.from_user = TgUser(id=777777, is_bot=False, first_name="RateTest")
        message.answer = AsyncMock()

        # Send 3 allowed requests
        for _ in range(3):
            result = await middleware(dummy_handler, message, {})
            assert result == "OK"

        assert dummy_handler.call_count == 3

        # 4th request must be throttled
        throttled_result = await middleware(dummy_handler, message, {})
        assert throttled_result is None
        # Handler must not have been called a 4th time
        assert dummy_handler.call_count == 3
        # Warning message answered to user
        message.answer.assert_called_once()
        assert "terlalu banyak" in message.answer.call_args[0][0].lower()
