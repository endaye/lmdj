#!/usr/bin/env python3
"""Score integer onset predictions against the retained sample.slice corpus."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

FORMAT = "slice-frame-predictions"
REPO_ROOT = Path(__file__).resolve().parents[2]

class ScoreError(ValueError):
    pass

def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda s: (_ for _ in ()).throw(ScoreError(f"{path}: non-finite number")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScoreError(f"{path}: cannot read JSON: {exc}") from exc

def _object(value, name, fields):
    if not isinstance(value, dict):
        raise ScoreError(f"{name}: why: expected object; remedy: provide a JSON object")
    unknown = set(value) - fields
    if unknown:
        raise ScoreError(f"{name}: why: unknown field {sorted(unknown)!r}; remedy: remove it")
    return value

def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ScoreError(f"{name}: why: expected integer >= {minimum}; remedy: provide a frame index")
    return value

def _digest(data):
    return hashlib.sha256(data).hexdigest()

def _manifest(path):
    raw = path.read_bytes()
    manifest = _object(_json(path), "manifest", {"schema", "capability", "generator", "license", "scenarios"})
    if manifest.get("schema") != "lmdj.provider-benchmark-fixtures.v1":
        raise ScoreError("manifest.schema: why: unsupported fixture manifest; remedy: use the retained sample.slice manifest")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ScoreError("manifest.scenarios: why: fixture inventory is missing; remedy: use a complete retained manifest")
    for index, scenario in enumerate(scenarios):
        row = _object(scenario, f"manifest.scenarios[{index}]", {"id", "class", "path", "sha256", "byte_length", "expected", "generation", "origin", "spdx_license", "sample_rate", "channels"})
        if not isinstance(row.get("id"), str) or row.get("class") not in {"success", "input_failure"}:
            raise ScoreError(f"manifest.scenarios[{index}]: why: invalid scenario identity; remedy: use the retained fixture manifest")
        expected = row.get("expected")
        generation = row.get("generation")
        if not isinstance(expected, dict) or not isinstance(generation, dict):
            raise ScoreError(f"manifest.scenarios[{index}]: why: expected and generation metadata are required; remedy: use the retained fixture manifest")
        if row["class"] == "success" and (not isinstance(row.get("path"), str) or not isinstance(row.get("sha256"), str) or not isinstance(row.get("byte_length"), int) or not isinstance(expected.get("onset_frames"), list) or not isinstance(expected.get("tolerance_frames"), int) or not isinstance(generation.get("frame_count"), int)):
            raise ScoreError(f"manifest.scenarios[{index}]: why: incomplete success metadata; remedy: use the retained fixture manifest")
    return manifest, _digest(raw)

def _repo_path(relative):
    p = Path(relative)
    if p.is_absolute() or p.as_posix() != relative or ".." in p.parts:
        raise ScoreError("fixture path: why: path is not repository-relative POSIX; remedy: use a manifest path")
    resolved = (REPO_ROOT / p).resolve()
    if resolved != REPO_ROOT / p or REPO_ROOT not in resolved.parents:
        raise ScoreError("fixture path: why: path escapes repository; remedy: use a retained fixture")
    return resolved

def _match(truth, predicted, tolerance):
    i = j = tp = 0
    pairs = []
    while i < len(truth) and j < len(predicted):
        if predicted[j] < truth[i] - tolerance:
            j += 1
        elif predicted[j] > truth[i] + tolerance:
            i += 1
        else:
            pairs.append([predicted[j], truth[i]])
            tp += 1
            i += 1
            j += 1
    return tp, len(predicted) - tp, len(truth) - tp, pairs

def _ratio(numerator, denominator):
    return None if denominator == 0 else numerator / denominator

def _case(scenario, frames):
    truth = scenario["expected"]["onset_frames"]
    tolerance = _integer(scenario["expected"]["tolerance_frames"], f"{scenario['id']}.tolerance_frames")
    tp, fp, fn, pairs = _match(truth, frames, tolerance)
    return {"fixture_id": scenario["id"], "tolerance_frames": tolerance, "matched_pairs": pairs,
            "tp": tp, "fp": fp, "fn": fn, "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn), "f1": _ratio(2 * tp, 2 * tp + fp + fn),
            "silence_correct": not truth and not frames}

def score(manifest_path, predictions_path):
    manifest, manifest_sha256 = _manifest(Path(manifest_path))
    prediction = _object(_json(Path(predictions_path)), "predictions", {"format", "format_version", "manifest_sha256", "cases"})
    if prediction.get("format") != FORMAT or prediction.get("format_version") != 1:
        raise ScoreError("predictions.format: why: unsupported prediction format; remedy: use slice-frame-predictions version 1")
    if prediction.get("manifest_sha256") != manifest_sha256:
        raise ScoreError("predictions.manifest_sha256: why: predictions target another manifest; remedy: compute the digest of this manifest")
    cases = prediction.get("cases")
    if not isinstance(cases, list):
        raise ScoreError("predictions.cases: why: expected an array; remedy: provide one case per success fixture")
    success = [s for s in manifest["scenarios"] if s.get("class") == "success"]
    expected_ids = {s["id"] for s in success}
    observed = {}
    for index, item in enumerate(cases):
        row = _object(item, f"cases[{index}]", {"fixture_id", "source_sha256", "frames"})
        fixture_id = row.get("fixture_id")
        if not isinstance(fixture_id, str) or fixture_id in observed:
            raise ScoreError(f"cases[{index}].fixture_id: why: duplicate or invalid fixture id; remedy: provide each success fixture exactly once")
        scenario = next((s for s in success if s["id"] == fixture_id), None)
        if scenario is None:
            raise ScoreError(f"cases[{index}].fixture_id: why: input-failure or unknown fixture is not quality-scored; remedy: include success fixtures only")
        raw = _repo_path(scenario["path"]).read_bytes()
        if row.get("source_sha256") != scenario["sha256"] or len(raw) != scenario["byte_length"] or _digest(raw) != scenario["sha256"]:
            raise ScoreError(f"cases[{index}].source_sha256: why: fixture bytes do not match manifest; remedy: restore the retained fixture")
        frames = row.get("frames")
        if not isinstance(frames, list):
            raise ScoreError(f"cases[{index}].frames: why: expected sorted frame integers; remedy: provide zero-based onset frames")
        parsed = []
        limit = scenario["generation"]["frame_count"]
        for frame_index, frame in enumerate(frames):
            value = _integer(frame, f"cases[{index}].frames[{frame_index}]")
            if value >= limit:
                raise ScoreError(f"cases[{index}].frames[{frame_index}]: why: frame is outside source; remedy: keep frames below frame_count")
            if parsed and value <= parsed[-1]:
                raise ScoreError(f"cases[{index}].frames: why: frames are not strictly increasing; remedy: sort and deduplicate predictions")
            parsed.append(value)
        observed[fixture_id] = parsed
    if set(observed) != expected_ids:
        raise ScoreError("cases: why: success-case inventory is incomplete or contains extras; remedy: provide exactly one case per success scenario")
    scored = [_case(s, observed[s["id"]]) for s in success]
    tp, fp, fn = (sum(row[key] for row in scored) for key in ("tp", "fp", "fn"))
    return {"format": "slice-frame-scores", "format_version": 1, "manifest_sha256": manifest_sha256,
            "cases": scored, "micro": {"tp": tp, "fp": fp, "fn": fn,
            "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn), "f1": _ratio(2 * tp, 2 * tp + fp + fn)}}

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = score(args.manifest, args.predictions)
    except (OSError, ScoreError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
