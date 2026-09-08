import pytest

from app.core.exceptions import FFmpegRequiredError, QualityNotAvailableError
from app.core.formatters import pretty_duration, pretty_size
from app.services.quality import build_qualities, build_ydl_plan, parse_quality_id
from tests.fakes import FAKE_VIDEO_INFO


def test_pretty_duration_and_size():
    assert pretty_duration(213) == "3:33"
    assert pretty_duration(3661) == "1:01:01"
    assert pretty_size(1536) == "1.5 KB"
    assert pretty_size(12_000_000) == "11.4 MB"


def test_parse_quality_id():
    video = parse_quality_id("video:720")
    assert video.kind == "video" and video.height == 720
    audio = parse_quality_id("audio:mp3:192")
    assert audio.codec == "mp3" and audio.abr == 192
    original = parse_quality_id("audio:best")
    assert original.codec == "original"
    with pytest.raises(QualityNotAvailableError):
        parse_quality_id("hdr:99")


def test_video_qualities_without_ffmpeg_only_progressive():
    video, audio = build_qualities(FAKE_VIDEO_INFO["formats"], ffmpeg=False, duration=213)
    ids = [item.id for item in video]
    assert ids == ["video:360"]
    assert "audio:best" in [item.id for item in audio]
    assert not any(item.id.startswith("audio:mp3") for item in audio)


def test_video_qualities_with_ffmpeg_include_dash_and_mp3():
    video, audio = build_qualities(FAKE_VIDEO_INFO["formats"], ffmpeg=True, duration=213)
    ids = [item.id for item in video]
    assert ids == ["video:1080", "video:720", "video:360"]
    assert video[0].label == "1080p Full HD"
    assert video[0].recommended is True
    assert video[1].label == "720p HD"
    assert {item.id for item in audio} >= {"audio:best", "audio:mp3:128", "audio:mp3:192", "audio:mp3:320"}
    mp3 = next(item for item in audio if item.id == "audio:mp3:192")
    assert mp3.filesize_bytes == int(213 * 192 * 1000 / 8)


def test_sixty_fps_is_separate_option():
    formats = list(FAKE_VIDEO_INFO["formats"]) + [
        {
            "format_id": "299",
            "ext": "mp4",
            "height": 1080,
            "width": 1920,
            "fps": 60,
            "vcodec": "avc1.64002a",
            "acodec": "none",
            "filesize": 90_000_000,
            "tbr": 4500,
        }
    ]
    video, _ = build_qualities(formats, ffmpeg=True)
    ids = [item.id for item in video]
    assert "video:1080:60" in ids
    assert "video:1080:30" in ids
    sixty = next(item for item in video if item.id == "video:1080:60")
    assert "60fps" in sixty.label


def test_ydl_plan_mp3_requires_ffmpeg():
    selector, post, merge = build_ydl_plan("video:720", ffmpeg=True)
    assert "height=720" in selector
    assert "vcodec^=avc1" in selector
    assert merge == "mp4"
    hi_fps, _, _ = build_ydl_plan("video:1080:60", ffmpeg=True)
    assert "fps>=50" in hi_fps
    with pytest.raises(FFmpegRequiredError):
        build_ydl_plan("audio:mp3:192", ffmpeg=False)
    selector, post, _ = build_ydl_plan("audio:mp3:192", ffmpeg=True)
    assert post and post[0]["preferredcodec"] == "mp3"
