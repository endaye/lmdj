# P1-Replay-Safety: current-main integration status (2026-10-12)

Status: SOURCE PREPARATION ONLY; the real main-first no-commit merge exists,
with no conflict and exactly nine imported index paths. The new candidate is
uncommitted. Root review and execution admission are pending; every new
minimum, Portal, full/current-head/batch-only and manual acceptance result is
UNRUN. This status applies to the integration Task below. The complete original
b87 plan after the historical boundary is retained literally as history, not
as a claim about this new Task's present state.

## Integration identity and authority

- New Task: `task_d808d75828b1`; Dispatch: `ctx_254e9fe40164`;
  author terminal: `term_2be5af91-9e30-4c49-90bd-3b9adaab20c1`.
- Own isolated worktree: `/Users/endaye/orca/workspaces/lmdj/fix-performance-replay-main-integration`;
  branch: `fix/performance-replay-main-integration`; ordinary UID 501/endaye;
  Orca setup was explicitly skipped.
- Selected Root-fetched main and current own HEAD:
  `7df1af16df5e6d864ca7968626d63f84a5d9cb63`, tree
  `ee2755ed11a13722a1a0b21e1582e477d0dd53ea`.
- Immutable imported PR #2029 head/MERGE_HEAD:
  `b87e9c922bae71e8b2f3f489103785d1e033528e`, tree
  `4af61df87be95aafd2faa987e8bf49c33d6c8fcd`; its sole parent is
  `08330f29c2889cfa54f5cee90e8d42da50593fc7`.
- Actual `git merge --no-commit --no-ff b87e9c922bae71e8b2f3f489103785d1e033528e`
  exited 0 at 2026-10-12T04:47:03.047923Z and stopped before commit. HEAD stays
  7df, MERGE_HEAD is b87, no unmerged entries exist, and only the nine declared
  paths were automatically imported/staged. This prefix is the sole subsequent
  working-tree edit and remains unstaged under Source-only authority.
- After later owning verification and staging admission, the proposed genuine
  Task Conventional Commit is
  `fix(facade): integrate replay admission with current runtime`, with ordered
  parents `[7df1af16df5e6d864ca7968626d63f84a5d9cb63,
  b87e9c922bae71e8b2f3f489103785d1e033528e]`. Its first-parent range must be only
  these nine, with every outside-nine mode/blob equal to selected main. No
  merge commit exists yet. Keeping b87 as a real parent permits a later normal
  fast-forward update of its existing PR branch; no force update is authorized.

Root owns Source review, all setup/heavy-window admission, publication,
current-head review and final guarded squash. This is a new integration Task,
not a retry or reuse of the failed/released `task_66de35f2b51b` /
`ctx_e6b88d31f429`. The old b87 local resources and failed native evidence stay
protected. The newly owned branch's nonforce rename intrinsically migrated
only its Orca `branch.base` section name, retaining exact 7df. Root explicitly
accepted that bounded migration after independent hash reconstruction; the
post-rename byte-equality assertion's exit 1 remains diagnostic evidence.
No manual/shared/global configuration repair or broader authority follows.

## Exact integration scope

1. `packages/application-facade/src/application.cpp`
2. `packages/application-facade/src/performance_replay.cpp`
3. `tests/core/facade/performance_replay_test.cpp`
4. `tests/core/facade/performance_engine_adapter_test.cpp`
5. `apps/docs-site/docs/core/modules/application-facade.mdx`
6. `apps/docs-site/diagrams/application-facade.architecture.json`
7. `apps/docs-site/static/diagrams/application-facade.html`
8. `apps/docs-site/static/diagrams/application-facade.svg`
9. `docs/plans/2026-10-11-performance-live-control-admission.md`

All eight non-plan files remain byte/mode/blob-identical to b87. The original
22298-byte plan, SHA-256
`393b64cb11b81a8801ae45dbdd8ef75815227fc41685d71769922395989a1666`,
is one exact contiguous suffix. The 35 intervening 08330-to-7df paths have no
intersection with these nine; all nine main inputs still retain 08330's exact
mode/blob/bytes, including the plan's absence. The merge imported only the
bounded Replay safety implementation. SDK, Host, Creator, Core Audio, CMake,
manifest, Contract, configuration, tooling, ledger and shared follow-up files
are outside this edit scope; reading dependencies grants no edit ownership.

## Current-base premise dispositions and retained failures

