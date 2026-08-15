# LMDJ Stage 8B Pad Capture Kickoff Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `feat/stage8b-pad-capture` from a freshly stacked branch to an
implementation-ready state: keep it correctly synced with the still-open Stage 8
branch, audit the capture reuse boundary Stage 8 deliberately left behind
(S8-D13), and produce an approved Stage 8B Pad Capture design spec — after
which this plan is extended with implementation tasks.

**Architecture:** Stage 8B records microphone / audio-input into a Pad by
producing bounded PCM16 WAV bytes that enter the Core through the *same*
Artifact import boundary Stage 8 built (Application Facade Sample mutations →
Project I/O staging → Cooker preparation). Capture device access, permission,
and monitoring live in the Web Runtime Host / Creator layer; the Core never
learns about `MediaStream` or browser permission state. No implementation
happens under this plan until the design gate closes.

**Tech Stack:** C++20, CMake 3.24+, Emscripten `6.0.5`, Wasm AudioWorklet,
WasmFS OPFS, React `19.2.8`, TypeScript `7.0.2`, Playwright `1.62.1`,
`getUserMedia` / `MediaDevices` (design-gated), JSON Schema 2020-12,
Docusaurus Architecture Portal.

## Global Constraints

- Execute only on `feat/stage8b-pad-capture` in
  `/Users/endaye/Projects/lmdj/.worktrees/stage8b-pad-capture`, stacked from
  Stage 8 commit `6b283fe964198bc114c5e1b1aac15055aadf08a7`. Never implement on
  `main`, and never commit Stage 8B work to `feat/stage8-sample-editor`.
- Never push to `feat/stage8-sample-editor` from this branch or worktree. PR
  [#137](https://github.com/endaye/lmdj/pull/137) is owned by the Stage 8
  completion work and must not be affected by Stage 8B activity.
- The authoritative stage ladder
  (`docs/superpowers/specs/2026-08-08-lmdj-stage8-sample-editor-design.md` §3)
  defines Stage 8B as **microphone / audio-input Pad Capture only**. Automatic
  Slice/Stem belongs to Stage 12, Take/Pattern recording to Stage 9, and a
  browser-wide Sample library to the Stage 2+ open questions. Do not pull them
  into Stage 8B.
- Per S8-D13 and `docs/prd/decision-log.md`, Stage 8B is unimplemented and
  unversioned, and its capture lifecycle is an **open product boundary**. Do
  not silently settle any open product-level Contract or concurrency question
  inside an implementation Task; the design gate (Task 3) is where those
  decisions are made and recorded.
- Preserve every Stage 8 architectural and safety boundary listed in
  `docs/quality/2026-08-15-stage8-sample-editor-handoff.md`: Facade-only Hosts,
  Pad-Slot-owned playback truth, `command_id` + `expected_revision` mutation
  semantics, allocation-free/lock-free audio render paths, fail-closed
  telemetry, single-owner lifecycle cleanup, and bounded browser payloads.
- `lmdj.patch.v1` and `lmdj.materials.v1` remain retired.
- Every Task is one reviewable Conventional Commit. Before every commit: verify
  the branch is not `main`; run the Task-specific verification and
  `scripts/architecture-portal.sh check`; stage only declared files; inspect
  `git diff --cached --name-status` and `git diff --cached --check`; after
  committing inspect `git show --name-status --oneline HEAD`.
- This plan authorizes local commits only. Push, PR creation, merge, tag,
  Release, publication, deployment, and Channel promotion each require
  separate explicit authorization.

---

## Current State (observed 2026-08-15)

| Item | Observed state |
| --- | --- |
| Stage 8 branch | `feat/stage8-sample-editor`, local tip `6b283fe9`, **7 commits ahead of origin** |
| Stage 8 PR | #137, Open, Draft; reflects remote tip `64a8ef0b` only |
| `origin/main` | `a71c62d4`, already merged into the Stage 8 local tip |
| Stage 8B branch | `feat/stage8b-pad-capture` at `6b283fe9`, this worktree |
| Product Build | `1.0.22.0 · canary` (immutable snapshot; belongs to Stage 8) |
| Stage 8B versions | None allocated (S8-D13: unimplemented, unversioned) |

### Stage 8 remaining work (prerequisite, tracked here, executed elsewhere)

The following work finishes Stage 8. It is executed **on
`feat/stage8-sample-editor` in `.worktrees/stage8-sample-editor`**, under
`docs/quality/2026-08-15-stage8-sample-editor-handoff.md` — never under this
plan or on this branch. Stage 8B tracks it only because each step can move the
Stage 8 tip and trigger a resync (see Branch and Sync Discipline).

- [ ] ~~Merge latest `main` and resolve the three known conflicts~~ — already
  done locally in `6b283fe9`; `origin/main` has not advanced past `a71c62d4`.
- [ ] Refresh mutable truth to the post-merge HEAD:
  `docs/quality/2026-08-09-stage8-sample-editor-acceptance.md` (its *current
  reviewed implementation* and external-state sections are stale), the PR #137
  body validation revision, and the handoff document if state changes
  materially. Do not touch the immutable `1.0.22.0` Portal snapshot.
- [ ] Run the post-merge local gates from the handoff §3 (`scripts/core.sh`
  full + stress + proof, dependency/tree/version checks,
  `scripts/architecture-portal.sh check`, Creator / Web Runtime Host / Web
  toolchain conformance gates).
- [ ] Push the 7 local commits, confirm remote SHA equals local HEAD, mark PR
  #137 ready for review, and obtain the exact-head full CI matrix (Core, ASan
  full+stress, coverage, package, Creator, Web Runtime Host, Web toolchain
  conformance, Portal, macOS).
- [ ] Stop. Merge of #137 requires new explicit user authorization.

## Branch and Sync Discipline

Stage 8B stacks on an unmerged branch, so synchronization is one-directional
and rebase-based. Keep `feat/stage8b-pad-capture` a **linear run of commits
sitting directly on the Stage 8 tip** at all times.

**When the Stage 8 branch gains commits** (review fixes, truth refreshes):

```bash
cd /Users/endaye/Projects/lmdj/.worktrees/stage8b-pad-capture
git fetch origin --prune
git rebase feat/stage8-sample-editor
```

**After PR #137 squash-merges into `main`** (the Stage 8 commits will not
exist in `main` as-is, so a plain rebase would replay them):

```bash
git fetch origin main
STAGE8_TIP=$(git rev-parse feat/stage8-sample-editor)
git rebase --onto origin/main "$STAGE8_TIP" feat/stage8b-pad-capture
```

**Never** merge `feat/stage8-sample-editor` into this branch (merge commits
break the final `--onto`), and **never** push, cherry-pick, or otherwise write
Stage 8B commits onto `feat/stage8-sample-editor`.

## Stage 8B Scope Authority

In scope (from the approved stage ladder and S8-D13):

1. Capturing microphone / audio-input into an empty or assigned Pad;
2. Input permission request flow, device selection, and capture monitoring;
3. Capture interruption, cancellation, and failure semantics;
4. Converting captured audio into the existing bounded PCM16 WAV Artifact
   identity and importing it through the existing Facade Sample mutations.

Explicitly not Stage 8B (do not design or implement here):

- Automatic slicing, Chop, Stem separation — Stage 12;
- Take / Pattern / Sequence recording, Quantize, Swing — Stage 9;
- Browser-wide / global Sample library, Asset delete, Artifact GC — open
  Stage 2+ questions;
- Non-destructive processing (Pitch, Reverse, Pan, envelopes, time-stretch) —
  excluded by the Stage 8 design §5 and the open BPM/time-stretch question;
- PWA, cloud, account, deployment, Channel promotion.

## Design Gate: open questions Task 3 must resolve

These are the product-level questions the Stage 8 design (§3, §19.5) and
`docs/prd/decision-log.md` explicitly deferred to Stage 8B. Each needs an
approved decision recorded in the Stage 8B design spec, and the corresponding
rows of `docs/prd/open-questions.md` / `docs/prd/decision-log.md` updated at
approval time:

