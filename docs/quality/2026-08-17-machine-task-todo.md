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
| B4 | Fold `assembly.lock.json` regeneration into whatever writes the compiled assembly, or make `version.py lock` refuse to run before the source is final | triage B4 | bit twice in one allocation; the second time surfaced only at the portal freeze ([#208](https://github.com/endaye/lmdj/issues/208)) |
| ~~C2~~ | ~~Restructure `decision-log.md` and `open-questions.md` so concurrent branches stop colliding~~ | triage C2 | **done 2026-08-18** (`5a9c11a7`, plan [`2026-08-18-lmdj-prd-append-structure.md`](../superpowers/plans/2026-08-18-lmdj-prd-append-structure.md)). One entry per file: new decisions in `docs/prd/decisions/`, each open question in `docs/prd/questions/`; no hand-maintained index — an index edited on every addition is itself a shared append point |
| ~~C4~~ | ~~Give `project_store.cpp`'s JSON read paths the `O_NOFOLLOW` symmetry `read_artifact()` already has~~ | 2026-08-03 backlog C2, still open | **closed by verification 2026-08-19** ([record](2026-08-18-project-io-json-symlink-symmetry.md)). The asymmetry is gone: both read paths share `ProjectStoragePlatform::read_complete()`, whose native implementation already opens with `O_NOFOLLOW` — the placement the 2026-08-03 plan prescribed when it withdrew the in-`read_json` edit. What was missing was the file-level test; `test_json_reads_reject_symlinked_files` now locks it |
| C5 | Make `scripts/architecture-portal.sh witness` refuse an existing witness file cleanly instead of throwing an unhandled `EEXIST` rejection | found while closing B2, 2026-08-18 | `create-squash-witness.mjs:41` is the only `wx` write in the script family, and it is the outlier: `version-docs.mjs:123` and `snapshot-provenance.mjs:394` both refuse with a named error. **Keep the refusal** — `wx` is what stops a witness being silently overwritten; only its presentation is wrong. Now easier to hit, since B2 made this the routine remedy command ([#209](https://github.com/endaye/lmdj/issues/209)) |
| ~~C7~~ | ~~Split `tests/core/facade/application_test.cpp` before it grows further~~ | found during C6, 2026-08-19 | **Done 2026-08-19** (`be279042`), paid for by the change that made it necessary. The C6 tests took the file from 15.97s to over its 30s budget on plain Ubuntu; the failure-contract tests now live in `facade.failure_contracts` with its own budget. Measured after the split: 3.99s and 0.21s against 30s each |
| ~~C8~~ | ~~Give `domain.model_sequence` a budget it fits in, or make it fit the one it has~~ | found during C6, 2026-08-19 | **Done 2026-08-19.** Sharded by seed range, not by scenario: the five test functions all assert on **one** `static const` matrix pass, so splitting them per scenario would have made each process rebuild the whole matrix and multiplied total ASan work by five. Four registrations of 64 seeds each now carry their own unit budget and cover the same 256 seeds; a bare run still covers all of them. Local ASan 0.68–1.22s per shard, projecting to ~5.3s against 30s. Zero coverage removed, no tier or policy change |
| ~~C9~~ | ~~Shard or shrink `project_io.project_store`~~ | found while merging C8, 2026-08-19 | **Done 2026-08-19** — and not by touching the test. 93% of the file's cost was one boundary test, and that test was slow because production hashed the whole artifact **before** the cheap bundle existence check, so every rejected import paid a full SHA-256 over bytes it then discarded. Swapping the two in both import paths took the test 7.41s → 0.32s and the file 7.99s → 1.45s, with **no test change at all**. The refusal is identical either way; production now does less work on every rejected import, not only in tests |
| ~~C10~~ | ~~Split `facade.application` itself~~ | found 2026-08-19 | **Done 2026-08-19.** Measured first: no single test dominated the way C8's and C9's did, so this one genuinely needed splitting. Three binaries — `facade.application` (14 tests), `facade.sample_surface` (10) and `facade.web_runtime_limits` (1, which generates three real WAVs at the resource boundaries and was 44% of the cost by itself). Local 4.80s → 1.73s / 1.47s / 2.52s, each well inside its own 30s budget. Two wrong theories were tested and discarded first: that `Application` construction dominated (measured at 0.16 **milliseconds**, four orders of magnitude off) and that startup cleanup scans were the cost (both already short-circuit) |
| ~~C11~~ | ~~Test budget guardrail~~ | filed and done 2026-08-19 | **Done** — `tests/quality/test_budget_report.py`, wired into the coverage lane with `if: always()` and `|| true`. It reports two things because one number cannot answer both questions: **absolute** share of budget, which is what CTest actually enforces, and a **normalised** comparison against a baseline run, which separates a slower test from a slower machine. That distinction was not theoretical — this session had `build.release_prepare` regress ×1.41 while `facade.application` looked worse but was ×0.74, purely because the suite ran 47% slower overall. Never fails a build |
| C12 | Diagnose `project_io.storage_platform`'s racing-reader failure when it next occurs | found 2026-08-19 | Failed once on Linux CI (`observed.has_value()`), passed on rerun. **Investigated and not resolved.** The publish path is correct — temp sibling plus `renameat` — and `same_stable_metadata` already tolerates the replacement case explicitly (`st_nlink 1→0` waives the ctime change). Not reproducible on macOS in 40 runs, nor in 3 runs at **60× the replacement load**. The writer's `LOCK_EX` is on the sibling inode while the reader's `LOCK_SH` is on the destination, so locks give no mutual exclusion against the rename by design; metadata revalidation is the only guard. The assertion now reports the error code and message, so the next occurrence identifies the path in one shot instead of costing another cycle (same defect as [#167](https://github.com/endaye/lmdj/issues/167)) |
| E2 | Add a range parameter to `CaptureBuffer.envelope(bins)` | triage E2 | only when waveform zoom is actually built; a narrow window at the same bin count currently falls back to the exact path and rescans the whole buffer ([#212](https://github.com/endaye/lmdj/issues/212)) |
| E3 | Add invalidation to the incremental block peaks in `append()` | triage E3 | only when pre-commit buffer editing is actually built ([#213](https://github.com/endaye/lmdj/issues/213)) |

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
and `G3` have since deliberately replaced their pinned defect assertions with
fixed-behaviour regressions; `G5` remains pinned to the current behaviour until
its decision is made.

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
| ~~G3~~ | ~~Give the Host settings lock crash recovery, or define what a surviving lock means~~ | **Done 2026-08-22** ([#204](https://github.com/endaye/lmdj/issues/204), [plan](../superpowers/plans/2026-08-22-lmdj-host-settings-flock-crash-recovery.md)). Native writers take fail-fast `flock(LOCK_EX | LOCK_NB)` and hold its descriptor across the complete read-modify-write; the kernel releases ownership when the process dies. Emscripten/Web remains a no-op because it has no persistent or concurrent Provider execution path. The crash-recovery regression deliberately replaces the pinned directory-lock behaviour. |
| G5 | Decide whether `publish_queue_full` should be reachable, or document the branch as defensive | Unreachable at the current equal capacities, so its rollback is dead code. Either the Bank and publish-queue headroom should differ deliberately, or the branch is defence against a future capacity change and should say so. `audio.snapshot_publication_stress` pins the current answer with a `static_assert`, so whichever way this goes the test must be updated with it ([#205](https://github.com/endaye/lmdj/issues/205)) |
| ~~C1~~ | ~~Stabilise the `application-facade` coverage gate~~ | **Done 2026-08-19**, though not as filed and not as first rebutted. A 2026-08-18 measurement claimed Ubuntu was deterministic and that C1 did not exist; that was undersampled and is **withdrawn** — a byte-identical tree measured 3526 and 3522 covered lines on two Ubuntu runs, the ±4 C1 described. The old 84 floor sat inside that band with ~2 lines of margin. Resolved by C6 raising real coverage and ratcheting the floor to 85, which leaves ~47 lines |
| ~~C6~~ | ~~Raise facade line coverage to 90% and ratchet the floor~~ | **Substantially done 2026-08-19** (#188, `93b7d3f2`). 84.04% → **86.15%** Ubuntu, via behavioral tests for failure semantics that had none: 22 public catch-alls, Sample import storage seams, the session limit, and startup's staging refusal — all mutation-verified. Floor ratcheted 84 → 85. The 90% target remains open: `render_offline` and `cook_project` need a cook/render seam the storage decorator does not reach, and belong in the new `facade.failure_contracts` binary |

---

## Ready — plan already written

| ID | Task | Plan | Status |
| --- | --- | --- | --- |
| F1 + F2 | Capture panel presentation, position and focus | [Creator UI remediation](../superpowers/plans/2026-08-17-lmdj-creator-capture-ui-remediation.md) Task 2 | blocked on P2 |
| F5 | Replace the trim handle pointer model | same plan, Task 3 | blocked on P2 ([#214](https://github.com/endaye/lmdj/issues/214)) |
| F3 | Recoverable presentation for `DUPLICATE_ID` | same plan, Task 4 | blocked on P2 ([#214](https://github.com/endaye/lmdj/issues/214)) |
| — | Design gate for the above | same plan, Task 1 | **this is P2** — a person decides, the agent records |

The whole plan is one branch's worth of work once P2 lands. Its Task 5 hands
back to the human list.

---

## Blocked on a decision

Listed so nothing is lost. Each becomes machine work the moment its decision
row is answered.

| ID | Task | Blocked by |
| --- | --- | --- |
| F1, F2, F3, F5 | Creator UI remediation Tasks 2–4 | P2 |
| F4 | Whatever the device/silence resolution turns out to be | F4 decision ([#214](https://github.com/endaye/lmdj/issues/214)) |
| F6 | Amplitude ramp in the render path, under a realtime-safety review | F6 decision ([#214](https://github.com/endaye/lmdj/issues/214)) |
| A2 | Rename `native-test-host` and change the Assembly, **or** remove it from the Assembly and every distribution and return it to `tests/`; either way, write the rule for what may enter a distribution package | A2 decision ([#210](https://github.com/endaye/lmdj/issues/210)) |
| A3 | Reshape the published artifacts to whichever reproducibility option is chosen | A3 decision ([#211](https://github.com/endaye/lmdj/issues/211)) |
| D1, D2 | Cooker Bank allocation, `PreparedSampleBank` publication layout, manifest semantics, Facade validation, and a new "quota consumed by another Pad" failure class | D1 + D2 decision |
| D3 | Schema provenance on `ArtifactRef` and an input resolver on `AttemptStore`; retire the prototype's Host-injected bridge rather than graduating it | D3 decision ([#206](https://github.com/endaye/lmdj/issues/206)) |
| D4, D5 | Sequence/Take Contract implementation | D4 + D5 decision — this is Stage 9 |

---

## Suggested order

1. ~~**B1 + B2**~~ — done 2026-08-18 on `fix/release-audit-ancestry`, plan
   [`2026-08-18-lmdj-release-audit-ancestry-and-witness-remedy.md`](../superpowers/plans/2026-08-18-lmdj-release-audit-ancestry-and-witness-remedy.md).
2. ~~**C1**~~ — invalidated by measurement; the gate is deterministic where it
   enforces. **C6 replaces it at the top of the ready queue**: Tier A alone is
   one Task and lands ≈88–89%.
3. **The Creator UI remediation branch** — the moment P2 lands. Four findings,
   one branch, and it is what makes Pad Capture usable by hand.
4. ~~**C2**~~ — done 2026-08-18 on `docs/prd-append-structure`.
5. ~~**B3**~~ — done 2026-08-21 (`4312a6de`, #226). **B4, C5** — mechanical
   hardening, schedule as capacity allows. C5 is the smallest of them and
   sits in the path operators now walk on every snapshot-carrying Build.
   (C4 closed by verification — see the Ready table.)
6. **E2, E3** — only when the feature that needs them is actually built.

Everything else waits on a decision, not on capacity.
