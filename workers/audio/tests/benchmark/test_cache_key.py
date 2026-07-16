from __future__ import annotations

import pytest

from lmdj_audio_worker.benchmark import cache_key
from lmdj_audio_worker.separation.registry import SeparatorEntry


def make_entry(**overrides) -> SeparatorEntry:
    fields = dict(
        id="htdemucs", family="demucs", runner="demucs",
        command=("x", "{input}", "{output_dir}"),
        source_url="https://example.com/a.th", source_revision="r1",
        artifact_sha256="c" * 64, license_code="MIT", license_weights="MIT",
        stems=("drums", "bass", "other", "vocals"),
        sample_rate=44100, channels=2, devices=("cpu", "mps"),
        inference={"shifts": 0, "overlap": 0.25},
        env_lock_sha256="d" * 64, status="verified")
    fields.update(overrides)
    return SeparatorEntry(**fields)


def test_runner_version_resolves_real_module():
    assert cache_key.runner_version(make_entry()) == "0.1.0"


def test_runner_version_unknown_module():
    with pytest.raises(ValueError):
        cache_key.runner_version(make_entry(runner="nonexistent"))


def test_config_hash_changes_with_inference():
    a = cache_key.config_hash(make_entry())
    b = cache_key.config_hash(make_entry(inference={"shifts": 1, "overlap": 0.25}))
    assert a != b and len(a) == 64


def test_config_hash_stable_under_key_order():
    a = cache_key.config_hash(make_entry(inference={"a": 1, "b": 2}))
    b = cache_key.config_hash(make_entry(inference={"b": 2, "a": 1}))
    assert a == b


def test_combo_key_varies_on_each_component():
    base = dict(input_sha256="a" * 64, entry=make_entry(), device="mps",
                seed=0, repeat=0)
    key = cache_key.combo_cache_key(**base)
    assert key != cache_key.combo_cache_key(**{**base, "input_sha256": "b" * 64})
    assert key != cache_key.combo_cache_key(**{**base, "device": "cpu"})
    assert key != cache_key.combo_cache_key(**{**base, "seed": 1})
    assert key != cache_key.combo_cache_key(**{**base, "repeat": 1})
    assert key != cache_key.combo_cache_key(
        **{**base, "entry": make_entry(artifact_sha256="e" * 64)})


def test_describe_lists_six_components():
    entry = make_entry()
    desc = cache_key.describe("a" * 64, entry, "mps", 0, 2)
    assert set(desc) == {"input_sha256", "checkpoint_sha256", "runner_version",
                         "config_hash", "device", "seed_repeat"}
    assert desc["seed_repeat"] == "0/2"
