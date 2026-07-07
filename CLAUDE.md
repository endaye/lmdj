# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

The git root (`lmdj/`) started as a PRD, architecture, and reference-material workspace. Formal product source boundaries now begin at:

- `apps/` — product applications, currently planned as `apps/web/` and `apps/api/`.
- `packages/` — shared product packages, currently planned as `packages/core-models/` and `packages/patchify/`.
- `workers/` — asynchronous cloud workers, currently planned as `workers/audio/`, `workers/generation/`, and `workers/render/`.

Reference demos live under `references/demos/` and are not part of the final product source boundary:

- `references/demos/lmdj-song-pipeline/` — 高嘉丰提供的 audio pipeline 参考项目。
- `references/demos/ascii-matrix-camera/` — ASCII 视觉互动参考 demo。

The commands below apply only when working inside the `lmdj-song-pipeline` reference demo. **Run `cd references/demos/lmdj-song-pipeline` first**, and the venv lives at `references/demos/lmdj-song-pipeline/.venv`.

Do not add formal Patchify product features to `references/demos/lmdj-song-pipeline/` unless the user explicitly asks. Patchify should be rebuilt as LMDJ-owned code under `packages/patchify/`, using the demo only as reference material, fixture source, or migration source.

`apps/`, `packages/`, and `workers/` are currently empty scaffolding (`.gitkeep` + a `README.md` each stating the intended boundary). The only runnable code today lives in `references/demos/`. `AGENTS.md` is the Codex-facing twin of this file — keep the two in sync when editing shared guidance.

## Product model & active work

LMDJ's product code is designed around its own object model, **not** the demo's `Sample`/`LoopWindow` types: `Project / Patch / Pad / Scene / Element / Render / Lineage` (see `packages/README.md`, `apps/README.md`). Patchify Core is the first real package: it turns an audio-pipeline package into a stable `patch.json` (schema `lmdj.patch.v1`) that Web, CLI, the Audio Worker, and the cloud API all consume. Its V1 input contract is a directory of `samples/*.wav` + `chart.mid` + `lanes.json` + `report.json`; V1 maps those lanes onto a fixed **8-pad Focus View** (`Drums`, `Bass`, `Harmony`, `Lead/Vocal`, `Fill`, `Drop`, `Mute`, `FX/Variation`) with deterministic (no-LLM) logic.

The current active plan is **Path B** — build `packages/patchify/` as a standalone Python package that reads the demo's output only as fixtures/migration source. Read `docs/superpowers/plans/2026-07-07-patchify-core-path-b.md` before starting Patchify work; the older `...2026-07-06-patchify-core-prototype.md` (Path A, adapter inside the demo) is marked historical / not to be executed.

## Commands

```bash
# Setup (requires system ffmpeg: brew install ffmpeg)
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/pip install -e ".[generate]"   # + MusicGen (stage 1), optional
.venv/bin/pip install -e ".[fetch]"       # + yt-dlp, optional

# Tests (6 smoke tests; must all pass)
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pytest tests/test_smoke.py::test_bpm_no_octave_error -q   # single test

# Run the pipeline (--fast = htdemucs single model, ~4x faster; use for local dev)
.venv/bin/song-pipeline run input.mp3 --song-id mysong --fast
.venv/bin/song-pipeline gen --bpm 85 --style "lofi hiphop beat" --seconds 30 --seed 42 --fast --run
.venv/bin/song-pipeline batch ./dir --fast   # → output/batch_report.json
.venv/bin/song-pipeline serve --port 8000    # FastAPI

# Regenerate the test fixture (synthesizes a 90bpm song WITH cached stems, so demucs is skipped)
.venv/bin/python scripts/make_test_song.py output/testsong
```

There is no linter/formatter configured. `numpy` is pinned `<2` (demucs/numba compatibility) — do not bump it.

## Commit convention

All commits **must** follow [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/): `<type>[optional scope]: <description>` (e.g. `feat(pipeline): ...`, `fix(slicer): ...`, `docs: ...`). Breaking changes use `!` or a `BREAKING CHANGE:` footer.

## Reference-demo architecture (`references/demos/lmdj-song-pipeline/`)

This section describes the reference pipeline, not the LMDJ product boundary. It is the fixture/migration source Patchify reads from, so its output contract matters even though the code itself is not product source.

A 6-stage audio pipeline that turns a finished song into a **≤6-sample + MIDI chart** package matching the `lmdj-pad-rhythm` game's input format (`sample-map` + `chart.mid`). Each stage is one module in `song_pipeline/`, wired together by `pipeline.py::run_pipeline`:

