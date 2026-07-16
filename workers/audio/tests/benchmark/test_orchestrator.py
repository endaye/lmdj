from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from lmdj_audio_worker.benchmark import orchestrator
from lmdj_audio_worker.benchmark.normalize import NormalizedInput
from lmdj_audio_worker.separation.cache import ChecksumError, sha256_file
from lmdj_audio_worker.separation.contract import (SeparationError,
                                                    SeparationResult,
                                                    SeparatorInfo,
                                                    write_result)

# ---------------------------------------------------------------------------
# fixtures: registry / manifest 构造（entry dict 结构照抄
# tests/separation/test_smoke_cli.py 的 make_env）
# ---------------------------------------------------------------------------


def _entry(id_: str, runner: str, devices: tuple[str, ...] = ("cpu",)) -> dict:
    return {
        "id": id_, "family": runner, "runner": runner,
        "command": ["true", "{input}", "{output_dir}", "{device}",
                    "{checkpoint_dir}", "{seed}", "{repeat_id}"],
        "source": {"url": f"https://example.com/{id_}.bin", "revision": "r1"},
        "artifact_sha256": "a" * 64,
        "license": {"code": "MIT", "weights": "MIT"},
        "stems": ["drums", "bass", "vocals", "other"],
        "sample_rate": 44100, "channels": 2, "devices": list(devices),
        "inference": {}, "env_lock_sha256": "b" * 64,
        "status": "experimental",
    }


def _registry(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "separators.json"
    path.write_text(json.dumps({
        "schema_version": "lmdj.separators.v1",
        "separators": entries,
    }))
    return path


def _manifest(tmp_path: Path, data_root: Path, track_ids: list[str]) -> Path:
    for tid in track_ids:
        p = data_root / f"{tid}.wav"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake-audio-" + tid.encode())
    path = tmp_path / "m.manifest.json"
    path.write_text(json.dumps({
        "schema_version": "lmdj.benchmark-manifest.v1",
        "dataset_id": "ds1",
        "tracks": [
            {"id": tid, "input": f"{tid}.wav", "split": "smoke", "tags": [],
             "has_ground_truth": False, "ground_truth": None}
            for tid in track_ids
        ],
    }))
    return path


# ---------------------------------------------------------------------------
# fakes: 每条链路阶段一个可注入 fake（单测全 fake，不碰真实 runner/subprocess）
# ---------------------------------------------------------------------------


class FakeNormalize:
    """伪造 normalize_input：写一个哑 wav 占位文件，sha256 可按 track 覆盖序列。"""

    def __init__(self, sha_overrides: dict[str, list[str]] | None = None):
        self._overrides = sha_overrides or {}
        self._counts: dict[str, int] = {}

    def __call__(self, src: Path, dest_dir: Path) -> NormalizedInput:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "normalized.wav"
        if not dest.exists():
            dest.write_bytes(b"normalized-" + Path(src).name.encode())
        track_id = dest_dir.name
        queue = self._overrides.get(track_id)
        if queue:
            idx = min(self._counts.get(track_id, 0), len(queue) - 1)
            self._counts[track_id] = self._counts.get(track_id, 0) + 1
            sha = queue[idx]
        else:
            sha = hashlib.sha256(track_id.encode()).hexdigest()
        return NormalizedInput(path=dest, sha256=sha, frames=100, duration_seconds=1.0)


def _make_completed(request, entry, sha: str) -> SeparationResult:
    result = SeparationResult(
        status="completed", source="runner", input_sha256=sha,
        separator=SeparatorInfo(id=entry.id, family=entry.family,
                                checkpoint_sha256=entry.artifact_sha256,
                                runner_version="0.1.0"),
        requested_device=request.device, actual_device=request.device,
        stems={k: f"stems/{k}.wav" for k in ("drums", "bass", "vocals", "other")},
        audio={"sample_rate": 44100, "channels": 2, "duration_seconds": 1.0},
        performance={"model_load_seconds": 0.0, "inference_seconds": 0.0,
                    "wall_seconds": 0.0, "peak_rss_bytes": 0,
                    "peak_device_memory_bytes": 0},
    )
    write_result(request.output_dir / "separation.json", result)
    return result


def _make_failed(request, entry, sha: str, category: str) -> SeparationResult:
    result = SeparationResult(
        status="failed", source="runner", input_sha256=sha,
        separator=SeparatorInfo(id=entry.id, family=entry.family,
                                checkpoint_sha256=entry.artifact_sha256,
                                runner_version="0.1.0"),
        requested_device=request.device,
        error=SeparationError(category=category, exit_code=1, stage="inference",
                              stderr_tail="boom", elapsed_seconds=0.1),
    )
    write_result(request.output_dir / "separation.json", result)
    return result


class FakeSeparate:
    """伪造 run_separator：按 (track_id, separator_id) 定向失败，其余走 completed。

    track_id 从 request.input_path 的父目录名还原
    （orchestrator 按 track.id 分目录归一化，见 run_benchmark 的 normalize dest_dir）。
    """

    def __init__(self, fail_for: set[tuple[str, str]] = frozenset()):
        self.fail_for = set(fail_for)
        self.calls: list[tuple[str, str, str, int]] = []

    def __call__(self, entry, request, checkpoint_dir, timeout_sec=None):
        track_id = Path(request.input_path).parent.name
        self.calls.append((track_id, entry.id, request.device, request.repeat_id))
        Path(request.output_dir).mkdir(parents=True, exist_ok=True)
        sha = sha256_file(Path(request.input_path))
        if (track_id, entry.id) in self.fail_for:
            return _make_failed(request, entry, sha, "inference")
        return _make_completed(request, entry, sha)


def fake_ensure_checkpoint(entry) -> Path:
    return Path("/fake/checkpoints") / entry.id


def fake_validate_ok(package_dir, result, expected_frames) -> list:
    return []


class FakeCompat:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, canonical_dir, legacy_dir, cfg=None) -> dict:
        self.calls += 1
        Path(legacy_dir).mkdir(parents=True, exist_ok=True)
        return {"drums": Path(legacy_dir) / "drums.wav"}


