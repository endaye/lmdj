"""frozen-stems parity 比较（spec §3.2）：旧 demo 输出 vs PipelineFromStems 输出。

比较项：report 字段（除耗时）、validation score |Δ|≤1e-4、lanes.json、
标准化 MIDI note events、preview/samples 音频（长度一致、最大绝对差 ≤1e-5）。
在 .venv-pfs 中运行（需要 numpy/soundfile/pretty_midi）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

SCORE_TOL = 1e-4
AUDIO_TOL = 1e-5
MIDI_TIME_TOL = 1e-6
# 耗时字段（elapsed_sec）与 attempts（含逐窗口过程记录，最终 score 单独比）除外
REPORT_EXACT_FIELDS = ("status", "bpm", "loop_start_sec", "loop_seconds",
                       "n_samples", "n_notes")


def compare_reports(old: dict, new: dict) -> list[str]:
    errors = []
    for field in REPORT_EXACT_FIELDS:
        if old.get(field) != new.get(field):
            errors.append(f"report.{field}: {old.get(field)!r} != {new.get(field)!r}")
    if abs(old.get("score", 0.0) - new.get("score", 0.0)) > SCORE_TOL:
        errors.append(f"report.score: |{old.get('score')} - {new.get('score')}|"
                      f" > {SCORE_TOL}")
    old_names = [l["name"] for l in old.get("lanes", [])]
    new_names = [l["name"] for l in new.get("lanes", [])]
    if old_names != new_names:
        errors.append(f"report.lanes 名称: {old_names} != {new_names}")
    return errors


def compare_lanes(old_path: Path, new_path: Path) -> list[str]:
    old = json.loads(old_path.read_text())
    new = json.loads(new_path.read_text())
    return [] if old == new else [f"lanes.json 不一致: {old_path} vs {new_path}"]


def _note_events(path: Path) -> list[tuple[int, int, float, float]]:
    pm = pretty_midi.PrettyMIDI(str(path))
    events = [(n.pitch, n.velocity, n.start, n.end)
              for inst in pm.instruments for n in inst.notes]
    return sorted(events)


def compare_midi(old_path: Path, new_path: Path) -> list[str]:
    old, new = _note_events(old_path), _note_events(new_path)
    if len(old) != len(new):
        return [f"MIDI note 数量: {len(old)} != {len(new)}"]
    errors = []
    for i, ((op, ov, os_, oe), (np_, nv, ns, ne)) in enumerate(zip(old, new)):
        if (op, ov) != (np_, nv):
            errors.append(f"MIDI note[{i}] pitch/velocity: "
                          f"({op},{ov}) != ({np_},{nv})")
        elif abs(os_ - ns) > MIDI_TIME_TOL or abs(oe - ne) > MIDI_TIME_TOL:
            errors.append(f"MIDI note[{i}] 时间偏差超过 {MIDI_TIME_TOL}")
    return errors


def compare_audio(old_dir: Path, new_dir: Path) -> list[str]:
    errors = []
    old_samples = {p.name for p in (old_dir / "samples").glob("*.wav")}
    new_samples = {p.name for p in (new_dir / "samples").glob("*.wav")}
    if old_samples != new_samples:
        errors.append(f"samples 集合不一致: {sorted(old_samples ^ new_samples)}")
    rels = ["loop_preview.wav", "render_preview.wav"]
    rels += [f"samples/{name}" for name in sorted(old_samples & new_samples)]
    for rel in rels:
        old_path, new_path = old_dir / rel, new_dir / rel
        if not old_path.exists() or not new_path.exists():
            errors.append(f"{rel}: 文件缺失")
            continue
        a, _ = sf.read(old_path, dtype="float64", always_2d=True)
        b, _ = sf.read(new_path, dtype="float64", always_2d=True)
        if a.shape != b.shape:
            errors.append(f"{rel}: 长度/形状 {a.shape} != {b.shape}")
            continue
        diff = float(np.abs(a - b).max()) if len(a) else 0.0
        if diff > AUDIO_TOL:
            errors.append(f"{rel}: 最大绝对差 {diff:.2e} > {AUDIO_TOL}")
    return errors


def compare_packages(old_dir: Path, new_dir: Path) -> list[str]:
    old_dir, new_dir = Path(old_dir), Path(new_dir)
    old_report = json.loads((old_dir / "report.json").read_text())
    new_report = json.loads((new_dir / "report.json").read_text())
    errors = compare_reports(old_report, new_report)
    errors += compare_lanes(old_dir / "lanes.json", new_dir / "lanes.json")
    errors += compare_midi(old_dir / "chart.mid", new_dir / "chart.mid")
    errors += compare_audio(old_dir, new_dir)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("parity", description=__doc__)
    parser.add_argument("old_dir", type=Path)
    parser.add_argument("new_dir", type=Path)
    args = parser.parse_args(argv)
    errors = compare_packages(args.old_dir, args.new_dir)
    if errors:
        print("parity FAIL：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("parity PASS（spec §3.2 全部比较项通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
