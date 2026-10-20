"""Asynchronous metadata extraction using yt-dlp.

Runs extraction in a thread pool without blocking the asyncio event loop,
applies strict timeouts, and maps platform errors to typed exceptions.
"""

import asyncio
from typing import Any, Dict, Optional

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError, UnsupportedError

from app.config import settings
from app.downloader.formats import MediaMetadata, parse_yt_dlp_info
from app.downloader.validator import detect_platform, validate_url
from app.utils.errors import (
    ContentUnavailableError,
    ExtractionTimeoutError,
    UnsupportedPlatformError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MetadataExtractor:
    """Extracts media metadata from supported platforms."""

    def __init__(self, timeout_seconds: Optional[int] = None):
        self.timeout = timeout_seconds or settings.metadata_timeout_seconds

    async def extract(self, raw_url: str) -> MediaMetadata:
        """Validate URL and extract media metadata with timeout protection."""
        # 1. Security & SSRF check
        valid_url = validate_url(raw_url, check_dns=True)
        platform_name = detect_platform(valid_url)

        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
            "socket_timeout": self.timeout,
            "no_color": True,
            # Prevent geographic bypass spoofing or unsafe headers
            "geo_bypass": False,
        }

        try:
            info_dict = await asyncio.wait_for(
                asyncio.to_thread(self._extract_sync, valid_url, ydl_opts),
                timeout=float(self.timeout),
            )
        except asyncio.TimeoutError:
            logger.warning(f"Metadata extraction timed out for URL: {valid_url}")
            raise ExtractionTimeoutError()
        except UnsupportedError as e:
            logger.warning(f"Unsupported platform for URL {valid_url}: {e}")
            raise UnsupportedPlatformError()
        except DownloadError as e:
            err_msg = str(e).lower()
            logger.warning(f"DownloadError extracting metadata: {err_msg}")
            if any(term in err_msg for term in ["private", "login", "authenticate", "removed", "deleted", "unavailable", "404"]):
                raise ContentUnavailableError(str(e))
            if "unsupported url" in err_msg:
                raise UnsupportedPlatformError(str(e))
            raise ContentUnavailableError(str(e))
        except ExtractorError as e:
            logger.warning(f"ExtractorError for URL {valid_url}: {e}")
            raise ContentUnavailableError(str(e))
        except Exception as e:
            logger.error(f"Unexpected error extracting metadata from {valid_url}: {e}", exc_info=True)
            raise ContentUnavailableError(f"Gagal memeriksa tautan: {e}")

        if not info_dict:
            raise ContentUnavailableError("Informasi video tidak ditemukan pada tautan tersebut.")

        return parse_yt_dlp_info(info_dict, valid_url, platform_name)

    def _extract_sync(self, url: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous extraction executed in worker thread."""
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