class FakePfsRun:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, stems_dir, out_dir, song_id) -> Path:
        self.calls += 1
        package_dir = Path(out_dir) / song_id
        package_dir.mkdir(parents=True, exist_ok=True)
        return package_dir


def fake_pfs_raises(stems_dir, out_dir, song_id):
    raise RuntimeError("pfs boom")


class FakePatchify:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, package_dir, out_path=None):
        self.calls += 1
        return None


def make_deps(*, normalize=None, ensure_checkpoint=None, separate=None,
             validate_stems=None, compat=None, pfs_run=None,
             patchify=None) -> orchestrator.OrchestratorDeps:
    return orchestrator.OrchestratorDeps(
        normalize=normalize or FakeNormalize(),
        ensure_checkpoint=ensure_checkpoint or fake_ensure_checkpoint,
        separate=separate or FakeSeparate(),
        validate_stems=validate_stems or fake_validate_ok,
        compat=compat or FakeCompat(),
        pfs_run=pfs_run or FakePfsRun(),
        patchify=patchify or FakePatchify(),
    )


def _combo(run_dir, track_id, sep_id, device="cpu", repeat=0):
    return orchestrator.snapshots.combo_dir(
        run_dir, "ds1", track_id, sep_id, device, repeat)


# ---------------------------------------------------------------------------
# 1. happy path：2 tracks × 2 separators -> 4 组合 completed
# ---------------------------------------------------------------------------


def test_happy_path_two_tracks_two_separators_all_completed(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1", "track-2"])
    registry_path = _registry(
        tmp_path, [_entry("sepA", "demucs"), _entry("sepB", "scnet")])

    fake_separate = FakeSeparate()
    deps = make_deps(separate=fake_separate)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA", "sepB"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-happy",
        registry_path=registry_path)

    summary = orchestrator.run_benchmark(cfg, deps=deps)

    assert summary.total == 4
    assert summary.completed == 4
    assert summary.failed == 0
    assert summary.cache_hits == 0
    assert summary.failures == []
    assert len(fake_separate.calls) == 4

    for track_id in ("track-1", "track-2"):
        for sep_id in ("sepA", "sepB"):
            record = orchestrator.snapshots.read_combo(
                _combo(summary.run_dir, track_id, sep_id))
            assert record["status"] == "completed"
            assert record["cached"] is False
            assert record["failed_stage"] is None
            assert record["error_category"] is None
            assert record["track"] == track_id
            assert record["separator"] == sep_id
            assert record["device"] == "cpu"
            assert record["repeat"] == 0
            for stage in ("normalize", "separate", "validate", "compat",
                         "pfs", "patchify"):
                assert record["stages"][stage]["status"] == "ok"
                assert isinstance(record["stages"][stage]["seconds"], (int, float))
            assert set(record["cache_key_components"]) == {
                "input_sha256", "checkpoint_sha256", "runner_version",
                "config_hash", "device", "seed_repeat"}
            assert isinstance(record["cache_key"], str) and record["cache_key"]


