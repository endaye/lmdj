# Machine Task TODO — 2026-08-17

Everything a coding agent can complete without a human in the loop. Its
companion is [`2026-08-17-manual-verification-todo.md`](2026-08-17-manual-verification-todo.md),
which holds the verifications and decisions that require a person. Between them
the two lists cover every open item in
[`2026-08-16-outstanding-work-before-stage9.md`](2026-08-16-outstanding-work-before-stage9.md),
which stays the canonical triage record; these two are the working lists.

Compiled against `main` at `801fa450` on 2026-08-17.

## Rules that apply to every task here

- Each task needs its own plan under `docs/superpowers/plans/` with a
  `## Version Management` section before implementation starts, per
  `CLAUDE.md`. Several tasks below already have one; the rest do not.
- Each task is one reviewable Conventional Commit on its own
  `feat/` / `fix/` / `docs/` branch in an isolated worktree. Never on `main`.
- A task marked **blocked** must not be started by inventing the missing
  decision. Take it to the decision row named in its Blocked-by column.
- Local commits are autonomous. Push, Pull Request, merge, tag, Release,
  publication, deployment and Channel promotion each need separate explicit
  authorization.

---

## Ready — no decision needed

| ID | Task | Source | Shape |
| --- | --- | --- | --- |
| ~~B1~~ | ~~Make `audit` assert `main` ancestry, matching what `prepare` already requires~~ | triage B1 | **done 2026-08-18** (`33dbff7c`). Narrower than triage stated: ancestry was already asserted after a remote tag existed; the gap was the two pre-mutation paths. Abandoned and superseded-unreleased intents stay ungated by design |
| ~~B2~~ | ~~Emit the Portal snapshot witness on the merge path, or make the failure name the exact command that resolves it~~ | triage B2 | **done 2026-08-18** (`edb16910`). The first option is impossible by construction — the witness records a revision that exists only after the merge, and must itself be committed. The failure now carries the command, and the command derives its second argument |
| ~~B3~~ | ~~Derive Product Build identity wherever a gate can read committed truth; where a literal is unavoidable, make its failure message name the version~~ | triage B3 | **done 2026-08-21** (`4312a6de`, [#226](https://github.com/endaye/lmdj/pull/226), plan [`2026-08-21-lmdj-product-version-identity-derivation.md`](../superpowers/plans/2026-08-21-lmdj-product-version-identity-derivation.md)). Current consumers derive from committed `products/lmdj/version.json`; Creator `module.json` / `package.json` / `package-lock.json` identity is gated; mismatch failures name expected, found, authority, and consumer. Issue [#207](https://github.com/endaye/lmdj/issues/207) stayed OPEN because the squash subject omitted `Closes #207` |
| ~~A3~~ | ~~Reshape the published artifacts: ship the Build Manifest as a detached sibling Release asset and keep the archive payload-only~~ | triage A3, decided 2026-08-24 in [`../prd/decisions/2026-08-24-build-manifest-detached.md`](../prd/decisions/2026-08-24-build-manifest-detached.md) ([#211](https://github.com/endaye/lmdj/issues/211)) | **Implemented 2026-08-24** ([#286](https://github.com/endaye/lmdj/issues/286), plan [`../superpowers/plans/2026-08-24-lmdj-detached-build-manifest.md`](../superpowers/plans/2026-08-24-lmdj-detached-build-manifest.md)). The packager writes `<package-name>.build-manifest.json` beside the archive instead of inside it — two clean packagings now produce byte-identical ZIPs with manifests differing only in `build_time` — and the three inventory gates (`profiles` / `prepare` / `audit`) are profile-aware: core-package four assets with the Manifest's Contract, Product identity and Git revision verified against the intent; web-runtime-host stays at three. Push, PR, merge, Issue closure and main CI remain separate evidence until performed |
| B4 | Fold `assembly.lock.json` regeneration into whatever writes the compiled assembly, or make `version.py lock` refuse to run before the source is final | triage B4 | bit twice in one allocation; the second time surfaced only at the portal freeze ([#208](https://github.com/endaye/lmdj/issues/208)) |
| ~~C2~~ | ~~Restructure `decision-log.md` and `open-questions.md` so concurrent branches stop colliding~~ | triage C2 | **done 2026-08-18** (`5a9c11a7`, plan [`2026-08-18-lmdj-prd-append-structure.md`](../superpowers/plans/2026-08-18-lmdj-prd-append-structure.md)). One entry per file: new decisions in `docs/prd/decisions/`, each open question in `docs/prd/questions/`; no hand-maintained index — an index edited on every addition is itself a shared append point |
| ~~C4~~ | ~~Give `project_store.cpp`'s JSON read paths the `O_NOFOLLOW` symmetry `read_artifact()` already has~~ | 2026-08-03 backlog C2, still open | **closed by verification 2026-08-19** ([record](2026-08-18-project-io-json-symlink-symmetry.md)). The asymmetry is gone: both read paths share `ProjectStoragePlatform::read_complete()`, whose native implementation already opens with `O_NOFOLLOW` — the placement the 2026-08-03 plan prescribed when it withdrew the in-`read_json` edit. What was missing was the file-level test; `test_json_reads_reject_symlinked_files` now locks it |
| C5 | Make `scripts/architecture-portal.sh witness` refuse an existing witness file cleanly instead of throwing an unhandled `EEXIST` rejection | found while closing B2, 2026-08-18 | `create-squash-witness.mjs:41` is the only `wx` write in the script family, and it is the outlier: `version-docs.mjs:123` and `snapshot-provenance.mjs:394` both refuse with a named error. **Keep the refusal** — `wx` is what stops a witness being silently overwritten; only its presentation is wrong. Now easier to hit, since B2 made this the routine remedy command ([#209](https://github.com/endaye/lmdj/issues/209)) |
| ~~C7~~ | ~~Split `tests/core/facade/application_test.cpp` before it grows further~~ | found during C6, 2026-08-19 | **Done 2026-08-19** (`be279042`), paid for by the change that made it necessary. The C6 tests took the file from 15.97s to over its 30s budget on plain Ubuntu; the failure-contract tests now live in `facade.failure_contracts` with its own budget. Measured after the split: 3.99s and 0.21s against 30s each |
| ~~C8~~ | ~~Give `domain.model_sequence` a budget it fits in, or make it fit the one it has~~ | found during C6, 2026-08-19 | **Done 2026-08-19.** Sharded by seed range, not by scenario: the five test functions all assert on **one** `static const` matrix pass, so splitting them per scenario would have made each process rebuild the whole matrix and multiplied total ASan work by five. Four registrations of 64 seeds each now carry their own unit budget and cover the same 256 seeds; a bare run still covers all of them. Local ASan 0.68–1.22s per shard, projecting to ~5.3s against 30s. Zero coverage removed, no tier or policy change |
| ~~C9~~ | ~~Shard or shrink `project_io.project_store`~~ | found while merging C8, 2026-08-19 | **Done 2026-08-19** — and not by touching the test. 93% of the file's cost was one boundary test, and that test was slow because production hashed the whole artifact **before** the cheap bundle existence check, so every rejected import paid a full SHA-256 over bytes it then discarded. Swapping the two in both import paths took the test 7.41s → 0.32s and the file 7.99s → 1.45s, with **no test change at all**. The refusal is identical either way; production now does less work on every rejected import, not only in tests |
| ~~C10~~ | ~~Split `facade.application` itself~~ | found 2026-08-19 | **Done 2026-08-19.** Measured first: no single test dominated the way C8's and C9's did, so this one genuinely needed splitting. Three binaries — `facade.application` (14 tests), `facade.sample_surface` (10) and `facade.web_runtime_limits` (1, which generates three real WAVs at the resource boundaries and was 44% of the cost by itself). Local 4.80s → 1.73s / 1.47s / 2.52s, each well inside its own 30s budget. Two wrong theories were tested and discarded first: that `Application` construction dominated (measured at 0.16 **milliseconds**, four orders of magnitude off) and that startup cleanup scans were the cost (both already short-circuit) |
| ~~C11~~ | ~~Test budget guardrail~~ | filed and done 2026-08-19 | **Done** — `tests/quality/test_budget_report.py`, wired into the coverage lane with `if: always()` and `|| true`. It reports two things because one number cannot answer both questions: **absolute** share of budget, which is what CTest actually enforces, and a **normalised** comparison against a baseline run, which separates a slower test from a slower machine. That distinction was not theoretical — this session had `build.release_prepare` regress ×1.41 while `facade.application` looked worse but was ×0.74, purely because the suite ran 47% slower overall. Never fails a build |
| ~~C12~~ | ~~Diagnose `project_io.storage_platform`'s racing-reader failure when it next occurs~~ | found 2026-08-19 | **done 2026-08-22** (plan [`2026-08-22-lmdj-storage-platform-replacement-reader.md`](../superpowers/plans/2026-08-22-lmdj-storage-platform-replacement-reader.md), [#167](https://github.com/endaye/lmdj/issues/167)). Native `read_complete` retries replacement-transient open/lock/short-pread/revalidation failures so a racing reader observes a complete old or new version; missing/symlink/non-regular complete-reads still fail. The contract test still drives shipped `read_complete` concurrently with shipped `replace_complete` and still reports `code=`/`message=` if a read returns no value |
| ~~E2~~ | ~~Add a range parameter to `CaptureBuffer.envelope(bins)`~~ | triage E2 | **implemented in corrected Product Build `1.0.29.0` by [#212](https://github.com/endaye/lmdj/issues/212)**. Recording requests the complete buffer; trimming and commit retry request the live selection. Exact integer boundaries, monotonic indexed chunk traversal, full-block-only summaries, exact partial edges, and range-keyed caching are covered. `1.0.28.0` remains the immutable rejected first candidate; it was never merged or published |
| ~~E3~~ | ~~Add invalidation to the incremental block peaks in `append()`~~ | triage E3 | **implemented in Product Build candidate `1.0.30.0` by [#213](https://github.com/endaye/lmdj/issues/213)**. Real pre-commit Crop materializes the selected PCM at frame zero, rebuilds chunk indexes and block peaks before atomic publication, and clears the range-keyed envelope cache. Repeated Crop and append-after-Crop are covered; push, PR, merge, Issue closure and main CI remain separate evidence until performed |

**C1 is deliberately not in this table.** The `application-facade` coverage
threshold sits at 84.00% against a measured 84.04% that moves ±4 lines between
runs on identical source, so any PR can be stopped at random. The fix — move
the threshold below the observed floor, or exclude the nondeterministic paths
from measurement — is a judgement about what the gate is for, so it is listed
under **Ready, but state the reasoning** below rather than as a free mechanical
change.

### Workspace state defects found by the runtime invariant harness

From [`2026-08-19-lmdj-runtime-invariant-harness.md`](../superpowers/plans/2026-08-19-lmdj-runtime-invariant-harness.md).
That plan checks the relations; it deliberately does **not** fix them. `G1`
has since replaced its pinned defect assertion with a fixed-behaviour
regression. `G3` has a branch-local implementation and replacement regression,
but remains pending exact-head CI, queue squash, Issue closure, and post-merge
`main` CI. `G5` is resolved by Issue #205: equal capacities stay unchanged,
`audio.snapshot_publication_stress` keeps the current unreachability pinned,
and the complete rollback remains defence against future capacity divergence.

**Batch G1, G2 and G4 into one commit.** All three edit
`packages/provider-sdk/src/attempt_store.cpp`, and a `provider-sdk` PATCH
cascades to 10 module manifests, ~20 hardcoded version literals, ~16 gate tables
with literal expectations, hand-authored portal prose, a new Product Build, and
an immutable portal snapshot — the `43a78e21` shape. Paying that once for three
fixes rather than three times is the whole argument.

| ID | Task | Shape |
| --- | --- | --- |
| ~~G1~~ | ~~Release the Attempt reservation on the two failure paths that write no terminal record~~ | found by the runtime invariant harness, 2026-08-19 | **Done 2026-08-20** (#200, `a3d13ad1`). The publish-failed and persist-failed paths now `remove_tree(attempt_root, …)` instead of clearing only `staging/` and `artifacts/`; the three cleanup-itself-failed paths are deliberately untouched, because leaking is the honest outcome when the filesystem is already failing. `test_orphan_reservation_is_detected_and_blocks_reuse` replaces the pinned defect assertion. **The fixed paths still have no fault-injection coverage** — they need `publish_attempt_outputs` or `persist_attempt` to actually fail; recorded in the plan rather than claimed as tested |
| ~~G4~~ | ~~Make temporary sibling names unique across processes~~ | found by the runtime invariant harness, 2026-08-19 | **Done 2026-08-20** (#200, `a3d13ad1`). `temporary_sibling` now mixes in a per-process nonce drawn once from `std::random_device`. Not `getpid()`: this module also compiles for Emscripten, where a stub pid would defeat the purpose |

### Ready, but state the reasoning in the plan


| ID | Task | Why it needs an argument, not just a diff |
| --- | --- | --- |
| G2 | `fsync` the Host settings write, or state why this state is allowed to be non-durable | `write_bytes` flushes and closes but never `fsync`s, and `write_replace_atomic` never syncs the containing directory around the `rename`, so a crash can leave a truncated file that every later read rejects. The asymmetry looks unintentional — the lease path *does* sync (`native/storage_platform.cpp:1057`) — but the fix changes the I/O primitive, costs a sync per selection write, and means nothing on the Emscripten/OPFS path. Argue durability scope, not just the call ([#203](https://github.com/endaye/lmdj/issues/203)) |
| G3 | Give the Host settings lock crash recovery, or define what a surviving lock means | **Implementation prepared 2026-08-22** ([#204](https://github.com/endaye/lmdj/issues/204), [plan](../superpowers/plans/2026-08-22-lmdj-host-settings-flock-crash-recovery.md)). Branch-local native writers take fail-fast `flock(LOCK_EX | LOCK_NB)` and hold its descriptor across the complete read-modify-write; the kernel releases ownership when the process dies. Emscripten/Web remains a no-op because it has no persistent or concurrent Provider execution path. Completion remains pending exact-head CI, Integration Queue squash, Issue closure, and post-merge `main` CI. |
| ~~G5~~ | ~~Decide whether `publish_queue_full` should be reachable, or document the branch as defensive~~ | **Done 2026-08-22** ([#205](https://github.com/endaye/lmdj/issues/205), [plan](../superpowers/plans/2026-08-22-lmdj-publish-queue-full-defensive.md)). Keep the equal capacities and the complete rollback: `audio.snapshot_publication_stress` pins current unreachability with a `static_assert`, zero `publish_queue_full` outcomes, and zero queue-drop telemetry; the production branch is documented as defence against a future capacity divergence. Realtime headroom is not changed merely to exercise an error path. |
| ~~C1~~ | ~~Stabilise the `application-facade` coverage gate~~ | **Done 2026-08-19**, though not as filed and not as first rebutted. A 2026-08-18 measurement claimed Ubuntu was deterministic and that C1 did not exist; that was undersampled and is **withdrawn** — a byte-identical tree measured 3526 and 3522 covered lines on two Ubuntu runs, the ±4 C1 described. The old 84 floor sat inside that band with ~2 lines of margin. Resolved by C6 raising real coverage and ratcheting the floor to 85, which leaves ~47 lines |
| ~~C6~~ | ~~Raise facade line coverage to 90% and ratchet the floor~~ | **Substantially done 2026-08-19** (#188, `93b7d3f2`). 84.04% → **86.15%** Ubuntu, via behavioral tests for failure semantics that had none: 22 public catch-alls, Sample import storage seams, the session limit, and startup's staging refusal — all mutation-verified. Floor ratcheted 84 → 85. The 90% target remains open: `render_offline` and `cook_project` need a cook/render seam the storage decorator does not reach, and belong in the new `facade.failure_contracts` binary |

---

## Ready — plan already written

| ID | Task | Plan | Status |
| --- | --- | --- | --- |
| ~~F1 + F2~~ | ~~Capture panel presentation, position and focus~~ | [Creator UI remediation](../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md) Task 2 | **done 2026-08-24** — viewport-anchored modal panel on a shared `ModalDialog` primitive, focus follows the phase's primary action, `Escape` closes in every phase; combined into Product Build `1.0.36.0` / Creator `1.5.5` |
| ~~F5~~ | ~~Replace the trim handle pointer model~~ | same plan, Task 3 | **done 2026-08-24** — visible grips with midpoint-partitioned grab zones, grab-offset drags with no jump-to-click, inert waveform middle, keyboard/AT channel unchanged; combined into Product Build `1.0.36.0` / Creator `1.5.5` |
| ~~F3~~ | ~~Recoverable presentation for `DUPLICATE_ID`~~ | same plan, Task 4 | **done 2026-08-24** — distinct non-fatal heading ("Project already on this device"), body names the refusal and that nothing was lost, `Open local Project` control leads to the local Projects list and dismisses the panel without a reload; combined into Product Build `1.0.36.0` / Creator `1.5.5` |
| ~~—~~ | ~~Design gate for the above~~ | same plan, Task 1 | **done 2026-08-24** — [decision](../prd/decisions/2026-08-24-capture-panel-modal-and-trim-handles.md): modal capture panel, focus follows the primary action, visible-grip midpoint-partitioned trim handles, recoverable `DUPLICATE_ID` |

The whole plan is one branch's worth of work now that P2 has landed. Its
Task 5 hands back to the human list.

---

## Blocked on a decision

Listed so nothing is lost. Each becomes machine work the moment its decision
row is answered.

| ID | Task | Blocked by |
| --- | --- | --- |
| ~~F1, F2, F3, F5~~ | ~~Creator UI remediation Tasks 2–4~~ | **done 2026-08-24** — viewport-anchored modal Capture panel with focus following the primary action, visible-grip midpoint-partitioned trim handles, and recoverable `DUPLICATE_ID`, per the [decision](../prd/decisions/2026-08-24-capture-panel-modal-and-trim-handles.md); combined into Product Build `1.0.36.0` / Creator `1.5.5` |
| ~~F4~~ | ~~Digital-silence commit gate plus visible input identity in the Capture panel~~ | **done 2026-08-24** — whole-take strict-zero peak refuses Commit with an in-panel explanation and the take kept; input device name shown during recording/trimming with a "Default input" placeholder fallback; non-blocking `devicechange` notice scoped to the recording phase, per the [decision](../prd/decisions/2026-08-24-capture-input-gate-and-identity.md); combined into Product Build `1.0.36.0` / Creator `1.5.5` |
| ~~F6~~ | ~~Amplitude ramp in the render path, under a realtime-safety review~~ | **done 2026-08-24** — 96-frame (2 ms at the fixed 48 kHz) linear attack ramp from trigger, stateless boundary fade over the last 96 frames for non-looping voices, and a 96-frame `stop_voice` release tail with `stopped` published at initiation and hard-kill on a second stop, all in POD voice state (no heap, no locks), per the [decision](../prd/decisions/2026-08-24-render-path-amplitude-ramp.md); loop-seam crossfade stays deferred; combined into Product Build `1.0.36.0` / audio-runtime `0.5.1` |
| ~~A2~~ | ~~Rename `native-test-host` and change the Assembly, **or** remove it from the Assembly and every distribution and return it to `tests/`; either way, write the rule for what may enter a distribution package~~ | **done 2026-08-24** on `endaye/assembly-native-test-host-ships-in-the-product-a` ([#210](https://github.com/endaye/lmdj/issues/210), plan [`2026-08-24-lmdj-native-host-rename-and-distribution-rule.md`](../superpowers/plans/2026-08-24-lmdj-native-host-rename-and-distribution-rule.md)). Decision: rename — `native-test-host` (retired at `1.0.14`, never reused) becomes `native-host 1.0.0` in Product Build `1.0.31.0`; binary, protocol and test surface unchanged. The distribution rule is [`docs/governance/distribution-contents.md`](../governance/distribution-contents.md), with `scripts/package-core.py` as its single mechanical inventory. Push, PR, merge and Issue closure remain separate authorized steps |
| D1, D2 | Cooker Bank allocation, `PreparedSampleBank` publication layout, manifest semantics, Facade validation, and the `bank_quota_exhausted` failure class | **Unblocked 2026-08-26** — the D1 + D2 [decision](../prd/decisions/2026-08-26-long-material-quota-and-bpm-stretch.md) merged in [#339](https://github.com/endaye/lmdj/pull/339); the work is decomposed into umbrella [#341](https://github.com/endaye/lmdj/issues/341), Tasks [#342](https://github.com/endaye/lmdj/issues/342)–[#346](https://github.com/endaye/lmdj/issues/346), gated first on the implementation plan (#342) |
| ~~D3~~ | ~~Schema provenance on `ArtifactRef` and an input resolver on `AttemptStore`; retire the prototype's Host-injected bridge rather than graduating it~~ | **Decided 2026-08-24** ([#206](https://github.com/endaye/lmdj/issues/206), [decision](../prd/decisions/2026-08-24-provider-artifact-byte-access.md), plan [`2026-08-24-lmdj-provider-artifact-byte-access-decision.md`](../superpowers/plans/2026-08-24-lmdj-provider-artifact-byte-access-decision.md)). A capability-gated `ArtifactSource` in provider-sdk is the sanctioned shape, deliberately **not implemented yet** — the trigger is the first formal Capability that must parse structured Artifact bytes. Option C is permanently rejected; the replay Provider proceeds under option B |
| ~~D4, D5~~ | ~~Stage 9 Sequence recording implementation (event-only Pattern Contract; the former "Sequence/Take Contract" naming is retired)~~ | **delivery merged 2026-08-27** — the D4 + D5 [decision](../prd/decisions/2026-08-23-sequence-recording-semantics.md) merged in [#324](https://github.com/endaye/lmdj/pull/324); prerequisite #321, umbrella #265 and Tasks [#266](https://github.com/endaye/lmdj/issues/266)–[#275](https://github.com/endaye/lmdj/issues/275) closed through delivery [#334](https://github.com/endaye/lmdj/pull/334) as Product Build `1.0.37.0`, with exact-main evidence added by [#356](https://github.com/endaye/lmdj/pull/356). This closes the original machine-delivery map, not physical/manual acceptance [#360](https://github.com/endaye/lmdj/issues/360) or findings in the pending post-delivery review [#367](https://github.com/endaye/lmdj/pull/367) |

---

## Suggested order

1. ~~**B1 + B2**~~ — done 2026-08-18 on `fix/release-audit-ancestry`, plan
   [`2026-08-18-lmdj-release-audit-ancestry-and-witness-remedy.md`](../superpowers/plans/2026-08-18-lmdj-release-audit-ancestry-and-witness-remedy.md).
2. ~~**C1**~~ — invalidated by measurement; the gate is deterministic where it
   enforces. **C6 replaces it at the top of the ready queue**: Tier A alone is
   one Task and lands ≈88–89%.
3. **The Creator UI remediation branch** — P2 landed 2026-08-24
   ([decision](../prd/decisions/2026-08-24-capture-panel-modal-and-trim-handles.md)).
   Four findings, one branch, and it is what makes Pad Capture usable by
   hand.
4. ~~**C2**~~ — done 2026-08-18 on `docs/prd-append-structure`.
5. ~~**B3**~~ — done 2026-08-21 (`4312a6de`, #226). **B4, C5** — mechanical
   hardening, schedule as capacity allows. C5 is the smallest of them and
   sits in the path operators now walk on every snapshot-carrying Build.
   (C4 closed by verification — see the Ready table.)
6. ~~**E2**~~ — implemented with real selection zoom in corrected candidate
   `1.0.29.0`; `1.0.28.0` is retained as rejected review evidence. **E3**
   starts only with the approved pre-commit Crop feature.

Everything else waits on a decision, not on capacity.
