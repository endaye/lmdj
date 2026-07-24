import io
import importlib
import json
import threading
import time
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient
from lmdj_core_models.model import load_patch_schema
from lmdj_audio_worker.status import JobStatus, write_status

from lmdj_api.app import create_app

from tests.conftest import FakeRunner, short_wav_bytes


def make_client(tmp_path: Path, runner=None) -> TestClient:
    app = create_app(runner=runner or FakeRunner(), jobs_root=tmp_path / "jobs")
    return TestClient(app)


def _upload(client: TestClient) -> str:
    resp = client.post(
        "/uploads",
        files={"file": ("song.wav", io.BytesIO(short_wav_bytes()), "audio/wav")},
    )
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


def _write_completed_export_job(
    jobs_root: Path,
    *,
    job_id: str = "exportjob",
    key: dict[str, object] | None = None,
) -> tuple[str, Path]:
    job_dir = jobs_root / job_id
    package = job_dir / "package"
    (package / "samples").mkdir(parents=True)
    (package / "stems").mkdir()
    (package / "patch.json").write_text(json.dumps({
        "schema": "lmdj.patch.v1",
        "patch_id": "night-bloom-ab12cd34",
    }))
    (package / "samples/kick.wav").write_bytes(b"kick")
    (package / "stems/drums.wav").write_bytes(b"drums")
    (package / "chart.mid").write_bytes(b"midi")
    (package / "export-source.json").write_text(json.dumps({
        "schema": "lmdj.creator-export-source.v1",
        "patch": "patch.json",
        "stems": ["stems/drums.wav"],
        "samples": ["samples/kick.wav"],
        "midi": ["chart.mid"],
        "music": {
            "bpm": 89.1,
            "key": (
                {"value": "A minor", "confidence": 0.72}
                if key is None
                else key
            ),
            "time_signature": {
                "numerator": 4,
                "denominator": 4,
                "source": "fixed-v1",
            },
            "loop": {
                "seconds": 10.6696,
                "steps": 64,
                "beats": 16,
                "bars": 4,
            },
        },
        "warnings": [],
    }))
    write_status(
        job_dir,
        JobStatus(
            job_id=job_id,
            state="completed",
            patch_id="night-bloom-ab12cd34",
            package_dir="package",
        ),
    )
    return job_id, package


def test_health(tmp_path: Path):
    assert make_client(tmp_path).get("/health").json() == {"ok": True}


def test_upload_then_poll_to_completed(tmp_path: Path, ffprobe_wav):
    client = make_client(tmp_path)
    job_id = _upload(client)
    final = _poll_completed(client, job_id)
    assert final["state"] == "completed"
    # FakeRunner copies the golden fixture verbatim; its report.json song_id is
    # "testsong", so patchify derives patch_id "testsong-<hash>" (the real
    # DemoPipelineRunner uses the job_id). Matches Task 1 / audio-worker tests.
    assert final["patch_id"].startswith("testsong-")


def test_get_patch_returns_schema_valid_json(tmp_path: Path, ffprobe_wav):
    client = make_client(tmp_path)
    job_id = _upload(client)
    _poll_completed(client, job_id)

    resp = client.get(f"/jobs/{job_id}/patch")
    assert resp.status_code == 200
    data = resp.json()
    jsonschema.validate(data, load_patch_schema())
    assert data["schema"] == "lmdj.patch.v1"


def test_get_sample_file_returns_bytes(tmp_path: Path, ffprobe_wav):
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
    assert client.get("/jobs/ghost/export/status").status_code == 404
    assert client.get("/jobs/ghost/export").status_code == 404


def test_patch_before_completed_is_409(tmp_path: Path, ffprobe_wav):
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


def test_export_routes_before_completed_are_409(tmp_path: Path, ffprobe_wav):
    barrier = threading.Event()
    client = make_client(tmp_path, runner=FakeRunner(barrier=barrier))
    job_id = _upload(client)
    for _ in range(50):
        if client.get(f"/jobs/{job_id}").json()["state"] in (
            "separating",
            "queued",
            "patchifying",
        ):
            break
        time.sleep(0.02)

    assert client.get(f"/jobs/{job_id}/export/status").status_code == 409
    assert client.get(f"/jobs/{job_id}/export").status_code == 409
    barrier.set()


