from __future__ import annotations

import shutil
import subprocess
import threading
import json
import io
import wave
from pathlib import Path

import pytest

# patchify 的 golden fixture（真实 pipeline 输出快照）
GOLDEN = Path(__file__).resolve().parents[3] / "packages" / "patchify" / "tests" / "fixtures" / "testsong"


def short_wav_bytes(*, duration_seconds: float = 0.1, sample_rate: int = 8_000) -> bytes:
    payload = io.BytesIO()
    with wave.open(payload, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\0\0" * int(duration_seconds * sample_rate))
    return payload.getvalue()


class FakeRunner:
    """拷 golden fixture 为 package，模拟 pipeline 成功；可注入运行屏障或失败。"""

    def __init__(self, package_source: Path = GOLDEN, barrier: threading.Event | None = None,
                 started: threading.Event | None = None, fail_with: Exception | None = None) -> None:
        self.package_source = package_source
        self.barrier = barrier
        self.started = started
        self.fail_with = fail_with

    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path:
        if self.started:
            self.started.set()
        if self.barrier:
            self.barrier.wait(timeout=5)
        if self.fail_with:
            raise self.fail_with
        dst = out_dir / song_id
        shutil.copytree(self.package_source, dst)
        return dst


@pytest.fixture
def golden_audio(tmp_path: Path) -> Path:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF....WAVEfmt fake-audio")
    return audio


@pytest.fixture
def ffprobe_wav(monkeypatch):
    def install(*, format_name: str = "wav", duration_seconds: float = 0.1) -> None:
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps(
                    {
                        "streams": [{"codec_name": "pcm_s16le"}],
                        "format": {
                            "format_name": format_name,
                            "duration": str(duration_seconds),
                        },
                    },
                ),
                stderr="",
            ),
        )

    install()
    return install
