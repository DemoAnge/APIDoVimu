from app.services.lyrics import enrich_lyrics, lyrics_from_info_fields, vtt_to_lrc
from app.services.tags import collect_tags, pretty_filename, resolve_cover, thumbnail_candidates


def test_collects_artist_album_title_from_youtube_music_fields():
    tags = collect_tags(
        {
            "title": "Never Gonna Give You Up",
            "artist": "Rick Astley",
            "album": "Whenever You Need Somebody",
            "genre": "Pop",
            "upload_date": "19870727",
            "lyrics": "Never gonna give you up",
            "track_number": 1,
            "thumbnail": "https://i.ytimg.com/vi/x/hqdefault.jpg",
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "description": "Official video",
        }
    )
    assert tags.title == "Never Gonna Give You Up"
    assert tags.artist == "Rick Astley"
    assert tags.album == "Whenever You Need Somebody"
    assert tags.year == "1987"
    assert tags.lyrics == "Never gonna give you up"
    assert tags.track == 1
    assert tags.duration_seconds is None
    assert tags.thumbnail_url.endswith("hqdefault.jpg")
    schema = tags.to_schema(embedded=True)
    assert schema.embedded is True
    assert schema.artist == "Rick Astley"


def test_splits_artist_from_title_when_missing():
    tags = collect_tags({"title": "Queen - Bohemian Rhapsody", "uploader": "QueenVEVO"})
    assert tags.artist == "Queen"
    assert tags.title == "Bohemian Rhapsody"


def test_collects_duration_and_size():
    tags = collect_tags({"title": "x", "duration": 213, "width": 1920, "height": 1080})
    assert tags.duration_seconds == 213
    assert tags.width == 1920
    assert tags.height == 1080


def test_uses_uploader_when_no_dash_in_title():
    tags = collect_tags({"title": "Me at the zoo", "uploader": "jawed"})
    assert tags.artist == "jawed"
    assert tags.title == "Me at the zoo"
    assert tags.album is None


def test_humanizes_restricted_filename_and_splits_artist():
    tags = collect_tags({"title": "Jose_Madero_-_Arropame", "uploader": "Jose Madero"})
    assert tags.artist == "Jose Madero"
    assert tags.title == "Arropame"
    assert pretty_filename(tags, ".mp3") == "Jose Madero - Arropame.mp3"


def test_keeps_album_when_present():
    tags = collect_tags(
        {
            "title": "Arrópame",
            "artist": "José Madero",
            "album": "Querido",
        }
    )
    assert tags.album == "Querido"
    assert pretty_filename(tags, "mp3") == "José Madero - Arrópame.mp3"


def test_thumbnail_prefers_jpeg_over_larger_webp():
    urls = thumbnail_candidates(
        {
            "id": "dQw4w9WgXcQ",
            "extractor": "youtube",
            "thumbnails": [
                {"url": "https://i.ytimg.com/vi_webp/dQw4w9WgXcQ/maxresdefault.webp", "width": 1280, "height": 720},
                {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg", "width": 480, "height": 360},
            ],
        }
    )
    assert urls[0].endswith("hqdefault.jpg")


def _mini_jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 400 + b"\xff\xd9"


def test_lyrics_from_description_letra_header():
    text = lyrics_from_info_fields(
        {
            "description": (
                "Video oficial\n\nLetra:\n\n"
                "Si me arropas esta noche\n"
                "no voy a tener frío\n"
                "quédate un momento más\n"
                "querido\n\n"
                "https://spotify.com/album\n"
            )
        }
    )
    assert text is not None
    assert "Si me arropas esta noche" in text
    assert "spotify" not in text.lower()


def test_ignores_description_without_lyrics_header():
    assert lyrics_from_info_fields({"description": "Suscríbete y activa la campana https://x.com"}) is None


def test_vtt_becomes_lrc():
    lrc = vtt_to_lrc(
        "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nNever gonna give you up\n\n"
        "00:00:04.000 --> 00:00:08.000\nNever gonna let you down\n"
    )
    assert lrc is not None
    assert "[00:01.00]Never gonna give you up" in lrc
    assert "[00:04.00]Never gonna let you down" in lrc


def test_enrich_lyrics_reads_sidecar_vtt(tmp_path):
    (tmp_path / "tema.es.vtt").write_text(
        "WEBVTT\n\n00:00:02.500 --> 00:00:05.000\nArrópame\n\n00:00:05.000 --> 00:00:08.000\nesta noche\n",
        encoding="utf-8",
    )
    text = enrich_lyrics(None, {}, tmp_path, catalog=False)
    assert text is not None
    assert "Arrópame" in text


def test_resolve_cover_reads_local_jpeg(tmp_path):
    jpeg = _mini_jpeg()
    (tmp_path / "track.jpg").write_bytes(jpeg)
    cover = resolve_cover({}, tmp_path)
    assert cover is not None
    assert cover.startswith(b"\xff\xd8")


def test_embed_mp3_writes_spaces_and_cover(tmp_path):
    import subprocess

    from mutagen import File

    from app.services.ffmpeg import detect_ffmpeg
    from app.services.tags import TagPayload, embed_tags

    ffmpeg = detect_ffmpeg()
    if not ffmpeg:
        return
    mp3 = tmp_path / "clip.mp3"
    cover_path = tmp_path / "art.jpg"
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", "0.3", "-q:a", "9", str(mp3),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64",
            "-frames:v", "1", str(cover_path),
        ],
        check=True,
        capture_output=True,
    )
    jpeg = cover_path.read_bytes()
    tags = TagPayload(
        title="Arrópame",
        artist="José Madero",
        album="Querido",
        lyrics="Si me arropas esta noche\nno voy a tener frío",
    )
    assert embed_tags(mp3, tags, jpeg) is True
    audio = File(mp3)
    assert str(audio.tags["TIT2"]) == "Arrópame"
    assert str(audio.tags["TPE1"]) == "José Madero"
    assert str(audio.tags["TALB"]) == "Querido"
    assert "arropas" in str(audio.tags.getall("USLT")[0])
    apic = audio.tags.getall("APIC")
    assert apic
    assert apic[0].data.startswith(b"\xff\xd8")
