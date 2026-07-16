from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from lmdj_audio_worker.separation import cache
from lmdj_audio_worker.separation.registry import SeparatorEntry

PAYLOAD = b"fake checkpoint weights"
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


def make_entry(sha: str = PAYLOAD_SHA) -> SeparatorEntry:
    return SeparatorEntry(
        id="htdemucs", family="demucs", runner="demucs",
        command=("run", "{input}", "{output_dir}"),
        source_url="https://example.com/weights/htdemucs.th",
        source_revision="v4.0.1", artifact_sha256=sha,
        license_code="MIT", license_weights="MIT",
        stems=("drums", "bass", "vocals", "other"),
        sample_rate=44100, channels=2, devices=("cpu",),
        inference={}, env_lock_sha256="d" * 64, status="verified")


@pytest.fixture(autouse=True)
def cache_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LMDJ_MODEL_CACHE", str(tmp_path / "cache"))
    return tmp_path / "cache"


def good_fetcher(url: str, dest: Path) -> None:
    dest.write_bytes(PAYLOAD)


def test_checkpoint_dir_layout(cache_env):
    entry = make_entry()
    assert cache.checkpoint_dir(entry) == cache_env / "htdemucs" / PAYLOAD_SHA


def test_download_verifies_and_places_artifact(cache_env):
    dest = cache.ensure_checkpoint(make_entry(), fetcher=good_fetcher)
    artifact = dest / "htdemucs.th"
    assert artifact.read_bytes() == PAYLOAD
    assert not list(cache_env.glob("tmp*"))  # 无残留临时文件


def test_checksum_mismatch_deletes_and_raises(cache_env):
    entry = make_entry(sha="0" * 64)
    with pytest.raises(cache.ChecksumError):
        cache.ensure_checkpoint(entry, fetcher=good_fetcher)
    assert not cache.checkpoint_dir(entry).exists()
    assert not list(cache_env.rglob("*.th"))


def test_cached_artifact_skips_fetch(cache_env):
    cache.ensure_checkpoint(make_entry(), fetcher=good_fetcher)

    def exploding_fetcher(url, dest):
        raise AssertionError("命中缓存时不得重新下载")

    dest = cache.ensure_checkpoint(make_entry(), fetcher=exploding_fetcher)
    assert (dest / "htdemucs.th").exists()


def test_fetcher_failure_propagates_and_cleans_tmp(cache_env):
    def broken(url, dest):
        dest.write_bytes(b"partial")
        raise OSError("connection reset")

    with pytest.raises(OSError):
        cache.ensure_checkpoint(make_entry(), fetcher=broken)
    assert not list(cache_env.glob("tmp*"))
