# Outstanding Work Before Stage 9 — 2026-08-16

Everything unresolved or undecided that Stage 8 and the stages before it leave
behind, gathered in one place so each item can be settled or scheduled before
Stage 9 begins.

This is a **triage document, not an implementation plan**. Each item that gets
worked needs its own plan under `docs/superpowers/plans/` with its own
`## Version Management` section, per `CLAUDE.md`.

Two working lists split this record by who can act on each item:
[`2026-08-17-manual-verification-todo.md`](2026-08-17-manual-verification-todo.md)
for what a human must do, and
[`2026-08-17-machine-task-todo.md`](2026-08-17-machine-task-todo.md) for what a
coding agent can complete alone. This document stays the canonical statement of
each item; the two lists carry status and ordering.

Verified against `main` at `9d079796` on 2026-08-16, and updated on 2026-08-17
with the outcome of A1's real-microphone row and the findings it returned
(section F). Items from
`docs/quality/2026-08-03-review-backlog.md` were re-checked against the current
tree rather than copied forward; the ones already fixed are listed under
"Closed since the backlog was written" so nobody re-does them.

---

## A. Blocks a Release, not Stage 9

These prevent shipping the current builds. They do not prevent starting Stage 9
development, but they must be settled before any tag, publication or Channel
promotion.

### A1. Physical acceptance is unverified for every Build

No physical or manual acceptance row has ever been converted to a pass on the
current builds. Automation proves wiring; it cannot prove sound, feel or
latency. These block any physical-pass claim and promotion to Beta or Stable.

| Build | Row | Status |
| --- | --- | --- |
| 1.0.23.0 | macOS Chrome — real microphone capture, commit, playback hearing | `PASS` 2026-08-17 ([evidence](../release-evidence/2026-08-17-stage8b-real-microphone-capture-1.0.23.0.md)) |
| 1.0.23.0 | macOS Chrome — external audio interface input | `deferred / unverified` |
| 1.0.23.0 | macOS Safari — `getUserMedia` and AudioWorklet capture | `deferred / unverified` |
| 1.0.23.0 | iPadOS Safari — capture behaviour | `deferred / unverified` |
| 1.0.22.0 | macOS Chrome — human hearing and subjective audio quality | `deferred / unverified` |
| 1.0.22.0 | macOS Chrome — physical MIDI controller | `deferred / unverified` |
| 1.0.22.0 | macOS Safari — pointer plus physical hearing | `deferred / unverified` |
| 1.0.22.0 | iPadOS Safari — physical touch ergonomics | `deferred / unverified` |
| 1.0.22.0 | iPadOS Safari — background, lock-screen and recovery lifecycle | `deferred / unverified` |
| Stage 6/7 inherited | macOS Safari pointer, macOS Chrome pointer, iPadOS Safari touch, iPadOS Safari lifecycle | `deferred / unverified` |

Two rows have passed: macOS Chrome physical MIDI on `1.0.21.0`, and the
macOS Chrome real-microphone round trip on `1.0.23.0`.

**The cheapest high-value item was the real-microphone capture round trip, and
it has now been done.** One session validated the whole capture chain end to
end — no silence, no clipping, no channel swap, no sample-rate error — none of
which the Chromium fake device can show. It also produced four findings, listed
as F1–F4 below. The remaining rows in the table are unaffected and every one of
them still blocks a full physical-pass claim.

### A2. `native-test-host` is in the Product Assembly and every distribution

A component whose module id says "test" ships in `products/lmdj/assembly.json`
and in every distribution package, while `CLAUDE.md` defines `apps/` as "thin
Core Hosts" with no test-host category. One of the two is wrong.

Also missing: any written rule for what may enter a distribution package. The
package has grown from CLI + MCP + library to include this Host with no stated
criterion.

Options: accept it as a product component and rename to `native-host` (Module
rename + Assembly change, breaking), or remove it from the Assembly and
distribution and return it to `tests/`.

Recorded in `docs/prd/open-questions.md`. The backlog marked this ✅ but the
component is still in the Assembly today, so the mark is stale.

### A3. Build Manifest reproducibility contradicts itself

`create_zip()` pins timestamps, ordering and file modes for reproducibility,
but `build-manifest.json` sits inside the archive and carries `build_time`, so
the same source produces different ZIP bytes every time and "the downloader
rebuilds and compares hashes" cannot work. `build_time` is required by
`version-management.md` §4, so this is two correct requirements in one
container, not an implementation defect.

Options: publish the manifest detached; strip mutable fields from the archived
copy and keep a detached one; or accept irreproducibility and drop that
verification claim explicitly. Changes the shape of published artifacts.

Due before the first external distribution (`dev` Channel or above).

---

