# Web Physical Evidence Dossier Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the Web realtime-audio lab from returning `passed` unless every required physical row carries the complete retained run dossier required by the approved decision.

**Architecture:** Keep `evaluatePhysicalMatrix(evidence)` as the only gate entry point, but validate each row against a fixed row identity and a shared evidence envelope before evaluating thresholds. Performance rows must contain 500 privacy-bounded trigger/acknowledgement records plus physical-method metadata; lifecycle rows must contain the same environment/runtime envelope plus the complete recovery action set. Missing or internally inconsistent dossier evidence remains `unverified`; an eligible, complete dossier that violates an approved threshold remains `failed`.

**Tech Stack:** JavaScript ES modules, Node.js built-in test runner, Markdown, Python active-tree verification.

## Global Constraints

- Browser estimates, CI, desktop emulation, and Bluetooth must never satisfy a physical required row.
- Required row identity is fixed: macOS Safari Pointer, macOS Chrome Pointer, macOS Chrome physical MIDI, iPadOS Safari Touch performance, and iPadOS Safari Touch lifecycle.
- Every run requires a UUID session ID, UTC timestamp, exact OS/browser version strings, broad device class, eligible output route, sample rate, AudioContext state history, exposed latency values, observed quantum sizes, processor callback count, errors, and unsupported-capability lists.
- Every performance row requires exactly 500 unique trigger/acknowledgement records, the expected input source, monotonic acknowledgement timing, and a physical method record.
- High-speed video requires at least 240 fps. Wired loopback requires a positive capture/sample rate. Calibration offset may be negative but must be finite.
- Runtime errors or unsupported capabilities make a row `unverified`; they are never silently ignored.
- A complete measured threshold violation outranks missing evidence elsewhere and yields overall `failed`.
- Do not add stable device identifiers, MIDI names/manufacturers/IDs, SysEx, raw MIDI bytes, absolute local paths, or automatic persistence.
- Work only on `feat/web-runtime-lab`; create one reviewable Conventional Commit and update existing PR #72 without merging.

## Version Management

- Product Build version impact: none; this changes experimental evidence validation only.
- Core Module SemVer impact: none.
- Provider SemVer impact: none.
- Contract SemVer impact: none; evidence JSON remains a local lab format, not a cross-language Contract.
- Evidence input version: remains `1`; the approved evaluator was introduced on this unmerged feature branch, and this change completes its required validation before merge.

---

### Task 1: Require a Complete Physical Run Dossier

**Files:**

- Create: `docs/plans/2026-08-01-web-physical-evidence-dossier.md`
- Modify: `apps/web-runtime-lab/src/physical-gate.mjs`
- Modify: `apps/web-runtime-lab/test/physical-gate.test.mjs`
- Modify: `apps/web-runtime-lab/README.md`
- Modify: `docs/quality/web-runtime-lab-acceptance.md`
- Modify: `apps/web-runtime-lab/test/active_tree_test.py`

**Interfaces:**

- Consumes: `evaluatePhysicalMatrix({ evidenceVersion: 1, runs: PhysicalRun[] })`.
- Produces: the existing deterministic evaluation shape with new stable unverified reason codes for missing/invalid envelope, runtime, trigger-record, physical-method, error, and unsupported-capability evidence.

- [ ] **Step 1: Write failing dossier tests**

Build passing fixtures with this exact common shape:

```javascript
{
  key,
  sessionId: "00000000-0000-4000-8000-000000000001",
  recordedAt: "2026-08-01T12:00:00.000Z",
  environment: {
    osVersion: "exact-version",
    browserVersion: "exact-version",
    deviceClass: "mac" | "ipad",
    routeCategory: "built-in" | "wired",
    sampleRate: 48000,
  },
  runtime: {
    audioContextStateHistory: [{ state: "running", atMs: 0 }],
    baseLatency: 0.003,
    outputLatency: 0.016,
    observedQuantumSizes: [128],
    processorCallbackCount: 1,
  },
  errors: [],
  unsupportedCapabilities: [],
}
```

Performance fixtures additionally contain exactly 500 records shaped as:

```javascript
{
  sequence: 1,
  source: "pointer" | "midi" | "touch",
  eventAtMs: 1,
  acknowledgementAtMs: 2,
  quantumSize: 128,
}
```

and physical evidence shaped as:

```javascript
{
  method: "high-speed-video",
  captureRateHz: 240,
  calibrationOffsetMs: 0,
  triggerCount: 500,
  p50Ms: 30,
  p95Ms: 50,
  p99Ms: 80,
  missedOnsets: 0,
  duplicateOnsets: 0,
}
```

Add separate tests proving that minimalist aggregate-only evidence, fewer than 500 records, wrong input source, duplicate sequence, inexact row identity, missing runtime metadata, a sub-240-fps video method, errors, and unsupported capabilities cannot produce `passed`.

- [ ] **Step 2: Run RED**

Run:

```bash
cd apps/web-runtime-lab
npm test
```

Expected: the new tests fail because aggregate-only rows currently pass and the dossier is not validated.

- [ ] **Step 3: Implement strict dossier validation**

Add fixed row descriptors containing expected `deviceClass`, `browser`, and `source`. Validate the common envelope first, then validate exactly 500 performance records and the physical method. Preserve stable ordering of reason codes. Keep threshold failures separate from unverified dossier reasons so measured failure continues to outrank missing rows.

- [ ] **Step 4: Run GREEN and boundary checks**

Run:

```bash
cd apps/web-runtime-lab
npm test
python3 test/active_tree_test.py
```

Expected: all evaluator, report, CLI, privacy, and active-tree checks pass.

- [ ] **Step 5: Document the evidence file**

Update the README and acceptance policy with the exact envelope, 500-record requirement, physical-method constraints, privacy exclusions, and the distinction between retained raw evidence and the local evaluation file. State that old aggregate-only examples remain `unverified`.

- [ ] **Step 6: Verify and commit atomically**

Run:

```bash
scripts/web-runtime-lab.sh test
scripts/core.sh proof
git diff --check
```

Verify the branch is not `main`, stage only the six declared files, inspect `git diff --cached --name-only` and `git diff --cached --check`, then commit:

```text
fix(web): require complete physical evidence dossiers
```

Inspect the committed file list and clean worktree, push `feat/web-runtime-lab`, and wait for PR #72 checks. Do not merge.
