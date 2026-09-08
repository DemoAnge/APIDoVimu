from app.services.normalize import normalize_media, normalize_search
from tests.fakes import FAKE_PLAYLIST_INFO, FAKE_SEARCH_INFO, FAKE_VIDEO_INFO


def test_normalize_video():
    result = normalize_media(FAKE_VIDEO_INFO, ffmpeg_available=True)
    assert result.media_id == "dQw4w9WgXcQ"
    assert result.source == "youtube"
    assert result.duration_label == "3:33"
    assert result.is_playlist is False
    assert len(result.video) == 3
    assert result.thumbnail.endswith("hqdefault.jpg")


def test_normalize_playlist():
    result = normalize_media(FAKE_PLAYLIST_INFO, ffmpeg_available=True)
    assert result.is_playlist is True
    assert len(result.entries) == 2
    assert result.entries[0].title == "Tema 1"
    assert result.video == []


def test_normalize_search():
    results = normalize_search(FAKE_SEARCH_INFO, "rick")
    assert results[0].media_id == "dQw4w9WgXcQ"
    assert results[0].url.startswith("https://")