# ---------------------------------------------------------------------------
# 2. 一个组合 separate 返回 failed -> failed_stage=separate、下游三阶段 skipped，
#    其余 3 组合 completed
# ---------------------------------------------------------------------------


def test_separate_failure_skips_downstream_others_complete(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1", "track-2"])
    registry_path = _registry(
        tmp_path, [_entry("sepA", "demucs"), _entry("sepB", "scnet")])

    fake_separate = FakeSeparate(fail_for={("track-1", "sepA")})
    deps = make_deps(separate=fake_separate)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA", "sepB"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-fail",
        registry_path=registry_path)

    summary = orchestrator.run_benchmark(cfg, deps=deps)

    assert summary.total == 4
    assert summary.completed == 3
    assert summary.failed == 1
    assert len(summary.failures) == 1
    failure = summary.failures[0]
    assert failure["track"] == "track-1"
    assert failure["separator"] == "sepA"
    assert failure["device"] == "cpu"
    assert failure["repeat"] == 0
    assert failure["stage"] == "separate"
    assert failure["category"] == "inference"
    assert "elapsed_seconds" in failure and "error" in failure
    # spec §10 字段集：checkpoint（entry.artifact_sha256）与 exit_code（来自
    # SeparationError.exit_code，_make_failed 写的是 1）都必须出现在失败记录里。
    assert failure["checkpoint"] == "a" * 64
    assert failure["exit_code"] == 1

    record = orchestrator.snapshots.read_combo(_combo(summary.run_dir, "track-1", "sepA"))
    assert record["status"] == "failed"
    assert record["failed_stage"] == "separate"
    assert record["error_category"] == "inference"
    assert record["stages"]["normalize"]["status"] == "ok"
    assert record["stages"]["separate"]["status"] == "failed"
    for stage in ("validate", "compat", "pfs", "patchify"):
        assert record["stages"][stage]["status"] == "skipped"

    for track_id, sep_id in (("track-1", "sepB"), ("track-2", "sepA"), ("track-2", "sepB")):
        rec = orchestrator.snapshots.read_combo(_combo(summary.run_dir, track_id, sep_id))
        assert rec["status"] == "completed"


# ---------------------------------------------------------------------------
# 3. entry.devices=("cpu",) 请求 mps -> unsupported_device，separate 调用计数为 0
# ---------------------------------------------------------------------------


def test_unsupported_device_short_circuits_before_separate(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1"])
    registry_path = _registry(tmp_path, [_entry("sepA", "demucs", devices=("cpu",))])

    fake_separate = FakeSeparate()
    deps = make_deps(separate=fake_separate)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA"],
        device="mps", out_root=tmp_path / "benchmarks", run_id="run-device",
        registry_path=registry_path)

    summary = orchestrator.run_benchmark(cfg, deps=deps)

    assert summary.total == 1
    assert summary.completed == 0
    assert summary.failed == 1
    assert fake_separate.calls == []

    failure = summary.failures[0]
    assert failure["category"] == "unsupported_device"
    assert failure["stage"] == "separate"

    record = orchestrator.snapshots.read_combo(
        _combo(summary.run_dir, "track-1", "sepA", device="mps"))
    assert record["error_category"] == "unsupported_device"
    assert record["failed_stage"] == "separate"
    assert record["stages"]["normalize"]["status"] == "ok"
    assert record["stages"]["separate"]["status"] == "failed"
    for stage in ("validate", "compat", "pfs", "patchify"):
        assert record["stages"][stage]["status"] == "skipped"


# ---------------------------------------------------------------------------
# 4. fake pfs 抛异常 -> failed_stage="pfs"、error_category="downstream"
# ---------------------------------------------------------------------------


def test_pfs_exception_maps_to_downstream_category(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1"])
    registry_path = _registry(tmp_path, [_entry("sepA", "demucs")])

    deps = make_deps(pfs_run=fake_pfs_raises)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-pfs",
        registry_path=registry_path)

    summary = orchestrator.run_benchmark(cfg, deps=deps)

    assert summary.total == 1
    assert summary.completed == 0
    assert summary.failed == 1
    failure = summary.failures[0]
    assert failure["stage"] == "pfs"
    assert failure["category"] == "downstream"

    record = orchestrator.snapshots.read_combo(_combo(summary.run_dir, "track-1", "sepA"))
    assert record["failed_stage"] == "pfs"
    assert record["error_category"] == "downstream"
    assert record["stages"]["normalize"]["status"] == "ok"
    assert record["stages"]["separate"]["status"] == "ok"
    assert record["stages"]["validate"]["status"] == "ok"
    assert record["stages"]["compat"]["status"] == "ok"
    assert record["stages"]["pfs"]["status"] == "failed"
    assert record["stages"]["patchify"]["status"] == "skipped"


