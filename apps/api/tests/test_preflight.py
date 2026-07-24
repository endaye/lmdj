from __future__ import annotations

import io
import json
import subprocess
import wave
from pathlib import Path

import pytest
from fastapi import UploadFile

from lmdj_api.preflight import AudioProbe, PreflightError, UploadLimits, persist_and_probe


def wav_bytes(*, duration_seconds: float = 0.1, sample_rate: int = 8_000) -> bytes:
    payload = io.BytesIO()
    with wave.open(payload, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\0\0" * int(duration_seconds * sample_rate))
    return payload.getvalue()


def upload(filename: str, payload: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(payload))


class RecordingBytesIO(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def probe_result(
    *,
    format_name: str,
    codec_name: str = "pcm_s16le",
    duration_seconds: float = 0.1,
    returncode: int = 0,
    stdout: str | None = None,
) -> subprocess.CompletedProcess[str]:
    body = stdout
    if body is None:
        body = json.dumps(
            {
                "streams": [{"codec_name": codec_name}],
                "format": {
                    "format_name": format_name,
                    "duration": str(duration_seconds),
                },
            },
        )
    return subprocess.CompletedProcess([], returncode, stdout=body, stderr="")


def test_persists_wav_in_one_mib_chunks_and_returns_probe(monkeypatch, tmp_path: Path):
    run = lambda *args, **kwargs: probe_result(format_name="wav")  # noqa: E731
    monkeypatch.setattr(subprocess, "run", run)
    destination = tmp_path / "song.wav"

    result = persist_and_probe(
        upload("song.wav", wav_bytes()),
        destination,
        UploadLimits(max_bytes=10_000, max_duration_seconds=600),
    )

    assert result == AudioProbe(
        format_name="wav",
        codec_name="pcm_s16le",
        duration_seconds=0.1,
    )
    assert destination.read_bytes() == wav_bytes()


def test_requests_exactly_one_mib_on_every_source_read(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: probe_result(format_name="wav"),
    )
    source = RecordingBytesIO(b"x" * (2 * 1024 * 1024 + 1))

    persist_and_probe(
        UploadFile(filename="song.wav", file=source),
        tmp_path / "song.wav",
        UploadLimits(max_bytes=3 * 1024 * 1024, max_duration_seconds=600),
    )

    assert source.read_sizes
    assert set(source.read_sizes) == {1024 * 1024}


def test_accepts_mp3_when_ffprobe_detects_mp3(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: probe_result(
            format_name="mp3",
            codec_name="mp3",
            duration_seconds=12.5,
        ),
    )

    result = persist_and_probe(
        upload("song.mp3", b"ID3-valid-enough-for-mocked-probe"),
        tmp_path / "song.mp3",
        UploadLimits(max_bytes=10_000, max_duration_seconds=600),
    )

    assert result.format_name == "mp3"
    assert result.codec_name == "mp3"
    assert result.duration_seconds == 12.5


def test_rejects_bytes_above_limit_and_removes_partial_file(monkeypatch, tmp_path: Path):
    run = pytest.fail
    monkeypatch.setattr(subprocess, "run", run)
    destination = tmp_path / "large.wav"

    with pytest.raises(PreflightError) as caught:
        persist_and_probe(
            upload("large.wav", b"x" * (1024 * 1024 + 1)),
            destination,
            UploadLimits(max_bytes=1024 * 1024, max_duration_seconds=600),
        )

    assert caught.value.status_code == 413
    assert caught.value.detail == {
        "code": "file_too_large",
        "max_bytes": 1024 * 1024,
    }
    assert not destination.exists()


@pytest.mark.parametrize(
    "result",
    [
        probe_result(format_name="wav", stdout="{broken"),
        subprocess.CompletedProcess([], 1, stdout="", stderr="invalid data"),
        subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {"streams": [], "format": {"format_name": "wav", "duration": "0.1"}},
            ),
            stderr="",
        ),
    ],
)
def test_rejects_corrupt_or_streamless_audio(monkeypatch, tmp_path: Path, result):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)

    with pytest.raises(PreflightError) as caught:
        persist_and_probe(
            upload("broken.wav", wav_bytes()),
            tmp_path / "broken.wav",
            UploadLimits(max_bytes=10_000, max_duration_seconds=600),
        )

    assert caught.value.status_code == 415
    assert caught.value.detail == {
        "code": "unsupported_audio",
        "supported": ["wav", "mp3"],
    }


def test_rejects_spoofed_extension(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: probe_result(format_name="mp3", codec_name="mp3"),
    )

    with pytest.raises(PreflightError) as caught:
        persist_and_probe(
            upload("pretend.wav", b"ID3"),
            tmp_path / "pretend.wav",
            UploadLimits(max_bytes=10_000, max_duration_seconds=600),
        )

    assert caught.value.status_code == 415
    assert caught.value.detail["code"] == "unsupported_audio"


def test_rejects_unsupported_filename_extension_before_probe(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(subprocess, "run", pytest.fail)

    with pytest.raises(PreflightError) as caught:
        persist_and_probe(
            upload("song.aiff", b"FORM"),
            tmp_path / "song.aiff",
            UploadLimits(max_bytes=10_000, max_duration_seconds=600),
        )

    assert caught.value.status_code == 415
    assert not (tmp_path / "song.aiff").exists()


def test_rejects_duration_above_limit(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: probe_result(
            format_name="wav",
            duration_seconds=600.01,
        ),
    )
    destination = tmp_path / "long.wav"

    with pytest.raises(PreflightError) as caught:
        persist_and_probe(
            upload("long.wav", wav_bytes()),
            destination,
            UploadLimits(max_bytes=10_000, max_duration_seconds=600),
        )

    assert caught.value.status_code == 422
    assert caught.value.detail == {
        "code": "duration_too_long",
        "max_duration_seconds": 600,
    }
    assert not destination.exists()


def test_invokes_ffprobe_with_the_stage_one_contract(monkeypatch, tmp_path: Path):
    seen: dict[str, object] = {}

    def run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return probe_result(format_name="wav")

    monkeypatch.setattr(subprocess, "run", run)
    destination = tmp_path / "song.wav"

    persist_and_probe(
        upload("song.wav", wav_bytes()),
        destination,
        UploadLimits(max_bytes=10_000, max_duration_seconds=600),
    )

    assert seen["command"] == [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name:format=format_name,duration",
        "-of",
        "json",
        str(destination),
    ]
    assert seen["kwargs"] == {
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": 15.0,
    }


def test_ffprobe_timeout_has_stable_preflight_error_and_removes_upload(
    monkeypatch,
    tmp_path: Path,
):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    destination = tmp_path / "slow.wav"

    with pytest.raises(PreflightError) as caught:
        persist_and_probe(
            upload("slow.wav", wav_bytes()),
            destination,
            UploadLimits(
                max_bytes=10_000,
                max_duration_seconds=600,
                ffprobe_timeout_seconds=0.25,
            ),
        )

    assert caught.value.status_code == 422
    assert caught.value.detail == {
        "code": "audio_probe_timeout",
        "timeout_seconds": 0.25,
    }
    assert not destination.exists()
