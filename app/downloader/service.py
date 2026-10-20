"""Media downloader service utilizing yt-dlp and FFmpeg.

Executes downloads in worker threads, handles post-processing, verifies
output integrity, validates file sizes, and generates thumbnails.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yt_dlp
from yt_dlp.utils import DownloadError

from app.config import settings
from app.downloader.ffmpeg_service import FFmpegService
from app.downloader.progress import DownloadProgressTracker
from app.utils.errors import (
    ContentUnavailableError,
    DownloadFailedError,
    EmptyOutputFileError,
    FileTooLargeError,
    JobCancelledError,
)
from app.utils.filenames import sanitize_filename
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DownloadedMediaResult:
    """Verified result of a completed media download."""

    file_path: Path
    file_size_bytes: int
    duration: float
    width: int
    height: int
    is_audio: bool
    title: str
    thumbnail_path: Optional[Path] = None

    @property
    def file_size_mb(self) -> float:
        return self.file_size_bytes / (1024.0 * 1024.0)


class DownloaderService:
    """Manages secure media downloading, verification, and post-processing."""

    def __init__(self, ffmpeg_service: Optional[FFmpegService] = None):
        self.ffmpeg = ffmpeg_service or FFmpegService()

    async def download(
        self,
        job_id: str,
        url: str,
        job_dir: Path,
        format_spec: str = "best",
        is_audio: bool = False,
        progress_tracker: Optional[DownloadProgressTracker] = None,
        title: str = "video",
    ) -> DownloadedMediaResult:
        """Download media, verify file integrity, and prepare for delivery."""
        job_dir.mkdir(parents=True, exist_ok=True)

        # Output template in isolated job directory
        output_tmpl = str(job_dir / "%(title).80s_%(id)s.%(ext)s")

        ydl_opts: Dict[str, Any] = {
            "outtmpl": output_tmpl,
            "format": format_spec,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "socket_timeout": 30,
            "max_filesize": settings.max_download_bytes,
            "retries": 3,
            "fragment_retries": 3,
        }

        # If FFmpeg is available and enabled, configure stream merging & audio extraction
        if settings.enable_ffmpeg and self.ffmpeg.is_available():
            if self.ffmpeg.ffmpeg_path:
                ydl_opts["ffmpeg_location"] = str(Path(self.ffmpeg.ffmpeg_path).parent)

            if is_audio:
                ydl_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ]
            else:
                ydl_opts["merge_output_format"] = "mp4"

        # Attach progress tracker hook
        if progress_tracker:
            ydl_opts["progress_hooks"] = [progress_tracker.yt_dlp_hook]

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._execute_yt_dlp_download, url, ydl_opts),
                timeout=float(settings.download_timeout_seconds),
            )
        except JobCancelledError:
            logger.info(f"Job {job_id} was successfully cancelled during download.")
            raise
        except asyncio.TimeoutError:
            logger.warning(f"Download timed out for job {job_id}")
            raise DownloadFailedError(
                "Waktu pengunduhan habis. Server sumber video mungkin terlalu lambat."
            )
        except DownloadError as e:
            err_str = str(e).lower()
            logger.warning(f"yt-dlp DownloadError on job {job_id}: {err_str}")
            if "file is larger than max-filesize" in err_str:
                raise FileTooLargeError(
                    file_size_mb=settings.max_download_mb,
                    max_upload_mb=settings.max_download_mb,
                    message="Source file exceeds maximum download limit.",
                    user_message=f"Ukuran file sumber melebihi batas unduhan server ({settings.max_download_mb:.0f} MB).",
                )
            if any(term in err_str for term in ["private", "404", "unavailable", "removed"]):
                raise ContentUnavailableError(str(e))
            raise DownloadFailedError(f"Gagal mengunduh media: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during download for job {job_id}: {e}", exc_info=True)
            raise DownloadFailedError(f"Terjadi kesalahan saat mengunduh: {e}")

        # Locate completed output file (ignore temporary .part or .ytdl files)
        output_files = [
            f
            for f in job_dir.iterdir()
            if f.is_file() and not f.name.endswith((".part", ".ytdl", ".temp", ".jpg", ".png", ".webp"))
        ]

        if not output_files:
            raise EmptyOutputFileError("File hasil unduhan tidak ditemukan di direktori kerja.")

        # Pick the largest media file
        target_file = max(output_files, key=lambda f: f.stat().st_size)
        file_size = target_file.stat().st_size

        if file_size == 0:
            raise EmptyOutputFileError("File hasil unduhan berukuran 0 byte (kosong).")

        # Media probing via FFmpeg/ffprobe
        probe_data: Dict[str, Any] = {}
        if settings.enable_ffmpeg and self.ffmpeg.is_available():
            probe_data = await self.ffmpeg.probe_media(target_file)

        duration = float(probe_data.get("duration") or 0.0)
        width = int(probe_data.get("width") or 0)
        height = int(probe_data.get("height") or 0)

        # File size validation against Telegram limit
        if file_size > settings.max_upload_bytes:
            file_size_mb = file_size / (1024.0 * 1024.0)
            logger.warning(
                f"File {target_file.name} ({file_size_mb:.1f} MB) exceeds max_upload_mb ({settings.max_upload_mb:.1f} MB)"
            )

            # Try compression if enabled
            if settings.enable_compression and settings.enable_ffmpeg and not is_audio and duration > 0:
                compressed_file = job_dir / f"compressed_{target_file.name}"
                logger.info(f"Attempting compression for {target_file.name} to {settings.max_upload_mb} MB")
                success = await self.ffmpeg.compress_video(
                    target_file,
                    compressed_file,
                    target_size_mb=settings.max_upload_mb * 0.9,
                    duration_seconds=duration,
                )
                if success and compressed_file.stat().st_size <= settings.max_upload_bytes:
                    target_file = compressed_file
                    file_size = target_file.stat().st_size
                else:
                    raise FileTooLargeError(file_size_mb=file_size_mb, max_upload_mb=settings.max_upload_mb)
            else:
                raise FileTooLargeError(file_size_mb=file_size_mb, max_upload_mb=settings.max_upload_mb)

        # Generate thumbnail for video
        thumb_path: Optional[Path] = None
        if not is_audio and settings.enable_ffmpeg and self.ffmpeg.is_available():
            thumb_candidate = job_dir / "thumbnail.jpg"
            thumb_time = min(2.0, duration / 2.0) if duration > 0 else 1.0
            if await self.ffmpeg.extract_thumbnail(target_file, thumb_candidate, timestamp_sec=thumb_time):
                thumb_path = thumb_candidate

        return DownloadedMediaResult(
            file_path=target_file,
            file_size_bytes=file_size,
            duration=duration,
            width=width,
            height=height,
            is_audio=is_audio,
            title=title,
            thumbnail_path=thumb_path,
        )

    def _execute_yt_dlp_download(self, url: str, opts: Dict[str, Any]) -> None:
        """Run yt-dlp in thread pool."""
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
