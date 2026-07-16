"""输入归一化：任意音频 -> 44.1kHz 双声道 float32 wav（benchmark 统一输入基准）。

所有 separator 组合吃同一个归一化产物；input_sha256 与 expected_frames
都以它为准。依赖系统 ffmpeg（仓库既有前置）。
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..separation.cache import sha256_file

_STDERR_TAIL = 2000


class NormalizeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizedInput:
    path: Path
    sha256: str
    frames: int
    duration_seconds: float


def normalize_input(src: Path, dest_dir: Path) -> NormalizedInput:
    import soundfile as sf

    src = Path(src)
    if not src.exists():
        raise NormalizeError(f"输入不存在: {src}")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (src.stem + ".wav")
    if not dest.exists():
        tmp = dest.with_suffix(".tmp.wav")
        try:
            proc = subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-ar", "44100", "-ac", "2",
                 "-c:a", "pcm_f32le", str(tmp)],
                capture_output=True, text=True)
        except FileNotFoundError as exc:
            tmp.unlink(missing_ok=True)
            raise NormalizeError(
                "找不到 ffmpeg —— benchmark 归一化依赖系统 ffmpeg（brew install ffmpeg / apt install ffmpeg）"
            ) from exc
        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise NormalizeError(
                f"ffmpeg 解码失败 {src.name}: "
                f"{(proc.stderr or '')[-_STDERR_TAIL:]}")
        tmp.replace(dest)
    info = sf.info(str(dest))
    return NormalizedInput(path=dest, sha256=sha256_file(dest),
                           frames=info.frames,
                           duration_seconds=round(info.frames / info.samplerate, 6))
