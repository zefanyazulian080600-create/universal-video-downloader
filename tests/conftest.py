"""Pytest fixtures and configuration for Universal Video Downloader Bot."""

import asyncio
import os
import shutil
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import Base
from app.downloader.ffmpeg_service import FFmpegService
from app.downloader.service import DownloaderService
from app.services.telegram_service import TelegramService


@pytest.fixture(scope="session")
def event_loop():
    """Create session-wide event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_temp_dir(tmp_path: Path) -> Path:
    """Provide isolated temporary directory for test jobs."""
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    return downloads_dir


@pytest_asyncio.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async database session for isolated testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def mock_bot() -> MagicMock:
    """Mock aiogram Bot instance."""
    bot = MagicMock()
    bot.edit_message_text = AsyncMock(return_value=True)
    bot.delete_message = AsyncMock(return_value=True)
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=101))
    bot.send_video = AsyncMock(return_value=MagicMock(message_id=102))
    bot.send_audio = AsyncMock(return_value=MagicMock(message_id=103))
    return bot


@pytest.fixture
def mock_ffmpeg() -> MagicMock:
    """Mock FFmpegService."""
    ffmpeg = MagicMock(spec=FFmpegService)
    ffmpeg.is_available.return_value = True
    ffmpeg.ffmpeg_path = "/usr/bin/ffmpeg"
    ffmpeg.ffprobe_path = "/usr/bin/ffprobe"
    ffmpeg.probe_media = AsyncMock(
        return_value={
            "duration": 45.0,
            "width": 1920,
            "height": 1080,
            "video_codec": "h264",
            "audio_codec": "aac",
            "bitrate": 2000000,
        }
    )
    ffmpeg.extract_thumbnail = AsyncMock(return_value=True)
    ffmpeg.compress_video = AsyncMock(return_value=True)
    return ffmpeg