# ---------------------------------------------------------------------------
# 5. resume：同 cfg 跑两遍 -> 第二遍 cache_hits==4 且 separate 第二遍零调用；
#    fresh=True 第三遍 -> 重新调用
# ---------------------------------------------------------------------------


def test_resume_cache_hits_then_fresh_forces_recompute(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1", "track-2"])
    registry_path = _registry(
        tmp_path, [_entry("sepA", "demucs"), _entry("sepB", "scnet")])

    fake_separate = FakeSeparate()
    deps = make_deps(separate=fake_separate)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA", "sepB"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-resume",
        registry_path=registry_path)

    first = orchestrator.run_benchmark(cfg, deps=deps)
    assert first.completed == 4
    assert first.cache_hits == 0
    assert len(fake_separate.calls) == 4

    combo_path = _combo(first.run_dir, "track-1", "sepA")
    combo_json_path = combo_path / "combo.json"
    first_bytes = combo_json_path.read_bytes()
    first_mtime_ns = combo_json_path.stat().st_mtime_ns

    second = orchestrator.run_benchmark(cfg, deps=deps)
    assert second.cache_hits == 4
    assert second.completed == 4
    assert second.failed == 0
    assert len(fake_separate.calls) == 4  # 第二遍 fake separate 零调用

    # 缓存命中不得重写 combo.json：原记录字节与 mtime 必须原封不动
    # （原始 cached=false、performance 都保留；命中只在 run.json summary 里可见）。
    second_bytes = combo_json_path.read_bytes()
    second_mtime_ns = combo_json_path.stat().st_mtime_ns
    assert second_bytes == first_bytes
    assert second_mtime_ns == first_mtime_ns

    record = orchestrator.snapshots.read_combo(combo_path)
    assert record["cached"] is False
    assert record["status"] == "completed"

    cfg_fresh = replace(cfg, fresh=True)
    third = orchestrator.run_benchmark(cfg_fresh, deps=deps)
    assert third.cache_hits == 0
    assert third.completed == 4
    assert len(fake_separate.calls) == 8  # fresh 强制重新执行全部 4 个组合


# ---------------------------------------------------------------------------
# 6. fake normalize 第二遍返回不同 sha -> 缓存不命中
# ---------------------------------------------------------------------------


def test_normalize_sha_change_invalidates_cache(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1"])
    registry_path = _registry(tmp_path, [_entry("sepA", "demucs")])

    fake_normalize = FakeNormalize(sha_overrides={"track-1": ["a" * 64, "b" * 64]})
    fake_separate = FakeSeparate()
    deps = make_deps(normalize=fake_normalize, separate=fake_separate)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-shachange",
        registry_path=registry_path)

    first = orchestrator.run_benchmark(cfg, deps=deps)
    assert first.completed == 1
    assert first.cache_hits == 0
    assert len(fake_separate.calls) == 1

    second = orchestrator.run_benchmark(cfg, deps=deps)
    assert second.cache_hits == 0
    assert second.completed == 1
    assert len(fake_separate.calls) == 2  # sha 变了，缓存不命中，重新跑


# ---------------------------------------------------------------------------
# 7. 未知 separator id -> ValueError
# ---------------------------------------------------------------------------