1. **Permission lifecycle** — when Creator requests `getUserMedia`, how denial,
   revocation mid-capture, and re-request are surfaced; Stage 8 deliberately
   never requests recording permission.
2. **Device selection** — which input devices are offered, where the selection
   lives (Workspace/Host settings per the Provider-selection invariant, never
   Project Truth), and how device disappearance mid-capture behaves.
3. **Capture lifecycle** — arm → record → stop → preview → commit/discard state
   machine; whether capture survives blur/hidden visibility or fails closed
   like Stage 8 Voice ownership; single-owner cleanup.
4. **Monitoring and feedback suppression** — whether input monitoring exists in
   v1 and how speaker-to-microphone feedback is prevented or documented.
5. **Quality and format** — capture sample rate/channel policy and how captured
   audio maps onto the existing bounded PCM16 WAV limits (`1,048,576` imported
   bytes, `240,000` decoded source frames per Pad); what happens when a capture
   exceeds them (truncate, reject, or pre-trim).
6. **Concurrency semantics** — how a capture commit interacts with
   `expected_revision` when the Project changed during recording; no auto-
   rebase, no optimistic success (Stage 8 invariant).
7. **Physical evidence gate** — which real-microphone / real-device sessions
   are required before Stage 8B acceptance, and which stay explicitly deferred.

---

### Task 1: Verify baseline and record sync facts

**Files:**
- No file changes. Read-only audit; findings feed Task 3.

**Interfaces:**
- Consumes: nothing.
- Produces: verified baseline facts (`STAGE8_TIP`, divergence counts) quoted in
  the Task 3 design spec's Current State section.

- [ ] **Step 1: Verify worktree, branch, and stacking base**

```bash
cd /Users/endaye/Projects/lmdj/.worktrees/stage8b-pad-capture
git status --short --branch
git merge-base --is-ancestor feat/stage8-sample-editor HEAD && echo "stacked on stage8 tip"
git rev-parse HEAD feat/stage8-sample-editor
```

Expected: branch `feat/stage8b-pad-capture`, clean tree, "stacked on stage8
tip", both SHAs equal until Stage 8B commits exist.

- [ ] **Step 2: Check whether the Stage 8 tip moved**

```bash
git fetch origin --prune
git rev-list --left-right --count feat/stage8b-pad-capture...feat/stage8-sample-editor
```

Expected: `N 0` (right side zero). A non-zero right side means the Stage 8
branch advanced: run the rebase from Branch and Sync Discipline before
continuing, then re-run this step.

- [ ] **Step 3: Confirm the build baseline is intact**

```bash
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
```

Expected: all pass. This proves the stacked baseline is healthy before any
Stage 8B work; failures here belong to Stage 8, not Stage 8B — report them,
do not fix them on this branch.

### Task 2: Audit the S8-D13 capture reuse boundary

**Files:**
- Read: `packages/application-facade/include/lmdj/facade/application.hpp`
- Read: `packages/application-facade/src/application.cpp`
- Read: `packages/web-runtime-platform/src/control_runtime.cpp`
- Read: `packages/project-io/src/project_store.cpp`
- Read: `docs/superpowers/specs/2026-08-08-lmdj-stage8-sample-editor-design.md`
- No file changes in this Task; the audit result becomes the "Reuse boundary"
  section of the Task 3 design spec.

**Interfaces:**
- Consumes: Task 1's verified baseline.
- Produces: the exact list of existing entry points capture must reuse — the
  Facade Sample import/replace mutation signatures (name, `command_id`,
  `expected_revision`, byte-payload parameters), the Web control-runtime
  transport shape for Sample bytes, and the Project I/O staging/lease
  semantics — quoted with file paths and line numbers in the design spec.

- [ ] **Step 1: Extract the Facade import surface**

```bash
grep -n -i "import\|replace" packages/application-facade/include/lmdj/facade/application.hpp
```

Record every Sample import/replace mutation signature verbatim. Capture must
commit through these mutations; if the audit finds capture *cannot* reuse them
without modification, that is a design-gate finding, not a licence to change
the Facade in this Task.

- [ ] **Step 2: Extract the transport and staging boundaries**

```bash
grep -n -i "sample\|import" packages/web-runtime-platform/src/control_runtime.cpp | head -40
grep -n -i "staging\|lease" packages/project-io/src/project_store.cpp | head -40
```

Record the bounded sidecar payload path (browser payloads never carry raw
Sample bytes outside the bounded verified sidecar boundary) and the
writer-lease / idempotent staging semantics the capture commit will inherit.

- [ ] **Step 3: Record the audit in scratch notes for Task 3**

Write the findings (signatures, payload limits, staging semantics, any reuse
blockers) into the working notes that seed the Task 3 spec. No repository file
changes; nothing to commit for Tasks 1–2.

### Task 3: Author the Stage 8B Pad Capture design spec

**Files:**
- Create: `docs/superpowers/specs/2026-08-15-lmdj-stage8b-pad-capture-design.md`
- Modify: `docs/prd/open-questions.md` (only rows the approved design resolves)
- Modify: `docs/prd/decision-log.md` (append the approved Stage 8B decisions)

**Interfaces:**
- Consumes: Task 1 baseline facts and Task 2 reuse-boundary audit.
- Produces: an approved design spec that becomes the authority for this plan's
  implementation extension (Task 4), plus updated PRD truth.

- [ ] **Step 1: Run the brainstorming skill with the user**

Use superpowers brainstorming to work through the seven Design Gate questions
above with the user. Every decision needs an ID (`S8B-D1`, `S8B-D2`, …)
mirroring the Stage 8 `S8-D*` convention. Do not proceed past this step
without explicit user approval of each decision.

- [ ] **Step 2: Write the design spec**

Mirror the Stage 8 design spec structure: Intent, Approved Decisions table,
Stage Boundary, Scope, Non-goals, the reuse-boundary contract from Task 2,
capture state machine, failure/interruption semantics, acceptance checklist,
and an explicit rollback/compatibility section. State plainly which physical
evidence stays deferred.

- [ ] **Step 3: Update PRD truth in the same commit**

Remove or narrow only the open-question rows the approved design actually
resolves; append the `S8B-D*` decisions to `docs/prd/decision-log.md` dated
with the approval date. Preserve unrelated open questions verbatim.

- [ ] **Step 4: Verify and commit**

```bash
cd /Users/endaye/Projects/lmdj/.worktrees/stage8b-pad-capture
scripts/architecture-portal.sh check
git add docs/superpowers/specs/2026-08-15-lmdj-stage8b-pad-capture-design.md \
        docs/prd/open-questions.md docs/prd/decision-log.md
git diff --cached --name-status && git diff --cached --check
git commit -m "docs(stage8b): approve pad capture design"
git show --name-status --oneline HEAD
```

Expected: portal check passes; exactly the three declared files in the commit.

### Task 4: Extend this plan with implementation tasks (governance gate)

**Files:**
- Modify: `docs/superpowers/plans/2026-08-15-lmdj-stage8b-pad-capture.md`

**Interfaces:**
- Consumes: the approved Task 3 design spec.
- Produces: the full Stage 8B implementation task list appended to this plan.

This is a deliberate gate, not an omission: writing implementation tasks now
would force decisions the design gate owns. After Task 3 approval, extend this
plan using the writing-plans skill with, at minimum, the same skeleton the
Stage 8 plan used (`docs/superpowers/plans/2026-08-09-lmdj-stage8-sample-editor.md`):

- [ ] A File Structure section locking file-level decomposition;
- [ ] Per-task TDD implementation tasks (failing test → run → implement → run →
  commit) across Creator capture UI, Web Runtime Host device/permission layer,
  transport, and the Facade-reusing commit path;
- [ ] A version-integration task allocating the Stage 8B Product Build and
  Module/Contract SemVer bumps (see Version Management below);
- [ ] An immutable Portal snapshot task
  (`scripts/architecture-portal.sh version PRODUCT_BUILD CHANNEL`);
- [ ] A final automated-acceptance task with an explicit deferred physical
  evidence ledger.

