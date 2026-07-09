import io
import threading
import time
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient
from lmdj_core_models.model import load_patch_schema

from lmdj_api.app import create_app

from tests.conftest import FakeRunner


def make_client(tmp_path: Path, runner=None) -> TestClient:
    app = create_app(runner=runner or FakeRunner(), jobs_root=tmp_path / "jobs")
    return TestClient(app)


def _upload(client: TestClient) -> str:
    resp = client.post("/uploads", files={"file": ("song.wav", io.BytesIO(b"RIFFfake"), "audio/wav")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "queued"
    return body["job_id"]


def _poll_completed(client: TestClient, job_id: str, tries: int = 50) -> dict:
    for _ in range(tries):
        body = client.get(f"/jobs/{job_id}").json()
        if body["state"] in ("completed", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_health(tmp_path: Path):
    assert make_client(tmp_path).get("/health").json() == {"ok": True}


def test_upload_then_poll_to_completed(tmp_path: Path):
    client = make_client(tmp_path)
    job_id = _upload(client)
    final = _poll_completed(client, job_id)
    assert final["state"] == "completed"
    # FakeRunner copies the golden fixture verbatim; its report.json song_id is
    # "testsong", so patchify derives patch_id "testsong-<hash>" (the real
    # DemoPipelineRunner uses the job_id). Matches Task 1 / audio-worker tests.
    assert final["patch_id"].startswith("testsong-")


def test_get_patch_returns_schema_valid_json(tmp_path: Path):
    client = make_client(tmp_path)
    job_id = _upload(client)
    _poll_completed(client, job_id)

    resp = client.get(f"/jobs/{job_id}/patch")
    assert resp.status_code == 200
    data = resp.json()
    jsonschema.validate(data, load_patch_schema())
    assert data["schema"] == "lmdj.patch.v1"


def test_get_sample_file_returns_bytes(tmp_path: Path):
    client = make_client(tmp_path)
    job_id = _upload(client)
    _poll_completed(client, job_id)
    patch = client.get(f"/jobs/{job_id}/patch").json()
    rel = patch["elements"][0]["source_path"]  # e.g. samples/drum_low.wav

    resp = client.get(f"/jobs/{job_id}/files/{rel}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/")
    assert len(resp.content) > 0


def test_unknown_job_is_404(tmp_path: Path):
    client = make_client(tmp_path)
    assert client.get("/jobs/ghost").status_code == 404
    assert client.get("/jobs/ghost/patch").status_code == 404
    assert client.get("/jobs/ghost/files/samples/x.wav").status_code == 404


def test_patch_before_completed_is_409(tmp_path: Path):
    barrier = threading.Event()
    client = make_client(tmp_path, runner=FakeRunner(barrier=barrier))
    job_id = _upload(client)
    # job 卡在 runner barrier → 尚未 completed
    for _ in range(50):
        if client.get(f"/jobs/{job_id}").json()["state"] in ("separating", "queued", "patchifying"):
            break
        time.sleep(0.02)
    resp = client.get(f"/jobs/{job_id}/patch")
    assert resp.status_code == 409
    assert "state" in resp.json()
    barrier.set()


def test_path_traversal_never_serves_out_of_package(tmp_path: Path):
    client = make_client(tmp_path)
    job_id = _upload(client)
    _poll_completed(client, job_id)

    # URL-encoded `../` is NOT normalized client-side, so it reaches the route
    # and must trip the app's resolve()-based guard → 400.
    encoded = client.get(f"/jobs/{job_id}/files/%2e%2e%2f%2e%2e%2fetc%2fpasswd")
    assert encoded.status_code == 400, encoded.status_code

    # Literal `..` / absolute paths: some clients normalize them away before the
    # route (→404). The security guarantee is only that an out-of-package file is
    # NEVER served — assert that, tolerating either the guard (400) or a 404.
    for bad in ["../../../etc/passwd", "/etc/passwd", "samples/../../secret"]:
        resp = client.get(f"/jobs/{job_id}/files/{bad}")
        assert resp.status_code in (400, 404), f"{bad} -> {resp.status_code}"
        assert resp.status_code != 200


def test_job_id_traversal_is_rejected(tmp_path: Path):
    client = make_client(tmp_path)
    job_id = _upload(client)
    _poll_completed(client, job_id)
    # Encoded `..` as the job_id segment reaches the handler (client doesn't
    # normalize %2e); must be rejected, never escape jobs_root.
    for endpoint in [
        "/jobs/%2e%2e",
        "/jobs/%2e%2e/patch",
        "/jobs/%2e%2e/files/status.json",
    ]:
        resp = client.get(endpoint)
        assert resp.status_code in (400, 404), f"{endpoint} -> {resp.status_code}"
        assert resp.status_code != 200
