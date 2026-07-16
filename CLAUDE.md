# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git workflow

`main` is protected and must remain deployable. During normal development, do not create, modify, or commit project files directly on local `main`.

- Before changing files, update `main`, then create a short-lived branch. Codex-created branches use the `codex/` prefix; use an isolated worktree when the work should not disturb the main checkout.
- Complete and verify all changes on the short-lived branch, push it, and merge it into `main` only through a Pull Request after required CI and review gates pass. Use squash merge unless the repository policy explicitly changes.
- After merge, delete the short-lived branch. Use `main` only for synchronization, read-only inspection, creating branches, and deploying already-merged commits.
- If an intended edit starts while the current branch is `main`, stop and create or switch to a short-lived branch before modifying files. Do not make the edits first and move them later.
- An administrator may bypass the PR path only for incident recovery or to repair branch protection that blocks its own fix. Keep the bypass minimal and follow it with a PR, issue, or incident record describing the reason, changes, and verification. Urgency alone is not an exception.

## Repository layout

The git root (`lmdj/`) started as a PRD, architecture, and reference-material workspace. The product stack is now built out across three source boundaries:

- `apps/` — product applications. `apps/web/` (React 19 + Vite + TypeScript Patch View workbench) and `apps/api/` (FastAPI backend: upload → job → status → patch).
- `packages/` — shared product packages. `packages/core-models/` (product object model + `lmdj.patch.v1` JSON Schema) and `packages/patchify/` (pure adapter: pipeline package → `patch.json`). `packages/generation`/`render` are not yet created.
- `workers/` — asynchronous cloud workers. `workers/audio/` is built (audio → pipeline subprocess → patchify). `workers/generation/` and `workers/render/` are still `.gitkeep` scaffolding.

Reference demos live under `references/demos/` and are **not** part of the product source boundary:

- `references/demos/lmdj-song-pipeline/` — 高嘉丰提供的 audio pipeline 参考项目 (frozen; consumed only as subprocess, fixture, or migration source).
- `references/demos/ascii-matrix-camera/` — ASCII 视觉互动参考 demo。

Do not add formal Patchify product features to `references/demos/lmdj-song-pipeline/` unless the user explicitly asks — treat the demo as frozen. Formal product code lives under `apps/`, `packages/`, and `workers/`, kept deliberately lightweight (the demo's heavy `torch`/`numpy<2` deps are quarantined behind the demo's own venv and reached only via subprocess).

`AGENTS.md` is the Codex-facing twin of this file — keep the two in sync when editing shared guidance.

The current end-to-end chain runs and has been exercised in the browser:

```text
browser upload → apps/api (POST /uploads) → workers/audio (process_job)
  → demo pipeline (subprocess, demo's own venv) → packages/patchify
  → patch.json (lmdj.patch.v1) + samples written to the job dir
  → apps/web polls GET /jobs/{id} → GET /patch + /files/* → loadPatch
  → 8-pad workbench: play / mute / trigger
Contract hub: packages/core-models (models + JSON Schema — the shared contract).
```

## Product model & active work

LMDJ's product code is designed around its own object model, **not** the demo's `Sample`/`LoopWindow` types: `Project / Patch / Pattern / Pad / Scene / Element / Render / Lineage`. The model dataclasses and the `lmdj.patch.v1` JSON Schema live in `packages/core-models/`; `packages/patchify/` is a pure adapter depending on it. Patchify turns an audio-pipeline package into a stable `patch.json` (schema `lmdj.patch.v1`) that Web, CLI, the Audio Worker, and the cloud API all consume — it carries normalized `patterns[]` (note events), so consumers never re-parse MIDI. Its V1 input contract is a directory of `samples/*.wav` + `chart.mid` + `lanes.json` + `report.json` (real demo contract: the wav key in lanes is `sample`, `song_id` lives in `report.json`); V1 maps those lanes onto a fixed **8-pad Focus View** (`Drums`, `Bass`, `Harmony`, `Lead/Vocal`, `Fill`, `Drop`, `Mute`, `FX/Variation`) with deterministic (no-LLM) trigger_group logic, and `patch_id` is content-derived. Contract decisions are recorded in `docs/prd/decision-log.md` (2026-07-07).

