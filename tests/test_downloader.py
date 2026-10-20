"""Tests for downloader execution, error handling, file verification, and FFmpeg."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.downloader.extractor import MetadataExtractor
from app.downloader.ffmpeg_service import FFmpegService
from app.downloader.service import DownloaderService
from app.utils.errors import (
    DownloadFailedError,
    EmptyOutputFileError,
    ExtractionTimeoutError,
    FFmpegNotFoundError,
    FileTooLargeError,
)


@pytest.mark.asyncio
class TestDownloader:
    """Downloader unit and edge-case testing."""

    # 12. Extractor timeout handled
    async def test_extractor_timeout_handled(self):
        extractor = MetadataExtractor(timeout_seconds=1)
        with patch.object(extractor, "_extract_sync", side_effect=asyncio.TimeoutError()):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                with pytest.raises(ExtractionTimeoutError):
                    await extractor.extract("https://www.youtube.com/watch?v=slowresponse")

    # 13. Downloader failure does not crash
    async def test_downloader_failure_handled(self, tmp_path: Path):
        service = DownloaderService()
        job_dir = tmp_path / "job_fail"

        async def fail_thread(*args, **kwargs):
            raise Exception("Network disconnected")

        with patch("asyncio.to_thread", side_effect=fail_thread):
            with pytest.raises(DownloadFailedError) as exc_info:
                await service.download(
                    job_id="test_fail",
                    url="https://youtube.com/watch?v=error",
                    job_dir=job_dir,
                )
            assert "gagal" in exc_info.value.user_message.lower()

    # 14. Empty output file rejected
    async def test_empty_output_file_rejected(self, tmp_path: Path, mock_ffmpeg):
        service = DownloaderService(ffmpeg_service=mock_ffmpeg)
        job_dir = tmp_path / "job_empty"
        job_dir.mkdir(parents=True, exist_ok=True)

        # Create zero-byte output file
        empty_file = job_dir / "output.mp4"
        empty_file.touch()

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=None):
            with pytest.raises(EmptyOutputFileError):
                await service.download(
                    job_id="test_empty",
                    url="https://youtube.com/watch?v=empty",
                    job_dir=job_dir,
                )

    # 15. File exceeding max size handled
    async def test_file_too_large_handled(self, tmp_path: Path, mock_ffmpeg):
        service = DownloaderService(ffmpeg_service=mock_ffmpeg)
        job_dir = tmp_path / "job_large"
        job_dir.mkdir(parents=True, exist_ok=True)

        large_file = job_dir / "large_video.mp4"
        # Write file larger than max_upload_bytes (mocked via size)
        with open(large_file, "wb") as f:
            f.seek(int(settings.max_upload_bytes + 1024))
            f.write(b"\0")

        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=None):
            with pytest.raises(FileTooLargeError) as exc_info:
                await service.download(
                    job_id="test_large",
                    url="https://youtube.com/watch?v=large",
                    job_dir=job_dir,
                )
            assert exc_info.value.max_upload_mb == settings.max_upload_mb

class TestFFmpeg:
    """FFmpeg availability tests."""

    # 23. FFmpeg not found returns informative error
    def test_ffmpeg_not_found_raises_informative_error(self):
        missing_ffmpeg = FFmpegService(ffmpeg_bin="", ffprobe_bin="")
        assert missing_ffmpeg.is_available() is False
        with pytest.raises(FFmpegNotFoundError) as exc_info:
            missing_ffmpeg.verify_availability()
        assert "ffmpeg" in exc_info.value.user_message.lower()
