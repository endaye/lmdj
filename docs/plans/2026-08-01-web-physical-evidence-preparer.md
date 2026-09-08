# Web Physical Evidence Preparer Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert one privacy-bounded Web Runtime Lab browser report into a deterministic physical-run dossier draft without claiming or fabricating physical evidence.

**Architecture:** The browser report first moves to local `reportVersion: 2` so Pointer Events retain `touch` separately from desktop `pointer`, while MIDI remains distinct. A pure preparer validates that report and the selected required row, copies only admissible runtime fields, strips user-agent/platform/language strings, and emits one `evidenceVersion: 1` run. A thin CLI accepts explicit exact OS/browser version strings, prints JSON to stdout, and leaves physical, foreground, or lifecycle measurements visibly incomplete so the strict evaluator returns `unverified` until the operator supplies retained real-device evidence.

**Tech Stack:** JavaScript ES modules, Node.js built-in test runner, Bash entry point, Markdown, Python active-tree verification.

## Global Constraints

- The preparer consumes only `reportVersion: 2` with `decisionStatus: "threshold-approved"` and `physicalMeasurement: null`; v1 reports are rejected because they cannot distinguish touch from pointer.
- Browser trigger sources are exactly `pointer`, `touch`, or `midi`; `pointerdown.pointerType === "touch"` is reported as `touch`, while mouse/pen remain `pointer`.
- Accept only one of the five fixed `REQUIRED_ROWS`; row identity comes from that descriptor and cannot be overridden by report strings.
- Require explicit non-empty `--os-version` and `--browser-version`; do not infer exact versions from user-agent text.
- Require built-in or wired output, positive sample rate, at least one running AudioContext lifecycle event, non-empty observed quantum sizes, positive processor callback count, and consistent trigger/acknowledgement counts.
- Report v2 retains every privacy-bounded trigger dispatch separately from acknowledgement estimates, so a missing acknowledgement does not erase the original trigger record.
- Performance rows require exactly 500 dispatch records from the row's required source. Acknowledgement time and quantum remain `null` for a missing acknowledgement and the prepared dossier preserves the observed loss as a measured failure. Lifecycle rows do not fabricate trigger records or recovery actions.
- Do not copy user agent, raw platform, language, MIDI input name/manufacturer/ID, SysEx, raw MIDI bytes, local paths, or source device identifiers.
- Physical method, capture rate, calibration, physical percentiles, foreground stability, and lifecycle recovery observations remain explicit `null`/empty draft fields.
- Passing a prepared draft to `evaluatePhysicalMatrix` must return `unverified`, never `passed` or `failed` solely from browser data.
- No automatic file write, persistence, upload, product version change, Core change, Provider change, or Contract change.
- Work only on `feat/web-runtime-lab`; create one reviewable Conventional Commit and update PR #72 without merging.

## Version Management

- Product Build version impact: none.
- Core Module SemVer impact: none.
- Provider SemVer impact: none.
- Contract SemVer impact: none; the preparer emits the existing local evidence input version `1`.
- Browser lab report version: increases from `1` to `2` because the report adds touch-source identity and `touchAcknowledgements`; this is a local experimental format and not a formal Contract.

---

### Task 1: Prepare a Physical-Run Draft from a Browser Report

**Files:**

- Create: `docs/plans/2026-08-01-web-physical-evidence-preparer.md`
- Create: `apps/web-runtime-lab/src/physical-evidence-preparer.mjs`
- Create: `apps/web-runtime-lab/src/prepare-physical-evidence.mjs`
- Create: `apps/web-runtime-lab/test/physical-evidence-preparer.test.mjs`
- Modify: `apps/web-runtime-lab/src/main.js`
- Modify: `apps/web-runtime-lab/src/physical-gate.mjs`
- Modify: `apps/web-runtime-lab/src/probe-core.mjs`
- Modify: `apps/web-runtime-lab/test/physical-gate.test.mjs`
- Modify: `apps/web-runtime-lab/test/probe-core.test.mjs`
- Modify: `scripts/web-runtime-lab.sh`
- Modify: `apps/web-runtime-lab/README.md`
- Modify: `docs/quality/web-runtime-lab-acceptance.md`
- Modify: `apps/web-runtime-lab/test/active_tree_test.py`
- Modify: `docs/plans/2026-08-01-web-realtime-audio-approved-gate.md`

**Interfaces:**

- Consumes: `preparePhysicalEvidence(rowKey, browserReport, { osVersion, browserVersion })`.
- Produces: `{ evidenceVersion: 1, runs: [PhysicalRunDraft] }`.
- CLI: `scripts/web-runtime-lab.sh prepare ROW_KEY REPORT.json --os-version VERSION --browser-version VERSION`.

- [x] **Step 1: Write failing touch-source, pure preparer, and CLI tests**

First prove report v2 accepts and counts `touch` acknowledgements separately, while keeping the existing pointer and MIDI counts, and retains dispatch records even when one has no acknowledgement. Create a valid 500-dispatch v2 report fixture and prove the preparer joins acknowledgements by sequence, maps session/time, fixed row identity, route/sample rate, AudioContext history, latency, quantum sizes, callback count, errors, unsupported core capabilities, and privacy-bounded records. Assert serialized output excludes report user-agent, raw platform, language, MIDI identity, and arbitrary extra fields.

Assert prepared performance and lifecycle drafts both evaluate as `unverified`. Assert the preparer rejects an unknown row, stale decision status, non-null physical measurement, Bluetooth/USB/unknown route, missing exact version options, wrong source, fewer than 500 records, count mismatch, missing running state, and MIDI rows without supported/granted physical MIDI evidence.

- [x] **Step 2: Run RED**

Run:

```bash
cd apps/web-runtime-lab
npm test
```

Expected: the new touch report assertion fails and the preparer test reports module-not-found.

- [x] **Step 3: Implement the pure preparer and CLI**

Record `touch` from Pointer Events without changing the shared realtime ring, retain each dispatch before publishing it to the ring, bump the local report to v2, and use `REQUIRED_ROWS` as the preparer identity authority. Join dispatches to acknowledgements without inventing missing values. Produce null physical/foreground/lifecycle measurement fields and preserve only the approved privacy-bounded trigger fields. The CLI parses the two required named options, emits pretty deterministic JSON, exits `0` on a prepared draft, and exits `64` with a JSON error on usage/input/report failure.

- [x] **Step 4: Run GREEN and script checks**

Run:

```bash
cd apps/web-runtime-lab
npm test
python3 test/active_tree_test.py
```

Expected: all tests pass and active-tree checks confirm the preparer never copies forbidden identity fields or fills physical results.

- [x] **Step 5: Document the operator flow**

Document the exact command, stdout redirection under operator control, required report prerequisites, explicit version flags, fields copied/stripped, fields still requiring physical observation, and the invariant that prepared output remains `unverified`.

- [ ] **Step 6: Verify, commit, and update PR**

Run:

```bash
scripts/web-runtime-lab.sh test
scripts/core.sh proof
git diff --check
```

Verify the branch is not `main`, stage only the fourteen declared files, inspect staged names and whitespace, then commit:

```text
feat(web): prepare privacy-bounded physical evidence
```

Inspect the committed file list and clean worktree, push `feat/web-runtime-lab`, and wait for PR #72 checks. Do not merge.
