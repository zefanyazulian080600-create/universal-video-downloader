"""FFmpeg and ffprobe wrapper service for media inspection, probing, and transcoding.

Executes subprocesses safely without shell invocation, parses JSON ffprobe data,
and generates thumbnails and compressed media if configured.
"""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.utils.errors import FFmpegNotFoundError, MergeProcessingError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class FFmpegService:
    """Service wrapping ffmpeg and ffprobe utilities."""

    def __init__(self, ffmpeg_bin: Optional[str] = None, ffprobe_bin: Optional[str] = None):
        if ffmpeg_bin is not None:
            self.ffmpeg_path = ffmpeg_bin if ffmpeg_bin.strip() else None
        else:
            self.ffmpeg_path = shutil.which("ffmpeg")

        if ffprobe_bin is not None:
            self.ffprobe_path = ffprobe_bin if ffprobe_bin.strip() else None
        else:
            self.ffprobe_path = shutil.which("ffprobe")

    def is_available(self) -> bool:
        """Check if FFmpeg executable is available on PATH."""
        return bool(self.ffmpeg_path)

    def verify_availability(self) -> None:
        """Raise FFmpegNotFoundError if ffmpeg executable is missing."""
        if not self.ffmpeg_path:
            raise FFmpegNotFoundError("FFmpeg executable was not found on system PATH.")

    async def probe_media(self, file_path: Path) -> Dict[str, Any]:
        """Inspect media file streams, resolution, duration, and codecs via ffprobe or ffmpeg."""
        if not self.ffmpeg_path or not file_path.exists() or file_path.stat().st_size == 0:
            return {}

        if self.ffprobe_path:
            return await self._probe_via_ffprobe(file_path)
        else:
            return await self._probe_via_ffmpeg(file_path)

    async def _probe_via_ffprobe(self, file_path: Path) -> Dict[str, Any]:
        """Inspect using ffprobe JSON output."""
        cmd = [
            str(self.ffprobe_path),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning(
                    f"ffprobe returned non-zero code {proc.returncode}: {stderr.decode('utf-8', errors='replace')}"
                )
                return {}

            data = json.loads(stdout.decode("utf-8", errors="replace"))
            return self._extract_probe_summary(data)
        except Exception as e:
            logger.warning(f"Error probing file {file_path} via ffprobe: {e}")
            return {}

    async def _probe_via_ffmpeg(self, file_path: Path) -> Dict[str, Any]:
        """Fallback inspect using ffmpeg -i stderr output."""
        cmd = [str(self.ffmpeg_path), "-i", str(file_path)]
        summary: Dict[str, Any] = {
            "duration": 0.0,
            "width": 0,
            "height": 0,
            "video_codec": None,
            "audio_codec": None,
            "bitrate": 0,
        }
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            text = stderr.decode("utf-8", errors="replace")

            # Match Duration: 00:01:23.45
            import re
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", text)
            if dur_match:
                h, m, s = dur_match.groups()
                summary["duration"] = int(h) * 3600 + int(m) * 60 + float(s)

            # Match Resolution: 1920x1080
            res_match = re.search(r",\s*(\d{2,5})x(\d{2,5})", text)
            if res_match:
                summary["width"] = int(res_match.group(1))
                summary["height"] = int(res_match.group(2))

            return summary
        except Exception as e:
            logger.warning(f"Error probing file {file_path} via ffmpeg: {e}")
            return summary

    def _extract_probe_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract clean summary from raw ffprobe JSON output."""
        summary: Dict[str, Any] = {
            "duration": 0.0,
            "width": 0,
            "height": 0,
            "video_codec": None,
            "audio_codec": None,
            "bitrate": 0,
        }

        format_info = data.get("format", {})
        try:
            summary["duration"] = float(format_info.get("duration", 0.0))
            summary["bitrate"] = int(format_info.get("bit_rate", 0))
        except (ValueError, TypeError):
            pass

        streams = data.get("streams", [])
        for s in streams:
            codec_type = s.get("codec_type")
            if codec_type == "video" and not summary["video_codec"]:
                summary["video_codec"] = s.get("codec_name")
                summary["width"] = int(s.get("width", 0))
                summary["height"] = int(s.get("height", 0))
            elif codec_type == "audio" and not summary["audio_codec"]:
                summary["audio_codec"] = s.get("codec_name")

        return summary

    async def extract_thumbnail(
        self,
        video_path: Path,
        thumbnail_path: Path,
        timestamp_sec: float = 1.0,
    ) -> bool:
        """Extract a single frame image as JPEG thumbnail."""
        self.verify_availability()
        if not video_path.exists():
            return False

        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.ffmpeg_path),
            "-y",  # Overwrite
            "-ss", str(timestamp_sec),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(thumbnail_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode == 0 and thumbnail_path.exists() and thumbnail_path.stat().st_size > 0
        except Exception as e:
            logger.warning(f"Failed to extract thumbnail: {e}")
            return False

    async def compress_video(
        self,
        input_path: Path,
        output_path: Path,
        target_size_mb: float,
        duration_seconds: float,
    ) -> bool:
        """Compress video using two-pass or single-pass libx264 to fit within target size."""
        self.verify_availability()
        if duration_seconds <= 0:
            duration_seconds = 60.0

        # Calculate target bitrate: total_bits / duration_secs
        # Reserve 128k for audio
        audio_bitrate_k = 128
        target_total_bitrate_k = int((target_size_mb * 8192) / duration_seconds)
        video_bitrate_k = max(200, target_total_bitrate_k - audio_bitrate_k)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.ffmpeg_path),
            "-y",
            "-i", str(input_path),
            "-c:v", "libx264",
            "-b:v", f"{video_bitrate_k}k",
            "-maxrate", f"{int(video_bitrate_k * 1.5)}k",
            "-bufsize", f"{video_bitrate_k * 2}k",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate_k}k",
            "-movflags", "+faststart",
            str(output_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(
                    f"FFmpeg compression failed: {stderr.decode('utf-8', errors='replace')}"
                )
                return False
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as e:
            logger.error(f"Error during video compression: {e}")
            return False
