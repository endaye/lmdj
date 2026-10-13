# Headered Performance capture capability

Date: 2026-10-13
Status: SOURCE-only implementation; all product verification UNRUN.

## Premises and integration base

The worktree was created at D03's actual integration
`ecc2c9ece903bcbd8205e6dde655c28ec07ebf2a` (PR #2107). Before any Source
edit, an actual origin/main fetch resolved
`fe6f30bbf3897d3b09e25e4e85f4b1b22df7db23`, whose parent is that D03
integration. Its successor PR #2116 changes two unrelated paths and no owning
SDK, API or governance path; only successor path metadata was inspected.
The clean isolated `fix/headered-performance-capture-handle` branch was
fast-forwarded to that revision, tree
`bb612dd16b2fb60acfb7be1d754160515042716c`, as UID/EUID 501.

The bounded preparation report at `25b8875478396df39ff0882c223c4c11bdf98806`
is historical diagnosis, not verification of this base. Current-source
dispositions at the refreshed base are:

- Still outstanding: headered `beginPerformanceRecording` awaits the bound
  SDK capture but discards its wrapper, and its result type has no capture
  capability. Retain and return that exact wrapper only for a supplied sink.
- Still outstanding: `releaseOwnership` qualifies active ownership but clears
  pending ownership unconditionally. A terminal A's first late stop can clear
  B's pending reservation and allow C to reach the lower start unnecessarily.
  Qualify pending cleanup with the existing `pendingOwner` object identity.
- Already delivered: Core-ready plus matching capture-start ACK, bounded
  input admission, original FX mapping and lower generation/binding isolation.
  Preserve them. The real lower controller already refuses overlapping starts;
  no two-tap, wrong-generation stop or current Creator failure is claimed.
- Current Creator is a positive source control: its existing legacy begin
  path retains a separately acquired capture. C1 owns later adoption and real
  Record / Stop / Save / Reopen / Replay / PCM / browser / hearing acceptance.

## One Task and exactly five declared files

1. `packages/web-runtime-platform/web/runtime_session.mjs`: retain the bound
   capture, expose it only on the sink result, and qualify pending cleanup.
2. `packages/web-runtime-platform/web/runtime_types.d.ts`: add optional
   `readonly capture?: PerformanceMasterCapture` to the headered result.
3. `packages/web-runtime-platform/test/runtime_session.test.mjs`: preserve the
   complete original suite and add public-boundary ownership regressions.
4. `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`: document the
   exact capability and caller stop/queue ownership; preserve D03/W1 text.
5. `docs/plans/2026-10-13-headered-performance-capture-handle.md`: this plan.

No Core, wire, Project Truth, Contract, controller, worklet, Creator, manifest,
compiler configuration or diagram mutation belongs here. No new owner token,
registry, private queue or stop-current API is needed. The separate pending-Pad
capacity repair remains queued after this Task's integration.

## Implementation invariants

The optional value is the already frozen SDK wrapper returned by this start,
never the lower handle or a global-current lookup. Legacy and headered no-sink
result shapes remain exact. Both original readiness observations precede begin
return and lane release; begin/session/owner generations, initial FX bindings,
parked first-Pad/FIFO, one running plus one ordinary waiter, reserved Pad release
slots, all deadlines and all budgets remain intact.

The wrapper keeps its original cached stop promise and at-most-once underlying
stop. Both active and pending release use owner identity. Old close, terminal
failure and stale/late callback isolation retain their existing behavior.

The caller finishes its recorded inputs/releases, awaits Core stop, invokes
the exact returned capture's stop, then awaits its durable queue. Core failure
still requires owned capture/queue cleanup before propagating that failure.
Capture ACK is not durable PCM: final partial flush and `finalSequence` precede
`onStopped`, and every append precedes seal. This repair does not add a later
fallible acquisition step inside begin or redesign its existing failure cleanup.

## Verification plan and defects caught

All commands below are future proposals, individually admitted by Root. The
initial phase runs no imports, syntax/tests/types/build/Portal checks or installs.

The lowest owning tier is the complete Node Runtime Session suite with actual
controller/worklet and existing sink interfaces. New regression facts are:

| Regression | Defect it catches |
| --- | --- |
| Original dual-ready/parked-Pad journey also inspects returned frozen SDK capture, binding, cached promise and one lower stop | Lost capability, early return or raw/global-current handle |
| Exact legacy/no-sink results and nonempty initial FX mapping | Added absent-path keys or changed initial binding identities |
| SDK begin, recorded press/release, Core stop, exact capture stop, final partial PCM and deferred queue completion | Stop capability fails to deliver final PCM or caller treats ACK as durable settlement |
| Core-stop failure followed by owned capture/queue completion and original error | Core failure bypasses capture cleanup or is swallowed |
| Terminal A's first late stop while B awaits its matching ACK; C refused before a third lower start; B finishes/stops once | Old A finally clears B's SDK reservation |

Use the existing real capture factory/worklet fixture pattern and the Creator
`MasterTapBatchQueue` public sink with a controlled writer in the test only.
The writer receipt models durability: this is no OPFS, physical audio, packaged
Host or C1 acceptance claim. Keep original full controller/worklet suites for
deadlines, malformed/stale traffic, generations, partial batches and teardown.

Future complete argv from this worktree (Node 26 executable identity must be
verified before admission; no test-name filter):

```sh
/Users/endaye/.hermes/node/bin/node --check packages/web-runtime-platform/web/runtime_session.mjs
/Users/endaye/.hermes/node/bin/node --check packages/web-runtime-platform/test/runtime_session.test.mjs
/Users/endaye/.hermes/node/bin/node --test packages/web-runtime-platform/test/runtime_session.test.mjs packages/web-runtime-platform/test/performance_master_capture.test.mjs packages/web-runtime-platform/test/performance_master_tap_worklet.test.mjs
```

From `apps/creator-web`, use the locked compiler and entire original tsconfig:

```sh
/Users/endaye/.hermes/node/bin/node node_modules/typescript/bin/tsc --noEmit
```

From the worktree root with Node 26 on PATH:

```sh
bash scripts/docs-site.sh check
```

The fresh worktree initially has no Creator or Portal `node_modules`; necessary
own-worktree locked installs need a later admission. Preserve natural logs,
actual exits and current-source guards for every run. No unrelated full Native,
Wasm, stress or browser lane is introduced. Shipping later also retains the
governance new-file ownership check after staging, declared-range/whitespace,
PR-body checks and genuine independent current-head review.

## Version Management

Version impact: compatible public Module/SDK capability addition; independent
MINOR accounting remains assigned to Goal V1 settlement. The current Module
manifest reads `5.8.0` at the audited base; this Task does not allocate a target
identity or edit any manifest. Product Build, Assembly, Host, Provider, Model,
persisted Contract and Project migration are unchanged here. No tag, immutable
snapshot, Release, deployment or Channel promotion is initiated. V1 must derive
actual source/target identities and dependency closure from integrated manifests.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform/
Reason: headered begin exposes its exact per-start capture capability, and
pending cleanup must retain a newer owner. Update current factual prose while
preserving derived identities and existing D03/W1 content. No topology change.

## Ownership, phase gates and retained debt

Initial authority covers own metadata preparation, read-only inspection,
external evidence and these five Source paths only. At Source-ready, provide
all five full files, full parent diff, head/parent/tree/branch/index/staging,
UID, byte/SHA inventories and concrete future argv/readiness; ask Root for the
next phase without settling the Dispatch. Verification, review, stage, commit,
push, PR and guarded squash remain sequential later admissions.

Open pitfalls for the relevant web-host/docs-governance areas were inspected.
The two product-logic defects are fully expressed by their regression tests,
so no new process-ledger entry is proposed. Keep Source findings distinct from
executed evidence and do not infer browser/physical or full-candidate acceptance.
C1's consumer/manual/hearing work, first-Pad/capacity follow-up, all unresolved
full candidate debt and V1 accounting remain open. Held/foreign resources and
their contents remain outside this Task; no cleanup is authorized.

## Executed verification checkpoint — Source V2

The status and future-command wording above preserve the initial SOURCE-only
snapshot. This dated append records the later, separately admitted execution;
it does not rewrite that history or claim an execution of the appended plan.
Root admitted this plan-only Source V3 append in `msg_44d8c93ff584` on
2026-10-13. The other four declared files remain byte-identical to Source V2.
No product rerun, Git operation or formal committed-head review is part of this
append.

All executed owning checks below bind the uncommitted Source V2 producer at
HEAD `fe6f30bbf3897d3b09e25e4e85f4b1b22df7db23`, parent
`ecc2c9ece903bcbd8205e6dde655c28ec07ebf2a`, and Source V2 manifest SHA256
`e3673615d8408fc7ec1dc9560273ffc3cb1604bf20cf412aee844e60ec43d884`.
They are not proof of a later integrated or deployed revision. Evidence root:
`/Users/endaye/Projects/lmdj-followup-evidence/2026-10-13-headered-performance-capture-handle/`.
Report paths in the following table are relative to that root; each report
binds full raw streams, exact argv, natural child and actual caller exits,
source/tool guards and process observations.

| Cut and actual result | Durable report | Report SHA256 |
| --- | --- | --- |
| Source V1: both pinned Node syntax checks passed | `syntax-v1/syntax-report.md` | `0064296bd8c9712257dab38feb8f49135b05f2bc33e3112c070a911e9274ae84` |
| Source V1: complete three-file Node run RED, 203 tests / 202 pass / 1 fail | `syntax-v1/complete-three-files.report.md` | `5e4f0f6d1a777936ddb360d01b145422c19f824192579b6f7228c575b71602e2` |
| Source V2: complete same three-file Node run PASS, 203/203, zero fail/skip/cancel/todo | `node-v2-proposal/source-v2-complete-three-files.report.md` | `c817da1a211756ced6e8ec5daeb8c94ce700b48678cd44b957bd8524c7a7478e` |
| Source V2: complete original Creator TypeScript configuration PASS | `creator-types-v1/creator-types.report.md` | `a4eab5d8082342e351b657b61f169f1df8fcb79bf292442c35d6bcfe46481a0f` |
| Source V2: whole original Portal check PASS, 177/177 tests and every later stage | `portal-check-v1/portal-check.report.md` | `e8565c6f63c043e63b999463230fd7534f200c7466cf74146f2233d1f9390242` |

The Source V1 failure was the new failure-path oracle expecting a raw Core
message. The existing SDK already sanitizes that message. Root admitted exactly
one assertion correction in `msg_11dd906c704f`: expect
`Host request was rejected`, retaining the same propagated SDK error identity,
`IO_ERROR`, all PCM/queue assertions and final order/close legs. No runtime
sanitizer, product behavior, original assertion, deadline or journey was changed
by that correction. The red run did not reach its final order/close assertions;
the complete Source V2 green run actually reached and passed them. Preserve the
original red record and the separate Source V1-to-V2 delta.

Source V1 independent SOURCE review provenance is retained in
`source-v2/preceding-node-admission-wire.json`, Root message
`msg_1c6bdc907c63`: reviewer provider session
`01a1301f-d080-7b01-a427-39aedff8554c` differs from author session
`01a13359-84d5-7bf3-9434-4a7890093efd`. Root reported a full five-path
source review with no findings, 173 original literal test bodies unchanged and
ten original dual-ready assertions retained. At that receipt the sealed report
was pending. This historical source review predates the oracle correction and
this factual append; it is not a formal review of a committed current head.

Source V2 Node used the original complete runtime-session, capture-controller
and worklet test files: 182 + 17 + 4 tests. It exercised the actual SDK/factory,
VM worklet and Creator queue with controlled ports/writer promises. Both stop
chains passed final partial PCM, finalSequence, append/seal ordering, settlement
and owned cleanup. It remains Node integration/model evidence, without real
browser scheduling, OPFS durability or hearing acceptance.

The actual Creator command, equivalent to the original entire-config proposal,
ran from the repository root with locked TypeScript 7.0.2:

```sh
/Users/endaye/.hermes/node/bin/node apps/creator-web/node_modules/typescript/bin/tsc --noEmit --project apps/creator-web/tsconfig.json
```

Every original `src`, `test` and `vite.config.ts` include remained. The 180
scope-file fingerprints and compiler/installed-lock inputs were unchanged; 180
is a source inventory count, not a claimed compiler program-file count. Both raw
streams were empty, natural child and actual caller exited 0. This existing
producer configuration passing does not close the separately identified public
FX type/overload gap or establish C1 consumer integration.

The whole `bash scripts/docs-site.sh check` preserved the original npm test,
validate:docs, validate:diagrams, facts, check:release-docs, typecheck, build and
check:build chain. Actual output reports 177/177 tests, 52 current pages,
10 diagram sources and 20 outputs, current Product snapshot matching repository
truth, full Portal typecheck, two Host/four Release changelog projections,
optimized static build, and 50 routes/internal links valid. Natural child and
actual caller exited 0; 612 before/609 after guards had no findings. Standard
ignored Portal output was retained. Seven localStorage ExperimentalWarnings
remain in stderr without suppression.

Root's final Portal acceptance is
`portal-check-v1/root-headered-capture-full-portal-acceptance-v2.json`, 1604 B,
SHA256 `d898416fe1dc72b4d182677c3c2dc76141589505ff519a1d1f5c38f4e750a08e`.
Its 4186 checks had no findings. Root preserved an earlier receipt whose
verification script incorrectly used splitlines for a NUL-delimited Git file
list; correcting that external parser required no product change or rerun.

### Setup and access-boundary provenance

Creator and Portal each received one separately admitted locked installation in
this own worktree, with distinct task-local npm caches. Original package/lock,
source/index and global configuration remained unchanged. Full setup receipts
are in `creator-install-v1/` and `portal-install-v1/`; install-script,
deprecation and npm-update warnings remain intact. Portal's declared
`npm@10.9.3` and Root's explicitly admitted pinned npm 11.19.0 are both recorded;
the declaration was not rewritten. Node was the pinned 26.8.1. The only child
environment override was its bin directory prepended to PATH, with HOME and
UID/EUID501 preserved. Direct live UID samples for the short Node test runs
remain UNKNOWN; later successful setup/type/Portal samples do not rewrite them.

`portal-boundary-v1/` preserves the stop before any Portal execution when the
unchanged historical facts helper was found to archive and extract an entire
Git tree. Root message `msg_85df059f0b7f` subsequently admitted only that standard
opaque mechanical copy of the normally validated metadata revision and resolved
contentRevision, plus existing synthetic Portal repositories, with the helper's
original temporary cleanup. Normal facts consumers remain Product
version/assembly/lock, component manifests, Contract schemas/profiles, Provider
source-package members and Product CMake/compiled assembly. No excluded Native
Facade replay/R-H content may be viewed, separately hashed for evidence,
imported, executed, reviewed, debugged or consumed through another agent.
No held worker resource/command/evidence access or worktree/cache cleanup was
admitted. This narrow exception did not reopen the held Task or permit a
modified archive/check. The preserved pre-execution stop consumed no invocation.

All earlier negative records remain separate: the original red test, Root's
corrected admission-wire hash metadata, read-only missing-path probes and Root's
NUL-parser receipt. No prior failed, unrun or unknown observation is relabeled as
a pass by this checkpoint.

### Remaining independent work and shipping boundary

- B1 public FX type closure, including the inherited nonfresh/overload boundary,
  remains a separate upstream Task; no public type workaround was folded here.
- B2a covers the initial SDK RPC interval; the earlier pre-SDK UI preparation
  product question remains pending and is not settled by this capability repair.
- B3 pending64/capacity work remains a separate follow-up after actual integration.
- C1 still owns Record consumer integration and Record / Stop / Save / Reopen /
  Replay / PCM acceptance. A returned capture capability is not a Record-ready
  or C1-accepted claim.
- Real browser, OPFS, physical audio/hearing, full-candidate verification and
  Goal V1 dependency/version settlement remain outstanding.

The compatible public Module/SDK addition retains independent MINOR accounting
in Goal V1. This Task allocates no manifest version, Product Build, Assembly,
immutable snapshot, tag or release identity. The documentation impact and owning
route above remain unchanged. No new Product/Contract/concurrency decision is
made by this verification appendix.

Source V3 changes only this plan appendix; all other four Source V2 files and
read-only inputs stay frozen. At this checkpoint Git staging/commit/push/PR,
formal current-head independent review, guarded merge and Task settlement await
Root's concrete source review and shipping disposition under the existing Task
authorization. Release, deployment, Channel promotion and cleanup remain outside
this Task.
