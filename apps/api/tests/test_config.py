from pathlib import Path

from fastapi.testclient import TestClient

from lmdj_api.app import create_app, default_jobs_root
from tests.conftest import FakeRunner


def test_cors_origins_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LMDJ_CORS_ORIGINS", "https://a.example, https://b.example")
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=tmp_path / "jobs"))

    response = client.get("/health", headers={"Origin": "https://a.example"})

    assert response.headers.get("access-control-allow-origin") == "https://a.example"


def test_cors_absent_when_env_empty(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LMDJ_CORS_ORIGINS", "")
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=tmp_path / "jobs"))

    response = client.get("/health", headers={"Origin": "https://a.example"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_default_is_dev_localhost(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("LMDJ_CORS_ORIGINS", raising=False)
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=tmp_path / "jobs"))

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_default_jobs_root_from_env(monkeypatch, tmp_path: Path):
    expected = tmp_path / "custom-jobs"
    monkeypatch.setenv("LMDJ_JOBS_ROOT", str(expected))

    assert default_jobs_root() == expected


def test_default_jobs_root_fallback(monkeypatch):
    monkeypatch.delenv("LMDJ_JOBS_ROOT", raising=False)

    assert default_jobs_root().name == "jobs"