The pre-edit issue-done §0 dispositions are bound to selected 7df in external
`2026-10-12-p1-main-integration/source-preparation-ctx_254e9fe40164/pre-edit-premise-dispositions.md`.
Unsupported Replay profile safety is still outstanding on that main; the
Application/Reference fences are present only in the imported b87 delta.
PR #2030 squash `a0c28d429ada83fd0416df7b9b508811151ca419` already delivered
the old Active Tree false missing-proof repair and is an ancestor of 7df;
that repair must not be duplicated. Inheriting it creates no Core PASS.

PR #2033's actual Journal prefix and `authenticated_prefix=0` test dependency,
and PR #2037's real M1 Pad gate/shared-FX Engine layout and behavior, are now
main inputs. The unchanged adapter still delegates Replay to Reference, but a
clean text merge does not prove combined binary compatibility. Fresh owning
three-suite, Portal and final exact-source batch verification are still owed.
M1's producer does not settle full P1 live-control playback/recording, header
apply ACK, binding/reset, Support, hearing/device or final Goal acceptance.

The original complete seven-Mac execution remains FAILED: actual wait 1 /
3148.173s. Core stopped at the old false Active Tree gate; Deploy's first
original runner exited 1 after 735.432s, with four shard exit-1 outcomes,
1865 discovered / 1727 executed / 138 omitted, and the remaining six Deploy
commands UNRUN. Those are not timeouts or 138 freshly executed failures.
The old limited Creator, Package, Web Runtime Host, Lab and Toolchain PASS
remain historical. They supply no keys for this new final committed head;
no owner accepted-risk has been granted. Earlier rebuilt causal RED/restored
whole GREEN and Portal receipts remain historical, without being recast as
current 7df/M1 binary proof.

Frozen S6 retains its 87-source Facade overlap and native/Source authority
under Root notice `msg_f1adcafd2d37`. These streams are semantically coupled;
future S6 integration must retain the shipped P1/current-main source. No S6
edit/retry/new Task/native GO is granted. Unknown unregistered old worktrees,
foreign dirty drafts and all five shared stashes remain protected; bounded
registries do not establish global inactivity.

## Future execution proposal — every result UNRUN / HOLD

After separate Root execution GO, capture the actual command environment and
freshly configure/build the current own Engine with these whole existing
registrations, serially:

```sh
scripts/core.sh configure dev
cmake --build --preset dev --parallel 1 --target lmdj_facade_performance_replay_tests lmdj_facade_performance_engine_adapter_tests lmdj_facade_performance_operation_contract_tests
ctest --preset dev -R '^facade\.performance_(replay|engine_adapter|operation_contract)$'
```

The literal executable selector has one backslash before the dot. Preserve
all original 17 Replay and 25 Engine cases, all b87 additions (24/27 direct
main calls), registrations, deadlines, journey legs and far-side assertions.
Keep header/any-sequence including 0, kinds 7/8, mixed later boundaries and
default-future denial, retained identity/legacy reset/retry and real running
Engine state after service/render. No automatic repetition of old mutants or
full CI gate precedes these lowest owning checks. Explicitly select Core
stress where concurrency is touched; full/proof/coverage do not imply stress.

The PATH defect is execution environment only: the validator and fixture
interpreter/runner remain unchanged. Fresh ordinary account home is
`/Users/endaye`. Current data-read PATH has no literal `~/.dotnet/tools`
component and all entries are absolute/nonempty. At future execution GO,
expand only that complete literal token, if present, to the freshly confirmed
ordinary user's absolute home plus `/.dotnet/tools`; preserve the order and
all other entries and validate the actual effective PATH as absolute/nonempty.
No repair has been executed. No verifier/fixture/RC/global configuration edit,
dotnet install, privilege, wrapper framework or PATH weakening is admitted.
The two existing causal checks precede a fresh complete Deploy lane:

```sh
python3 tests/build/release_task_verification_test.py VerificationTest.test_actual_checks_receipt_and_reuse
python3 tests/build/release_candidate_cut_test.py CutRecoveryTest.test_one_complete_cut_and_revalidation_preserve_source
```

They too are UNRUN. Preserve original fork/ready/release/exit assertions if
those existing cases are later admitted; focused passes cannot clear the 138
old omissions or the full Deploy seven-command obligation.

Before a genuine Task commit, run the whole `scripts/docs-site.sh check`,
the existing 77-test ownership suite and 15-test pitfall suite, and inspect
exact nine staged paths, complete cached diff and cached whitespace check.
Missing own Portal dependencies require separate Root setup admission; no
implicit install is allowed. Refresh relevant-main §0 premises before commit
and premerge. Commit, general staging, PR-body editing and publication remain
HOLD now, including staging this prefix.

