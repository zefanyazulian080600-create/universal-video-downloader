"""Format analysis, metadata extraction, and resolution mapping.

Parses raw yt-dlp metadata into clean structured objects and produces
Telegram-compatible quality selectors.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.utils.filenames import format_duration, format_file_size


@dataclass
class MediaFormatOption:
    """Represents a selectable download quality or audio stream."""

    format_id: str
    label: str  # e.g., "1080p (Full HD)", "720p (HD)", "480p (SD)", "Audio MP3"
    resolution_label: str  # e.g., "1080p", "720p", "480p", "360p", "audio"
    ext: str  # e.g., "mp4", "m4a", "mp3"
    filesize: Optional[int] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    is_audio_only: bool = False
    yt_dlp_format_spec: str = "best"

    @property
    def formatted_size(self) -> str:
        return format_file_size(self.filesize)


@dataclass
class MediaMetadata:
    """Normalized media information extracted from source URL."""

    url: str
    title: str
    uploader: str
    platform: str
    duration: int
    thumbnail_url: Optional[str] = None
    webpage_url: Optional[str] = None
    description: Optional[str] = None
    formats: List[MediaFormatOption] = field(default_factory=list)
    best_format: Optional[MediaFormatOption] = None
    audio_format: Optional[MediaFormatOption] = None

    @property
    def formatted_duration(self) -> str:
        return format_duration(self.duration)

    def get_summary_card(self) -> str:
        """Format an elegant metadata summary in natural Indonesian."""
        lines = [
            "🎬 <b>Informasi Media</b>",
            "",
            f"<b>Judul:</b> {self.title}",
            f"<b>Platform:</b> {self.platform}",
            f"<b>Kanal/Pembuat:</b> {self.uploader}",
            f"<b>Durasi:</b> {self.formatted_duration}",
        ]

        if self.best_format and self.best_format.filesize:
            lines.append(f"<b>Estimasi Ukuran:</b> {self.best_format.formatted_size}")

        lines.append("")
        lines.append("Pilih opsi pengunduhan di bawah ini:")
        return "\n".join(lines)


def parse_yt_dlp_info(info: Dict[str, Any], original_url: str, platform_name: str) -> MediaMetadata:
    """Transform raw yt-dlp dictionary into structured MediaMetadata."""
    title = info.get("title") or "Video Tanpa Judul"
    uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "Tidak diketahui"
    duration = int(info.get("duration") or 0)
    thumbnail = info.get("thumbnail") or None
    webpage_url = info.get("webpage_url") or original_url

    raw_formats = info.get("formats") or []

    # Map of height -> best format info
    standard_heights = [1080, 720, 480, 360]
    height_buckets: Dict[int, Dict[str, Any]] = {}
    best_audio_entry: Optional[Dict[str, Any]] = None

    for f in raw_formats:
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        height = f.get("height")
        filesize = f.get("filesize") or f.get("filesize_approx")

        # Audio-only stream
        if vcodec == "none" and acodec != "none":
            if not best_audio_entry or (filesize and filesize > (best_audio_entry.get("filesize") or 0)):
                best_audio_entry = f
            continue

        # Video stream
        if height:
            # Match closest standard resolution bucket
            for target_h in standard_heights:
                if height >= target_h and (target_h not in height_buckets or height == target_h):
                    height_buckets[target_h] = f
                    break
            if height < 360 and 360 not in height_buckets:
                height_buckets[360] = f

    # Build selectable format options
    options: List[MediaFormatOption] = []

    # 1. Best overall video (Default)
    best_size = info.get("filesize") or info.get("filesize_approx")
    best_option = MediaFormatOption(
        format_id="best",
        label="⭐️ Kualitas Terbaik (Auto)",
        resolution_label="best",
        ext="mp4",
        filesize=best_size,
        yt_dlp_format_spec="bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
    )
    options.append(best_option)

    # 2. Individual resolutions if available
    for h in [1080, 720, 480, 360]:
        if h in height_buckets:
            f = height_buckets[h]
            f_size = f.get("filesize") or f.get("filesize_approx")
            res_label = f"{h}p"
            label = f"🎬 {res_label}"
            if h >= 1080:
                label = f"🎬 {res_label} (Full HD)"
            elif h >= 720:
                label = f"🎬 {res_label} (HD)"
            elif h <= 480:
                label = f"🎬 {res_label} (SD)"

            spec = f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={h}]+bestaudio/best[height<={h}]"
            options.append(
                MediaFormatOption(
                    format_id=f"res_{h}",
                    label=label,
                    resolution_label=res_label,
                    ext="mp4",
                    filesize=f_size,
                    vcodec=f.get("vcodec"),
                    acodec=f.get("acodec"),
                    is_audio_only=False,
                    yt_dlp_format_spec=spec,
                )
            )

    # 3. Audio only option
    audio_option = MediaFormatOption(
        format_id="audio_best",
        label="🎵 Audio Saja (MP3/M4A)",
        resolution_label="audio",
        ext="mp3",
        filesize=best_audio_entry.get("filesize") or best_audio_entry.get("filesize_approx") if best_audio_entry else None,
        is_audio_only=True,
        yt_dlp_format_spec="bestaudio/best",
    )
    options.append(audio_option)

    return MediaMetadata(
        url=original_url,
        title=title,
        uploader=uploader,
        platform=platform_name,
        duration=duration,
        thumbnail_url=thumbnail,
        webpage_url=webpage_url,
        description=info.get("description"),
        formats=options,
        best_format=best_option,
        audio_format=audio_option,
    )
