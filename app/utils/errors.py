"""Custom exception hierarchy for Universal Video Downloader Bot.

All business and technical errors are mapped to user-friendly messages
in natural Indonesian while preserving technical details for logging.
"""

from typing import Optional


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, user_message: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.user_message = (
            user_message
            or "Terjadi kesalahan internal pada sistem. Silakan coba lagi nanti."
        )

    def __str__(self) -> str:
        return self.message


class InvalidURLError(AppError):
    """Raised when the provided string is not a valid HTTP/HTTPS URL."""

    def __init__(
        self,
        message: str = "Invalid URL provided",
        user_message: str = "Tautan yang kamu kirimkan tidak valid. Pastikan format tautan diawali dengan http:// atau https://.",
    ):
        super().__init__(message, user_message)


class SSRFBlockedError(AppError):
    """Raised when URL attempts to access private/loopback/cloud metadata networks."""

    def __init__(
        self,
        message: str = "URL target blocked by SSRF protection",
        user_message: str = "Tautan ditolak demi keamanan server (mengarah ke alamat privat atau terlarang).",
    ):
        super().__init__(message, user_message)


class UnsupportedPlatformError(AppError):
    """Raised when no extractor can handle the URL or platform is unsupported."""

    def __init__(
        self,
        message: str = "Platform not supported by extractor",
        user_message: str = "Maaf, platform atau tautan ini belum didukung. Gunakan tautan publik dari YouTube, TikTok, Instagram, X, Facebook, atau platform didukung lainnya.",
    ):
        super().__init__(message, user_message)


class ContentUnavailableError(AppError):
    """Raised when media is deleted, private, geo-blocked, or requires login."""

    def __init__(
        self,
        message: str = "Media is private, deleted or unavailable",
        user_message: str = "Konten tidak dapat diakses. Video mungkin disetel privat, telah dihapus oleh pemiliknya, atau dibatasi wilayahnya.",
    ):
        super().__init__(message, user_message)


class ExtractionTimeoutError(AppError):
    """Raised when metadata extraction exceeds configured timeout."""

    def __init__(
        self,
        message: str = "Metadata extraction timed out",
        user_message: str = "Waktu pemeriksaan tautan telah habis karena platform merespons terlalu lambat. Silakan coba lagi nanti.",
    ):
        super().__init__(message, user_message)


class FormatNotAvailableError(AppError):
    """Raised when requested format or resolution cannot be extracted."""

    def __init__(
        self,
        message: str = "Requested video format not found",
        user_message: str = "Pilihan kualitas atau format video yang dipilih tidak tersedia untuk video ini.",
    ):
        super().__init__(message, user_message)


class DownloadFailedError(AppError):
    """Raised when media download fails during execution."""

    def __init__(
        self,
        message: str = "Download process failed",
        user_message: str = "Proses pengunduhan gagal. Hal ini dapat disebabkan oleh gangguan jaringan sementara atau pembatasan dari platform sumber.",
    ):
        super().__init__(message, user_message)


class FFmpegNotFoundError(AppError):
    """Raised when FFmpeg or ffprobe executable is not available on PATH."""

    def __init__(
        self,
        message: str = "FFmpeg executable not found on system",
        user_message: str = "Sistem pemrosesan media (FFmpeg) sedang tidak tersedia di server. Hubungi administrator.",
    ):
        super().__init__(message, user_message)


class MergeProcessingError(AppError):
    """Raised when FFmpeg fails to merge separate video and audio streams."""

    def __init__(
        self,
        message: str = "FFmpeg failed to merge audio and video streams",
        user_message: str = "Gagal memproses dan menggabungkan audio-video. Silakan coba kualitas lain.",
    ):
        super().__init__(message, user_message)


class EmptyOutputFileError(AppError):
    """Raised when the downloaded file is missing or zero bytes."""

    def __init__(
        self,
        message: str = "Downloaded output file is empty or non-existent",
        user_message: str = "File hasil unduhan kosong atau rusak. Pengunduhan dibatalkan.",
    ):
        super().__init__(message, user_message)


class FileTooLargeError(AppError):
    """Raised when the resulting media file exceeds Telegram upload limit."""

    def __init__(
        self,
        file_size_mb: float,
        max_upload_mb: float,
        message: Optional[str] = None,
        user_message: Optional[str] = None,
    ):
        msg = message or f"File size {file_size_mb:.1f} MB exceeds upload limit {max_upload_mb:.1f} MB"
        u_msg = (
            user_message
            or f"Ukuran video ({file_size_mb:.1f} MB) melebihi batas pengiriman bot ({max_upload_mb:.1f} MB). Coba pilih opsi kualitas yang lebih rendah atau versi audio saja."
        )
        super().__init__(msg, u_msg)
        self.file_size_mb = file_size_mb
        self.max_upload_mb = max_upload_mb


class TelegramUploadError(AppError):
    """Raised when uploading file to Telegram Bot API fails."""

    def __init__(
        self,
        message: str = "Failed to upload file to Telegram",
        user_message: str = "Gagal mengirimkan video ke Telegram. Silakan coba lagi nanti.",
    ):
        super().__init__(message, user_message)


class TelegramRateLimitError(AppError):
    """Raised when Telegram Bot API responds with 429 Too Many Requests."""

    def __init__(
        self,
        retry_after: int = 5,
        message: str = "Telegram rate limit exceeded",
        user_message: Optional[str] = None,
    ):
        u_msg = (
            user_message
            or f"Terlalu banyak permintaan ke Telegram. Tunggu {retry_after} detik sebelum mencoba kembali."
        )
        super().__init__(message, u_msg)
        self.retry_after = retry_after


class QueueFullError(AppError):
    """Raised when the global job queue capacity is exceeded."""

    def __init__(
        self,
        message: str = "Global job queue is full",
        user_message: str = "Antrean unduhan server sedang penuh. Mohon tunggu sejenak hingga antrean berkurang.",
    ):
        super().__init__(message, user_message)


class UserJobLimitError(AppError):
    """Raised when a user attempts to run more concurrent jobs than allowed."""

    def __init__(
        self,
        max_jobs: int = 2,
        message: str = "User active job limit exceeded",
        user_message: Optional[str] = None,
    ):
        u_msg = (
            user_message
            or f"Kamu masih memiliki {max_jobs} unduhan aktif yang sedang berjalan. Tunggu hingga proses sebelumnya selesai atau gunakan /cancel."
        )
        super().__init__(message, u_msg)
        self.max_jobs = max_jobs


class JobCancelledError(AppError):
    """Raised when a job is cancelled by the user or administrator."""

    def __init__(
        self,
        message: str = "Job was cancelled by user request",
        user_message: str = "Proses unduhan berhasil dibatalkan.",
    ):
        super().__init__(message, user_message)


class DiskSpaceLowError(AppError):
    """Raised when host disk space is too low to safely process downloads."""

    def __init__(
        self,
        message: str = "Server disk space is dangerously low",
        user_message: str = "Kapasitas penyimpanan server sementara tidak mencukupi. Hubungi administrator.",
    ):
        super().__init__(message, user_message)
