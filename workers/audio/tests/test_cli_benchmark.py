"""CLI `benchmark` 子命令测试：monkeypatch run_benchmark，不跑真实 orchestrator。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lmdj_audio_worker import cli
from lmdj_audio_worker.benchmark.orchestrator import RunConfig, RunSummary


def _fake_run_benchmark(captured: dict):
    def _fake(cfg: RunConfig, **kwargs) -> RunSummary:
        captured["cfg"] = cfg
        captured["kwargs"] = kwargs
        return captured["summary"]
    return _fake


def _install_fake(monkeypatch, summary: RunSummary) -> dict:
    captured: dict = {"summary": summary}
    monkeypatch.setattr(cli, "run_benchmark", _fake_run_benchmark(captured))
    return captured


def test_separators_split_into_list(tmp_path: Path, monkeypatch):
    summary = RunSummary(run_dir=tmp_path / "run", total=1, completed=1, failed=0, cache_hits=0)
    captured = _install_fake(monkeypatch, summary)

    cli.main(["benchmark", "--dataset", "a.json", "--separators", "a,b", "--device", "cpu"])

    cfg: RunConfig = captured["cfg"]
    assert cfg.separator_ids == ["a", "b"]


def test_multiple_dataset_flags_aggregate(tmp_path: Path, monkeypatch):
    summary = RunSummary(run_dir=tmp_path / "run", total=1, completed=1, failed=0, cache_hits=0)
    captured = _install_fake(monkeypatch, summary)

    cli.main([
        "benchmark",
        "--dataset", "a.json", "--dataset", "b.json",
        "--separators", "x", "--device", "cpu",
    ])

    cfg: RunConfig = captured["cfg"]
    assert cfg.manifests == ["a.json", "b.json"]


def test_fresh_flag_defaults_false_and_true_when_passed(tmp_path: Path, monkeypatch):
    summary = RunSummary(run_dir=tmp_path / "run", total=1, completed=1, failed=0, cache_hits=0)
    captured = _install_fake(monkeypatch, summary)

    cli.main(["benchmark", "--dataset", "a.json", "--separators", "x", "--device", "cpu"])
    assert captured["cfg"].fresh is False

    cli.main([
        "benchmark", "--dataset", "a.json", "--separators", "x",
        "--device", "cpu", "--fresh",
    ])
    assert captured["cfg"].fresh is True


def test_full_option_set_maps_onto_run_config(tmp_path: Path, monkeypatch):
    summary = RunSummary(run_dir=tmp_path / "run", total=1, completed=1, failed=0, cache_hits=0)
    captured = _install_fake(monkeypatch, summary)
    registry = tmp_path / "registry.json"

    cli.main([
        "benchmark",
        "--dataset", "a.json",
        "--separators", "a,b",
        "--device", "mps",
        "--repeats", "3",
        "--seed", "7",
        "--fresh",
        "--timeout", "60",
        "--out", str(tmp_path / "out"),
        "--run-id", "run-x",
        "--registry", str(registry),
    ])

    cfg: RunConfig = captured["cfg"]
    assert cfg.manifests == ["a.json"]
    assert cfg.separator_ids == ["a", "b"]
    assert cfg.device == "mps"
    assert cfg.repeats == 3
    assert cfg.seed == 7
    assert cfg.fresh is True
    assert cfg.timeout_sec == 60
    assert cfg.out_root == tmp_path / "out"
    assert cfg.run_id == "run-x"
    assert cfg.registry_path == registry


def test_prints_run_dir_and_counts(tmp_path: Path, monkeypatch, capsys):
    summary = RunSummary(run_dir=tmp_path / "run", total=4, completed=3, failed=1, cache_hits=2)
    _install_fake(monkeypatch, summary)

    with pytest.raises(SystemExit):
        cli.main(["benchmark", "--dataset", "a.json", "--separators", "x", "--device", "cpu"])

    out = capsys.readouterr().out
    assert f"run_dir: {summary.run_dir}" in out
    assert "total: 4" in out
    assert "completed: 3" in out
    assert "failed: 1" in out
    assert "cache_hits: 2" in out


def test_failed_greater_than_zero_exits_1(tmp_path: Path, monkeypatch):
    summary = RunSummary(run_dir=tmp_path / "run", total=2, completed=1, failed=1, cache_hits=0)
    _install_fake(monkeypatch, summary)

    with pytest.raises(SystemExit) as exc:
        cli.main(["benchmark", "--dataset", "a.json", "--separators", "x", "--device", "cpu"])
    assert exc.value.code == 1


def test_all_completed_no_failures_exits_0(tmp_path: Path, monkeypatch):
    summary = RunSummary(run_dir=tmp_path / "run", total=3, completed=3, failed=0, cache_hits=1)
    _install_fake(monkeypatch, summary)

    # no SystemExit raised -> implicit success (same convention as `run`/`status`)
    cli.main(["benchmark", "--dataset", "a.json", "--separators", "x", "--device", "cpu"])