On the actual final committed head, freshly discover canonical lanes. Current
source rules predict 13 selected / 10 batch-only, not an executed selection:
Mac `core_macos`, `creator`, `deploy_contract`, `package`, `web_runtime_host`,
`web_runtime_lab`, `web_toolchain`; Linux `core_ubuntu`, `core_asan`,
`core_coverage`; PR `ci_contract`, `docs_static`, `portal`.
Every selected batch-only lane requires its actual source-bound pass key or
actual explicit owner accepted-risk before shipping merge; none is supplied
here. Root's explicit requirement prevails over ordinary optional wording.
Unavailable, deferred, old or quick checks are not complete PASS.

Run each host's admitted lanes serially in its own roots. Deploy retains all
seven original commands, four 1200s shards, fresh full discovery/multiset
accounting and follow-on checks. Linux ASAN retains full plus stress; Core,
Package, Creator and Web retain their original full inputs/journeys/budgets.
No source fixture, timeout, coverage floor, test skip or owning lane shrinks.
Root will later reuse PR #2029 with normal FF, truthful body, trusted exact-head
review/review_wait, actual findings/conversations/conflict/live protection and
expected-head guarded squash. Source preparation is not that acceptance.

## Integration Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/
Reason: preserve the imported Replay admission limitation, current MDX,
architecture JSON and official generated HTML/SVG pair. Full Portal check
before commit remains UNRUN. Manifest-derived identities and existing immutable
snapshots are retained; no Build or snapshot is allocated.

## Integration Version Management

Version impact: internal application-facade Replay support bugfix with deferred
V1 Module settlement; not none. Actual selected-main Facade 6.7.0/api 3 and
Audio 5.2.0/api 2 are read from active manifests. No guessed PATCH, new manifest,
Assembly, Product Build, tag, Release, deployment, Channel or snapshot identity
is allocated. The complete original `## Version Management` record below stays
historical; coherent V1 settlement and broader P1/manual/Goal acceptance remain
open.

---

The following complete original b87 plan is preserved as historical evidence.

# P1-Replay-Safety: reject unsupported Performance Replay profiles

Status: Root accepted the independent source review and both bounded runtime
evidence phases, including the completed conjunctive causal proof and whole
owning-suite GREEN. The original complete Portal check passed. This plan now
records those actual results after a preserving fast-forward to verified main;
the updated pre-commit candidate, selected-lane evidence and current committed
head still require Root's next verification/shipping admission. No commit or
shipping has occurred. This remains the bounded safety Task; full P1
live-control playback/recording and final Goal acceptance remain pending.

## Fresh premises and ownership

The source-only worker refreshed `origin/main` with noninteractive
`git fetch origin main` before editing. Actual selected base/HEAD is
`6423a596360f64a0def1e33c37bd1551b0de838e`, tree
`a6f78783e969403a373d52f65c6c13f50b9defdf`; its parent is
`6fa983261e2740f5773598cda1491dfb1eb21468`, whose parent is the preparation's
`9ffd1f71121a04dbfdb393822a8af72a3ae11ae9`. The two intervening merges affect CI
historical evidence and Sound Set golden verification. All eight existing
declared inputs remain identical, the ninth plan was absent, and the complete
`packages/`, `contracts/`, AGENTS/CLAUDE, issue-done and governance comparison
has no delta. The live open-PR read found only #2001 at
`aa1f4b3dd62c6dbf4f51b97ffb4880962fb914d5`, with four nonintersecting paths.
This bounded observation does not establish absence of private remote owners.

At the source-start base, all actionable premises were outstanding: Application
accepts headered targets through an injectable controller and clears completed
active bookkeeping before classification; Reference admits header/sequence/new
payload projections before identity insertion and native effects; the actual
Engine delegates to Reference, so its zero-effect rejection needs an owning
component oracle. IO/Domain validation and Cooker projection already support
valid headered data and must remain intact. No intervening source-start
successor had delivered these fences.

Under Root's pre-commit admission, a second normal narrow main fetch returned
`08330f29c2889cfa54f5cee90e8d42da50593fc7`, tree
`09f5250a28eb1917357a1b81a87e9b12cd8e2bfb`. The complete `6423a596` to `08330f29`
delta is exactly `apps/creator-web/test/package_test.py`, one insertion and one
deletion correcting the existing Creator full-lane binding assertion. It does
not intersect the declared nine. All eight original base blobs/modes and the
plan's absence in main were checked before a normal `git merge --ff-only` to
that exact target. All nine uncommitted candidate bytes were preserved. The
inherited package-test change belongs to main, not this Task's file declaration.
Current own HEAD/base is `08330f29c2889cfa54f5cee90e8d42da50593fc7`; stage is
empty and its index entries match that main tree. The 3409 outside-nine paths
retain their source-start bytes/types/executable modes except that one verified
inherited main update. This is a bounded own-worktree comparison, not a global
refs, owners or environment freeze.

