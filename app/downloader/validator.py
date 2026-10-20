"""URL validation, SSRF protection, platform detection, and URL extraction.

Ensures strict security:
- Only HTTP/HTTPS schemes permitted.
- Rejects localhost, loopback, private networks (RFC 1918), link-local, cloud metadata.
- Resolves hostnames against DNS to block DNS rebinding and internal IP bypasses.
- Sanitizes query strings to remove sensitive tokens before storage/logging.
- Extracts URLs from arbitrary chat messages safely without executing shell code.
"""

import ipaddress
import re
import socket
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from typing import Optional, Tuple

from app.utils.errors import InvalidURLError, SSRFBlockedError


# Regex to extract HTTP/HTTPS URLs from conversational text
URL_REGEX = re.compile(
    r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
)

# Known platform patterns
PLATFORM_PATTERNS = [
    (re.compile(r"(?:youtube\.com|youtu\.be)", re.I), "YouTube"),
    (re.compile(r"(?:tiktok\.com|douyin\.com)", re.I), "TikTok"),
    (re.compile(r"(?:instagram\.com|instagr\.am)", re.I), "Instagram"),
    (re.compile(r"(?:facebook\.com|fb\.watch|fb\.com)", re.I), "Facebook"),
    (re.compile(r"(?:twitter\.com|x\.com)", re.I), "X (Twitter)"),
    (re.compile(r"vimeo\.com", re.I), "Vimeo"),
    (re.compile(r"reddit\.com|redd\.it", re.I), "Reddit"),
    (re.compile(r"pinterest\.(?:com|[a-z]{2})|pin\.it", re.I), "Pinterest"),
    (re.compile(r"threads\.net", re.I), "Threads"),
    (re.compile(r"dailymotion\.com|dai\.ly", re.I), "Dailymotion"),
    (re.compile(r"twitch\.tv", re.I), "Twitch"),
    (re.compile(r"soundcloud\.com", re.I), "SoundCloud"),
]

# Sensitive query params to strip from stored/logged URLs
SENSITIVE_QUERY_PARAMS = {
    "access_token",
    "token",
    "auth",
    "key",
    "api_key",
    "password",
    "secret",
    "sig",
    "signature",
    "session",
    "session_id",
}


def extract_url_from_text(text: str) -> Optional[str]:
    """Safely extract the first valid web URL from arbitrary message text.

    Returns normalized URL with http/https scheme or None.
    """
    if not text or not text.strip():
        return None

    match = URL_REGEX.search(text.strip())
    if not match:
        return None

    extracted = match.group(0).strip()

    # Prepend https:// if starts with www. or domain without scheme
    if not extracted.startswith(("http://", "https://")):
        extracted = f"https://{extracted}"

    return extracted


def is_ip_literal(host: str) -> bool:
    """Check if string is a valid IPv4 or IPv6 address literal."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def is_private_ip(ip_str: str) -> bool:
    """Check if given IP address is private, loopback, link-local, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            # Explicitly block AWS/GCP/Azure link-local metadata IP
            or ip == ipaddress.ip_address("169.254.169.254")
        )
    except ValueError:
        return False


def validate_url(url: str, check_dns: bool = True) -> str:
    """Validate URL format, scheme, host, length, and SSRF restrictions.

    Raises:
        InvalidURLError: If scheme is forbidden, host is missing, or malformed.
        SSRFBlockedError: If host resolves to localhost/private/reserved IP.

    Returns:
        The validated URL string.
    """
    if not url or len(url) > 2048:
        raise InvalidURLError("URL is missing or exceeds 2048 characters.")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InvalidURLError(f"Malformed URL syntax: {e}")

    # 1. Scheme check: Strictly http and https only
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise InvalidURLError(
            f"Scheme '{scheme}' is forbidden. Only HTTP and HTTPS are permitted."
        )

    # 2. Hostname check
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise InvalidURLError("URL hostname is missing or empty.")

    # 3. Direct localhost / loopback rejection
    if hostname in ("localhost", "localhost.localdomain", "127.0.0.1", "::1", "0.0.0.0"):
        raise SSRFBlockedError(f"Target host '{hostname}' is blocked (localhost).")

    # 4. Check if hostname is direct IP literal
    if is_ip_literal(hostname) and is_private_ip(hostname):
        raise SSRFBlockedError(
            f"Target IP '{hostname}' belongs to a private or restricted network."
        )

    # 5. DNS Resolution SSRF check (if enabled)
    if check_dns:
        try:
            # Resolve all IPv4 and IPv6 addresses for hostname
            addr_info = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if scheme == "https" else 80),
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
            )
            for family, _, _, _, sockaddr in addr_info:
                ip_addr = sockaddr[0]
                if is_private_ip(ip_addr):
                    raise SSRFBlockedError(
                        f"Resolved IP '{ip_addr}' for host '{hostname}' is a restricted address."
                    )
        except socket.gaierror:
            # Host name could not be resolved - allow yt-dlp to handle connection or report
            pass

    return url


def detect_platform(url: str) -> str:
    """Identify platform brand name based on URL domain or return 'Direct / Lainnya'."""
    try:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        full_check = f"{netloc}{path}"

        for pattern, name in PLATFORM_PATTERNS:
            if pattern.search(full_check):
                return name

        # Check if direct media file
        if path.endswith((".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv", ".m4v")):
            return "Direct Video File"
        if path.endswith((".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aac")):
            return "Direct Audio File"

        return "Web / Platform Eksternal"
    except Exception:
        return "Web / Platform Eksternal"


def sanitize_url_for_storage(url: str) -> str:
    """Remove sensitive auth/token query parameters for safe database storage and logging."""
    try:
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query, keep_blank_values=True)
        sanitized_query = {
            k: ["[REDACTED]"] if k.lower() in SENSITIVE_QUERY_PARAMS else v
            for k, v in query_dict.items()
        }
        clean_query = urlencode(sanitized_query, doseq=True)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                clean_query,
                parsed.fragment,
            )
        )
    except Exception:
        return url
