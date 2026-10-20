"""Telegram message, media delivery, and UI presentation service.

Handles throttled status updates, sends video/audio/document with metadata,
and catches Telegram API exceptions (flood control, file size limits).
"""

import asyncio
from pathlib import Path
from typing import Optional, Union

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from app.downloader.service import DownloadedMediaResult
from app.utils.errors import TelegramRateLimitError, TelegramUploadError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class TelegramService:
    """Service handling interactions with Telegram Bot API."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def edit_status_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> bool:
        """Edit message text with rate-limiting safety."""
        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return True
        except TelegramRetryAfter as e:
            logger.warning(f"Telegram flood control: retry after {e.retry_after}s for chat {chat_id}")
            return False
        except TelegramBadRequest as e:
            # Usually happens if message content didn't change or message was deleted
            if "message is not modified" not in str(e).lower():
                logger.debug(f"Telegram edit message rejected: {e}")
            return False
        except TelegramAPIError as e:
            logger.warning(f"Failed to edit Telegram status message: {e}")
            return False

    async def send_media_result(
        self,
        chat_id: int,
        media: DownloadedMediaResult,
        status_message_id: Optional[int] = None,
    ) -> Message:
        """Send downloaded video or audio to the user with caption and metadata."""
        caption = f"✅ <b>{media.title}</b>"
        if len(caption) > 1000:
            caption = caption[:995] + "..."

        input_file = FSInputFile(str(media.file_path))
        thumb_file = FSInputFile(str(media.thumbnail_path)) if media.thumbnail_path else None

        try:
            if media.is_audio:
                msg = await self.bot.send_audio(
                    chat_id=chat_id,
                    audio=input_file,
                    caption=caption,
                    title=media.title,
                    duration=int(media.duration),
                    parse_mode="HTML",
                )
            else:
                msg = await self.bot.send_video(
                    chat_id=chat_id,
                    video=input_file,
                    caption=caption,
                    duration=int(media.duration),
                    width=media.width if media.width > 0 else None,
                    height=media.height if media.height > 0 else None,
                    thumbnail=thumb_file,
                    supports_streaming=True,
                    parse_mode="HTML",
                )

            # If status message exists, delete or update it to completed
            if status_message_id:
                try:
                    await self.bot.delete_message(chat_id=chat_id, message_id=status_message_id)
                except Exception:
                    pass

            return msg
        except TelegramRetryAfter as e:
            raise TelegramRateLimitError(retry_after=e.retry_after)
        except TelegramBadRequest as e:
            logger.error(f"TelegramBadRequest when sending media: {e}")
            raise TelegramUploadError(f"Telegram menolak pengiriman file: {e}")
        except TelegramAPIError as e:
            logger.error(f"TelegramAPIError when sending media: {e}")
            raise TelegramUploadError(f"Gagal mengunggah media ke Telegram: {e}")
