import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fakes import FakeDownloader, FakeExtractor


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        test_client.app.state.extractor = FakeExtractor()
        test_client.app.state.downloader = FakeDownloader()
        test_client.app.state.runner._downloader = test_client.app.state.downloader
        test_client.app.state.ffmpeg_available = True
        yield test_client
