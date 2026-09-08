import time

from tests.fakes import FAKE_PLAYLIST_INFO, FakeExtractor, FailingExtractor


def test_root_and_health(client):
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["name"] == "DoVimu API"
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["ffmpeg"] is True


def test_inspect_video(client):
    response = client.post(
        "/api/v1/media/inspect",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Never Gonna Give You Up"
    assert body["video"][0]["id"] == "video:1080"
    assert body["video"][0]["recommended"] is True
    assert body["video"][0]["label"] == "1080p Full HD"
    assert any(item["id"] == "video:720" for item in body["video"])
    assert any(item["id"] == "audio:mp3:192" for item in body["audio"])


def test_inspect_without_ffmpeg_hides_dash_and_mp3(client):
    client.app.state.ffmpeg_available = False
    response = client.post(
        "/api/v1/media/inspect",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    body = response.json()
    assert [item["id"] for item in body["video"]] == ["video:360"]
    assert not any(item["id"].startswith("audio:mp3") for item in body["audio"])


def test_inspect_rejects_localhost(client):
    response = client.post("/api/v1/media/inspect", json={"url": "http://127.0.0.1/video.mp4"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_URL"


def test_inspect_extraction_error(client):
    client.app.state.extractor = FailingExtractor()
    response = client.post(
        "/api/v1/media/inspect",
        json={"url": "https://www.youtube.com/watch?v=nope"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EXTRACTION_FAILED"


def test_inspect_playlist(client):
    client.app.state.extractor = FakeExtractor(info=FAKE_PLAYLIST_INFO)
    response = client.post(
        "/api/v1/media/inspect",
        json={"url": "https://www.youtube.com/playlist?list=PLtest", "playlist": True},
    )
    body = response.json()
    assert body["is_playlist"] is True
    assert len(body["entries"]) == 2


def test_download_job_and_file(client):
    started = client.post(
        "/api/v1/media/download",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "quality_id": "video:720",
        },
    )
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]

    body = None
    for _ in range(80):
        polled = client.get(f"/api/v1/jobs/{job_id}")
        assert polled.status_code == 200
        body = polled.json()
        if body["status"] in {"ready", "failed"}:
            break
        time.sleep(0.05)

    assert body is not None
    assert body["status"] == "ready", body
    assert body["progress"] == 100
    assert body["download_url"] == f"/api/v1/jobs/{job_id}/file"

    file_response = client.get(f"/api/v1/jobs/{job_id}/file")
    assert file_response.status_code == 200
    assert file_response.content == b"fake-media-bytes"
    assert "attachment" in file_response.headers.get("content-disposition", "")


def test_download_unknown_quality(client):
    response = client.post(
        "/api/v1/media/download",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "quality_id": "video:2160",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "QUALITY_NOT_AVAILABLE"


def test_job_not_found(client):
    response = client.get("/api/v1/jobs/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_search(client):
    response = client.get("/api/v1/search", params={"q": "never gonna"})
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["title"].startswith("Never")