The worker owns only the new isolated `fix/performance-replay-profile-safety`
branch and the nine paths below. Orca initially returned a pristine
`endaye/fix-performance-replay-profile-safety` branch; after collision and owner
checks, only that branch was renamed nonforce and fast-forwarded to actual main.
Tracked symlinks are materialized and LFS objects are normal checked-out bytes.
Root authenticated the relayed Task/Dispatch at Run home; a local registry miss
was retained as limited lookup evidence. At source admission H held the separate
M4 heavy window. Root later admitted two exclusive bounded verification windows
for this Task after the respective other owner's release; all owned command
roots were waited/exited and both windows explicitly released. Foreign history
merge/index/evidence and all negative Native evidence remain retained; Root
remains sole publisher. Full P1 and future BPM I2b share paths and must follow
this reviewed result in Root's order.

## Declared files

One safety behavior, one eventual Conventional Commit:
`fix(facade): reject unsupported performance replay profiles`.

1. `packages/application-facade/src/application.cpp`
2. `packages/application-facade/src/performance_replay.cpp`
3. `tests/core/facade/performance_replay_test.cpp`
4. `tests/core/facade/performance_engine_adapter_test.cpp`
5. `apps/docs-site/docs/core/modules/application-facade.mdx`
6. `apps/docs-site/diagrams/application-facade.architecture.json`
7. `apps/docs-site/static/diagrams/application-facade.html`
8. `apps/docs-site/static/diagrams/application-facade.svg`
9. `docs/plans/2026-10-11-performance-live-control-admission.md`

No public header, Engine adapter production implementation, SDK, manifest,
Assembly, CMake, schema, operation registration or Foundation error enum changes.
No additional parser, Store, cache or asynchronous state. Preserve every existing
legacy test and assertion, budgets and acceptance journey leg.

## Admission behavior

Only the legacy profile is supported: absent `initial_live_state`, absent
`input_sequence` on every event, and an explicit allowlist of locked kinds 0–6.
Any present sequence, including 0, is a marker; kinds 7/8 and future kinds are
rejected by default. Classification does not revalidate all legacy events or
reject the whole v5 Project Contract.

Application retains shape/UUID/path errors, known identity exact retry,
different-payload `DUPLICATE_ID` and playing exclusion before loading. A known
legacy retry uses its saved projection/status without reloading later Truth.
For a new ID, completed-active cleanup is local pending work. Normal validated
`ProjectStore::load` runs, then the found Performance is classified before that
cleanup, Cook or controller begin. Unsupported data preserves Replay bookkeeping.
Loader failures keep their original error and original completed-active cleanup;
missing targets and legacy Cook failures also keep existing behavior.

Reference keeps UUID/null/count checks first, then scans the header and every
boundary before mutex/map/active insertion or sink calls. It keeps existing
canonical-offset validation and all legacy reset/retry/error semantics. Direct
same-ID unsupported projections fail while their saved legacy entry remains;
the original legacy exact retry still works. Native/headless adapters reuse this
fence without a second implementation. Engine's legacy retained-playing fallback
after a real empty-reset failure remains necessary and unchanged.

Failure uses the existing `invalid_argument` Result/envelope and diagnostic
`details.reason=performance_replay_profile_unsupported`, with no new public
result keys, status fields, ACK or committed revision. This fence precedes
Replay/Performance state, bookkeeping and native effects. Normal load still
owns history acquire, writer lease, recovery and staging maintenance; this is
not a whole-bundle zero-side-effect assertion.

## Owning oracles and verification debt

Root independently reviewed the frozen source before runtime admission. Both
bounded phases ran the complete existing registrations, including all original
17 replay and 25 Engine cases with unchanged bodies/calls and the new cases.
The following facts have owning-suite evidence on the frozen source candidate
at `6423a596`; this plan-only update and inherited main fast-forward do not
manufacture verification or pass keys for a new committed head.

