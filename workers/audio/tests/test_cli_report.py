"""CLI `report` / `listening-package` 子命令测试（Task 8）。

monkeypatch 五个下游函数（`collect_run`/`build_summary`/`write_summary`/
`load_listening_scores`/`build_listening_package`），只断言 CLI 层的参数装配
与打印格式——不跑真实的 benchmark/report/listening 逻辑（那些已经在
`tests/benchmark/test_report.py`/`test_listening.py` 里覆盖过）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lmdj_audio_worker import cli


def _fake_collect_run(captured: dict):
    def _fake(run_dir):
        captured.setdefault("collect_run_calls", []).append(run_dir)
        return {"run_id": str(run_dir), "raw_combos": [], "warnings": []}
    return _fake


def _fake_build_summary(captured: dict, summary: dict):
    def _fake(runs, listening=None, attestations=None):
        captured["build_summary_runs"] = runs
        captured["build_summary_listening"] = listening
        captured["build_summary_attestations"] = attestations
        return summary
    return _fake


def _fake_write_summary(captured: dict):
    def _fake(out_dir, summary):
        captured["write_summary_out_dir"] = out_dir
        captured["write_summary_summary"] = summary
    return _fake


def _fake_load_listening_scores(captured: dict, result: dict):
    def _fake(scores_path, key_path):
        captured["listening_scores_path"] = scores_path
        captured["listening_key_path"] = key_path
        return result
    return _fake


def _install_report_fakes(monkeypatch, captured: dict, summary: dict,
                          listening_result: dict | None = None):
    monkeypatch.setattr(cli, "collect_run", _fake_collect_run(captured))
    monkeypatch.setattr(cli, "build_summary", _fake_build_summary(captured, summary))
    monkeypatch.setattr(cli, "write_summary", _fake_write_summary(captured))
    monkeypatch.setattr(
        cli, "load_listening_scores",
        _fake_load_listening_scores(captured, listening_result or {}))


def _summary(gate_blocked: bool = False) -> dict:
    return {
        "scores": {
            "sep-a": {"total": 72.5, "scored_out_of": 90.0},
        },
        "gates": {
            "sep-a": {
                "contract_compliance": "pass",
                "success_rate": "fail" if gate_blocked else "pass",
                "gate_blocked": gate_blocked,
            },
            "any_gate_failed": gate_blocked,
        },
    }


def test_report_single_run_default_out_is_first_run(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary())

    cli.main(["report", "--run", str(run_dir)])

    assert captured["collect_run_calls"] == [run_dir]
    assert captured["write_summary_out_dir"] == run_dir


def test_report_multiple_runs_aggregate(tmp_path: Path, monkeypatch):
    run_1 = tmp_path / "run-1"
    run_2 = tmp_path / "run-2"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary())

    cli.main(["report", "--run", str(run_1), "--run", str(run_2)])

    assert captured["collect_run_calls"] == [run_1, run_2]
    assert len(captured["build_summary_runs"]) == 2
    # default --out still the *first* --run dir when multiple are given
    assert captured["write_summary_out_dir"] == run_1


def test_report_out_flag_overrides_default(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    out_dir = tmp_path / "custom-out"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary())

    cli.main(["report", "--run", str(run_dir), "--out", str(out_dir)])

    assert captured["write_summary_out_dir"] == out_dir


def test_report_listening_scores_default_key_path(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    scores_path = tmp_path / "scores.json"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary(), listening_result={"sep-a": {"score": 8.0, "veto": False}})

    cli.main(["report", "--run", str(run_dir), "--listening-scores", str(scores_path)])

    assert captured["listening_scores_path"] == scores_path
    assert captured["listening_key_path"] == run_dir / "listening-test" / "private-key.json"
    assert captured["build_summary_listening"] == {"sep-a": {"score": 8.0, "veto": False}}


def test_report_listening_key_flag_overrides_default(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    scores_path = tmp_path / "scores.json"
    key_path = tmp_path / "custom-key.json"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary())

    cli.main([
        "report", "--run", str(run_dir),
        "--listening-scores", str(scores_path),
        "--listening-key", str(key_path),
    ])

    assert captured["listening_key_path"] == key_path


def test_report_no_listening_scores_flag_skips_load(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary())

    cli.main(["report", "--run", str(run_dir)])

    assert "listening_scores_path" not in captured
    assert captured["build_summary_listening"] is None


def test_report_attestations_json_read_and_passed_through(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    attestations_path = tmp_path / "attestations.json"
    attestations_path.write_text(
        '{"macos_mps_smoke": {"sep-a": true}, "mac_physical_memory_bytes": 17179869184}')
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary())

    cli.main(["report", "--run", str(run_dir), "--attestations", str(attestations_path)])

    assert captured["build_summary_attestations"] == {
        "macos_mps_smoke": {"sep-a": True},
        "mac_physical_memory_bytes": 17179869184,
    }


def test_report_no_attestations_flag_passes_none(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary())

    cli.main(["report", "--run", str(run_dir)])

    assert captured["build_summary_attestations"] is None


def test_report_prints_header_and_row(tmp_path: Path, monkeypatch, capsys):
    run_dir = tmp_path / "run-1"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary(gate_blocked=False))

    cli.main(["report", "--run", str(run_dir)])

    out = capsys.readouterr().out
    assert "separator" in out
    assert "total_score" in out
    assert "scored_out_of" in out
    assert "sep-a" in out
    assert "72.50" in out
    assert "90.00" in out
    assert "GATE FAILED" not in out


def test_report_prints_gate_failed_marker_when_blocked(tmp_path: Path, monkeypatch, capsys):
    run_dir = tmp_path / "run-1"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary(gate_blocked=True))

    cli.main(["report", "--run", str(run_dir)])

    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.startswith("sep-a")]
    assert len(lines) == 1
    assert lines[0].rstrip().endswith("GATE FAILED")


def test_report_gate_failure_does_not_change_exit_code(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    captured: dict = {}
    _install_report_fakes(monkeypatch, captured, _summary(gate_blocked=True))

    # no SystemExit raised: report is a reporting tool, not a gatekeeper
    cli.main(["report", "--run", str(run_dir)])


def test_listening_package_default_includes_stems(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    captured: dict = {}

    def _fake_build_listening_package(run_dir_arg, include_stems=True):
        captured["run_dir"] = run_dir_arg
        captured["include_stems"] = include_stems
        return run_dir_arg / "listening-test"

    monkeypatch.setattr(cli, "build_listening_package", _fake_build_listening_package)

    cli.main(["listening-package", "--run", str(run_dir)])

    assert captured["run_dir"] == run_dir
    assert captured["include_stems"] is True


def test_listening_package_no_stems_flag(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run-1"
    captured: dict = {}

    def _fake_build_listening_package(run_dir_arg, include_stems=True):
        captured["include_stems"] = include_stems
        return run_dir_arg / "listening-test"

    monkeypatch.setattr(cli, "build_listening_package", _fake_build_listening_package)

    cli.main(["listening-package", "--run", str(run_dir), "--no-stems"])

    assert captured["include_stems"] is False


def test_listening_package_prints_output_path(tmp_path: Path, monkeypatch, capsys):
    run_dir = tmp_path / "run-1"

    def _fake_build_listening_package(run_dir_arg, include_stems=True):
        return run_dir_arg / "listening-test"

    monkeypatch.setattr(cli, "build_listening_package", _fake_build_listening_package)

    cli.main(["listening-package", "--run", str(run_dir)])

    out = capsys.readouterr().out
    assert str(run_dir / "listening-test") in out