**Contract purity is the load-bearing invariant.** `lmdj.patch.v1` is the single contract shared four ways (Web / CLI / Audio Worker / API). The schema's single source of truth is `packages/core-models/lmdj_core_models/schemas/lmdj.patch.v1.schema.json`; the web copy under `apps/web/src/patch/schema/` and the generated `types.ts` are `npm run sync-contract` outputs, and `npm run check-contract` fails CI-style if they drift. **Consumers read only `patch.json`** — never `lanes.json` or `chart.mid` (the "truth is three-tier" decision, `docs/prd/decision-log.md` 2026-07-07). `patch_id` is a content hash of `lanes.json` + `chart.mid`, which is what makes worker re-runs idempotent.

Patchify (Path B — standalone package, demo output as fixture/migration source only) is **built and merged**; `docs/superpowers/plans/2026-07-07-patchify-core-path-b.md` is now historical record rather than a to-do. The older `...2026-07-06-patchify-core-prototype.md` (Path A, adapter inside the demo) was never executed. For current state and next-step candidates, read `docs/superpowers/2026-07-10-status-and-backlog.md` before starting new work.

## Commands

### Product stack

`scripts/dev.sh` is the top-level dev helper (bash; run from anywhere, acts on repo root). Each formal package has its **own** venv — there is no repo-wide venv. Local `path` deps are not written in `pyproject.toml` metadata, so install order matters: `core-models` before `patchify`, both before `audio`/`api`.

```bash
scripts/dev.sh setup        # create/repair core-models + patchify venvs (idempotent)
scripts/dev.sh test         # run all core-models + patchify tests
scripts/dev.sh smoke        # end-to-end: testsong → patch.json → summary (auto-builds testsong)
scripts/dev.sh all          # setup + test + smoke
scripts/dev.sh setup-demo   # create the demo venv (heavy: demucs/torch, first run 10min+)
scripts/dev.sh setup-pfs    # create the pipeline-from-stems venv (DSP deps pinned by parity-constraints.txt)
scripts/dev.sh parity       # frozen-stems parity gate: demo pipeline vs PipelineFromStems (spec §3.2)
scripts/dev.sh setup-sep-demucs   # create the HT Demucs runner venv (torch stack, pinned)
scripts/dev.sh setup-sep-scnet    # create the SCNet runner venv + MSST pinned clone
scripts/dev.sh setup-sep-bs-roformer   # create the BS-RoFormer runner venv (shares MSST clone/constraints)
scripts/dev.sh setup-sep-mel-roformer  # create the Mel-Band RoFormer runner venv (shares MSST clone/constraints)
scripts/dev.sh separate <id> <audio> [device]   # run one separator via registry -> canonical stems smoke
scripts/dev.sh patchify <package_dir> [--out PATH]   # generate patch.json for a package
scripts/dev.sh song <audio> <song_id>                # full demo pipeline + patchify (needs setup-demo)

# Per-package tests (each package has its own .venv; see each README for the install line)
packages/core-models/.venv/bin/python -m pytest packages/core-models/tests -q
packages/patchify/.venv/bin/python  -m pytest packages/patchify/tests  -q
# apps/api and workers/audio: cd in, install path deps + ".[test]", then pytest tests/ -q

# Web app (apps/web)
cd apps/web
npm install
npm run make-example   # first run; prereq: scripts/dev.sh smoke (produces the example patch)
npm run dev            # http://localhost:5173
npm test               # Vitest + React Testing Library
npm run check-contract # assert schema copy + generated types.ts have not drifted from core-models
npm run sync-contract  # regenerate the web-side contract after a core-models schema change
```

App API + web end-to-end (needs `scripts/dev.sh setup-demo` first):

```bash
cd apps/api && .venv/bin/uvicorn lmdj_api.app:app --port 8000   # then run apps/web dev server
```

### Reference demo (`references/demos/lmdj-song-pipeline/`)

The commands below apply only inside the reference demo. **Run `cd references/demos/lmdj-song-pipeline` first**; its venv lives at `references/demos/lmdj-song-pipeline/.venv`.

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

## Product stack architecture

Four packages, one contract. Data flows one direction; `core-models` is depended on by everything and depends on nothing.

