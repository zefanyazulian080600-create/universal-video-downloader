"""Progress tracking and throttling for media downloads.

Captures yt-dlp progress hooks, calculates download speed and ETA,
enforces message update rate-limiting, and supports graceful cancellation.
"""

import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, Optional

from app.utils.errors import JobCancelledError
from app.utils.filenames import format_duration, format_file_size


@dataclass
class ProgressState:
    """Current snapshot of a download operation."""

    status: str  # 'downloading', 'processing', 'finished', 'error'
    percentage: float  # 0.0 to 100.0
    downloaded_bytes: int
    total_bytes: Optional[int]
    speed_bytes_sec: Optional[float]
    eta_seconds: Optional[int]
    filename: Optional[str] = None

    @property
    def formatted_speed(self) -> str:
        if not self.speed_bytes_sec or self.speed_bytes_sec <= 0:
            return "-- KB/s"
        return f"{format_file_size(self.speed_bytes_sec)}/s"

    @property
    def formatted_progress(self) -> str:
        down = format_file_size(self.downloaded_bytes)
        tot = format_file_size(self.total_bytes) if self.total_bytes else "?"
        return f"{down} / {tot}"

    @property
    def formatted_eta(self) -> str:
        return format_duration(self.eta_seconds)

    def render_telegram_progress_bar(self, bar_length: int = 10) -> str:
        """Render a clean Unicode progress bar."""
        if self.percentage <= 0.0:
            filled = 0
        else:
            filled = min(bar_length, int((self.percentage / 100.0) * bar_length))
        empty = bar_length - filled
        return f"[{'■' * filled}{'□' * empty}] {self.percentage:.1f}%"


class DownloadProgressTracker:
    """Thread-safe progress tracker with cancellation check and rate-limiting."""

    def __init__(
        self,
        min_update_interval: float = 2.5,
        async_callback: Optional[Callable[[ProgressState], Coroutine[Any, Any, None]]] = None,
    ):
        self.min_update_interval = min_update_interval
        self.async_callback = async_callback
        self.last_update_time: float = 0.0
        self.is_cancelled: bool = False
        self.current_state = ProgressState(
            status="starting",
            percentage=0.0,
            downloaded_bytes=0,
            total_bytes=None,
            speed_bytes_sec=None,
            eta_seconds=None,
        )

    def cancel(self) -> None:
        """Mark this download job as cancelled."""
        self.is_cancelled = True

    def yt_dlp_hook(self, d: Dict[str, Any]) -> None:
        """Synchronous hook invoked by yt-dlp in download worker thread."""
        if self.is_cancelled:
            # Raising an exception in the hook aborts yt-dlp download immediately
            raise JobCancelledError("Unduhan dibatalkan oleh pengguna.")

        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            speed = d.get("speed")
            eta = d.get("eta")

            percent = 0.0
            if total and total > 0:
                percent = min(100.0, (downloaded / total) * 100.0)

            self.current_state = ProgressState(
                status="downloading",
                percentage=percent,
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed_bytes_sec=speed,
                eta_seconds=eta,
                filename=d.get("filename"),
            )
        elif status == "finished":
            self.current_state.status = "processing"
            self.current_state.percentage = 100.0
            self.current_state.filename = d.get("filename")