| Existing owning suite | Defect and far-side assertions authored/retained |
| --- | --- |
| `facade.performance_replay` / Application | Real Store accepts neutral/nonneutral zero-event headers, header+sequenced old FX, FilterChange and PadGates. CapturingController cannot hide the Application defect: failure envelope, begin/stop/status calls zero, new status NOT_FOUND, unchanged clean-fixture Performance Truth/revision and recovery list. v5 legacy can reuse the rejected ID. |
| `facade.performance_replay` / direct | Header with zero/nonzero events, sequence 0/1 on old events including later boundaries, and no-header legacy Pad before kind 7/8 with/without sequence fail before calls/reset/identity/active use. Status and Stop are NOT_FOUND, advance has no active replay, legacy admission on the same ID then produces its original Pad/FX effects. |
| `facade.performance_replay` / retained identity | Reject unsupported direct same-ID input after legacy progress; cursor/state/count/revision and sink snapshot remain fixed, then original exact retry succeeds. Application preserves known-ID and playing-exclusion priority before nonexistent path, fixed-revision retry after Truth deletion, original missing/corrupt loader errors, missing-target NOT_FOUND and legacy completed-active cleanup. Status call counts distinguish retained bookkeeping after header rejection from an early clear. |
| `facade.performance_engine_adapter` | Real factory and running/prepared Engine seed typed Filter, Delay and HOLD, then reject zero-event headers, sequenced old events and later mixed kinds before/after service/render. Compare FX/typed/tempo queue counters, Pad/voice counters, Pattern generation/publication counters, epoch and complete accepted/applied Filter/HOLD state; rejected status/Stop remain NOT_FOUND. Actual legacy Pad/Pattern/FX can then reuse the rejected ID. Same-ID unsupported input preserves the 120-BPM frame-50 delayed Pad anchor. |
| Existing legacy cases / both suites | All old 0–6 actions, v4/v5 legacy, empty neutral complete, pending/error reset and explicit retry, fixed revision/BPM, no reanchor, restart fractional progress, projection PCM/Pattern material/retired tails, queue pressure, nine-gesture reset and Stop/complete remain unchanged. |
| `facade.performance_operation_contract` | Existing command/query registration, request/envelope shape and error parity; no new operation or keys. |

The Application fixture has no clock/sequencer measurement collaborators; no
actual zero-clock/zero-sequence counter proof is claimed. Production inspection
shows this replay route does not use those recording collaborators. Truth
comparison concerns a clean fixture, not unchanged bundle bytes across recovery.

The admitted minimum command shape used the stable dev configure, built
`lmdj_facade_performance_replay_tests`,
`lmdj_facade_performance_engine_adapter_tests` and
`lmdj_facade_performance_operation_contract_tests`, then selects:

```sh
ctest --preset dev -R '^facade\.performance_(replay|engine_adapter|operation_contract)$'
```

The causal requirement remains conjunctive: rebuilt old-source Application and
Reference boundaries must produce their respective owning REDs, and reduced
admission must be caught for no-header sequence **and** kind 7 **and** kind 8.
The CapturingController oracle owns the Application fact; direct Reference and
the actual Engine adapter own the projection facts. Keep original RED lines,
every successful rebuild/exit, and complete owning selections. Restore externally
saved uncommitted bytes with fresh mtime strictly newer than mutant objects,
confirm actual recompilation, and never restore this implementation from old
HEAD/index. The following separately admitted runs fulfill these causal facts;
the earlier header-only run alone is not typed-kind proof.

| Actual boundary | Original result |
| --- | --- |
| Phase001 stable `scripts/core.sh configure dev` and minimum three-target build | Both exit 0; whole three registrations initially GREEN 3/3, exit 0. |
| Application-only old-source fence removal; Reference candidate retained | Actual replay-target rebuild 0; complete replay suite RED 8 at replay test line 814, `response.size()==2`. |
| Reference-only old-source fence removal; Application candidate restored | Actual two-target rebuild 0; complete replay and Engine suites RED 8 at replay line 880 / Engine line 1147, `!rejected.has_value()`. |
| Reduced header-only Reference fence | Actual two-target rebuild 0; both complete suites RED 8 at the same owning lines. First no-header sequence 0 attribution follows unchanged fixture order; no fixture index was printed. Fail-fast prevented this run from proving later kinds 7/8. |
| Phase001 exact fresh-mtime candidate restore | All three targets actually rebuilt 0; complete three registrations GREEN 3/3, exit 0. |
| Phase002 kind-7-only allowlist mutant | From exact candidate, add only `filter_change` to legacy-true cases, retaining header/any-sequence/default-other denial and all test bodies/order/assertions. Actual two-target rebuild 0; both unchanged whole suites RED 8 at lines 880/1147. |
| Phase002 kind-8-only allowlist mutant | Physically restore and hash-check exact candidate first, then independently add only `pad_gates_set`. Actual two-target rebuild 0; both unchanged whole suites RED 8 at lines 880/1147. |
| Phase002 final exact fresh-mtime candidate restore | All three targets actually rebuilt 0, with compile line and newer object receipt; original whole three registrations GREEN 3/3, exit 0. |
| Original complete `scripts/docs-site.sh check`, initially without dependencies | Exit 1: 78 tests passed and eight failed on missing package imports. This negative is preserved. |
| Root-admitted original `scripts/docs-site.sh install`, then unchanged full check | Install exit 0; complete check exit 0: 176/176 tests, 52 pages, 10 diagram sources/20 outputs, existing Product 2.0.90.0 snapshot/facts, typecheck, production build and 50 routes/links. |

