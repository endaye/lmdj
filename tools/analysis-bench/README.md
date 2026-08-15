# analysis-bench (prototype)

Disposable prototype validating that the Core Provider mechanism
(`provider::Registry` + Capability v2 port bindings + `AttemptStore`) can
host multiple pluggable audio-analysis tools. It is independent of
`web-runtime-host` and `creator-web`, touches no Project Truth, and carries
no Product/Module/Provider identity (no `module.json`).

## What it validates / does not validate

Validates: multi-Provider registration, per-Capability selection, the
Attempt execute path (port validation, staging, evidence), deterministic
analysis output, and accuracy/performance against numpy/scipy ground truth.

Does not validate: Candidate adoption into Project Truth (open Contract
question), SDK-level input-Artifact byte resolution (the bench Host injects
`analysis::ArtifactByteResolver` at composition time instead), out-of-process
Provider Hosts, or real-time constraints.

## Layout

- `shared/` — strict WAV PCM16 parser, mono mixdown, radix-2 FFT, resolver alias
- `providers/peaks` — `analysis.waveform-peaks.v1` (mirrored peak envelope)
- `providers/loudness` — `analysis.loudness.v1` (peak/RMS dBFS, clipping)
- `providers/onsets` — `analysis.onsets.v1` (spectral-flux onset times)
- `src/main.cpp` — bench CLI: registers all Providers, runs N attempts per
  Provider through `AttemptStore`, times them, checks determinism, prints a
  JSON report
- `compare/` — numpy/scipy ground-truth diff (Markdown table)
- `tests/` — C++ unit tests + CLI smoke test

## Usage

```bash
scripts/core.sh configure dev && scripts/core.sh build dev
build/core/dev/bin/lmdj_analysis_bench \
  --workspace /tmp/analysis-bench \
  --fixture tests/fixtures/audio/kick.wav \
  --capability analysis.waveform-peaks.v1 \
  --iterations 10 --parameters '{"samples_per_bucket": 512}'

python3 -m venv .venv && .venv/bin/pip install -r compare/requirements.txt
.venv/bin/python3 compare/compare.py \
  --bench ../../build/core/dev/bin/lmdj_analysis_bench \
  --fixtures-dir ../../tests/fixtures/audio \
  --report ../../build/core/dev/analysis-bench-report.md
```

## Graduation path (not part of this prototype)

If the validation succeeds, production analysis Providers move to
`providers/` with real `module.json` identities, the SDK grows a first-class
input-Artifact byte resolver, and display rendering lives in `creator-web`.
