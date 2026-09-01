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

### A1. Several physical acceptance rows remain unverified

Several physical or manual acceptance rows remain unverified on the current
builds. Automation proves wiring; it cannot prove sound, feel or latency.
Those open rows block any broader physical-pass claim and promotion to Beta or
Stable.

| Build | Row | Status |
| --- | --- | --- |
| 1.0.23.0 | macOS Chrome — real microphone capture, commit, playback hearing | `PASS` 2026-08-17 ([evidence](../release-evidence/2026-08-17-stage8b-real-microphone-capture-1.0.23.0.md)) |
| 1.0.23.0 | macOS Chrome — external audio interface input | `deferred / unverified` |
| 1.0.23.0 | macOS Safari — `getUserMedia` and AudioWorklet capture | `deferred / unverified` |
| 1.0.23.0 | iPadOS Safari — capture behaviour | `deferred / unverified` |
| 1.0.40.0 | macOS Chrome — human hearing and subjective audio quality | **`PASS` 2026-09-01** — all eight checklist groups passed; exact replay corrected the initial interpretation of the 40 ms loop's rapid texture ([evidence](../release-evidence/2026-09-01-stage8-m2-macos-chrome-hearing-1.0.40.0.md)) |
| 1.0.22.0 | macOS Chrome — physical MIDI controller | `deferred / unverified` |
| 1.0.22.0 | macOS Safari — pointer plus physical hearing | `deferred / unverified` |
| 1.0.22.0 | iPadOS Safari — physical touch ergonomics | `deferred / unverified` |
| 1.0.22.0 | iPadOS Safari — background, lock-screen and recovery lifecycle | `deferred / unverified` |
| Stage 6/7 inherited | macOS Safari pointer, macOS Chrome pointer, iPadOS Safari touch, iPadOS Safari lifecycle | `deferred / unverified` |

Three rows have passed: macOS Chrome physical MIDI on `1.0.21.0`, the macOS
Chrome real-microphone round trip on `1.0.23.0`, and macOS Chrome human hearing
and subjective audio quality on `1.0.40.0`.

**The cheapest high-value item was the real-microphone capture round trip, and
it has now been done.** One session validated the whole capture chain end to
end — no silence, no clipping, no channel swap, no sample-rate error — none of
which the Chromium fake device can show. It also produced four findings, listed
as F1–F4 below. The remaining rows in the table are unaffected and every one of
them still blocks a full physical-pass claim.

### A2. `native-test-host` is in the Product Assembly and every distribution