def test_export_status_and_download_for_complete_job(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    job_id, _ = _write_completed_export_job(jobs_root)
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))

    status = client.get(f"/jobs/{job_id}/export/status")

    assert status.status_code == 200
    assert status.json()["downloadable"] is True
    assert status.json()["music"]["key"] == {
        "value": "A minor",
        "confidence": 0.72,
    }
    assert list(status.json()["items"]) == ["stems", "samples", "midi", "music"]

    download = client.get(f"/jobs/{job_id}/export")

    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert (
        download.headers["content-disposition"]
        == 'attachment; filename="creator-export-night-bloom-ab12cd34.zip"'
    )
    assert download.content.startswith(b"PK")


def test_missing_key_returns_partial_status_and_409_download(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    job_id, package = _write_completed_export_job(jobs_root)
    source_path = package / "export-source.json"
    source = json.loads(source_path.read_text())
    source["music"]["key"] = None
    source_path.write_text(json.dumps(source))
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))

    status = client.get(f"/jobs/{job_id}/export/status")
    download = client.get(f"/jobs/{job_id}/export")

    assert status.status_code == 200
    assert status.json()["status"] == "partial"
    assert status.json()["downloadable"] is False
    assert status.json()["items"]["music"] == {
        "status": "missing",
        "missing": ["music.key"],
    }
    assert download.status_code == 409
    assert download.json() == {
        "detail": {
            "code": "export_incomplete",
            "missing": ["music.key"],
        },
    }


@pytest.mark.parametrize(
    ("missing_file", "missing"),
    [
        ("patch.json", "patch.json"),
        ("chart.mid", "chart.mid"),
        ("samples/kick.wav", "samples"),
    ],
)
def test_missing_required_export_file_returns_409(
    tmp_path: Path,
    missing_file: str,
    missing: str,
):
    jobs_root = tmp_path / "jobs"
    job_id, package = _write_completed_export_job(jobs_root)
    (package / missing_file).unlink()
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))

    response = client.get(f"/jobs/{job_id}/export")

    assert response.status_code == 409
    assert missing in response.json()["detail"]["missing"]


def test_missing_one_inventoried_sample_returns_409_without_zip(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    job_id, package = _write_completed_export_job(jobs_root)
    extra_sample = package / "samples/snare.wav"
    extra_sample.write_bytes(b"snare")
    source_path = package / "export-source.json"
    source = json.loads(source_path.read_text())
    source["samples"].append("samples/snare.wav")
    source_path.write_text(json.dumps(source))
    extra_sample.unlink()
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))

    status = client.get(f"/jobs/{job_id}/export/status")
    download = client.get(f"/jobs/{job_id}/export")

    assert status.status_code == 200
    assert status.json()["status"] == "partial"
    assert status.json()["downloadable"] is False
    assert status.json()["items"]["samples"]["status"] == "missing"
    assert "samples/snare.wav" in status.json()["missing"]
    assert download.status_code == 409
    assert "samples/snare.wav" in download.json()["detail"]["missing"]
    assert not (jobs_root / job_id / "exports").exists()


def test_export_routes_reject_export_source_symlink_outside_package(
    tmp_path: Path,
):
    jobs_root = tmp_path / "jobs"
    job_id, package = _write_completed_export_job(jobs_root)
    source_path = package / "export-source.json"
    outside = tmp_path / "outside-source.json"
    source_path.replace(outside)
    source_path.symlink_to(outside)
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))

    assert client.get(f"/jobs/{job_id}/export/status").status_code == 400
    assert client.get(f"/jobs/{job_id}/export").status_code == 400
    assert not (jobs_root / job_id / "exports").exists()


def test_export_download_rejects_output_symlink_outside_job(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    job_id, _ = _write_completed_export_job(jobs_root)
    job_dir = jobs_root / job_id
    outside = tmp_path / "outside-exports"
    outside.mkdir()
    (job_dir / "exports").symlink_to(outside, target_is_directory=True)
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))

    assert client.get(f"/jobs/{job_id}/export/status").status_code == 200
    download = client.get(f"/jobs/{job_id}/export")

    assert download.status_code == 400
    assert list(outside.iterdir()) == []


