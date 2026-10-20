"""Tests for bot handlers, inline keyboards, and Telegram upload error handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, User as TgUser

from app.bot.handlers import download, settings as bot_settings, start
from app.downloader.service import DownloadedMediaResult
from app.services.telegram_service import TelegramService
from app.utils.errors import TelegramUploadError


@pytest.mark.asyncio
class TestHandlersAndCallbacks:
    """Test callback query handling and Telegram API service."""

    # 20. Callback keyboard queries are correctly answered
    async def test_navigation_callbacks_answered(self):
        # 1. nav_help
        callback = MagicMock(spec=CallbackQuery)
        callback.data = "nav_help"
        callback.answer = AsyncMock()
        callback.message = MagicMock(spec=Message)
        callback.message.answer = AsyncMock()

        await start.callback_nav_help(callback)
        callback.answer.assert_called_once()
        callback.message.answer.assert_called_once()

        # 2. nav_platforms
        callback_plat = MagicMock(spec=CallbackQuery)
        callback_plat.data = "nav_platforms"
        callback_plat.answer = AsyncMock()
        callback_plat.message = MagicMock(spec=Message)
        callback_plat.message.answer = AsyncMock()

        await start.callback_nav_platforms(callback_plat)
        callback_plat.answer.assert_called_once()
        callback_plat.message.answer.assert_called_once()

        # 3. dl_cancel callback
        callback_cancel = MagicMock(spec=CallbackQuery)
        callback_cancel.data = "dl_cancel:dummy-uuid"
        callback_cancel.answer = AsyncMock()
        callback_cancel.message = MagicMock(spec=Message)
        callback_cancel.message.edit_text = AsyncMock()

        download.pending_inspections["dummy-uuid"] = {"user_id": 123}
        await download.callback_cancel_inspection(callback_cancel)
        callback_cancel.answer.assert_called_once_with("Unduhan dibatalkan.")
        assert "dummy-uuid" not in download.pending_inspections

    # 22. Telegram upload failure is caught and handled
    async def test_telegram_upload_failure_handled(self, tmp_path, mock_bot):
        telegram_service = TelegramService(mock_bot)

        # Create dummy file
        media_file = tmp_path / "test.mp4"
        media_file.write_bytes(b"content")

        result = DownloadedMediaResult(
            file_path=media_file,
            file_size_bytes=len(b"content"),
            duration=10.0,
            width=1280,
            height=720,
            is_audio=False,
            title="Test Video",
        )

        # Simulate Telegram API error (e.g. file too big for Bot API or connection dropped)
        mock_bot.send_video.side_effect = TelegramBadRequest(
            method="sendVideo",
            message="Request Entity Too Large",
        )

        with pytest.raises(TelegramUploadError) as exc_info:
            await telegram_service.send_media_result(chat_id=12345, media=result)

        assert "telegram" in exc_info.value.user_message.lower()