Each extension commit to this plan is itself a reviewable
`docs(stage8b): …` Conventional Commit.

> **Task 4 executed 2026-08-15.** The approved design is
> `docs/superpowers/specs/2026-08-15-lmdj-stage8b-pad-capture-design.md`
> (S8B-D1–D10, amended by `docs(stage8b): bind capture context to creator
> host`). Tasks 5–13 below are the implementation extension. A conflict with
> the design returns to design review; implementation must not silently
> weaken it.

---

## Implementation File Structure

All implementation code lives in `apps/creator-web`; the end-to-end suite
lives in `tests/platform/web`. No file under `packages/`, `contracts/`,
`apps/web-runtime-host/src`, or `products/` changes before Task 11.

```text
apps/creator-web/src/capture/capture_buffer.ts        Task 5  ring buffer + envelope (pure)
apps/creator-web/src/capture/wav_encoder.ts           Task 5  deterministic float→PCM16 WAV (pure)
apps/creator-web/src/state/capture_state.ts           Task 6  capture state machine (pure reducer)
apps/creator-web/src/capture/capture_worklet_source.ts Task 7 worklet processor source string
apps/creator-web/src/capture/capture_controller.ts    Task 7  getUserMedia + context + node owner
apps/creator-web/src/components/capture_panel.tsx     Task 8  record/level/trim/commit UI
apps/creator-web/src/runtime/sample_actions.ts        Task 9  captureCommitJourney (modify)
apps/creator-web/src/components/sample_surface.tsx    Task 9  capture entry (modify)
apps/creator-web/test/capture_buffer.test.ts          Task 5
apps/creator-web/test/wav_encoder.test.ts             Task 5
apps/creator-web/test/capture_state.test.ts           Task 6
apps/creator-web/test/capture_controller.test.ts      Task 7
apps/creator-web/test/capture_panel.test.tsx          Task 8
apps/creator-web/test/sample_actions.test.ts          Task 9  (modify)
tests/platform/web/creator/fixtures/make_capture_fixture.mjs  Task 10
tests/platform/web/creator/creator_web_capture.spec.mjs       Task 10
tests/platform/web/playwright.config.mjs                      Task 10 (modify)
```

Design boundaries: `capture_buffer`/`wav_encoder`/`capture_state` are pure and
dependency-free (unit-testable without Web Audio). `capture_controller` owns
every browser resource behind injected dependencies. `capture_panel` renders
state and forwards intents. `sample_actions` stays the only module that talks
to the runtime session.

### Task 5: Capture buffer and deterministic WAV encoder

**Files:**
- Create: `apps/creator-web/src/capture/capture_buffer.ts`
- Create: `apps/creator-web/src/capture/wav_encoder.ts`
- Test: `apps/creator-web/test/capture_buffer.test.ts`
- Test: `apps/creator-web/test/wav_encoder.test.ts`

**Interfaces:**
- Consumes: nothing (pure modules).
- Produces:
  `CAPTURE_SAMPLE_RATE = 48_000`, `CAPTURE_MAX_FRAMES = 2_880_000`,
  `COMMIT_MAX_FRAMES = 240_000`;
  `class CaptureBuffer { constructor(channelCount: 1 | 2); readonly channelCount: number; readonly frameCount: number; readonly atCapacity: boolean; append(channels: readonly Float32Array[]): number; slice(startFrame: number, frameCount: number): Float32Array[]; envelope(bins: number): Float32Array }`;
  `quantizePcm16(value: number): number`;
  `encodePcm16Wav(channels: readonly Float32Array[], sampleRate?: number): Uint8Array`.

- [ ] **Step 1: Write the failing tests**

```ts
// apps/creator-web/test/capture_buffer.test.ts
import {describe, expect, it} from "vitest";
import {CAPTURE_MAX_FRAMES, CaptureBuffer} from "../src/capture/capture_buffer";

describe("CaptureBuffer", () => {
  it("appends batches and reports frame count", () => {
    const buffer = new CaptureBuffer(2);
    const accepted = buffer.append([new Float32Array(4800), new Float32Array(4800)]);
    expect(accepted).toBe(4800);
    expect(buffer.frameCount).toBe(4800);
    expect(buffer.atCapacity).toBe(false);
  });

  it("truncates the batch that crosses 60 s and reports capacity", () => {
    const buffer = new CaptureBuffer(1);
    buffer.append([new Float32Array(CAPTURE_MAX_FRAMES - 100)]);
    const accepted = buffer.append([new Float32Array(4800)]);
    expect(accepted).toBe(100);
    expect(buffer.frameCount).toBe(CAPTURE_MAX_FRAMES);
    expect(buffer.atCapacity).toBe(true);
  });

  it("rejects mismatched channel counts and invalid slices", () => {
    const buffer = new CaptureBuffer(2);
    expect(() => buffer.append([new Float32Array(8)])).toThrow(TypeError);
    buffer.append([new Float32Array(8), new Float32Array(8)]);
    expect(() => buffer.slice(4, 8)).toThrow(RangeError);
  });

  it("slices exact frames per channel and bins a max-abs envelope", () => {
    // Values k/8 are exact in float32, so equality assertions are stable.
    const left = Float32Array.from({length: 8}, (_, i) => (i + 1) / 8);
    const buffer = new CaptureBuffer(1);
    buffer.append([left]);
    const [mono] = buffer.slice(2, 3);
    expect(Array.from(mono)).toEqual([0.375, 0.5, 0.625]);
    const envelope = buffer.envelope(2);
    expect(Array.from(envelope)).toEqual([0.5, 1]);
  });
});
```

```ts
// apps/creator-web/test/wav_encoder.test.ts
import {createHash} from "node:crypto";
import {describe, expect, it} from "vitest";
import {encodePcm16Wav, quantizePcm16} from "../src/capture/wav_encoder";

describe("quantizePcm16", () => {
  it("clamps, scales by 32767, rounds ties away from zero", () => {
    expect(quantizePcm16(0)).toBe(0);
    expect(quantizePcm16(1)).toBe(32767);
    expect(quantizePcm16(-1)).toBe(-32767);
    expect(quantizePcm16(2)).toBe(32767);
    expect(quantizePcm16(-2)).toBe(-32767);
    // Ties-away-from-zero is symmetric; Math.round alone (ties toward +∞)
    // breaks the negative side. Sweep avoids float-exact tie construction.
    for (const value of [0.1, 0.33, 0.5001, 0.9999]) {
      expect(quantizePcm16(-value)).toBe(-quantizePcm16(value));
    }
  });
});

describe("encodePcm16Wav", () => {
  it("produces a byte-stable 48 kHz stereo RIFF with correct sizes", () => {
    const frames = Float32Array.from([0, 0.25, -0.25, 1]);
    const wav = encodePcm16Wav([frames, frames]);
    expect(wav.length).toBe(44 + 4 * 2 * 2);
    const view = new DataView(wav.buffer);
    expect(view.getUint32(24, true)).toBe(48_000);        // sample rate
    expect(view.getUint16(22, true)).toBe(2);             // channels
    expect(view.getUint16(34, true)).toBe(16);            // bits per sample
    expect(view.getUint32(40, true)).toBe(16);            // data chunk bytes
    const digest = createHash("sha256").update(wav).digest("hex");
    const again = createHash("sha256").update(encodePcm16Wav([frames, frames])).digest("hex");
    expect(again).toBe(digest);                            // determinism
  });

  it("rejects empty, mismatched, or >2 channel input", () => {
    expect(() => encodePcm16Wav([])).toThrow(TypeError);
    expect(() => encodePcm16Wav([new Float32Array(2), new Float32Array(3)])).toThrow(TypeError);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix apps/creator-web test -- run capture_buffer wav_encoder`
Expected: FAIL — modules `../src/capture/capture_buffer` and
`../src/capture/wav_encoder` do not exist.

- [ ] **Step 3: Implement the modules**

