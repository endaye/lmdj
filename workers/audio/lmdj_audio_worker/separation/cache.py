"""模型权重缓存（spec §6）：${LMDJ_MODEL_CACHE:-~/.cache/lmdj/separators}/<id>/<sha256>/。

下载 = 临时文件 + SHA-256 校验 + 原子 rename；checksum 不符立即删除，不得运行。
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from .registry import SeparatorEntry

DEFAULT_CACHE = "~/.cache/lmdj/separators"


class ChecksumError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_root() -> Path:
    return Path(os.environ.get("LMDJ_MODEL_CACHE", DEFAULT_CACHE)).expanduser()


def checkpoint_dir(entry: SeparatorEntry) -> Path:
    return cache_root() / entry.id / entry.artifact_sha256


def _artifact_name(entry: SeparatorEntry) -> str:
    return entry.source_url.rstrip("/").rsplit("/", 1)[-1] or "artifact"


def _urllib_fetch(url: str, dest: Path) -> None:
    urllib.request.urlretrieve(url, dest)  # noqa: S310 —— registry 已校验来源


def ensure_checkpoint(entry: SeparatorEntry,
                      fetcher: Callable[[str, Path], None] | None = None) -> Path:
    dest = checkpoint_dir(entry)
    artifact = dest / _artifact_name(entry)
    if artifact.exists():
        return dest
    fetch = fetcher or _urllib_fetch
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="tmp", dir=root)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        fetch(entry.source_url, tmp)
        digest = sha256_file(tmp)
        if digest != entry.artifact_sha256:
            raise ChecksumError(
                f"{entry.id}: 下载 artifact SHA-256 {digest} "
                f"与 registry {entry.artifact_sha256} 不符，已删除")
        dest.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, artifact)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
