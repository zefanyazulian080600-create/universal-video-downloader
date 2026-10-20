"""Utilities for safe filename handling, formatting, and path sanitization.

Prevents path traversal, cleans illegal filesystem characters, and formats
units (duration, size) for clean Telegram display.
"""

import re
import unicodedata
from pathlib import Path


# Windows and POSIX illegal characters: <>:"/\\|?* and control characters
ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def sanitize_filename(
    raw_name: str,
    max_length: int = 120,
    default_name: str = "video",
    fallback_ext: str = ".mp4",
) -> str:
    """Sanitize arbitrary string into safe, valid cross-platform filename.

    - Normalizes unicode characters
    - Strips path traversal sequences (../, ..\\)
    - Replaces forbidden characters (<>:"/\\|?*)
    - Protects against Windows reserved device names (CON, NUL, etc.)
    - Preserves file extension cleanly
    - Enforces max length limits
    """
    if not raw_name or not raw_name.strip():
        return f"{default_name}{fallback_ext}"

    # Split stem and extension if present
    path_obj = Path(raw_name)
    ext = path_obj.suffix.lower()
    stem = path_obj.stem

    if not ext:
        ext = fallback_ext

    # Normalize unicode to NFKD
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")

    # Remove illegal chars
    stem = ILLEGAL_FILENAME_CHARS.sub("_", stem)

    # Remove repeated underscores/spaces and strip leading/trailing dots/spaces
    stem = re.sub(r"[\s_]+", "_", stem).strip(". _")

    if not stem:
        stem = default_name

    # Check for Windows reserved device names
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"{stem}_file"

    # Truncate stem if too long
    available_stem_len = max(10, max_length - len(ext))
    if len(stem) > available_stem_len:
        stem = stem[:available_stem_len].rstrip(". _")

    # Clean extension
    ext = ILLEGAL_FILENAME_CHARS.sub("", ext)
    if not ext.startswith("."):
        ext = f".{ext}"

    return f"{stem}{ext}"


def format_duration(seconds: int | float | None) -> str:
    """Format duration in seconds to standard HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return "--:--"

    total_secs = int(seconds)
    hours = total_secs // 3600
    minutes = (total_secs % 3600) // 60
    secs = total_secs % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_file_size(size_bytes: int | float | None) -> str:
    """Format byte size to human readable string (KB, MB, GB)."""
    if size_bytes is None or size_bytes < 0:
        return "Tidak diketahui"

    bytes_val = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024.0 or unit == "TB":
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} GB"