The two typed mutants each have a one-case source diff. Their kind-specific
attribution comes from those diffs and unchanged fixture order, not a printed
runtime index. Original argv/start/end/PID waits/exits/stdout/stderr/CTest logs,
source digests/diffs and object/library/executable timestamps/digests remain
external. Final copied `LastTestsFailed.log` contains stale preceding intentional
RED entries; current final exit 0, stdout and `LastTest.log` prove the current
GREEN. No reduced harness, assertion deletion, selector narrowing, changed
budget/timeout, extra public API or CMake change was used.

Root authenticated the exact 41-member source intake, 81-member Phase001 intake
and 47-original Phase002 intake, then read complete independent reviews. The
Phase002 review resolved the sole prior P2 causal gap; no concrete P1/P2 remained
in that bounded review. This is source/runtime review of the actual candidate,
not a future committed-head review or final product acceptance. Source candidate
manifest SHA-256 is
`90c4c63f6b3bdf25ab205253e46f294f24cbe851f2c65c140fbcce21ea78c4de`;
Phase001 final receipt is
`fe008655d555a9f052a8ca77802098814b4848ec6a3677b0d333445bb691de27`;
Phase002 typed manifest is
`69d9ea53cb37eba6d125ac4d60bd9b29c91cc520988afe51134f0072027358f1`.

Retained evidence limits are explicit. The first data-only Phase001 receipt
assembly stopped on duplicate initial CTest-log inventory entries before a
receipt was written/sent; the diagnostic and corrected inventory remain. One
mutable external command helper advanced from the original 1851-byte Core
version to the 2123-byte Portal version; the original 77-path audit confirmed
76 old paths unchanged, not all 77. The historical helper bytes were recovered
and hash-matched separately, and actual Portal helper bytes bound to the Portal
receipts. An early hand-typed helper metadata error was corrected by computed
metadata while retaining the original messages. Raw private index/refs/worktree/
stash snapshots, excluded duplicate candidate copies and the recovered historical
helper retain Source-only descriptor boundaries; they are not silently added to
Root's bounded runtime intake or claimed as all-original-path custody.

The admitted Portal install/check used actual Node 26.7.0/npm 11.19.0, unchanged
package/lockfile and a command-scoped cache in this worktree's ignored Portal
build area. The manifest declares npm 10.9.3; pinned npm 10 execution is not
claimed. Missing-import failures and npm install-script warnings remain intact;
no npmrc/global/toolchain/account or foreign-cache repair occurred. Phase001's
14 and Phase002's six owning command roots exited after waits, limited release
`ps` observations were empty, and no background product service was launched.
Each heavy window was released before waiting for Root's next admission.

No new concurrent or lock-free producer/consumer path is introduced. A scope
change in that direction requires renewed Task declaration and owning race/
stress obligations. H/D5 and pre-existing full Core/stress/ASAN, physical/hearing
and final combined-proof debt remain open; focused tests cannot discharge them.
Full new-profile replay/record/header ACK/masks/filter/producer, Support and M1
delivery remain pending. The user requires every actually selected batch-only
lane on the committed head to have its own input-bound pass key or explicit
owner-accepted risk; list-only selection and these focused receipts supply
neither. No borrowed key or worker self-exemption is permitted.

The actual pre-commit canonical invocation
`scripts/local-ci.sh --profile full --list --base-ref 08330f29c2889cfa54f5cee90e8d42da50593fc7 --json`
exited 0 without running a product lane. Its mode is `full`, with reason
`three expensive families: core, creator, web-runtime`. Selected PR-verified
lanes are `ci_contract`, `docs_static` and `portal`; selected batch-only lanes
are `core_asan`, `core_coverage`, `core_macos`, `core_ubuntu`, `creator`,
`deploy_contract`, `package`, `web_runtime_host`, `web_runtime_lab` and
`web_toolchain`. All 13 are selected and all 10 batch-only committed-head
receipts remain pending. The `--list` result is selection, not execution or
permission to omit any lane.

## Version Management

Version impact: internal application-facade Replay support bugfix with deferred
Module settlement; not `none`. Active Facade identity remains 6.7.0/api 3;
Product remains 2.0.90.0 and Project Contract remains `lmdj.project.v5` 5.4.1.
No new Module Package, manifest/Assembly cut, Product Build, tag, snapshot,
Channel, Provider or SDK identity is allocated here. The next Build/tag is
UNALLOCATED. Version policy §6 permits internal implementation work without an
immediate new Package publication.