```
generate.py   MusicGen, prompt template pins BPM+style (optional stage 1)
  → stems.py       Demucs separation → drums / bass / melody(other[+vocals])
  → loop_finder.py beat/downbeat detection → scored 4-bar candidate windows → crossfade seamless
  → slicer.py      drum onsets → KMeans into kick/snare/hat one-shots; bass/melody → long phrase samples
  → sequencer.py   onset/cross-correlation → 16th-note grid quantize → chart.mid + lanes.json
  → validate.py    re-render MIDI+samples, log-mel similarity score vs original loop
```

### Data flow & key contracts

- **`PipelineConfig` (config.py) is the single source of truth for all tuning.** Every stage takes a `cfg` argument. CLI flags (`--fast`, `--bars`, `--max-loop-seconds`) and the `gen` command's BPM mutate this dataclass before the run.
- **`LoopWindow` (loop_finder.py)** is the central artifact passed between stages — it carries the chosen time window, per-beat times, BPM, score, and a `grid_times()` method that produces the 16th-note quantization grid used by the sequencer.
- **`Sample` (slicer.py)** carries `name` + `kind` ("drum"/"long") + audio. The `name` maps to a MIDI pitch via `cfg.lane_pitches` — this dict is the three-way contract (pitch ↔ wav file ↔ game lane) that `lanes.json` serializes and the game consumes. **Changing `lane_pitches` changes the game-facing output format.**
- **Retry loop:** `run_pipeline` tries up to `cfg.n_candidate_windows` scored windows, keeps the best, and stops early once one clears `cfg.similarity_threshold` (0.50). If none clear it, the best is written with `status: "rejected"` (not an error).

### Two pipeline entry points in pipeline.py

- `run_pipeline` — the standard MPC-style path (kick/snare/hat one-shots + bass/melody long samples).
- `run_pipeline_abc` (CLI `--abc`) — cuts three loops A(1 bar)/B(front half)/C(back half) and writes an A-A-A-BC chart. B/C are constrained to their half of the source bar to preserve rhythmic grammar.

### Non-obvious design points

- **BPM octave correction:** `detect_beats` halves the tempo when it exceeds `cfg.max_bpm` (130) to fix cases where 8th-note hats fool librosa into 2x. Setting `cfg.bpm_hint` (which `gen --run` does automatically from the generation BPM) **skips this correction entirely**.
- **Downbeat detection is a 3-way vote** (loop_finder.py `detect_beats`): harmonic change (weight 0.4) + bass root onsets (0.3) + kick low-freq (0.3). Pure kick energy alone gets fooled by backbeats/pickups.
- **Drum classification ignores demucs labels:** `slicer.py` picks kick/snare/hat by relative spectral features (low vs high energy, brightness, transience), not the cluster label — demucs drum stems have snare/hat high-freq confusion. See SETUP_AND_USAGE.md §6.3 for the scoring formulas.
- **API concurrency:** `api.py` serializes all jobs behind a single `threading.Lock` because the demucs model is not thread-safe. Jobs run in a background thread; status is polled via a `status.json` file per song.
- **`SONG_PIPELINE_DEVICE`** env var forces the demucs device (cuda/cpu/mps).

### scripts/ — experimental "playing styles" on top of the base pipeline

These are standalone `.venv/bin/python scripts/*.py` tools built iteratively, not part of the installed package: DEF multi-loop packages (`make_def_package.py`, which records cut windows in `loop_windows.json` to auto-avoid overlap on re-runs), drum variation (`render_drumvar.py`), drum swap (`render_drumswap.py`), and boom-bap re-render (`rerender_boombap.py`). SETUP_AND_USAGE.md §5–6 documents their parameters.

## Output format

`output/{song_id}/`: `samples/*.wav` (≤6), `chart.mid` (16th-quantized), `lanes.json` (pitch↔wav↔lane map + bpm/loop metadata), `loop_preview.wav` (original loop), `render_preview.wav` (re-rendered for QA), `report.json` (score/retries/timing).

## Further docs

**Product / PRD (repo root `docs/`, mostly written in Chinese):** this repo began as a PRD-iteration workspace, so product decisions live in docs, not code. Consult before making product-shaping choices:
- `docs/prd/working-prd.md` — the current working PRD (rewritten freely as it converges).
- `docs/prd/decision-log.md` — confirmed decisions; `docs/prd/open-questions.md` — undecided questions; `docs/prd/source-materials.md` — external-input index.
- `docs/superpowers/specs/` — the AI-native sampler workstation design and the cloud architecture/infra spec.
- `docs/superpowers/plans/` — implementation plans (Patchify Path B is the active one).

**Reference demo:** its own `README.md` (quick reference) and `SETUP_AND_USAGE.md` (exhaustive setup, migration, and per-parameter tuning tables) are current and worth consulting before deep changes inside the demo — especially SETUP_AND_USAGE.md §6 for the tuning cheat sheet.