```ts
// apps/creator-web/src/capture/capture_buffer.ts
export const CAPTURE_SAMPLE_RATE = 48_000;
export const CAPTURE_MAX_FRAMES = 2_880_000; // 60 s at 48 kHz (S8B-D3)
export const COMMIT_MAX_FRAMES = 240_000;    // manifest decoded_frames_per_pad

export class CaptureBuffer {
  readonly channelCount: number;
  #chunks: Float32Array[][];
  #frames = 0;

  constructor(channelCount: 1 | 2) {
    if (channelCount !== 1 && channelCount !== 2) {
      throw new TypeError("Capture channel count must be 1 or 2");
    }
    this.channelCount = channelCount;
    this.#chunks = Array.from({length: channelCount}, () => []);
  }

  get frameCount(): number { return this.#frames; }
  get atCapacity(): boolean { return this.#frames >= CAPTURE_MAX_FRAMES; }

  append(channels: readonly Float32Array[]): number {
    if (channels.length !== this.channelCount ||
        channels.some((c) => !(c instanceof Float32Array) || c.length !== channels[0].length)) {
      throw new TypeError("Capture batch shape is invalid");
    }
    const accepted = Math.min(channels[0].length, CAPTURE_MAX_FRAMES - this.#frames);
    if (accepted <= 0) { return 0; }
    channels.forEach((c, i) => this.#chunks[i].push(c.slice(0, accepted)));
    this.#frames += accepted;
    return accepted;
  }

  slice(startFrame: number, frameCount: number): Float32Array[] {
    if (!Number.isInteger(startFrame) || !Number.isInteger(frameCount) ||
        startFrame < 0 || frameCount <= 0 || startFrame + frameCount > this.#frames) {
      throw new RangeError("Capture slice is out of range");
    }
    return this.#chunks.map((chunks) => {
      const out = new Float32Array(frameCount);
      let base = 0, written = 0;
      for (const chunk of chunks) {
        const from = Math.max(startFrame - base, 0);
        if (from < chunk.length && written < frameCount) {
          const take = Math.min(chunk.length - from, frameCount - written);
          out.set(chunk.subarray(from, from + take), written);
          written += take;
        }
        base += chunk.length;
        if (written === frameCount) { break; }
      }
      return out;
    });
  }

  envelope(bins: number): Float32Array {
    if (!Number.isInteger(bins) || bins <= 0) {
      throw new TypeError("Envelope bin count is invalid");
    }
    const out = new Float32Array(bins);
    if (this.#frames === 0) { return out; }
    const perBin = this.#frames / bins;
    for (const chunks of this.#chunks) {
      let index = 0;
      for (const chunk of chunks) {
        for (const value of chunk) {
          const bin = Math.min(Math.floor(index / perBin), bins - 1);
          const magnitude = Math.abs(value);
          if (magnitude > out[bin]) { out[bin] = magnitude; }
          index += 1;
        }
      }
    }
    return out;
  }
}
```

```ts
// apps/creator-web/src/capture/wav_encoder.ts
import {CAPTURE_SAMPLE_RATE} from "./capture_buffer";

export function quantizePcm16(value: number): number {
  const clamped = Math.min(1, Math.max(-1, value));
  const scaled = clamped * 32767;
  // Deterministic ties-away-from-zero (JS Math.round alone is ties-toward-+∞).
  return Math.sign(scaled) * Math.round(Math.abs(scaled));
}

export function encodePcm16Wav(
  channels: readonly Float32Array[],
  sampleRate: number = CAPTURE_SAMPLE_RATE,
): Uint8Array {
  if (channels.length < 1 || channels.length > 2 ||
      channels.some((c) => !(c instanceof Float32Array) || c.length !== channels[0].length) ||
      channels[0].length === 0) {
    throw new TypeError("WAV encode input is invalid");
  }
  const channelCount = channels.length;
  const frames = channels[0].length;
  const dataBytes = frames * channelCount * 2;
  const bytes = new Uint8Array(44 + dataBytes);
  const view = new DataView(bytes.buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) { bytes[offset + i] = text.charCodeAt(i); }
  };
  ascii(0, "RIFF"); view.setUint32(4, 36 + dataBytes, true); ascii(8, "WAVE");
  ascii(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, channelCount, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channelCount * 2, true);
  view.setUint16(32, channelCount * 2, true); view.setUint16(34, 16, true);
  ascii(36, "data"); view.setUint32(40, dataBytes, true);
  let offset = 44;
  for (let frame = 0; frame < frames; frame += 1) {
    for (let channel = 0; channel < channelCount; channel += 1) {
      view.setInt16(offset, quantizePcm16(channels[channel][frame]), true);
      offset += 2;
    }
  }
  return bytes;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix apps/creator-web test -- run capture_buffer wav_encoder`
Expected: PASS (all cases).

- [ ] **Step 5: Verify and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web/src/capture/capture_buffer.ts \
        apps/creator-web/src/capture/wav_encoder.ts \
        apps/creator-web/test/capture_buffer.test.ts \
        apps/creator-web/test/wav_encoder.test.ts
git diff --cached --name-status && git diff --cached --check
git commit -m "feat(creator): add capture buffer and wav encoder"
git show --name-status --oneline HEAD
```

### Task 6: Capture state machine

**Files:**
- Create: `apps/creator-web/src/state/capture_state.ts`
- Test: `apps/creator-web/test/capture_state.test.ts`

**Interfaces:**
- Consumes: `COMMIT_MAX_FRAMES` from Task 5.
- Produces:
  `type CapturePhase = "idle" | "requesting-permission" | "permission-error" | "recording" | "trimming" | "committing" | "commit-error"`;
  `type CaptureStopReason = "user" | "capacity" | "blur" | "hidden" | "device-lost" | "permission-revoked"`;
  `interface CaptureState { phase: CapturePhase; stopReason: CaptureStopReason | null; frameCount: number; peak: number; selectionStart: number; selectionFrames: number; errorMessage: string | null; conflict: boolean }`;
  `const initialCaptureState: CaptureState`;
  `type CaptureEvent = {kind: "record"} | {kind: "granted"} | {kind: "denied"; message: string} | {kind: "frames"; frames: number; peak: number} | {kind: "stop"; reason: CaptureStopReason} | {kind: "select"; start: number; frames: number} | {kind: "discard"} | {kind: "commit"} | {kind: "committed"} | {kind: "commit-failed"; message: string; conflict: boolean}`;
  `function reduceCapture(state: CaptureState, event: CaptureEvent): CaptureState`.

- [ ] **Step 1: Write the failing test**

```ts
// apps/creator-web/test/capture_state.test.ts
import {describe, expect, it} from "vitest";
import {initialCaptureState, reduceCapture} from "../src/state/capture_state";

const run = (events: Parameters<typeof reduceCapture>[1][]) =>
  events.reduce(reduceCapture, initialCaptureState);