## B. Release governance defects found during Stage 8

These are real defects in the release machinery, found by Stage 8 rather than
introduced by it. Each is currently worked around by hand.

### B1. `audit` and `prepare` check different things about a release target

`tools/release/audit.py` checks that a target commit **exists in the object
store**. `tools/release/prepare.py` checks that it is an **ancestor of main**
and then checks it out to build.

Ancestry is the stronger condition, and only the weaker one gates. Two intents
(`1.0.22.0`, `1.0.23.0`) pointed at branch-side allocation commits that squash
merging had collapsed, so they were unpreparable from the moment they were
written — and the audit stayed green until garbage collection removed the
objects months later. Fixed for those two by #180; the mismatch that let them
through is untouched.

**Fix shape:** have `audit` assert main ancestry, so an unpreparable intent
fails immediately and by name instead of eventually and by accident.

### B2. Squash merge silently breaks snapshot provenance

Every Product Build carrying an immutable Portal snapshot goes red on `main`
immediately after merge, because the squash collapses the freeze revision and
the snapshot's source projection resolves to neither a direct parent nor a
byte-identical squash. The remedy — `scripts/architecture-portal.sh witness` —
exists and is documented, but is applied manually after `main` is already red.

This happened for `1.0.16.8`, `1.0.16.9`, `1.0.21.0`, `1.0.22.0` and
`1.0.23.0`. Five builds is a process, not an incident.

**Fix shape:** emit the witness on the merge path, or have the audit failure
name the exact command that resolves it.

### B3. Product Build identity is hand-written in too many places

Allocating `1.0.23.0` required edits in seven hand-maintained locations plus
five derived artifacts and gate tables. None of the failures named a version:

| Where | How it failed |
| --- | --- |
| `products/lmdj/CMakeLists.txt` compile-time allowlist | `HOST_PROTOCOL_MISMATCH` at browser boot — the whole packaged Creator, not just capture |
| `products/lmdj/src/compiled_assembly.cpp` | facade test aborted with a bare `AssertionError` |
| `tests/host/native_host_test.py` | bare `AssertionError`, failed `core-asan` and `core-coverage` |
| `tests/platform/web/host/web_runtime_host_lifecycle.spec.mjs` | host state read `failed` |
| `apps/creator-web/package.json` | no gate at all; npm identity would have silently disagreed with the Module identity |
| release test fixtures (24 assertions) | assorted |
| portal current-truth prose (5 pages) | portal gate |

Two were converted to derive-from-manifest during Stage 8 (the compiled
allowlist via `module_graph_test`, and the two Host fixtures). The rest remain
literal.

**Fix shape:** derive wherever a gate can read the committed truth; where a
literal is unavoidable, make its failure message name the version.

### B4. `assembly.lock.json` must be regenerated twice

The lock hashes the product-assembly source, so editing
`compiled_assembly.cpp` invalidates a lock generated moments earlier. This bit
twice in one allocation; the second time surfaced only at the portal freeze as
`product assembly source hash mismatch`.

**Fix shape:** fold lock regeneration into whatever writes the compiled
assembly, or have `version.py lock` refuse to run before the source is final.

---

## C. Test and CI reliability

### C1. `application-facade` coverage threshold has no margin

Threshold is 84.00%; the measured value is 84.04% (3413/4061). The package
contains concurrency code exercised by stress and concurrency tiers, and the
covered-line count moves ±4 lines between runs on identical source. One Stage 8
run measured 83.94% and failed; the next measured 84.04% and passed.

Any PR can be stopped by this at random, and a genuine 4-line regression is
indistinguishable from noise.

**Fix shape:** decide whether the threshold should sit below the observed
floor, or whether the nondeterministic paths should be excluded from the
measurement.

### C2. `decision-log.md` and `open-questions.md` conflict on every parallel branch

Both files are append-at-the-end, and every concurrent session appends to the
same place. Stage 8b hit conflicts in both on its final sync.

**Fix shape:** structural — dated section files with an index, or an append
convention that keeps concurrent additions apart.

### C3. Playwright evidence retention was two bugs deep