**Resolved 2026-08-24 by the rename option** ([#210](https://github.com/endaye/lmdj/issues/210),
decision [`../prd/decisions/2026-08-24-native-test-host-classification.md`](../prd/decisions/2026-08-24-native-test-host-classification.md)):
`native-test-host` (retired at `1.0.14`) became `native-host 1.0.0` in Product
Build `1.0.31.0`, and the distribution-contents rule now lives in
[`../governance/distribution-contents.md`](../governance/distribution-contents.md).
The original finding follows as filed.

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

### ~~A3. Build Manifest reproducibility contradicts itself~~ — decided 2026-08-24

`create_zip()` pins timestamps, ordering and file modes for reproducibility,
but `build-manifest.json` sits inside the archive and carries `build_time`, so
the same source produces different ZIP bytes every time and "the downloader
rebuilds and compares hashes" cannot work. `build_time` is required by
`version-management.md` §4, so this is two correct requirements in one
container, not an implementation defect.

**Decided 2026-08-24** in
[`../prd/decisions/2026-08-24-build-manifest-detached.md`](../prd/decisions/2026-08-24-build-manifest-detached.md)
([#211](https://github.com/endaye/lmdj/issues/211)): the Manifest becomes a
detached sibling asset, the archive keeps payload only, and the Contract and
fields are unchanged. **Implemented the same day** as machine task A3
([#286](https://github.com/endaye/lmdj/issues/286), plan
[`../superpowers/plans/2026-08-24-lmdj-detached-build-manifest.md`](../superpowers/plans/2026-08-24-lmdj-detached-build-manifest.md)):
the packager ships `<package-name>.build-manifest.json` beside the archive, two
clean packagings produce byte-identical ZIPs, and the release inventory gates
are profile-aware (core-package four assets, web-runtime-host three). This
clears the A3 item ahead of the first external distribution (`dev` Channel or
above).

---

## B. Release governance defects found during Stage 8

These are real defects in the release machinery, found by Stage 8 rather than
introduced by it. Each is currently worked around by hand.

### ~~B1. `audit` and `prepare` check different things about a release target~~ — fixed 2026-08-18

`tools/release/audit.py` checks that a target commit **exists in the object
store**. `tools/release/prepare.py` checks that it is an **ancestor of main**
and then checks it out to build.

Ancestry is the stronger condition, and only the weaker one gates. Two intents
(`1.0.22.0`, `1.0.23.0`) pointed at branch-side allocation commits that squash
merging had collapsed, so they were unpreparable from the moment they were
written — and the audit stayed green until garbage collection removed the
objects months later. Fixed for those two by #180; the mismatch that let them
through is untouched.

**Fixed** in `33dbff7c`. Investigation narrowed the defect: `audit` already
asserted ancestry, but only once a remote tag existed. The gap was the two
pre-mutation paths — an allocated intent, and a releasable intent with no
remote state — which returned `ok` on object existence alone. Both now probe
ancestry through one shared helper, the releasable path before CI evidence.
Abandoned and superseded-unreleased intents remain ungated: neither authorizes
a mutation and their targets may legitimately sit outside `main`.

### ~~B2. Squash merge silently breaks snapshot provenance~~ — fixed 2026-08-18

Every Product Build carrying an immutable Portal snapshot goes red on `main`
immediately after merge, because the squash collapses the freeze revision and
the snapshot's source projection resolves to neither a direct parent nor a
byte-identical squash. The remedy — `scripts/architecture-portal.sh witness` —
exists and is documented, but is applied manually after `main` is already red.

This happened for `1.0.16.8`, `1.0.16.9`, `1.0.21.0`, `1.0.22.0` and
`1.0.23.0`. Five builds is a process, not an incident.

**Fixed** in `edb16910` — by the second shape only. Emitting the witness on the
merge path is impossible by construction: the witness records the introducing
squash revision, which exists only after the merge, and the witness file must
itself be committed, which on protected `main` is a follow-up PR either way.
The verifier now emits `run: scripts/architecture-portal.sh witness <build>
<introducing>` with both arguments filled from values it already held, and the
command derives that second argument itself when it is omitted.

The merge still goes red; what changed is that the red now states its own cure.

### ~~B3. Product Build identity is hand-written in too many places~~ — fixed 2026-08-21

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

**Fixed** in `4312a6de` (#226), against
[`2026-08-21-product-version-identity-derivation-design.md`](../superpowers/specs/2026-08-21-product-version-identity-derivation-design.md)
§12 rather than the historical seven-location count. Current consumers derive
from committed `products/lmdj/version.json`; `assembly.json`, release intents,
and immutable snapshots stay explicit exact records; pure behavior tests use
named synthetic Product Builds; Creator Host `module.json` / `package.json` /
`package-lock.json` identity is gated; mismatch failures name expected, found,
authority, and consumer, with a stable remedy on generated stale outputs.
Issue [#207](https://github.com/endaye/lmdj/issues/207) stayed OPEN because
the squash subject omitted `Closes #207`.

### B4. `assembly.lock.json` must be regenerated twice

The lock hashes the product-assembly source, so editing
`compiled_assembly.cpp` invalidates a lock generated moments earlier. This bit
twice in one allocation; the second time surfaced only at the portal freeze as
`product assembly source hash mismatch`.

**Fix shape:** fold lock regeneration into whatever writes the compiled
assembly, or have `version.py lock` refuse to run before the source is final.

---

## C. Test and CI reliability

### ~~C1. `application-facade` coverage threshold has no margin~~ — resolved 2026-08-19

Threshold is 84.00%; the measured value is 84.04% (3413/4061). The package
contains concurrency code exercised by stress and concurrency tiers, and the
covered-line count moves ±4 lines between runs on identical source. One Stage 8
run measured 83.94% and failed; the next measured 84.04% and passed.

Any PR can be stopped by this at random, and a genuine 4-line regression is
indistinguishable from noise.

**Resolved 2026-08-19** by raising real coverage rather than by tuning the
gate, and the intermediate diagnosis was itself corrected.

A 2026-08-18 measurement concluded Ubuntu was deterministic and that this item
did not exist. That was undersampled and is withdrawn: PR #188's head and its
squash share a byte-identical tree yet measured 3526 and 3522 covered lines on
Ubuntu — the ±4 recorded here originally. The 84 floor sat inside that band
with about two lines of margin, so it genuinely could stop a PR at random.

The fix was coverage, not threshold tuning: behavioral tests for previously
unexercised failure semantics took the package from 84.04% to 86.15% on
Ubuntu, and the floor then ratcheted to 85, leaving about 47 lines of headroom
— comfortably outside the noise. Full history in
[`2026-08-18-facade-coverage-gate-measurement.md`](2026-08-18-facade-coverage-gate-measurement.md).
floor — upward.

### ~~C2. `decision-log.md` and `open-questions.md` conflict on every parallel branch~~ — fixed 2026-08-18

Both files are append-at-the-end, and every concurrent session appends to the
same place. Stage 8b hit conflicts in both on its final sync.

**Fix shape:** structural — dated section files with an index, or an append
convention that keeps concurrent additions apart.

**Fixed** in `5a9c11a7` (plan
[`2026-08-18-lmdj-prd-append-structure.md`](../superpowers/plans/2026-08-18-lmdj-prd-append-structure.md)):
one entry per file, deliberately **without** an index — an index file edited
on every addition is itself a shared append point and would recreate this
defect. New decisions are dated files under `docs/prd/decisions/`; each open
question is its own file under `docs/prd/questions/`, which also removes the
shared `更新时间` line every session edited. Both canonical paths survive as
convention pages: `decision-log.md` keeps the pre-2026-08-18 archive frozen,
`open-questions.md` migrated all 18 open rows verbatim.

### C3. Playwright evidence retention was two bugs deep

Closed during Stage 8, recorded here because the second half is easy to
regress: CI now uploads `test-results` on failure (#172), **and** each of the
Creator Proof's six sequential Playwright invocations writes to its own results
slot. Without the second fix the upload only ever captured the last lane, since
Playwright clears `outputDir` at the start of every run.

---

## D. Product questions awaiting a design review

Carried from `docs/prd/open-questions.md`. Listed by when they become blocking.

### ~~D1. Long-material resource model~~ — decided 2026-08-26, merged 2026-08-26

~~Per-Pad 240,000 frames comes from the 64/128 MiB prepared-PCM budget. A 60 s
sample needs 369 MB/Bank under the uniform model, over the 512 MiB fixed heap;
a shared Bank quota supports ≈60 s on one Pad and ≈174 s stereo per Bank
without raising it. Raising to 1 GiB is excluded by iPadOS single-page memory
limits.~~

~~Touches Cooker Bank allocation, the `PreparedSampleBank` lock-free publication
layout, manifest semantics, Facade validation, and a new "quota consumed by
another Pad" failure class. (S8B-D10)~~

**Decided 2026-08-26** ([#237](https://github.com/endaye/lmdj/issues/237),
[decision](../prd/decisions/2026-08-26-long-material-quota-and-bpm-stretch.md),
merged in [#339](https://github.com/endaye/lmdj/pull/339)): Bank-shared quota
with no per-Pad cap; the quota model lives in Core, numbers are injected per
Host manifest (the 512 MiB heap and Web values are browser-tier numbers);
ingest (Host tier) and prepared (Core tier) split — capture and long-file
import converge at one deterministic commit validation with a new
`BANK_QUOTA_EXHAUSTED` / `PROJECT_QUOTA_EXHAUSTED` failure classes. The
2026-08-27 readiness gap was settled by [#357](https://github.com/endaye/lmdj/issues/357),
and machine implementation [#343](https://github.com/endaye/lmdj/issues/343)–[#346](https://github.com/endaye/lmdj/issues/346)
merged through PRs #400, #406, #408, and #411 as Product Build `1.0.38.0`.
The first physical macOS Safari attempt found recoverability defect
[#415](https://github.com/endaye/lmdj/issues/415); [PR #419](https://github.com/endaye/lmdj/pull/419)
fixed it in Product Build `1.0.39.0`, with exact-main full CI passing at
`925499293f7b79eb7dacbe85318595c4b11098a3`. No machine implementation remains
inside umbrella [#341](https://github.com/endaye/lmdj/issues/341). Its final
gate is the complete macOS Safari and physical iPadOS Safari acceptance matrix
[#359](https://github.com/endaye/lmdj/issues/359), restarted from the beginning
on exact `1.0.39.0`; the failed `1.0.38.0` prefix is not carried forward.
The original plan Task [#342](https://github.com/endaye/lmdj/issues/342)
remains completed history.

### ~~D2. Loop material BPM time-stretch~~ — decided 2026-08-26, merged 2026-08-26

~~Whether and how Loop material follows global BPM when its own BPM differs,
including pitch-shift. Determines the Audio Runtime DSP scope and the
Capability list. Most long material is BPM-following Loops, which is why this
and D1 belong in one review.~~

**Decided 2026-08-26** (same review and decision file as D1): samples carry no
BPM property; global BPM drives the sequencer only and never alters sample
playback speed or pitch (Koala-verified default). The v1 realtime engine stays
zero-DSP; time-stretch becomes a named future per-Pad opt-in offline-baked
capability, tracked as
[#347](https://github.com/endaye/lmdj/issues/347).

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

### ~~D4. Recording concurrency semantics~~ — decided 2026-08-23, delivery merged 2026-08-27

~~Which unrelated Commands should not trigger a conflict, and whether selective
rebase is allowed. The Core Proof uses "any revision change conflicts and seals
the Take" for determinism; that cannot stand as the product rule. Affects the
recording Journal, Take commit experience and a public Contract.~~

**Decided 2026-08-23** ([#238](https://github.com/endaye/lmdj/issues/238),
[decision](../prd/decisions/2026-08-23-sequence-recording-semantics.md),
merged 2026-08-26 in [#324](https://github.com/endaye/lmdj/pull/324)):
concurrency is classified — a closed selective-rebase allowlist (BPM,
Quantize/Swing, armed-Pad Capture commit), Sample-class Commands fail while
recording continues, unknown Commands fail closed; one Project-scoped session
under the writer lease, idempotent flush, fingerprint-gated recovery.
The original implementation map was prerequisite #321, umbrella #265 and
Stage 9 Tasks
[#266](https://github.com/endaye/lmdj/issues/266)–[#275](https://github.com/endaye/lmdj/issues/275).
It closed through delivery
[#334](https://github.com/endaye/lmdj/pull/334) as Product Build `1.0.37.0`,
with exact-main evidence added by [#356](https://github.com/endaye/lmdj/pull/356).
That delivery status does not convert the physical/manual rows under
[#360](https://github.com/endaye/lmdj/issues/360) into passes, and it does not
resolve findings in the pending post-delivery review
[#367](https://github.com/endaye/lmdj/pull/367).

### ~~D5. Take scope — events only, or audio bounce too~~ — decided 2026-08-23, delivery merged 2026-08-27

~~Determines the Take contract, Web Audio recording and Export Pack. Also
Stage 9-adjacent.~~

**Decided 2026-08-23** (same review and decision file as D4): events only —
no Take product object and no audio bounce; the next Project Contract removes
`takes` and records tick-native Pattern events; Export Pack derives only from
Project Truth. The delivery and its remaining acceptance/review boundaries are
recorded with D4 above.

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
F1–F5 and the F6 attack/release ramp are combined into Product Build
`1.0.36.0` (Creator `1.5.5`, audio-runtime `0.5.1`). The 2026-09-01 M2 run on
`1.0.40.0` physically confirmed the strict non-zero trim boundary, stop ramp,
and both loop modes. The approximately 40 ms loop's rapid repeated texture was
initially described as a seam click, but exact replay produced no obvious
independent transient and the operator corrected the final classification to
normal short-loop playback. The resulting #511 report records that superseded
interpretation, not a reproducible product defect.

F1, F2, F3 and F5 are Creator front-end defects and are scoped together in
[`2026-08-17-lmdj-creator-capture-ui-remediation.md`](../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md).
F4 and F6 each needed a product decision and were explicitly excluded from
that plan; both decisions landed 2026-08-24, F4 is implemented in
[`2026-08-24-lmdj-capture-input-gate-and-identity.md`](../superpowers/plans/2026-08-24-lmdj-capture-input-gate-and-identity.md)
and F6 in
[`2026-08-24-lmdj-render-path-amplitude-ramp.md`](../superpowers/plans/2026-08-24-lmdj-render-path-amplitude-ramp.md).

### ~~F1. The capture panel has no styling and opens below the fold~~ — fixed in `1.0.36.0`

`.capture-panel` has no rule in `apps/creator-web/src/styles.css`. It renders
as an unstyled flow element at the end of the Sample surface, with no
scroll-into-view and no focus move. Measured at 1440×900: box `y ≈ 790`,
height `157`, document height `983`. In a real browser window the panel and its
`Record into Pad N` button are entirely below the fold, so pressing
`Record Sample` looks like nothing happened.

### ~~F2. Stop is pushed off screen when recording starts~~ — fixed in `1.0.36.0`

Same root cause. Entering `recording` adds the level meter and waveform canvas,
growing the panel from 157 px to 277 px, all downward, and the page does not
scroll to follow. The take cannot be stopped from the visible surface.

F1 and F2 are one fix, combined 2026-08-24 into Product Build `1.0.36.0` /
Creator `1.5.5` (remediation plan Task 2): the panel is now a viewport-anchored modal
`<dialog>` with fixed geometry that does not grow when entering `recording`,
focus moves to the phase's primary action on open and after phase transitions,
and the Playwright gate asserts the panel's and `Stop`'s `boundingBox` against
a 1280×720 viewport. The physical re-walk that confirms the fix by hand stays
open in `2026-08-17-manual-verification-todo.md` (remediation plan Task 5).
Every automated journey locates the panel by role and
label, which never requires the element to be above the fold — this class of
defect was invisible to the whole browser gate until the `boundingBox`
assertion was added.

### ~~F3. `DUPLICATE_ID` presents as fatal with no way out~~ — fixed in `1.0.36.0`

Re-importing a bundle whose local Project has since diverged renders under
`Creator unavailable` with no recovery control (`error_panel.tsx:36`); only
`PROJECT_BUSY` and `HOST_RESTART_REQUIRED` get one. No data is lost —
`Open local` still opens the diverged Project, and a plain reload clears the
error. The defect is the presentation and the missing affordance.

Fixed 2026-08-24 in Product Build `1.0.36.0` / Creator `1.5.5` (remediation
plan Task 4): `DUPLICATE_ID` no longer renders under the fatal
`Creator unavailable` heading — the panel names the actual situation
("Project already on this device"), explains that the import was refused
because the local copy of the Project has newer changes and that nothing was
lost, and offers an `Open local Project` recovery control that leads to the
local Projects list (the same destination as `Open local`) and dismisses the
panel without a reload. Every other error code's heading, message and
retry wiring is unchanged. The physical re-walk that confirms the fix by
hand stays open in `2026-08-17-manual-verification-todo.md` (remediation
plan Task 5).

### ~~F4. A silent default input commits silence with no indication~~ — fixed in `1.0.36.0`

`capture_controller.ts:62` requests audio with no `deviceId`, so capture follows
the OS default input; the absent device picker is a **declared** scope boundary
for this Build, so that omission is not the finding. The finding is its physical
consequence: when the default input changes silently, `getUserMedia` succeeds,
the stream carries digital silence, and the Creator commits a full 5 s of
silence onto a Pad with no input-level gate, no silence detection and no
warning. The operator's only signal is the level meter, which F1 and F2 keep
off screen.

Fixed 2026-08-24 in Product Build `1.0.36.0` / Creator `1.5.5`, implementing
the [2026-08-24 decision](../prd/decisions/2026-08-24-capture-input-gate-and-identity.md)
(option a + b, no device picker): committing a take whose whole-take measured
peak is exactly zero — digital silence — is refused with an in-panel
explanation that the input device may have been switched by the system; the
take is kept intact so the operator can re-record or discard, and only
strict zero refuses, so quiet-but-nonzero real takes are never blocked. The
Capture panel also shows the current input device name during recording and
trimming (falling back to a "Default input" placeholder when the browser
withholds the label) and shows a non-blocking notice when the device set
changes mid-recording. The device picker remains a declared scope boundary.
The physical re-run that proves the gap is closed by hand stays open in
`2026-08-17-manual-verification-todo.md` (the "F4 resolution lands" trigger
row).

### ~~F5. The waveform trim handles cannot be aimed~~ — fixed in `1.0.36.0`

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

Fixed 2026-08-24 in Product Build `1.0.36.0` / Creator `1.5.5` (remediation
plan Task 3): each handle line is now a visible grip (14px bar with top/bottom
affordances) whose grab zone spans 12 px to each side of the line, partitioned
at the midpoint between the two lines so adjacent handles stay independently
grabbable; a press grabs only the handle pointed at, the drag preserves the
grab offset so no press can jump a trim point, and a press on the waveform
body outside both zones moves nothing. The range inputs remain the
keyboard/assistive-technology channel with their live-second accessible
names, removed from the pointer path. The physical re-walk that confirms the
fix by hand stays open in `2026-08-17-manual-verification-todo.md`
(remediation plan Task 5).

Scoped in
[`2026-08-17-lmdj-creator-capture-ui-remediation.md`](../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md)
with F1–F3.

### ~~F6. The render path has no amplitude ramp anywhere~~ — fixed in `1.0.36.0`

Trimming a Sample and triggering it produces audible clicks at the trim
boundaries — the first check of row M2, 2026-08-17.

Not a Creator defect. `realtime_engine.cpp:710` renders
`voice.samples[voice.cursor] * voice.gain` and at `end_frame` either assigns
`voice.cursor = voice.start_frame` for a loop or hard-stops; `stop_voice`
(`:195`) sets `voice.active = false` immediately. There is no attack ramp, no
release ramp, no fade at the trim boundary, no crossfade at the loop seam and
no zero-crossing snap. A trim edge on a non-zero sample is a step
discontinuity, which is what the click is.

The same absence left loop seams and held release as physical-hearing risks.
The later physical rerun found held release clean and, after exact replay and
operator correction, found no obvious independent loop-seam click.

Fixed 2026-08-24 in Product Build `1.0.36.0` (audio-runtime `0.5.1`),
implementing the
[2026-08-24 decision](../prd/decisions/2026-08-24-render-path-amplitude-ramp.md)
(96-frame linear attack/release, no zero-crossing snap): the realtime render
path now ramps voice gain from 0 to full over exactly 96 frames (2 ms at the
engine's fixed 48 kHz) from trigger, fades non-looping voices linearly to
zero across the last 96 frames before `end_frame`, and turns `stop_voice`
into a 96-frame release tail with the `stopped` publication timing unchanged
(published at stop initiation) — a second stop or a steal hard-kills a
releasing voice. All ramp state is POD fields on the voice; the render path
stays allocation-free and lock-free. The loop-seam crossfade remained
**deferred** by the decision. The 2026-09-01 physical M2 rerun on `1.0.40.0`
confirmed a clean strict non-zero trim boundary, clean Gate release/Toggle
stop, and both loop modes. Exact replay of the 40 ms loop produced no obvious
independent seam transient; the operator corrected the initially reported
rapid “clicking” to the normal texture of the short selection repeating about
25 times per second. The exact run and correction are retained in the
[hearing evidence](../release-evidence/2026-09-01-stage8-m2-macos-chrome-hearing-1.0.40.0.md).
M2 therefore passes without an Audio Runtime change.

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
the `O_NOFOLLOW` symmetry that `read_artifact()` has). ~~D4
(`native-test-host` in the Assembly, listed as A2 above)~~ — resolved
2026-08-24 by the rename; see A2.

---

## Suggested order

1. ~~**A1 real-microphone check**~~ — done 2026-08-17. The capture chain
   passed all five hearing criteria; the session returned F1–F4, of which
   ~~**F1 + F2 are one cheap fix**~~, ~~F5~~, ~~F3~~ and ~~F4~~ are combined
   into `1.0.36.0` (2026-08-24). Only the physical
   re-walks remain (remediation plan Task 5 and the F4 trigger row).
2. ~~**B1 + B2 together**~~ — done 2026-08-18. ~~B3~~ done 2026-08-21 in #226
   (`4312a6de`). B4 remains open.
3. ~~**C1**~~ — invalidated by measurement; superseded by the facade
   coverage-raise plan (machine list C6).
4. ~~**D4 + D5** — Stage 9 depends on them.~~ — decided in
   [#324](https://github.com/endaye/lmdj/pull/324); the original delivery map
   closed through [#334](https://github.com/endaye/lmdj/pull/334) on
   2026-08-27. Physical/manual acceptance remains under
   [#360](https://github.com/endaye/lmdj/issues/360), and pending review
   [#367](https://github.com/endaye/lmdj/pull/367) is a separate remediation
   boundary.
5. ~~**D1 + D2 product direction**~~ — decided 2026-08-26; the bounded D1
   accounting and Web ingest-memory amendment [#357](https://github.com/endaye/lmdj/issues/357)
   remains mandatory before any long-material implementation.
6. ~~**A2**~~ — done 2026-08-24 (rename to `native-host` + distribution
   contents rule; see the A2 section). (~~A3~~ decided and implemented
   2026-08-24, [#286](https://github.com/endaye/lmdj/issues/286).)
7. ~~**B3**~~ — done 2026-08-21 in #226. **B4, C2, backlog C2** — mechanical
   hardening, schedule as capacity allows.