- **`packages/core-models/`** — frozen dataclasses (`Patch / Pattern / Pad / Scene / Element / Note / RenderRef`) + the `lmdj.patch.v1` JSON Schema (bundled as package data). `model.py` hand-writes `Patch.to_dict` / `Pattern.to_dict` to pin top-level key order in the serialized JSON. `LIVE_ACTIONS` = `{trigger_element, trigger_group, empty}` are the only actions a v1 consumer executes; `RESERVED_ACTIONS` (`scene_fill`, `scene_drop`, `mute_group`, `ai_variation`) **must be no-ops** in v1.
- **`packages/patchify/`** — pure adapter, no heavy deps (only `pretty_midi`). `package_loader.py` reads a pipeline package (`samples/*.wav` + `chart.mid` + `lanes.json` + `report.json`); `pad_mapper.py` maps elements onto the fixed 8-pad Focus View (`FOCUS_SLOTS`) — pads 0–3 are semantic (`drums/bass/harmony/lead`), pads 4–7 are reserved actions. Non-obvious: the demo never emits a `lead`/`vocal` element, so when there's no lead but ≥2 harmony elements, the 2nd harmony falls back into the `Lead/Vocal` slot. `patchify.py` only maps the `standard` profile (raises on `loops`), and derives `patch_id = f"{song_id}-{sha256(lanes.json + chart.mid)[:8]}"`.
- **`workers/audio/`** — audio → `patch.json`, no heavy deps of its own. `runner.py::DemoPipelineRunner` shells out to the **demo's own venv** (`references/.../.venv/bin/song-pipeline`) as a subprocess — this is how the torch/numpy quarantine works. `job.py::process_job` drives the state machine `queued → separating → patchifying → completed|failed`, writing `status.json` atomically (tmp + `os.replace`) before every transition so an external reader always sees complete JSON. `status.py::STATES` enumerates the full infra-spec state set, but v1 only emits the five above. Any exception lands as `failed` on disk — never swallowed silently, never crashes. `separation/` holds the lmdj.separation.v1 contract + checkpoint registry + runner protocol (orchestrator synthesizes failure records when the runner dies); `pipeline_from_stems/` is the stages-3–6 migration (runs in its own `.venv-pfs`, versions pinned by `config/parity-constraints.txt`; behavior changes must pass `scripts/dev.sh parity` first). `separation/runners/` holds per-family separator runners (htdemucs verified; scnet-large / bs-roformer-4stem / mel-roformer-4stem experimental — the three MSST-family runners share runners/_msst.py, one pinned clone and one constraints file, each in its own `.venv-sep-*` venv driven by the registry command); `separation/smoke.py` is the registry→cache→runner→canonical-validation smoke entry.
- **`apps/api/`** — FastAPI (`app.py::create_app`, DI-friendly for tests). Routes: `POST /uploads` → `{job_id, state}`; `GET /jobs/{id}` → status; `GET /jobs/{id}/patch`; `GET /jobs/{id}/files/{path}`. `executor.py::JobExecutor` runs jobs on a daemon thread serialized behind a single `Lock` (avoids concurrent subprocesses saturating CPU/RAM, not thread-safety). Both `job_id` and file `path` are validated with `resolve()` + `is_relative_to` against the jobs root — path-traversal guards, do not weaken them. Known accepted v1 risks: no upload size cap, temp uploads not reclaimed (see the app-api spec).
- **`apps/web/`** — React 19 + Vite + TypeScript. `src/patch/loader.ts::loadPatch` is the **single** patch-loading entry point; all three sources (dropped directory, bundled example, API fetch via `src/api/client.ts`) funnel into it. It Ajv-validates against the bundled schema, fails fast on scene→pattern reference gaps, and decodes each element's audio (missing/undecodable samples degrade to `missingElementIds` + a warning rather than throwing). `src/engine/` is the Web Audio playback clock/engine.

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
- `docs/superpowers/2026-07-10-status-and-backlog.md` — **read this first for current state**: shipped milestones, the running end-to-end chain, deferred follow-ups, and next-step candidates.
- `docs/superpowers/specs/` — per-component design specs (workstation / cloud-infra / patch-view / audio-worker / app-api / web-api-integration / phase1-deploy).
- `docs/superpowers/plans/` — implementation plans (all shipped components have one; Patchify Path B and the others are now historical record).

**Reference demo:** its own `README.md` (quick reference) and `SETUP_AND_USAGE.md` (exhaustive setup, migration, and per-parameter tuning tables) are current and worth consulting before deep changes inside the demo — especially SETUP_AND_USAGE.md §6 for the tuning cheat sheet.