Closed during Stage 8, recorded here because the second half is easy to
regress: CI now uploads `test-results` on failure (#172), **and** each of the
Creator Proof's six sequential Playwright invocations writes to its own results
slot. Without the second fix the upload only ever captured the last lane, since
Playwright clears `outputDir` at the start of every run.

---

## D. Product questions awaiting a design review

Carried from `docs/prd/open-questions.md`. Listed by when they become blocking.

### D1. Long-material resource model — with D2, same review

Per-Pad 240,000 frames comes from the 64/128 MiB prepared-PCM budget. A 60 s
sample needs 369 MB/Bank under the uniform model, over the 512 MiB fixed heap;
a shared Bank quota supports ≈60 s on one Pad and ≈174 s stereo per Bank
without raising it. Raising to 1 GiB is excluded by iPadOS single-page memory
limits.

Touches Cooker Bank allocation, the `PreparedSampleBank` lock-free publication
layout, manifest semantics, Facade validation, and a new "quota consumed by
another Pad" failure class. (S8B-D10)

### D2. Loop material BPM time-stretch — with D1, same review

Whether and how Loop material follows global BPM when its own BPM differs,
including pitch-shift. Determines the Audio Runtime DSP scope and the
Capability list. Most long material is BPM-following Loops, which is why this
and D1 belong in one review.

### D3. Provider SDK Artifact byte access, both directions

`lmdj.capability.v2` identifies declared Schema identity by port, but
`ArtifactRef` carries no Schema provenance and `AttemptStore` has no input
resolver. The 2026-08-16 analysis-bench prototype confirmed the gap is
bidirectional: the output side has no accessor for committed Artifact bytes
either, so the Host had to rebuild paths from the private
`.lmdj-workspace/attempts/` layout. The prototype's Host-injected bridge is
temporary and must not graduate into the formal interface.

Due before the first Capability implementation that parses structured Artifact
bytes.

### D4. Recording concurrency semantics

Which unrelated Commands should not trigger a conflict, and whether selective
rebase is allowed. The Core Proof uses "any revision change conflicts and seals
the Take" for determinism; that cannot stand as the product rule. Affects the
recording Journal, Take commit experience and a public Contract.

Due before Sequence/Take Contract enters product implementation — **Stage 9
territory**, so this one likely needs settling first.

### D5. Take scope — events only, or audio bounce too

Determines the Take contract, Web Audio recording and Export Pack. Also
Stage 9-adjacent.

---

## E. Known-good, tracked for awareness

### E1. 60 s capture buffer cap has unit coverage only

`capture_buffer.test.ts` proves truncation at 2,880,000 frames. The browser
journeys assert the 5 s commit clamp rather than elapsing a real minute, so no
end-to-end journey reaches the cap. Deliberate — waiting out a real minute
proves nothing the clamp does not — but it means the cap's browser behaviour is
unobserved.

### E2. `envelope()` has no zoom window

`CaptureBuffer.envelope(bins)` renders the whole buffer. If long-material
support adds waveform zoom, a narrow window at the same bin count falls back to
the exact path and re-scans the entire buffer — reintroducing the cost the
block summary removed. The fix is a range parameter; recorded in the code.

### E3. Capture summaries assume an append-only buffer

Block peaks are maintained incrementally in `append()`. Adding pre-commit
buffer editing requires invalidation logic. Recorded in the code.

---

## F. Defects found by the 2026-08-17 physical session

F1–F4 were found while performing A1's real-microphone row (M1); F5 and F6 came
from the first check of row M2, which stopped there. Each was reproduced or
traced to source before being recorded; measurements for F1–F4 are in the
[evidence file](../release-evidence/2026-08-17-stage8b-real-microphone-capture-1.0.23.0.md).
None is fixed.

F1, F2, F3 and F5 are Creator front-end defects and are scoped together in
[`2026-08-17-lmdj-creator-capture-ui-remediation.md`](../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md).
F4 and F6 each need a product decision and are explicitly excluded from that
plan.

### F1. The capture panel has no styling and opens below the fold

`.capture-panel` has no rule in `apps/creator-web/src/styles.css`. It renders
as an unstyled flow element at the end of the Sample surface, with no
scroll-into-view and no focus move. Measured at 1440×900: box `y ≈ 790`,
height `157`, document height `983`. In a real browser window the panel and its
`Record into Pad N` button are entirely below the fold, so pressing
`Record Sample` looks like nothing happened.

### F2. Stop is pushed off screen when recording starts

Same root cause. Entering `recording` adds the level meter and waveform canvas,
growing the panel from 157 px to 277 px, all downward, and the page does not
scroll to follow. The take cannot be stopped from the visible surface.

F1 and F2 are one fix. Every automated journey locates the panel by role and
label, which never requires the element to be above the fold — this class of
defect is invisible to the whole browser gate.

### F3. `DUPLICATE_ID` presents as fatal with no way out

Re-importing a bundle whose local Project has since diverged renders under
`Creator unavailable` with no recovery control (`error_panel.tsx:36`); only
`PROJECT_BUSY` and `HOST_RESTART_REQUIRED` get one. No data is lost —
`Open local` still opens the diverged Project, and a plain reload clears the
error. The defect is the presentation and the missing affordance.

### F4. A silent default input commits silence with no indication

`capture_controller.ts:62` requests audio with no `deviceId`, so capture follows
the OS default input; the absent device picker is a **declared** scope boundary
for this Build, so that omission is not the finding. The finding is its physical
consequence: when the default input changes silently, `getUserMedia` succeeds,
the stream carries digital silence, and the Creator commits a full 5 s of
silence onto a Pad with no input-level gate, no silence detection and no
warning. The operator's only signal is the level meter, which F1 and F2 keep
off screen.

Needs a product decision — device picker, visible input identity, an
input-level gate before commit, or some combination — not a unilateral fix
inside an implementation Task. Belongs with D1–D5 in a design review.

### F5. The waveform trim handles cannot be aimed

Both trim handles are native `input[type="range"]` elements
(`waveform_editor.tsx:372`, `:393`) styled `position: absolute; inset-inline: 0;
width: 100%; min-height: 44px; opacity: .01` (`styles.css:127`), stacked over
the waveform canvas with Start anchored to the top and End to the bottom.

Three consequences follow from that geometry: which handle a press grabs is
decided by **vertical band**, not by the handle being pointed at, so aiming at
the drawn handle line is meaningless; the middle band of the canvas belongs to
neither input and does nothing; and because a native range jumps its thumb to
the clicked track position, a mis-aimed press **moves the wrong trim point**
rather than being ignored. `opacity: .01` makes none of it learnable.

Found within a minute of a human first trying to trim a Sample. The keyboard
path is sound and must survive the fix.

Scoped in
[`2026-08-17-lmdj-creator-capture-ui-remediation.md`](../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md)
with F1–F3.

### F6. The render path has no amplitude ramp anywhere

Trimming a Sample and triggering it produces audible clicks at the trim
boundaries — the first check of row M2, 2026-08-17.

Not a Creator defect. `realtime_engine.cpp:710` renders
`voice.samples[voice.cursor] * voice.gain` and at `end_frame` either assigns
`voice.cursor = voice.start_frame` for a loop or hard-stops; `stop_voice`
(`:195`) sets `voice.active = false` immediately. There is no attack ramp, no
release ramp, no fade at the trim boundary, no crossfade at the loop seam and
no zero-crossing snap. A trim edge on a non-zero sample is a step
discontinuity, which is what the click is.

The same absence predicts clicks at the loop seam and on releasing a held
voice; neither has been tested yet.

Needs a Core/DSP product decision — ramp length, zero-crossing snap, crossfade,
or a combination — with a realtime-safety review, since the render path is
allocation-free and lock-free and any ramp state must stay inside that
contract. Explicitly out of scope for the Creator UI plan.

---

## Closed since the 2026-08-03 review backlog

Re-verified against `main` at `9d079796`; do not re-do these.

| # | Item | Evidence |
| --- | --- | --- |
| A1 | Apple-only code untouched by sanitizers | `core-asan-macos` job exists in `ci.yml` |
| A2 | spsc stress excluded from PR-blocking jobs | `scripts/core.sh test asan stress` runs in CI |
| A3 | `CLAUDE.md` misdescribed `core.sh test` tiers | Tier semantics documented in `CLAUDE.md` |
| A4 | `realtime_engine.hpp` lacked thread preconditions | Thread contract now in the header |
| B1 | No JSON Schema validator | `tests/conformance/json_schema.py` + `json_schema_test.py` |
| C1/C3 | `parse_bounded_json` copied three times | Single definition in `foundation/json.hpp`; all others are call sites |
| D1 | `package` ran no tests | Runs unit and component tiers before packaging |
| D2 | Dirty tree not detected | `package` refuses a modified working tree |
| D3 | `build_time` breaks ZIP reproducibility | Superseded by A3 above, still open as a governance question |

**Still open from that backlog:** C2 (`project_store.cpp` JSON read paths lack
the `O_NOFOLLOW` symmetry that `read_artifact()` has) and D4
(`native-test-host` in the Assembly, listed as A2 above).

---

## Suggested order

1. ~~**A1 real-microphone check**~~ — done 2026-08-17. The capture chain
   passed all five hearing criteria; the session returned F1–F4, of which
   **F1 + F2 are one cheap fix** and should be taken next in this group, since
   they make Pad Capture unusable on a normal window without knowing to scroll.
2. **B1 + B2 together** — same root cause shape, both currently absorbed by
   hand on every release, and both make the release path lie about its own
   readiness.
3. **C1** — cheap, and it stops random PR failures polluting every future
   signal.
4. **D4 + D5** — Stage 9 depends on them.
5. **D1 + D2** — one review, before any long-material work.
6. **A2, A3** — before the first external distribution.
7. **B3, B4, C2, backlog C2** — mechanical hardening, schedule as capacity allows.