def test_unknown_separator_id_raises_value_error(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1"])
    registry_path = _registry(tmp_path, [_entry("sepA", "demucs")])

    deps = make_deps()
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["nope"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-unknown",
        registry_path=registry_path)

    with pytest.raises(ValueError):
        orchestrator.run_benchmark(cfg, deps=deps)


# ---------------------------------------------------------------------------
# 8. 错误类别归类：ensure_checkpoint 抛 ChecksumError/其他异常，
#    deps.separate 自身抛异常 -> checksum / download / inference
# ---------------------------------------------------------------------------


def fake_ensure_checkpoint_checksum_error(entry) -> Path:
    raise ChecksumError(f"{entry.id}: 校验和不符")


def fake_ensure_checkpoint_os_error(entry) -> Path:
    raise OSError("网络不可达")


def fake_separate_raises(entry, request, checkpoint_dir, timeout_sec=None):
    raise RuntimeError("separate 内部炸了")


def test_ensure_checkpoint_checksum_error_maps_to_checksum_category(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1"])
    registry_path = _registry(tmp_path, [_entry("sepA", "demucs")])

    deps = make_deps(ensure_checkpoint=fake_ensure_checkpoint_checksum_error)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-checksum",
        registry_path=registry_path)

    summary = orchestrator.run_benchmark(cfg, deps=deps)

    assert summary.total == 1
    assert summary.completed == 0
    assert summary.failed == 1
    failure = summary.failures[0]
    assert failure["stage"] == "checkpoint"
    assert failure["category"] == "checksum"

    record = orchestrator.snapshots.read_combo(_combo(summary.run_dir, "track-1", "sepA"))
    assert record["failed_stage"] == "checkpoint"
    assert record["error_category"] == "checksum"
    assert record["stages"]["normalize"]["status"] == "ok"
    assert record["stages"]["checkpoint"]["status"] == "failed"
    for stage in ("separate", "validate", "compat", "pfs", "patchify"):
        assert record["stages"][stage]["status"] == "skipped"


def test_ensure_checkpoint_os_error_maps_to_download_category(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1"])
    registry_path = _registry(tmp_path, [_entry("sepA", "demucs")])

    deps = make_deps(ensure_checkpoint=fake_ensure_checkpoint_os_error)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-download",
        registry_path=registry_path)

    summary = orchestrator.run_benchmark(cfg, deps=deps)

    assert summary.total == 1
    assert summary.completed == 0
    assert summary.failed == 1
    failure = summary.failures[0]
    assert failure["stage"] == "checkpoint"
    assert failure["category"] == "download"

    record = orchestrator.snapshots.read_combo(_combo(summary.run_dir, "track-1", "sepA"))
    assert record["failed_stage"] == "checkpoint"
    assert record["error_category"] == "download"


def test_separate_raises_maps_to_inference_category(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1"])
    registry_path = _registry(tmp_path, [_entry("sepA", "demucs")])

    deps = make_deps(separate=fake_separate_raises)
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-sepraise",
        registry_path=registry_path)

    summary = orchestrator.run_benchmark(cfg, deps=deps)

    assert summary.total == 1
    assert summary.completed == 0
    assert summary.failed == 1
    failure = summary.failures[0]
    assert failure["stage"] == "separate"
    assert failure["category"] == "inference"

    record = orchestrator.snapshots.read_combo(_combo(summary.run_dir, "track-1", "sepA"))
    assert record["failed_stage"] == "separate"
    assert record["error_category"] == "inference"
    assert record["stages"]["normalize"]["status"] == "ok"
    assert record["stages"]["checkpoint"]["status"] == "ok"
    assert record["stages"]["separate"]["status"] == "failed"
    for stage in ("validate", "compat", "pfs", "patchify"):
        assert record["stages"][stage]["status"] == "skipped"


# ---------------------------------------------------------------------------
# 9. normalize 抛异常只影响该 track 的所有组合，其余 track 不受影响
# ---------------------------------------------------------------------------


class FakeNormalizeRaisesForTrack:
    """伪造 normalize_input：指定 track_id 抛异常，其余走真实 FakeNormalize 逻辑。"""

    def __init__(self, fail_track_id: str):
        self._fail_track_id = fail_track_id
        self._ok = FakeNormalize()

    def __call__(self, src: Path, dest_dir: Path) -> NormalizedInput:
        track_id = Path(dest_dir).name
        if track_id == self._fail_track_id:
            raise RuntimeError("normalize 炸了")
        return self._ok(src, dest_dir)


def test_normalize_exception_fails_all_combos_for_track_others_unaffected(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(data_root))
    manifest_path = _manifest(tmp_path, data_root, ["track-1", "track-2"])
    registry_path = _registry(
        tmp_path, [_entry("sepA", "demucs"), _entry("sepB", "scnet")])

    deps = make_deps(normalize=FakeNormalizeRaisesForTrack("track-1"))
    cfg = orchestrator.RunConfig(
        manifests=[str(manifest_path)], separator_ids=["sepA", "sepB"],
        device="cpu", out_root=tmp_path / "benchmarks", run_id="run-normfail",
        registry_path=registry_path)

    summary = orchestrator.run_benchmark(cfg, deps=deps)

    assert summary.total == 4
    assert summary.completed == 2
    assert summary.failed == 2

    for sep_id in ("sepA", "sepB"):
        record = orchestrator.snapshots.read_combo(_combo(summary.run_dir, "track-1", sep_id))
        assert record["status"] == "failed"
        assert record["failed_stage"] == "normalize"
        assert record["error_category"] == "inference"
        for stage in ("checkpoint", "separate", "validate", "compat", "pfs", "patchify"):
            assert record["stages"][stage]["status"] == "skipped"

        other_record = orchestrator.snapshots.read_combo(
            _combo(summary.run_dir, "track-2", sep_id))
        assert other_record["status"] == "completed"
        assert other_record["failed_stage"] is None