def test_export_routes_reject_package_dir_outside_job(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / "unsafe"
    outside = jobs_root / "outside"
    outside.mkdir(parents=True)
    write_status(
        job_dir,
        JobStatus(
            job_id="unsafe",
            state="completed",
            patch_id="unsafe",
            package_dir="../outside",
        ),
    )
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))

    assert client.get("/jobs/unsafe/export/status").status_code == 400
    assert client.get("/jobs/unsafe/export").status_code == 400


def test_path_traversal_never_serves_out_of_package(tmp_path: Path, ffprobe_wav):
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


def test_job_id_traversal_is_rejected(tmp_path: Path, ffprobe_wav):
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


def test_oversized_upload_is_413_and_does_not_create_job(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("LMDJ_UPLOAD_MAX_BYTES", "4")
    client = make_client(tmp_path)

    response = client.post(
        "/uploads",
        files={"file": ("large.wav", io.BytesIO(b"12345"), "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "file_too_large",
        "max_bytes": 4,
    }
    assert not (tmp_path / "jobs").exists()


def test_unsupported_audio_is_415_and_does_not_create_job(
    monkeypatch,
    tmp_path: Path,
    ffprobe_wav,
):
    ffprobe_wav(format_name="mp3")
    client = make_client(tmp_path)

    response = client.post(
        "/uploads",
        files={"file": ("spoofed.wav", io.BytesIO(short_wav_bytes()), "audio/wav")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == {
        "code": "unsupported_audio",
        "supported": ["wav", "mp3"],
    }
    assert not (tmp_path / "jobs").exists()


def test_too_long_audio_is_422_and_does_not_create_job(
    tmp_path: Path,
    ffprobe_wav,
):
    ffprobe_wav(duration_seconds=600.01)
    client = make_client(tmp_path)

    response = client.post(
        "/uploads",
        files={"file": ("long.wav", io.BytesIO(short_wav_bytes()), "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "duration_too_long",
        "max_duration_seconds": 600,
    }
    assert not (tmp_path / "jobs").exists()


def test_unexpected_preflight_error_cleans_temp_and_does_not_create_job(
    monkeypatch,
    tmp_path: Path,
):
    app_module = importlib.import_module("lmdj_api.app")
    upload_temp = tmp_path / "upload-temp"

    def make_temp(**_kwargs):
        upload_temp.mkdir()
        return str(upload_temp)

    def fail_preflight(*_args, **_kwargs):
        raise OSError("disk stopped")

    monkeypatch.setattr(app_module.tempfile, "mkdtemp", make_temp)
    monkeypatch.setattr(app_module, "persist_and_probe", fail_preflight)
    client = make_client(tmp_path)

    with pytest.raises(OSError, match="disk stopped"):
        client.post(
            "/uploads",
            files={"file": ("song.wav", io.BytesIO(short_wav_bytes()), "audio/wav")},
        )

    assert not upload_temp.exists()
    assert not (tmp_path / "jobs").exists()


def test_synchronous_submit_error_cleans_temp_and_does_not_create_job(
    monkeypatch,
    tmp_path: Path,
    ffprobe_wav,
):
    app_module = importlib.import_module("lmdj_api.app")
    upload_temp = tmp_path / "upload-temp"

    def make_temp(**_kwargs):
        upload_temp.mkdir()
        return str(upload_temp)

    def fail_submit(*_args, **_kwargs):
        raise RuntimeError("executor unavailable")

    monkeypatch.setattr(app_module.tempfile, "mkdtemp", make_temp)
    monkeypatch.setattr(app_module.JobExecutor, "submit", fail_submit)
    client = make_client(tmp_path)

    with pytest.raises(RuntimeError, match="executor unavailable"):
        client.post(
            "/uploads",
            files={"file": ("song.wav", io.BytesIO(short_wav_bytes()), "audio/wav")},
        )

    assert not upload_temp.exists()
    assert not (tmp_path / "jobs").exists()
