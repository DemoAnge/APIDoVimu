import pytest

from app.core.exceptions import InvalidUrlError
from app.core.urls import validate_media_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "http://youtu.be/dQw4w9WgXcQ",
        "https://www.tiktok.com/@user/video/123",
        "https://172.15.0.1/video.mp4",
    ],
)
def test_accepts_public_urls(url):
    assert validate_media_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/a.mp3",
        "javascript:alert(1)",
        "http://localhost/secret",
        "http://127.0.0.1/x",
        "https://10.0.0.8/x",
        "http://192.168.1.10/x",
        "http://169.254.1.1/x",
        "http://172.16.0.1/x",
        "http://172.31.255.1/x",
        "not-a-url",
        "",
    ],
)
def test_rejects_unsafe_urls(url):
    with pytest.raises(InvalidUrlError):
        validate_media_url(url)