Public signatures/layouts, virtual methods, operation/envelope shape and
persisted grammar remain unchanged; the controlled rejection is not itself a
new C++ ABI MAJOR. V1 must settle the actual bugfix classification with the
complete delivered surface and actual verification before a coherent Package/
Assembly cut, without guessing a PATCH number or clearing existing P0/Audio/
Facade MAJOR debt. Old identity does not make an old binary proof of this source.
Reverting the eventual source commit reopens unsafe unsupported-profile execution;
it is not acceptance of that risk and does not move immutable tags or old Builds.

## Documentation impact

Documentation impact: required — `/core/modules/application-facade/` plus its
existing architecture JSON and officially generated HTML/SVG. Only the
Performance authority card changes; topology and operation count remain intact.
Data read/Cook support is distinguished from legacy-only Replay and pending full
P1 header apply ACK, typed Filter, 64-Pad gates, recording/binding/reset support.
Portal identities continue to derive from manifests.

The existing official `apps/docs-site/scripts/render-diagrams.mjs` entry point
unconditionally globs all architecture sources and writes every HTML/SVG pair;
it has no narrow CLI selector, so the initial source checkpoint retained both
original generated artifacts. Root then explicitly admitted a minimal Node ESM
invocation of the same existing `renderDiagram` export from
`apps/docs-site/scripts/lib/diagram.mjs`, reading exactly the declared Facade JSON
and writing only its declared HTML/SVG. The renderer's source is byte-identical
to the selected base; actual invocation exited 0, changed only those two files,
and retained all outside-nine bytes and index entries. Generated artifacts bind
canonical source SHA-256
`da6c3f81579d4bfdf74d3413be2bd49d6bc3ce7bdce6359850e9d74958fd49d8`.
This invocation is official source generation. The later original complete
`scripts/docs-site.sh check` passed as recorded above; Phase002 did not repeat
Portal because its consumed source candidate remained unchanged. Before commit,
the applicable current-candidate check and selected-lane evidence still follow
Root's admission; historical Portal success is not a new committed-head pass
key. Current-only lint/build remains insufficient, and no snapshot exception
applies because no Product Build is allocated.

## Phase and shipping boundaries

Root owns runtime admission, current-source/current-head independent review,
commit and ordinary PR/merge under standing user Task authorization. The initial
source checkpoint ran only the specifically admitted narrow diagram generation.
Subsequent Core/mutation/Portal/install work ran solely in the separately admitted
bounded phases recorded above. Current preparation admits the preserving main
fast-forward, this plan evidence update, external PR-body draft and canonical
list-only selection; further tests/Portal/full lanes and stage/commit/push/PR/
merge remain HOLD pending Root's inspection and next phase. No product SDK or
browser workflow, foreign process action, release or deployment was performed.
Preserve all drafts,
stashes, indices, refs, originals and negative Native evidence.

Before shipping, follow issue-done's fresh-premise and pitfall checks. Read open
`declared-gap-is-not-discharged` and
`mutation-proof-restores-away-uncommitted-work`; declaring full P1 pending does
not close its safety/acceptance gap. The guard is derivable from product code,
so this Task does not invent a ledger recurrence or expand its nine paths.
Current-head review, applicable Task checks, conflicts and conversation protection
remain required; no universal strict-update/full-CI ordinary merge gate is added.
Explicit complete-candidate/Goal obligations remain separately unverified until
their actual selected lanes and journeys produce exact evidence. Release and
deployment are outside this Task.


## Main integration measured minimum verification — 2026-10-12

Root accepted the one finite native3/PATH2 window in `msg_f6d9a4728d26`; these are uncommitted integrated Source results on selected `7df1af16df5e6d864ca7968626d63f84a5d9cb63` with `MERGE_HEAD=b87e9c922bae71e8b2f3f489103785d1e033528e`, not full P1 or committed-head batch acceptance. Ordinary UID501 `MacBookPro17,1` used a fresh own dev build, serial real three-target build, exact whole native registrations and unchanged TIMEOUT30; Replay24/Engine27 whole bodies and existing Operation Contract passed. Both existing causal PATH fixtures passed once with the already-absolute PATH; no literal-token repair, product verifier/fixture edit, retry or tool install occurred.

