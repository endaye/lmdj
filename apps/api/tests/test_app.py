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


class CountingRunner(FakeRunner):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[str] = []
        self._calls_lock = threading.Lock()

    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path:
        with self._calls_lock:
            self.calls.append(out_dir.name)
        return super().run(audio, out_dir, song_id)


def make_client(tmp_path: Path, runner=None) -> TestClient:
    app = create_app(runner=runner or FakeRunner(), jobs_root=tmp_path / "jobs")
    return TestClient(app)


def _upload(
    client: TestClient,
    *,
    filename: str = "song.wav",
    submission_id: str | None = None,
    control_token: str | None = None,
) -> str:
    headers = {}
    if submission_id is not None:
        headers["Idempotency-Key"] = submission_id
    if control_token is not None:
        headers["X-LMDJ-Job-Control"] = control_token
    resp = client.post(
        "/uploads",
        files={"file": (filename, io.BytesIO(short_wav_bytes()), "audio/wav")},
        headers=headers or None,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] in {
        "queued",
        "separating",
        "extracting",
        "patchifying",
        "completed",
    }
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


def test_health(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LMDJ_PRODUCT_VERSION", raising=False)
    monkeypatch.delenv("LMDJ_BUILD_REVISION", raising=False)

    assert make_client(tmp_path).get("/health").json() == {
        "ok": True,
        "version": "dev",
        "revision": "unknown",
    }


def test_duplicate_submission_id_returns_same_job_and_runs_once(
    tmp_path: Path,
    ffprobe_wav,
):
    runner = CountingRunner()
    client = make_client(tmp_path, runner=runner)

    first = _upload(client, submission_id="submission-same")
    second = _upload(
        client,
        filename="ignored-name.wav",
        submission_id="submission-same",
    )
    _poll_completed(client, first)

    assert second == first
    assert runner.calls == [first]
    status = client.get(f"/jobs/{first}").json()
    assert status["submission_id"] == "submission-same"
    assert status["original_filename"] == "song.wav"


def test_duplicate_submission_rejects_a_different_control_token(
    tmp_path: Path,
    ffprobe_wav,
):
    client = make_client(tmp_path)
    _upload(
        client,
        submission_id="submission-controlled",
        control_token="a" * 32,
    )

    response = client.post(
        "/uploads",
        files={"file": ("song.wav", io.BytesIO(short_wav_bytes()), "audio/wav")},
        headers={
            "Idempotency-Key": "submission-controlled",
            "X-LMDJ-Job-Control": "b" * 32,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "job_control_mismatch"


def test_different_submission_ids_create_distinct_jobs(tmp_path: Path, ffprobe_wav):
    client = make_client(tmp_path)

    first = _upload(client, submission_id="submission-first")
    second = _upload(client, submission_id="submission-second")

    assert first != second


def test_queue_capacity_and_position_are_truthful(tmp_path: Path, ffprobe_wav):
    barrier = threading.Event()
    started = threading.Event()
    client = make_client(
        tmp_path,
        runner=FakeRunner(barrier=barrier, started=started),
    )
    first = _upload(
        client,
        filename="song-a.wav",
        submission_id="submission-song-a",
    )
    assert started.wait(timeout=5)
    second = _upload(
        client,
        filename="song-b.wav",
        submission_id="submission-song-b",
    )

    first_status = client.get(f"/jobs/{first}").json()
    second_status = client.get(f"/jobs/{second}").json()
    capacity = client.get("/queue").json()

    assert first_status["queue_position"] is None
    assert second_status["state"] == "queued"
    assert second_status["queue_position"] == 1
    assert capacity == {
        "max_concurrency": 1,
        "processing": 1,
        "waiting": 1,
    }
    assert second_status["capacity"] == capacity

    barrier.set()


def test_submission_route_recovers_job_after_response_loss(tmp_path: Path, ffprobe_wav):
    client = make_client(tmp_path)
    job_id = _upload(client, submission_id="submission-lost-response")

    recovered = client.get("/submissions/submission-lost-response")

    assert recovered.status_code == 200
    assert recovered.json()["job_id"] == job_id


def test_completed_job_can_be_deleted_with_its_control_token(
    tmp_path: Path,
    ffprobe_wav,
):
    client = make_client(tmp_path)
    control_token = "delete-control-token-1234567890ab"
    job_id = _upload(client, control_token=control_token)
    _poll_completed(client, job_id)
    job_dir = tmp_path / "jobs" / job_id
    assert (job_dir / "input").is_dir()

    response = client.delete(
        f"/jobs/{job_id}",
        headers={"X-LMDJ-Job-Control": control_token},
    )

    assert response.status_code == 204
    assert not job_dir.exists()
    assert client.get(f"/jobs/{job_id}").status_code == 404


def test_delete_rejects_the_wrong_control_token(
    tmp_path: Path,
    ffprobe_wav,
):
    client = make_client(tmp_path)
    job_id = _upload(client, control_token="c" * 32)
    _poll_completed(client, job_id)

    response = client.delete(
        f"/jobs/{job_id}",
        headers={"X-LMDJ-Job-Control": "d" * 32},
    )

    assert response.status_code == 403
    assert (tmp_path / "jobs" / job_id).is_dir()


def test_delete_rejects_an_active_job_without_deferring_deletion(
    tmp_path: Path,
    ffprobe_wav,
):
    barrier = threading.Event()
    started = threading.Event()
    client = make_client(
        tmp_path,
        runner=FakeRunner(barrier=barrier, started=started),
    )
    control_token = "active-control-token-1234567890ab"
    job_id = _upload(client, control_token=control_token)
    assert started.wait(timeout=5)

    response = client.delete(
        f"/jobs/{job_id}",
        headers={"X-LMDJ-Job-Control": control_token},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "job_in_progress"
    assert (tmp_path / "jobs" / job_id).is_dir()
    barrier.set()


def test_queued_job_can_be_removed_without_running(
    tmp_path: Path,
    ffprobe_wav,
):
    barrier = threading.Event()
    started = threading.Event()
    runner = CountingRunner(barrier=barrier, started=started)
    client = make_client(tmp_path, runner=runner)
    first = _upload(
        client,
        submission_id="submission-active",
        control_token="active-queue-control-token-12345",
    )
    assert started.wait(timeout=5)
    second_token = "queued-control-token-1234567890abcd"
    second = _upload(
        client,
        submission_id="submission-waiting",
        control_token=second_token,
    )
    assert client.get(f"/jobs/{second}").json()["state"] == "queued"

    response = client.delete(
        f"/jobs/{second}",
        headers={"X-LMDJ-Job-Control": second_token},
    )

    assert response.status_code == 204
    assert not (tmp_path / "jobs" / second).exists()
    assert client.get("/queue").json()["waiting"] == 0
    barrier.set()
    _poll_completed(client, first)
    assert runner.calls == [first]


def test_app_startup_marks_old_nonterminal_job_interrupted(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    write_status(
        jobs_root / "oldjob",
        JobStatus(
            job_id="oldjob",
            state="separating",
            submission_id="submission-old-job",
            original_filename="old.wav",
            created_at="2026-07-26T00:00:00Z",
        ),
    )

    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))
    status = client.get("/jobs/oldjob").json()

    assert status["state"] == "interrupted"
    assert status["error_code"] == "service_interrupted"
    assert "restarted" in status["error"]


def test_public_status_contains_visible_identity_fields(tmp_path: Path, ffprobe_wav):
    client = make_client(tmp_path)
    job_id = _upload(
        client,
        filename="visible-song.wav",
        submission_id="submission-visible",
    )

    status = client.get(f"/jobs/{job_id}").json()

    assert status["job_id"] == job_id
    assert status["original_filename"] == "visible-song.wav"
    assert status["created_at"]
    assert status["state"] in {"queued", "separating", "patchifying", "completed"}
    assert "queue_position" in status
    assert status["capacity"]["max_concurrency"] == 1


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


def test_internal_material_contract_is_not_publicly_served(tmp_path: Path):
    jobs_root = tmp_path / "jobs"
    job_id, package = _write_completed_export_job(jobs_root)
    (package / "materials.json").write_text('{"schema":"lmdj.materials.v1"}')
    (package / "separation.json").write_text(
        '{"schema_version":"lmdj.separation.v1"}'
    )
    client = TestClient(create_app(runner=FakeRunner(), jobs_root=jobs_root))

    assert client.get(f"/jobs/{job_id}/files/materials.json").status_code == 404
    assert client.get(f"/jobs/{job_id}/files/separation.json").status_code == 404


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


def test_upload_preflight_does_not_block_app_event_loop(
    monkeypatch,
    tmp_path: Path,
):
    app_module = importlib.import_module("lmdj_api.app")
    started = threading.Event()
    release = threading.Event()
    health_done = threading.Event()
    responses: dict[str, object] = {}

    def blocking_preflight(_file, destination, _limits):
        started.set()
        assert release.wait(timeout=2)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(short_wav_bytes())

    monkeypatch.setattr(app_module, "persist_and_probe", blocking_preflight)
    app = create_app(runner=FakeRunner(), jobs_root=tmp_path / "jobs")

    with TestClient(app) as client:
        upload_thread = threading.Thread(
            target=lambda: responses.setdefault(
                "upload",
                client.post(
                    "/uploads",
                    files={
                        "file": (
                            "song.wav",
                            io.BytesIO(short_wav_bytes()),
                            "audio/wav",
                        ),
                    },
                ),
            ),
        )
        upload_thread.start()
        assert started.wait(timeout=1)

        def request_health() -> None:
            responses["health"] = client.get("/health")
            health_done.set()

        health_thread = threading.Thread(target=request_health)
        health_thread.start()
        event_loop_was_responsive = health_done.wait(timeout=0.2)
        release.set()
        upload_thread.join(timeout=2)
        health_thread.join(timeout=2)

    assert event_loop_was_responsive
    assert responses["health"].status_code == 200
    assert responses["upload"].status_code == 200


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
