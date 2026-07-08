from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# patchify 的 golden fixture（真实 pipeline 输出快照；wav 为占位字节，patchify 只查存在性）
GOLDEN = Path(__file__).resolve().parents[3] / "packages" / "patchify" / "tests" / "fixtures" / "testsong"


class FakeRunner:
    """把 golden fixture 拷成 package，模拟 pipeline 成功；可注入观察点或失败。"""

    def __init__(
        self,
        package_source: Path = GOLDEN,
        on_run=None,
        fail_with: Exception | None = None,
    ) -> None:
        self.package_source = package_source
        self.on_run = on_run
        self.fail_with = fail_with
        self.calls: list[tuple[Path, Path, str]] = []

    def run(self, audio: Path, out_dir: Path, song_id: str) -> Path:
        self.calls.append((audio, out_dir, song_id))
        if self.on_run:
            self.on_run()
        if self.fail_with:
            raise self.fail_with
        dst = out_dir / song_id
        shutil.copytree(self.package_source, dst)
        return dst


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def sample_audio(tmp_path: Path) -> Path:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF....WAVEfmt fake-audio")
    return audio


def make_stub_demo(tmp_path: Path, body: str) -> Path:
    """伪 demo 目录：.venv/bin/song-pipeline 是一个可执行 python 脚本。"""
    demo = tmp_path / "demo"
    bin_dir = demo / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / "song-pipeline"
    exe.write_text("#!/usr/bin/env python3\n" + body)
    exe.chmod(0o755)
    return demo


STUB_OK_BODY = f'''
import argparse, shutil
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("cmd")
p.add_argument("input", type=Path)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--song-id", required=True)
p.add_argument("--fast", action="store_true")
a = p.parse_args()
shutil.copytree(Path({str(GOLDEN)!r}), a.out / a.song_id)
'''

STUB_FAIL_BODY = '''
import sys
sys.stderr.write("demucs exploded: CUDA out of memory\\n")
sys.exit(2)
'''

STUB_EMPTY_BODY = '''
import argparse
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("cmd"); p.add_argument("input", type=Path)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--song-id", required=True)
p.add_argument("--fast", action="store_true")
p.parse_args()
'''