| Measured step | Direct elapsed | Result |
| --- | --- | --- |
| 01-configure | 3.192758s | 0; natural wait; owned group empty |
| 02-build | 96.311548s | 0; natural wait; owned group empty |
| 03-registration | 0.088023s | 0; natural wait; owned group empty |
| 04-ctest | 3.726922s | 0; natural wait; owned group empty |
| 05-causal-task | 3.405878s | 0; natural wait; owned group empty |
| 06-causal-cut | 18.505028s | 0; natural wait; owned group empty |

Whole Source/output report: `/Users/endaye/Projects/lmdj-followup-evidence/2026-10-12-p1-main-integration/minimum-window-ctx_254e9fe40164/minimum-owning-verification-report.md` (11212B, SHA256 `0daaa87030f4796ce49538b92571f608ee22a8f08bb7e779393f81a1cec7e95c`). Raw six argv/PID/PGID/birth/natural exits, twelve complete streams, exact3 registration, LastTest log, fresh actual7df Audio/Facade artifact identities and final whole Source guard are linked there. Eight imported files remain exactb87; all3414 outside-nine tracked bytes/types/exec flags,10 symlinks and five stashes were preserved.

Fresh §0 main `1a9d4ee44e2163ccb305ca3e1fb037331b0995b1` adds only PR2047 Creator/input documentation and its plan, with zero declared-nine or product Source overlap; selected integration parents remain `[7df,b87]`. Active Tree PR2030 is already delivered and must not be duplicated; Journal/M1 complete verification, frozen S6 future integration and broad live-P1/SDK/Host/Creator/hearing/V1 debts remain.

Current finite precommit boundary: whole Portal dependency preparation/check, current full ownership/pitfall suites, stage/check/one real two-parent Conventional Commit are pending and must pass under Root GO. Final-head canonical lane discovery, all selected10 batch pass-keys or actual explicit owner risk, current-head trusted review/protection/conversations/conflict and Root-only shipping remain UNRUN/HOLD; no risk is granted. Documentation impact stays required `/core/modules/application-facade/` with the declared source/generated diagrams; internal Facade replay-support bugfix and deferred V1 Module settlement remain unchanged. No Build/Release/Channel/snapshot allocation or cleanup is authorized.


### Measured whole Portal and precommit checks — 2026-10-12

The necessary one canonical `scripts/docs-site.sh install` naturally exited0 in 34.295451s, group22316 empty, using existing Node26.8.1/npm11.19.0, unchanged723882B lock, default allowScripts/optional policy and child-only own ignored cache/devdir/temp paths. Audit/allowScripts/devdir warnings were retained; no approval, flag, upgrade or fix was made. The one original complete `scripts/docs-site.sh check` naturally exited0 in 78.209826s, group31569 empty:176/176 tests,0 failed/skipped,52 pages,10 diagram sources/20 outputs, existing snapshot/facts, typecheck/build and50 routes/internal links. This is precommit Source evidence, not final committed-head Portal or full-lane proof.

The complete existing `python3 tests/build/ci_change_scope_test.py` ran77 tests and naturally exited0, group45297 empty; `python3 tests/build/ci_pitfall_ledger_test.py` ran15 and naturally exited0, group52979 empty. The added plan path was already indexed by the authorized nine-path merge import BEFORE the77-test run; every-tracked-path and top-level admission oracles passed on that actual index. Updating only its body adds no path ownership. Raw argv/birth/streams/natural waits and strict Source/index/lock/environment guards: `/Users/endaye/Projects/lmdj-followup-evidence/2026-10-12-p1-main-integration/precommit-window-ctx_254e9fe40164`.

A later read-only precommit preparation guard exited1 at line3 because it incorrectly demanded newly fetched refs still equal obsolete1a9d. Actual fresh `bb5a3643d31534de46b5adf55a37ae816cc4c952` adds only PR2045 explicit-cwd pitfall to prior PR2047 documentation; no declared-nine/product/interface/Portal/tool/test overlap exists. OwnHEAD7df/MERGE_HEADb87 and resolvable Git LFS were intact. No later append/stage/commit ran under that failed guard. Root `msg_c6a22925d8b2` accepted its bounded disposition, retained the original negative, and authorized continuation without repeating prior passed checks. Future worktree commands carry explicit absolute cwd and same-invocation own identity proof; legitimate remote-ref drift remains non-gating and is never restored.

All other eight bytes, the whole36783B prior plan prefix, its33863B prior prefix and exact22298B historical region at11565 are conserved. Only the admitted one genuine `[7df,b87]` Task commit follows precise staging/cached-content/check verification; its actual result is reported externally. Final-head discovery, all10 selected batch keys or actual owner risk, trusted current-head review and Root-only publication/merge remain HOLD, with no risk granted and no release/build/channel/snapshot/cleanup authority.
