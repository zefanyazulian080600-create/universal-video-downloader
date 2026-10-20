"""Tests for URL validation, SSRF protection, and platform detection."""

import pytest

from app.downloader.validator import (
    detect_platform,
    extract_url_from_text,
    is_private_ip,
    sanitize_url_for_storage,
    validate_url,
)
from app.utils.errors import InvalidURLError, SSRFBlockedError


class TestURLValidation:
    """Test suite for URL security and platform recognition."""

    # 1. Valid YouTube URL recognized
    def test_youtube_url_recognized(self):
        urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtube.com/shorts/3l8_z7pM4f0",
        ]
        for u in urls:
            assert detect_platform(u) == "YouTube"
            assert validate_url(u, check_dns=False) == u

    # 2. Valid TikTok URL recognized
    def test_tiktok_url_recognized(self):
        urls = [
            "https://www.tiktok.com/@user/video/7123456789012345678",
            "https://vt.tiktok.com/ZS2xyz123/",
        ]
        for u in urls:
            assert detect_platform(u) == "TikTok"
            assert validate_url(u, check_dns=False) == u

    # 3. Valid Instagram URL recognized
    def test_instagram_url_recognized(self):
        urls = [
            "https://www.instagram.com/reel/C8xyz123/",
            "https://instagram.com/p/C9abc456/",
        ]
        for u in urls:
            assert detect_platform(u) == "Instagram"
            assert validate_url(u, check_dns=False) == u

    # 4. Valid Facebook URL recognized
    def test_facebook_url_recognized(self):
        urls = [
            "https://www.facebook.com/watch/?v=123456789",
            "https://fb.watch/xyz123/",
        ]
        for u in urls:
            assert detect_platform(u) == "Facebook"
            assert validate_url(u, check_dns=False) == u

    # 5. Malformed URL rejected
    def test_malformed_url_rejected(self):
        invalid_urls = [
            "",
            "not-a-url",
            "http://",
            "https://",
            "://invalid.com",
            "http:///example.com",
        ]
        for u in invalid_urls:
            with pytest.raises(InvalidURLError):
                validate_url(u, check_dns=False)

    # 6. file:// rejected
    def test_file_scheme_rejected(self):
        with pytest.raises(InvalidURLError) as exc_info:
            validate_url("file:///etc/passwd", check_dns=False)
        assert "forbidden" in str(exc_info.value).lower()

        # Also ftp://, gopher://
        with pytest.raises(InvalidURLError):
            validate_url("ftp://example.com/movie.mp4", check_dns=False)

    # 7. Host localhost rejected
    def test_localhost_rejected(self):
        hosts = [
            "http://localhost/video.mp4",
            "http://localhost:8080/test",
            "http://127.0.0.1/video.mp4",
            "http://[::1]/video.mp4",
            "http://0.0.0.0/",
        ]
        for u in hosts:
            with pytest.raises(SSRFBlockedError):
                validate_url(u, check_dns=False)

    # 8. Host with private IP rejected
    def test_private_ip_rejected(self):
        private_ips = [
            "http://10.0.0.1/video.mp4",
            "http://172.16.0.5/test",
            "http://192.168.1.100/media",
            "http://169.254.169.254/latest/meta-data/",  # Cloud metadata
            "http://127.0.0.2/media",
        ]
        for u in private_ips:
            with pytest.raises(SSRFBlockedError):
                validate_url(u, check_dns=False)

    # 9. Private IP detector helper
    def test_private_ip_helper(self):
        assert is_private_ip("127.0.0.1") is True
        assert is_private_ip("10.1.2.3") is True
        assert is_private_ip("192.168.0.1") is True
        assert is_private_ip("169.254.169.254") is True
        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("1.1.1.1") is False

    # 10. URL with special characters does not cause shell injection
    def test_special_characters_handling(self):
        dangerous_url = "https://example.com/video;rm -rf /;$(calc.exe)?param=1&foo=|bash"
        # Should be parsed safely as a URL without throwing uncaught shell exceptions
        sanitized = sanitize_url_for_storage(dangerous_url)
        assert ";rm -rf" in sanitized  # Kept as literal text in path, never executed
        # Query sanitization handles special characters without crashing
        clean = sanitize_url_for_storage("https://example.com/watch?v=123&token=secret123&auth=my_pw")
        assert "token=%5BREDACTED%5D" in clean or "token=[REDACTED]" in clean
        assert "secret123" not in clean

    # 11. Unsupported platform handling
    def test_unsupported_platform_detection(self):
        unknown = "https://random-unknown-site-987.org/article/123"
        assert detect_platform(unknown) == "Web / Platform Eksternal"

    def test_url_extraction_from_conversation(self):
        text = "Tolong downloadkan video ini dong https://www.youtube.com/watch?v=abc1234 terima kasih!"
        extracted = extract_url_from_text(text)
        assert extracted == "https://www.youtube.com/watch?v=abc1234"

        no_scheme = "coba cek tiktok.com/@user/video/123 ini"
        assert extract_url_from_text(no_scheme) == "https://tiktok.com/@user/video/123"

        no_url = "Halo bot apa kabar?"
        assert extract_url_from_text(no_url) is None