describe("reduceCapture", () => {
  it("follows the happy path record→stop→trim→commit→idle", () => {
    let state = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 96_000, peak: 0.5},
      {kind: "stop", reason: "user"},
    ]);
    expect(state.phase).toBe("trimming");
    expect(state.selectionFrames).toBe(96_000); // clamped default ≤ 240,000
    state = reduceCapture(state, {kind: "commit"});
    expect(state.phase).toBe("committing");
    state = reduceCapture(state, {kind: "committed"});
    expect(state).toEqual(initialCaptureState);
  });

  it("clamps the default selection to COMMIT_MAX_FRAMES", () => {
    const state = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 2_880_000, peak: 1},
      {kind: "stop", reason: "capacity"},
    ]);
    expect(state.selectionFrames).toBe(240_000);
    expect(state.stopReason).toBe("capacity");
  });

  it("rejects selections above COMMIT_MAX_FRAMES", () => {
    const trimming = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 480_000, peak: 0.2},
      {kind: "stop", reason: "hidden"},
    ]);
    const rejected = reduceCapture(trimming, {kind: "select", start: 0, frames: 240_001});
    expect(rejected).toBe(trimming); // unchanged
  });

  it("keeps the buffer through every interruption and commit failure", () => {
    const trimming = run([
      {kind: "record"}, {kind: "granted"},
      {kind: "frames", frames: 48_000, peak: 0.4},
      {kind: "stop", reason: "device-lost"},
    ]);
    expect(trimming.frameCount).toBe(48_000);
    const failed = reduceCapture(
      reduceCapture(trimming, {kind: "commit"}),
      {kind: "commit-failed", message: "conflict", conflict: true});
    expect(failed.phase).toBe("commit-error");
    expect(failed.frameCount).toBe(48_000);
    expect(failed.conflict).toBe(true);
    expect(reduceCapture(failed, {kind: "commit"}).phase).toBe("committing");
    expect(reduceCapture(failed, {kind: "discard"})).toEqual(initialCaptureState);
  });

  it("routes permission denial to a retryable error state", () => {
    const denied = run([{kind: "record"}, {kind: "denied", message: "blocked"}]);
    expect(denied.phase).toBe("permission-error");
    expect(reduceCapture(denied, {kind: "record"}).phase).toBe("requesting-permission");
  });

  it("ignores events that are invalid for the phase", () => {
    expect(reduceCapture(initialCaptureState, {kind: "committed"})).toBe(initialCaptureState);
    expect(reduceCapture(initialCaptureState, {kind: "stop", reason: "user"})).toBe(initialCaptureState);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm --prefix apps/creator-web test -- run capture_state`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the reducer**

```ts
// apps/creator-web/src/state/capture_state.ts
import {COMMIT_MAX_FRAMES} from "../capture/capture_buffer";

export type CapturePhase =
  "idle" | "requesting-permission" | "permission-error" |
  "recording" | "trimming" | "committing" | "commit-error";
export type CaptureStopReason =
  "user" | "capacity" | "blur" | "hidden" | "device-lost" | "permission-revoked";

export interface CaptureState {
  phase: CapturePhase;
  stopReason: CaptureStopReason | null;
  frameCount: number;
  peak: number;
  selectionStart: number;
  selectionFrames: number;
  errorMessage: string | null;
  conflict: boolean;
}

export const initialCaptureState: CaptureState = Object.freeze({
  phase: "idle", stopReason: null, frameCount: 0, peak: 0,
  selectionStart: 0, selectionFrames: 0, errorMessage: null, conflict: false,
});

export type CaptureEvent =
  | {kind: "record"} | {kind: "granted"} | {kind: "denied"; message: string}
  | {kind: "frames"; frames: number; peak: number}
  | {kind: "stop"; reason: CaptureStopReason}
  | {kind: "select"; start: number; frames: number}
  | {kind: "discard"} | {kind: "commit"} | {kind: "committed"}
  | {kind: "commit-failed"; message: string; conflict: boolean};

export function reduceCapture(state: CaptureState, event: CaptureEvent): CaptureState {
  switch (event.kind) {
    case "record":
      return state.phase === "idle" || state.phase === "permission-error"
        ? {...initialCaptureState, phase: "requesting-permission"} : state;
    case "granted":
      return state.phase === "requesting-permission" ? {...state, phase: "recording"} : state;
    case "denied":
      return state.phase === "requesting-permission"
        ? {...state, phase: "permission-error", errorMessage: event.message} : state;
    case "frames":
      return state.phase === "recording"
        ? {...state, frameCount: event.frames, peak: event.peak} : state;
    case "stop":
      return state.phase === "recording" && state.frameCount > 0
        ? {...state, phase: "trimming", stopReason: event.reason, peak: 0,
           selectionStart: 0, selectionFrames: Math.min(state.frameCount, COMMIT_MAX_FRAMES)}
        : state.phase === "recording" ? initialCaptureState : state;
    case "select":
      return (state.phase === "trimming" || state.phase === "commit-error") &&
             Number.isInteger(event.start) && Number.isInteger(event.frames) &&
             event.start >= 0 && event.frames > 0 &&
             event.frames <= COMMIT_MAX_FRAMES &&
             event.start + event.frames <= state.frameCount
        ? {...state, phase: "trimming", selectionStart: event.start,
           selectionFrames: event.frames, errorMessage: null, conflict: false}
        : state;
    case "discard":
      return state.phase === "trimming" || state.phase === "commit-error"
        ? initialCaptureState : state;
    case "commit":
      return (state.phase === "trimming" || state.phase === "commit-error") &&
             state.selectionFrames > 0
        ? {...state, phase: "committing", errorMessage: null, conflict: false} : state;
    case "committed":
      return state.phase === "committing" ? initialCaptureState : state;
    case "commit-failed":
      return state.phase === "committing"
        ? {...state, phase: "commit-error", errorMessage: event.message,
           conflict: event.conflict}
        : state;
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm --prefix apps/creator-web test -- run capture_state`
Expected: PASS.

- [ ] **Step 5: Verify and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web/src/state/capture_state.ts apps/creator-web/test/capture_state.test.ts
git diff --cached --name-status && git diff --cached --check
git commit -m "feat(creator): add capture state machine"
git show --name-status --oneline HEAD
```

### Task 7: Capture controller and worklet source

**Files:**
- Create: `apps/creator-web/src/capture/capture_worklet_source.ts`
- Create: `apps/creator-web/src/capture/capture_controller.ts`
- Test: `apps/creator-web/test/capture_controller.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks (batches are delivered to a listener;
  the panel in Task 8 feeds them into `CaptureBuffer`).
- Produces:
  `const CAPTURE_WORKLET_NAME = "lmdj-capture-recorder"`;
  `const CAPTURE_WORKLET_SOURCE: string`;
  `const CAPTURE_BATCH_FRAMES = 4_800` (100 ms at 48 kHz, S8B batching rule);
  `class CapturePermissionError extends Error`;
  `interface CaptureListener { onBatch(channels: Float32Array[], peak: number): void; onEnded(reason: "device-lost" | "permission-revoked"): void }`;
  `interface CaptureControllerDeps { getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream>; createContext(): {sampleRate: number; audioWorklet: {addModule(url: string): Promise<void>}; createMediaStreamSource(stream: MediaStream): {connect(node: unknown): void; disconnect(): void}; close(): Promise<void>}; createNode(context: unknown, name: string): {port: {onmessage: ((event: {data: {channels: Float32Array[]; peak: number}}) => void) | null}; disconnect(): void}; createModuleUrl(source: string): string; revokeModuleUrl(url: string): void }`;
  `class CaptureController { constructor(deps: CaptureControllerDeps, listener: CaptureListener); readonly channelCount: number; start(): Promise<void>; stop(): Promise<void> }`.

Key rules the test locks in: `getUserMedia` is called with
`{audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: false}}`
(S8B-D7); the module URL is a Blob URL so the built bundle gains no new
distribution asset; `stop()` is idempotent and releases track → node → source
→ context → module URL in one owner (S8B-D5/§7); a track `ended` event maps to
`onEnded("device-lost")`.

The worklet processor ships as a source string, so it must also be tested
directly — evaluate `CAPTURE_WORKLET_SOURCE` in the test with stub globals
(`class AudioWorkletProcessor {constructor() {this.port = {postMessage}}}` and
a `registerProcessor` that captures the class), instantiate the processor, and
drive `process([[frames]])` with 128-frame quanta. Assert: no message before
4,800 frames accumulate; exactly one message at 4,800 with the right peak; and
— the boundary case — feeding quanta until a single quantum straddles the
batch edge still posts correctly and keeps accepting frames without throwing
(the batch is nulled after each post and must be reallocated inside the loop).

- [ ] **Step 1: Write the failing test** — fake deps record every call:

```ts
// apps/creator-web/test/capture_controller.test.ts
import {describe, expect, it, vi} from "vitest";
import {CaptureController, CapturePermissionError} from "../src/capture/capture_controller";
import {CAPTURE_WORKLET_SOURCE} from "../src/capture/capture_worklet_source";

function makeDeps(overrides: Record<string, unknown> = {}) {
  const track = {
    stopped: 0, stop() { this.stopped += 1; },
    onended: null as (() => void) | null,
    addEventListener(name: string, handler: () => void) { if (name === "ended") this.onended = handler; },
    removeEventListener() {},
    getSettings: () => ({channelCount: 1}),
  };
  const stream = {getAudioTracks: () => [track]};
  const source = {connected: 0, connect() { this.connected += 1; }, disconnect: vi.fn()};
  const node = {port: {onmessage: null}, disconnect: vi.fn()};
  const context = {
    sampleRate: 48_000, closed: 0,
    audioWorklet: {added: [] as string[], async addModule(url: string) { this.added.push(url); }},
    createMediaStreamSource: () => source,
    async close() { this.closed += 1; },
  };
  return {
    track, stream, source, node, context,
    deps: {
      getUserMedia: vi.fn(async () => stream),
      createContext: () => context,
      createNode: () => node,
      createModuleUrl: vi.fn(() => "blob:capture"),
      revokeModuleUrl: vi.fn(),
      ...overrides,
    },
  };
}

describe("CaptureController", () => {
  it("requests raw audio constraints and wires the graph", async () => {
    const {deps, context, source} = makeDeps();
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    await controller.start();
    expect(deps.getUserMedia).toHaveBeenCalledWith({audio: {
      echoCancellation: false, noiseSuppression: false, autoGainControl: false,
    }});
    expect(deps.createModuleUrl).toHaveBeenCalledWith(CAPTURE_WORKLET_SOURCE);
    expect(context.audioWorklet.added).toEqual(["blob:capture"]);
    expect(source.connected).toBe(1);
    expect(controller.channelCount).toBe(1);
  });

  it("maps getUserMedia rejection to CapturePermissionError", async () => {
    const {deps} = makeDeps({getUserMedia: vi.fn(async () => { throw new DOMException("denied", "NotAllowedError"); })});
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    await expect(controller.start()).rejects.toBeInstanceOf(CapturePermissionError);
  });

  it("forwards worklet batches to the listener", async () => {
    const {deps, node} = makeDeps();
    const onBatch = vi.fn();
    const controller = new CaptureController(deps as never, {onBatch, onEnded: vi.fn()});
    await controller.start();
    node.port.onmessage?.({data: {channels: [new Float32Array(4800)], peak: 0.7}});
    expect(onBatch).toHaveBeenCalledWith([expect.any(Float32Array)], 0.7);
  });

  it("stops once as the single owner and is idempotent", async () => {
    const {deps, track, node, source, context} = makeDeps();
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded: vi.fn()});
    await controller.start();
    await controller.stop();
    await controller.stop();
    expect(track.stopped).toBe(1);
    expect(node.disconnect).toHaveBeenCalledTimes(1);
    expect(source.disconnect).toHaveBeenCalledTimes(1);
    expect(context.closed).toBe(1);
    expect(deps.revokeModuleUrl).toHaveBeenCalledTimes(1);
  });

  it("reports track end as device loss", async () => {
    const {deps, track} = makeDeps();
    const onEnded = vi.fn();
    const controller = new CaptureController(deps as never, {onBatch: vi.fn(), onEnded});
    await controller.start();
    track.onended?.();
    expect(onEnded).toHaveBeenCalledWith("device-lost");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm --prefix apps/creator-web test -- run capture_controller`
Expected: FAIL — modules do not exist.

- [ ] **Step 3: Implement worklet source and controller**

`capture_worklet_source.ts` exports the processor as a template string; the
processor accumulates input frames into per-channel arrays and posts one
message per `CAPTURE_BATCH_FRAMES` (4,800) frames — never per 128-frame
quantum — with the batch peak:

```ts
// apps/creator-web/src/capture/capture_worklet_source.ts
export const CAPTURE_WORKLET_NAME = "lmdj-capture-recorder";
export const CAPTURE_BATCH_FRAMES = 4_800;

export const CAPTURE_WORKLET_SOURCE = `
class LmdjCaptureRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.batch = null;
    this.filled = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) { return true; }
    const frames = input[0].length;
    let offset = 0;
    while (offset < frames) {
      // Allocate inside the loop: a quantum that crosses a batch boundary
      // posts (and nulls) the batch mid-loop, then keeps writing.
      if (this.batch === null) {
        this.batch = input.map(() => new Float32Array(${CAPTURE_BATCH_FRAMES}));
      }
      const take = Math.min(frames - offset, ${CAPTURE_BATCH_FRAMES} - this.filled);
      for (let channel = 0; channel < this.batch.length; channel += 1) {
        const data = input[channel] ?? input[0];
        this.batch[channel].set(data.subarray(offset, offset + take), this.filled);
      }
      this.filled += take;
      offset += take;
      if (this.filled === ${CAPTURE_BATCH_FRAMES}) {
        let peak = 0;
        for (const channel of this.batch) {
          for (const value of channel) {
            const magnitude = Math.abs(value);
            if (magnitude > peak) { peak = magnitude; }
          }
        }
        this.port.postMessage(
          {channels: this.batch, peak},
          this.batch.map((channel) => channel.buffer));
        this.batch = null;
        this.filled = 0;
      }
    }
    return true;
  }
}
registerProcessor("${CAPTURE_WORKLET_NAME}", LmdjCaptureRecorder);
`;
```

`capture_controller.ts` owns start/stop:

```ts
// apps/creator-web/src/capture/capture_controller.ts
import {CAPTURE_WORKLET_NAME, CAPTURE_WORKLET_SOURCE} from "./capture_worklet_source";

export class CapturePermissionError extends Error {}

// (CaptureListener / CaptureControllerDeps exactly as in the Interfaces block)

export class CaptureController {
  #deps; #listener;
  #resources: null | {track; node; source; context; moduleUrl: string; onended: () => void} = null;
  channelCount = 0;

  constructor(deps, listener) { this.#deps = deps; this.#listener = listener; }

  async start(): Promise<void> {
    if (this.#resources !== null) { throw new Error("Capture is already active"); }
    let stream: MediaStream;
    try {
      stream = await this.#deps.getUserMedia({audio: {
        echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      }});
    } catch (error) {
      throw new CapturePermissionError(
        error instanceof DOMException ? error.name : "getUserMedia failed");
    }
    const track = stream.getAudioTracks()[0];
    this.channelCount = track.getSettings().channelCount === 2 ? 2 : 1;
    const context = this.#deps.createContext();
    const moduleUrl = this.#deps.createModuleUrl(CAPTURE_WORKLET_SOURCE);
    await context.audioWorklet.addModule(moduleUrl);
    const source = context.createMediaStreamSource(stream);
    const node = this.#deps.createNode(context, CAPTURE_WORKLET_NAME);
    node.port.onmessage = (event) => this.#listener.onBatch(event.data.channels, event.data.peak);
    source.connect(node);
    const onended = () => this.#listener.onEnded("device-lost");
    track.addEventListener("ended", onended);
    this.#resources = {track, node, source, context, moduleUrl, onended};
  }

  async stop(): Promise<void> {
    const resources = this.#resources;
    if (resources === null) { return; }
    this.#resources = null;
    resources.track.removeEventListener("ended", resources.onended);
    resources.track.stop();               // microphone indicator goes dark here
    resources.node.port.onmessage = null;
    resources.node.disconnect();
    resources.source.disconnect();
    await resources.context.close();
    this.#deps.revokeModuleUrl(resources.moduleUrl);
  }
}

export function browserCaptureDeps(): CaptureControllerDeps {
  return {
    getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
    createContext: () => new AudioContext({sampleRate: 48_000}),
    createNode: (context, name) => new AudioWorkletNode(context, name),
    createModuleUrl: (source) =>
      URL.createObjectURL(new Blob([source], {type: "text/javascript"})),
    revokeModuleUrl: (url) => URL.revokeObjectURL(url),
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm --prefix apps/creator-web test -- run capture_controller`
Expected: PASS.

- [ ] **Step 5: Verify and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web/src/capture/capture_worklet_source.ts \
        apps/creator-web/src/capture/capture_controller.ts \
        apps/creator-web/test/capture_controller.test.ts
git diff --cached --name-status && git diff --cached --check
git commit -m "feat(creator): add capture controller and worklet"
git show --name-status --oneline HEAD
```

### Task 8: Capture panel UI

**Files:**
- Create: `apps/creator-web/src/components/capture_panel.tsx`
- Test: `apps/creator-web/test/capture_panel.test.tsx`

**Interfaces:**
- Consumes: `CaptureBuffer`, `COMMIT_MAX_FRAMES` (Task 5);
  `reduceCapture`, `initialCaptureState`, `CaptureState`, `CaptureEvent`
  (Task 6); `CaptureController`, `CapturePermissionError`,
  `browserCaptureDeps` (Task 7).
- Produces:
  `interface CapturePanelProps { padLabel: string; onCommit(buffer: CaptureBuffer, selection: {startFrame: number; frameCount: number}): Promise<{kind: "committed"} | {kind: "conflict"; message: string} | {kind: "failed"; message: string}>; onClose(): void; makeController?(listener: CaptureListener): CaptureController }`;
  `function CapturePanel(props: CapturePanelProps): JSX.Element`.

Behavior locked by the component test (Testing Library, patterns as in
`sample_controls.test.tsx`):

1. Renders a `button` named `Record into ${padLabel}`; pressing it drives
   `record` → controller `start()`; denial renders `role="alert"` text with a
   retryable Record button (S8B-D2).
2. While recording: elapsed-time text, `role="meter"` level element fed by
   batch peaks, growing waveform `<canvas>` from `CaptureBuffer.envelope`,
   and a Stop button. Batches append into a `CaptureBuffer`; when
   `atCapacity` becomes true the panel dispatches `stop("capacity")` and
   calls controller `stop()` (S8B-D3).
3. `window` `blur` and `document` `visibilitychange`(hidden) listeners are
   registered only while `phase === "recording"`, dispatch the matching stop
   reason, and are removed on cleanup (S8B-D5). Controller `onEnded` maps to
   `stop("device-lost")`.
4. Trimming: selection sliders clamp to `COMMIT_MAX_FRAMES`; per-reason stop
   message text is visible; Preview of committed behavior is not duplicated
   here (post-commit trim/preview already exists in the Sample surface).
5. Commit and Discard buttons call `props.onCommit` / reset; a `conflict`
   result renders the retry affordance with the buffer intact (S8B-D6).
6. Unmount while recording performs the single-owner cleanup exactly once.

- [ ] **Step 1: Write the failing component test** covering behaviors 1–6
  with a fake controller injected through `makeController` (no real Web
  Audio in jsdom).
- [ ] **Step 2: Run** `npm --prefix apps/creator-web test -- run capture_panel`
  — expected FAIL.
- [ ] **Step 3: Implement `CapturePanel`** with `useReducer(reduceCapture,
  initialCaptureState)`, a `useRef<CaptureBuffer | null>`, and a
  `useRef<CaptureController | null>`; default `makeController` builds
  `new CaptureController(browserCaptureDeps(), listener)`.
- [ ] **Step 4: Run** the test again — expected PASS. Also run the full
  creator suite: `npm --prefix apps/creator-web test -- run` — expected PASS.
- [ ] **Step 5: Verify and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web/src/components/capture_panel.tsx \
        apps/creator-web/test/capture_panel.test.tsx
git diff --cached --name-status && git diff --cached --check
git commit -m "feat(creator): add capture panel ui"
git show --name-status --oneline HEAD
```

### Task 9: Wire capture into the Sample surface and commit journey

**Files:**
- Modify: `apps/creator-web/src/runtime/sample_actions.ts`
- Modify: `apps/creator-web/src/components/sample_surface.tsx`
- Test: `apps/creator-web/test/sample_actions.test.ts` (extend)
- Test: `apps/creator-web/test/workspace_shell.test.tsx` or
  `apps/creator-web/test/sample_controls.test.tsx` (extend where the Sample
  surface entry is asserted today — follow the existing surface tests)

**Interfaces:**
- Consumes: `importAssignSampleJourney`, `SampleImportOptions`,
  `SampleMutationResolution`, `SAMPLE_CONFLICT_MESSAGE`
  (`sample_actions.ts`); `CaptureBuffer`, `encodePcm16Wav`,
  `COMMIT_MAX_FRAMES` (Task 5); `CapturePanel` (Task 8).
- Produces:
  `function captureCommitJourney(session: CreatorSampleRuntimeSession, buffer: CaptureBuffer, selection: {startFrame: number; frameCount: number}, options: SampleImportOptions): Promise<SampleMutationResolution>`.

Rules locked by tests:

1. `captureCommitJourney` validates `selection.frameCount <= COMMIT_MAX_FRAMES`
   (TypeError otherwise), encodes `buffer.slice(...)` with `encodePcm16Wav`,
   wraps it as `new File([wav], "capture.wav", {type: "audio/wav"})`, and
   delegates to `importAssignSampleJourney` unchanged — same journey, same
   conflict classification, no second commit path.
2. `options.expectedRevision` is read from current Project state at the
   moment the user presses Commit (S8B-D6); the Sample surface passes it the
   same way the file-import entry does today.
3. The Sample surface shows the capture entry for the selected Pad; recording
   onto an assigned Pad goes through the existing Replace confirmation before
   the panel opens (S8-D12); a committed capture then flows through the
   existing post-import selection/waveform behavior with no capture-specific
   branches.
4. A conflict resolution from the journey surfaces as the panel's `conflict`
   result: buffer intact, retry re-encodes the same bytes with a fresh
   `command_id`/`expectedRevision` (asserted by calling the fake session
   twice and comparing the received bytes).

- [ ] **Step 1: Write the failing tests** — extend `sample_actions.test.ts`
  (journey rules 1, 2, 4 against the existing fake
  `CreatorSampleRuntimeSession`) and the surface test (rule 3).
- [ ] **Step 2: Run** `npm --prefix apps/creator-web test -- run` — expected
  FAIL on the new cases only.
- [ ] **Step 3: Implement** `captureCommitJourney` in `sample_actions.ts` and
  the surface entry in `sample_surface.tsx`.
- [ ] **Step 4: Run** `npm --prefix apps/creator-web test -- run` — expected
  PASS, no existing case regressed. Also run the build gate:
  `bash scripts/creator-web.sh build` — expected success with no new
  distribution asset beyond the manifest `expected_assets` roles.
- [ ] **Step 5: Verify and commit**

```bash
scripts/architecture-portal.sh check
git add apps/creator-web/src/runtime/sample_actions.ts \
        apps/creator-web/src/components/sample_surface.tsx \
        apps/creator-web/test/sample_actions.test.ts \
        <extended surface test file>
git diff --cached --name-status && git diff --cached --check
git commit -m "feat(creator): wire capture into sample surface"
git show --name-status --oneline HEAD
```

### Task 10: Chromium fake-device end-to-end journeys

**Files:**
- Create: `tests/platform/web/creator/fixtures/make_capture_fixture.mjs`
- Create: `tests/platform/web/creator/creator_web_capture.spec.mjs`
- Modify: `tests/platform/web/playwright.config.mjs`

**Interfaces:**
- Consumes: the built Creator (`bash scripts/creator-web.sh build`) served by
  the existing toolchain server; UI roles/names from Tasks 8–9.
- Produces: the `creator-capture-chromium` and
  `creator-capture-denied-chromium` Playwright projects that gate Stage 8B
  acceptance (S8B-D8).

Plumbing rules:

1. `make_capture_fixture.mjs` exports
   `ensureCaptureFixture(path: string): string` — synthesizes a deterministic
   2 s, 48 kHz, mono, 440 Hz PCM16 WAV (same quantization rule as
   `wav_encoder.ts`) and writes it only when absent; the config calls it at
   load time so the file exists before browser launch.
2. `playwright.config.mjs` adds
   `const captureSpec = /creator_web_capture\.spec\.mjs/;` and two projects:
   `creator-capture-chromium` with
   `launchOptions.args: ["--use-fake-device-for-media-stream", "--use-file-for-fake-audio-capture=<fixture>", "--use-fake-ui-for-media-stream"]`
   (auto-granted mic streaming the fixture) and
   `creator-capture-denied-chromium` with only
   `--use-fake-device-for-media-stream` (headless prompt auto-dismisses →
   deterministic `NotAllowedError`). Both use `testMatch: captureSpec`;
   existing projects are untouched.
3. The spec skips per project:
   granted-path tests run under `creator-capture-chromium`; the denial test
   runs under `creator-capture-denied-chromium`
   (`test.skip(test.info().project.name !== ...)`).

Journeys the spec must cover (mirroring `creator_web_sample_editor.spec.mjs`
patterns for project open and pad naming):

- record → stop → trim → commit on an empty Pad → the Pad reads as assigned,
  waveform visible, trigger press produces the active-Voice UI state;
- record until the 60 s cap is simulated — instead of waiting, assert the
  5 s selection clamp: record ≥6 s of fixture audio, stop, verify the commit
  control reports the ≤5 s selection;
- blur during recording (`window.dispatchEvent(new Event("blur"))`, pattern
  from `creator_web_lifecycle.spec.mjs:446`) → recording stops, trim view
  retains the buffer;
- conflict: mutate the Project revision through a second import before
  pressing Commit → conflict message visible, Retry succeeds;
- denial project: press Record → `role="alert"` permission message, Record
  remains enabled;
- privacy assertion (pattern from `creator_web_sample_editor.spec.mjs:505`):
  page text never leaks device identifiers, `file://`, or filesystem paths.

- [ ] **Step 1: Write fixture generator + config projects + the spec.**
- [ ] **Step 2: Build and run.**

```bash
bash scripts/creator-web.sh build
npm --prefix tests/platform/web test -- --project=creator-capture-chromium \
  "$PWD/tests/platform/web/creator/creator_web_capture.spec.mjs"
npm --prefix tests/platform/web test -- --project=creator-capture-denied-chromium \
  "$PWD/tests/platform/web/creator/creator_web_capture.spec.mjs"
```

Expected: all journeys PASS. Rebuild stale Web artifacts before diagnosing a
browser failure (handoff rule).

- [ ] **Step 3: Run the existing creator specs unchanged** —
  `npm --prefix tests/platform/web test -- --project=creator-sample-chromium`
  — expected PASS (no regression from the config edit).
- [ ] **Step 4: Verify and commit**

```bash
scripts/architecture-portal.sh check
git add tests/platform/web/creator/fixtures/make_capture_fixture.mjs \
        tests/platform/web/creator/creator_web_capture.spec.mjs \
        tests/platform/web/playwright.config.mjs
git diff --cached --name-status && git diff --cached --check
git commit -m "test(creator): add fake-device capture e2e"
git show --name-status --oneline HEAD
```

### Task 11: Version integration and Portal current truth

**Files:**
- Modify: `products/lmdj/version.json`, `products/lmdj/assembly.json`
  (creator-web version identity — derived paths per the version tooling, do
  not hand-copy generated files)
- Modify: the Portal current Creator page under
  `apps/architecture-portal/docs/` (capture behavior section)
- Test: `python3 tests/build/version_test.py`,
  `python3 scripts/version.py verify --version-file products/lmdj/version.json`

Steps:

- [ ] Allocate the next Product Build after `1.0.22.0` and the `creator-web`
  minor bump **only** through `scripts/version.py` /
  `scripts/architecture-portal.sh` flows per
  `docs/governance/version-management.md` — never hand-enter identities
  (CLAUDE.md portal rule). `web-runtime-host` is bumped only if Tasks 5–10
  actually changed its files (expected: they did not — verify with
  `git log --oneline <plan-start>..HEAD -- apps/web-runtime-host/`).
- [ ] Update the Portal current Creator page with the capture journey,
  the 60 s buffer / 5 s commit boundary, and the deferred-evidence note.
- [ ] Run: both version tests above plus `scripts/architecture-portal.sh
  check` — expected PASS.
- [ ] Commit as `feat(product): integrate stage 8b versions and portal truth`
  with only the declared version/portal files staged.

### Task 12: Immutable Portal snapshot

- [ ] After Task 11 is committed and the Product Build is allocated, run
  `scripts/architecture-portal.sh version <PRODUCT_BUILD> canary` (exact
  Build from Task 11 — Product Build or Assembly changes cannot declare
  `Documentation impact: none`).
- [ ] Run `scripts/architecture-portal.sh check`; commit the snapshot as
  `docs(portal): freeze stage 8b portal snapshot`. Do not modify the existing
  `1.0.22.0` snapshot.

### Task 13: Automated acceptance record and deferred ledger

**Files:**
- Create: `docs/quality/<date>-stage8b-pad-capture-acceptance.md`

- [ ] Run the full local gate set and record each result against the exact
  revision it ran on (handoff evidence rule): creator unit suite, creator
  build, both capture Playwright projects, existing creator/sample specs,
  `scripts/core.sh test dev fast` (Core untouched — record it as the
  no-regression proof), version tests, portal check.
- [ ] Record the deferred ledger explicitly: real-microphone hearing, Safari
  desktop capture behavior, iPadOS capture behavior, external audio
  interface — all `deferred / unverified` until actually performed (S8B-D8).
- [ ] Commit as `docs(quality): record stage 8b pad capture acceptance`.
- [ ] Stop. Push, PR creation, merge, tag, Release, deployment, and Channel
  promotion each require new explicit authorization; PR sequencing also
  depends on Stage 8 (#137) merging first (see Branch and Sync Discipline).

## Requirement-to-Task Coverage

| Design requirement | Tasks |
| --- | --- |
| S8B-D1 default device | 7 (constraints), 10 (fake device) |
| S8B-D2 permission on gesture, retryable denial | 7, 8, 10 |
| S8B-D3 60 s buffer / 5 s commit clamp | 5, 6, 8, 9, 10 |
| S8B-D4 no monitoring, level meter | 7 (no output routing), 8 |
| S8B-D5 blur/hidden stop, buffer retained | 6, 8, 10 |
| S8B-D6 commit-time session, conflict retry | 6, 9, 10 |
| S8B-D7 raw constraints | 7 |
| S8B-D8 fake-device gate + deferred ledger | 10, 13 |
| S8B-D9 AudioWorklet pipeline, deterministic PCM16 | 5, 7 |
| S8B-D10 shared quota stays out of scope | File Structure (no `packages/`/`contracts/` edits before Task 11) |
| Version/Portal governance | 11, 12, 13 |

---

## Documentation Impact

Documentation impact: **required at Task 3 and beyond** —
`docs/prd/open-questions.md`, `docs/prd/decision-log.md`, and the new design
spec change in Task 3; the Task 4 extension will declare Portal route impact
for the implementation stage (a Stage 8B Product Build cannot declare
`Documentation impact: none`). The initial commit of this plan document itself
touches no Portal route, active manifest, or derived identity; it is covered
by `scripts/architecture-portal.sh check` before commit.

## Version Management

Version impact: **none for this plan document and Tasks 1–3** — Stage 8B is
recorded in the decision log as unimplemented and unversioned (S8-D13), and
nothing in Tasks 1–3 changes active manifests, Module versions, Contract
versions, or Product Builds.

Planned impact, allocated only in the Task 4 extension after design approval:

- A new Product Build (`MILESTONE.MINOR.BUILD.PATCH`, next after `1.0.22.0`,
  allocated through the portal/version tooling — never hand-entered);
- SemVer bumps for the Modules the approved design actually touches (per the
  amended design and Task 2 audit: `creator-web` minor only;
  `web-runtime-host` only if its files actually change; Facade/Contract
  bumps: none — the audit found no reuse blocker);
- Contract changes only via new Contract SemVer on stable Contract IDs; the
  retired contracts stay retired.

## Completion Boundary

This plan ends when Task 3's approved design spec is committed and Task 4 has
extended this plan with implementation tasks. Push of `feat/stage8b-pad-capture`,
PR creation, and everything after remain separately authorized. PR #137 and
`feat/stage8-sample-editor` are never written to by work under this plan.
