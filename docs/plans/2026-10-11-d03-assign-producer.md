# D03 retained-Asset ASSIGN producer — main integration

## Goal and authority

Deliver the missing Control Runtime publication, Bridge notification and typed
SDK producer for the approved [Sample Assign decision](../prd/decisions/2026-10-10-sample-assign-and-numeric-editing.md).
Select an Asset retained by the current Project and an explicit A01–D16 target;
keep the source Pad and immutable material. The later Creator consumer owns its
picker, occupied-target confirmation, cancellation before submission and stale
editing context. This Task renders no Creator ASSIGN control and does not
implement Numeric editing, D04, a recording exception or new product semantics.

The dispatched Task is initially **SOURCE-ONLY**. Root admits each concrete
verification stage separately, followed by atomic commit and ordinary protected
shipping. Until admission, no install, Node, TypeScript, configure, build,
CTest, Portal, Web/browser/full lane, commit, push, PR or merge runs. Ordinary
UID only; no root/sudo/global changes, Release, deployment or cleanup. This
staging preserves the complete Task acceptance scope.

## Refreshed premises before implementation

Fresh isolated worktree:
`/Users/endaye/orca/workspaces/lmdj/feat-d03-assign-main-integration`, branch
`feat/d03-assign-main-integration`. Orca created a clean checkout at the exact
approved base; its automatically prefixed branch was renamed locally to the
required short-lived name. Worker `git fetch origin main` independently completed
and retained `a5bc444be23edf4d4d14378e3ff60c3c8bf037fc`, parent
`08330f29c2889cfa54f5cee90e8d42da50593fc7`, tree
`5a5a135a1963335c81e237e5c8b3baaf45d17ef5`. All ten Git mode-120000 entries
were compared with lstat: pristine real symlinks; no restoration or shared config
change was necessary. Source premises use this exact Git object, never Root's
older live checkout. Refresh affected premises before commit and final merge.

Read current AGENTS/CLAUDE, issue-done §0, minimization, architecture/Portal,
version rules, relevant open core/Creator/core-host/ci-release pitfalls, approved
decisions and the latest parent follow-up plan. The complete bounded independent
current-main handoff, frozen v2 inventory/deltas, original review corrections and
A1–A6 raw receipts are historical inputs, not executable helper authority.

| Premise | Evidence at exact a5bc | Disposition |
| --- | --- | --- |
| Assign operation registration | Facade `application.cpp` command inventory/dispatch, Bridge supported operations, SDK `protocol.mjs` include `pad.assign` | Already delivered. Do not add a new protocol or dispatch route. |
| Current retained inventory | Facade `project.inspect` emits assets, lineage/artifact identity and all 64 Pad references; Web query has empty payload/no sidecar and retained Session | Already delivered. Host must not parse bundles or reimport Assets. |
| Durable Assign authority | Facade `pad_assign` exact keys, `admit_non_sequence_authoring`, ProjectStore `execute_with_identity`; immutable full command payload is retained | Already delivered. Reuse membership, expected revision, exact replay and payload-collision rejection. Storage load/reconciliation can perform maintenance; refusal is not a blanket zero-disk-side-effect claim. |
| Destination semantics | Domain `apply_new_command(AssignPad)` only changes the target; different/null Asset resets playback, same Asset retains playback; colour retained except native null unassignment | Already delivered. Preserve source/materials and native nullable compatibility; new SDK Asset UUID is nonnull. |
| Recording admission | Facade non-sequence owner admission and ProjectStore Performance/recovery checks | Already delivered. Sequence, Performance, recording Pattern and recovery-required boundaries remain fail closed. |
| Runtime publication | Complete `pad.assign` handler returns Facade result with only cached project revision; positive `sample.update_pad` uses controls and `sample_mutation_result`/current-Truth prepare/exact Bank ACK | Outstanding. Reuse that path after known commit; precommit refusal must not stop sound. |
| Bridge snapshot classification | Complete nine-entry `snapshot_notification_operation` and pump `sample_mutation` both include `sample.update_pad`, both omit Assign, while supported inventory contains Assign | Outstanding. Add both classifications through existing reservation/claim/cancellation machinery. |
| Public typed SDK | Actual Session export and capability interfaces have update/reset/delete/colour/inspect, but no assignPad; generic protocol already admits Assign | Outstanding. Add immutable caller identity, strict independent result validation and dispatch-time owner recheck on both existing tails. |
| Callback observation | #2004 head `12ee167ca6ee586f79fd515bcf8583cf67a70c49`, squash `8769907ea75320f051d43707301af5188c0f0086`, actually merged | Delivered prerequisite. Preserve complete ContinuousAudioDriver, counters and both completed-callback far sides; it is not Assign delivery. |
| Semantic decision | #1929 squash `314d1cadd8aab7504513b15a42cc96bb9c8742d8`, actual decision source | Delivered decision only; not producer implementation. |
| Main successor changes | #2010 squash `9ffd1f71121a04dbfdb393822a8af72a3ae11ae9`; #2001 squash a5bc; five of seven old tracked paths changed upstream | Retain all current Pattern opening/receipt/observation/successor/snap, normalization and tests. Integrate deltas individually; no old whole-file donors. |
| Issue and consumer disposition | #1214/#1995/#1822 remain separate retained product/consumer/navigation work; Creator ProjectView lacks retained directory and Assign capability/journey | Producer does not finish the umbrella, Numeric, Creator ASSIGN, A1/A2, V1 or Goal. Use related-Issue vocabulary only. |
| Ownership | Root's refreshed public #2029 nine-file and #2030 two-file inventories have zero overlap; worker refresh retained externally; new worktree is sole Task writer | Bounded known ownership only. Unobserved remote writers remain unknown; old dirty/staged worktrees and stashes are preserved. |

The old read-only worktree remains `feat/d03-assign-producer` at
`8769907ea75320f051d43707301af5188c0f0086`, seven modified tracked files plus
untracked plan, empty index. Its eight bytes match frozen v2, complete historical
patch SHA256 `2df87082e11b114f632c61953289b0d709c74401768541987caabbdb19f5dfbe`.
Neither it nor Root/Numeric/BPM/K1 source, index, stash or build trees are scratch
inputs to mutate. External before/after guards bind source bytes, index, full
status, HEAD/tree, old patch and all five shared stash identities.

## Declared files — exactly eight

1. `packages/web-runtime-platform/src/control_runtime.cpp`
2. `packages/web-runtime-platform/src/bridge.cpp`
3. `packages/web-runtime-platform/web/runtime_session.mjs`
4. `packages/web-runtime-platform/web/runtime_types.d.ts`
5. `packages/web-runtime-platform/test/control_runtime_test.cpp`
6. `packages/web-runtime-platform/test/runtime_session.test.mjs`
7. `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
8. `docs/plans/2026-10-11-d03-assign-producer.md`

No CMake/header/fixture/manifest/schema/Contract/Facade/Creator/follow-up/shared
decision edits. The existing `lmdj_web_control_runtime_tests` target links real
Bridge and already owns submit/pump/poll fixtures. A necessary scope delta must
be concretely reported to Root before editing.

## Implementation and retained upstream union

Native wire remains `{command_id, expected_revision, slot:{bank,pad}, asset_id}`,
no sidecar or caller path. Preserve legacy result fields `slot`, `asset_id`,
`committed_revision`, `replayed`, `project_revision`; only after known Facade
commit stop the destination live voice and clear preview. During replay, use
existing live-only control so replay/Pattern voices survive. Reuse local
`SampleMutationResult{committed_revision,true}`, current-Truth preparation,
publication and exact-generation ACK. Add Runtime revision/publication and typed
error; quota/timeout failure after commit does not become generic cancellation
or rollback. Exact replay publishes current Truth, not historical assignment.

Bridge keeps response-before-event, actual current revisions/generation, reserved
capacity, publication claim and cancellation-generation arbitration. Refused
precommit/preclaim emits no snapshot. No private queue, protocol or Host Truth.

SDK `assignPad({commandId,expectedRevision,slot,assetId})` captures target, retained
material and complete durable identity before queuing. Both current Project action
and actual Host protocol tail, including original 30s budget/callback receipt,
remain in use. Recheck this exact Session owner at actual dispatch; closing/fatal
owners retain typed refusal. No automatic retry/resend, replacement UUID or
inference of unknown durability from current Truth. Explicit caller retry keeps
all original fields. Independent Assign normalization requires valid typed error
on failed publication, no error and Runtime=current Truth on success; existing
Sample no-prepare normalization remains unchanged.

Preserve all main test registrations and full modified bodies, seven-mode loops,
#2004 observations, OneShot overlap/default128/two-second limits, kernel lease
`4108 > 4104`, reclaim/reload and every publication/recovery/Pattern journey.
Static direct native calls are base153/main167/old-v2174: expected union188
(153 + main14 + Assign21). Static census is not executed count or PASS.
OneShot observes completion of already arranged renders under its original mutex,
without an extra permit; +1200-cent preview establishes the real old kernel lease
without changing Truth/Bank bytes or Engine stop rules. Original exact generation
expectations change only where public Assign now causally publishes a Bank.

## Source, test and acceptance inventory

All **new-base dynamic obligations remain UNRUN** until actual admitted receipts.
The complete owning executables and original Node suites remain the selections;
no journey leg, test, assertion, timeout, job count or quota is dropped.

| Owning fact | Complete required far-side evidence |
| --- | --- |
| Occupied Y→X publication | Public Assign; unique stereo PCM signs, exact Bank increment, source and complete current Truth. A new-base old-handler reduced v3 actual rebuild must fail at the owning PCM/publication assertion; restore combined source with fresh mtime and read actual rebuild exit. |
| Bank admission versus ACK | Only early nonconsuming `events_pending` waits on the same prepared Bank within the original deadline. No-progress admission preserves the single commit but accepts no Bank; ACK timeout/wrong ACK first proves one accepted new Bank pending with the old current generation. Both timeout journeys retain fresh-owner reopen and complete stereo128-frame PCM. |
| Assign→Undo→Redo→close/reopen | Complete Truth/material retention at each leg; full Artifact SHA, byte length and bytes; X/Y stereo PCM, history cursor/session and reopen identity. |
| Same Asset / D16 / native null | Playback preserved for same Asset; explicit {3,15}; null empty destination/colour semantics; strict material retention. |
| Exact identity replay after later edit | Old immutable receipt identity, current Truth/Runtime revision and Y PCM, unchanged history; changed payload refused. |
| Missing/foreign/stale/recording owner | Separate errors, complete Truth/history/Bank; live voice undisturbed before commit; real Sequence/Performance/recording Pattern owners remain active. |
| Postcommit quota/deadline/ACK | Known persistence distinct from Runtime error, exact replay without history duplication, exact generation rather than later unrelated ACK; running timeout safety retained. |
| Non-FIFO residency | Original kernel lease active after both Assigns, generation2/3/4, exact4108/4104 refusal and typed quota; actual current trigger/outcome, real128-frame retirement, reload recovery gen5. |
| Real Bridge | Submit→pump→poll response before success/replay event; current revision/generation; rejection error; no third message; preclaim/cancel/refusal no event; known-commit deadline remains durable. |
| SDK identity and ownership | A01/D16 request translation; immutable fields while Project action held; actual Host query tail;30s budget; strict typed failure authority; conflict/unknown receipt single send; explicit exact retry; close/fatal dispatch-time recheck. |
| Upstream main regression | All14 new Pattern cases/full modified original bodies, snap input/undefined semantics, complete callback observations and all original native/SDK cases preserved. |
| Session/Bridge owning graph | Whole `host.web_control_runtime`, `host.web_realtime_session`, `host.web_performance_bridge` dev and native-ASAN three targets; real Bridge linking, original120s/360s budgets and every far side. |
| Typed surface / Portal | TypeScript owner check and full `scripts/docs-site.sh check` before commit; current module page and derived identities. |
| Added-plan ownership / pitfall | After exact eight-file stage, original ownership77 and ledger15 suites; full staged diff and whitespace inspection. No gate or pitfall delta presumed. |

No unrelated old causal mutant is rerun for a count. If Bridge classification
needs distinct causal proof, change only Assign's existing Sample predicate,
actually rebuild the owning target and require failure at the event assertion,
then fresh-mtime restore/rebuild and whole original target. No old binaries,
donor objects, generated build graph or pass keys prove this new base.

## Historical receipts, preserved failures and pending verification

Frozen source root resolves to
`/Users/endaye/Projects/lmdj-followup-evidence/2026-10-11-d03-assign-producer/source-cut-v2-20261011T003005Z`.
The initial dispatch's nested source-start spelling does not exist; bounded path
inventory resolved the actual original root without executing helper text.
Its A1–A6 direct-child terminal receipts and full raw logs were read and hashed:

| Historical stage / actual original command | Actual result (old-v2 only) |
| --- | --- |
| A1 `node --test packages/web-runtime-platform/test/runtime_session.test.mjs`, unfixed typed-authority validator | exit1,171P/1F; owning missing-error rejection assertion |
| A2 `node --check packages/web-runtime-platform/web/runtime_session.mjs` | exit0 |
| A3 original whole RuntimeSession suite | exit0,172P/0F |
| A4 `node --test packages/web-runtime-platform/test/protocol.test.mjs` | exit0,36P/0F |
| A5 original whole RuntimeSession suite, actual Host-tail bypass | exit1,170P/2F; held-query serialization and queued-close ownership |
| A6 fresh restored original whole RuntimeSession suite | exit0,172P/0F |

Each child was actually reaped; skip/cancel/todo are0. Historical first cut
171=170P/1F invalid-slot TypeError/RangeError oracle remains retained separately.
Original F1–F4 reviews, native reduced v1/v2/v3 UNRUN cuts and independent SDK
reviews are preserved; A1/A5 are actual negative facts, not new-main tests.

After Root light admission: original SDK syntax, whole RuntimeSession and
protocol suites and TypeScript owner check. After separate heavy admission:
new-base reduced PCM actual-built RED, whole three dev/native-ASAN owning
targets, any necessary distinct Bridge proof, whole Portal. Install scope and
physical-host serial scheduling are separate concrete admissions. Capture each
command's own argv/input hashes/start/end/direct exit/log; a wrapper's last child
exit is not generic success.

At the final committed head, actual canonical
`scripts/local-ci.sh --profile full --list` must retain all selections for Root
scheduling: current static forecast is13 total/10 batch-only, not a run result.
Core Ubuntu/ASAN(full+stress)/coverage/macOS, Web toolchain/Runtime/Creator/Lab,
Deploy Contract and Package debt remains visible. Pinned Node26/Emscripten6.0.5
and locked browsers are prerequisites, not inspected-installed PASS claims.
No accepted risk, full PASS or complete verification debt clearance is invented.
Creator picker/browser/hearing/physical, parent A1/A2 and overall Goal remain
separate acceptance work.

## Initial source-only checkpoint (2026-10-12, historical freeze)

All seven reviewed frozen-v2 owning deltas were applied individually on a5bc;
the new plan was written before implementation. Reversing those deltas only in
external source copies reconstructs each current-main file byte-for-byte. The
whole eight-file diff was inspected; no additional tracked/untracked paths or
staged entries exist. `git diff --check` passes as a source whitespace check,
not product verification.

Measured static native direct calls are153/167/174/188 for old base/main/v2/new
union. Both prior registration orders remain subsequences; every main-added14
and Assign-added21 full body is byte-equal to its owning input. All35 changed
existing main test bodies retain their journeys with only the reviewed Assign
publication setup/generation changes. The seven-mode loop, complete
ContinuousAudioDriver and both callback observations remain unchanged. SDK
literal registrations are main159/v2168/new170; all main registrations retain
order and the existing Sample normalizer is byte-equal. These are static
inventories; actual Node/native counts are unmeasured.

Independent byte checks match the entire22819-byte handoff SHA
`0409781ae1bf03ecc2bdb8622f5a08675ccda598901c1a202d935d4eb388edfa`,
its124044-byte receipt SHA
`d3c707f1e77a747447e054d8d6698d2709e96605239a65473abf44e99a0a6e7e`,
all41 named original input artifacts and eight frozen-v2 files. Root and old D03
HEAD/tree/branch/full-status/index/source/patch guards, plus all five stash
identities, remain byte-equal to the worker's before guards. No foreign source,
index, builds or processes were mutated.

At that initial checkpoint the worker inspection was UID501, own Core build and all three owning npm
prefixes absent. Executable paths alone establish no tool version or runtime
readiness. The concrete first light proposal is Node version readback followed
by original SDK syntax, complete RuntimeSession and protocol suites, each with
its own retained direct exit/log and exact new-source guards, no installs or
historical mutants. TypeScript owner check still needs an admitted locked own
dependency setup; native, ASAN, Portal, stage, full lanes and shipping are UNRUN.

## Publication-race source revision (2026-10-12)

Root accepted the initial eight-file source review, actual original SDK174P/0F
and protocol38P/0F, then the whole TypeScript owner check with595 own inputs.
Those receipts cover their respective windows. They do not settle native,
Portal or candidate acceptance. The first native dev configure, serial owning
three-target build and actual registration discovery returned0; the first whole
three-registration run returned8 (2P/1F/0skip). Control failed at the original
full128-frame positive destination PCM predicate; realtime and Performance Bridge
passed. Static188 calls were never a passing native census.

The separately admitted temporary diagnostic changed only the native test to
log the saved receipt and both full128-channel arrays before the unchanged
predicate. A genuine target rebuild returned0; once full control registration
returned8 at that same predicate. Assign committed revision5/currentTruth5 while
Runtime remained revision4, `runtime_published:false`, `HOST_STATE_INVALID`.
Two stop/preview controls remained queued, Bank generation/accepted/applied3,
pending0 and only the activation ACK poll. The next trigger drained the controls
and each channel contained one zero plus127 negative Y frames. Exact test bytes
were restored with a fresh mtime, then genuinely rebuilt0; no restored test was
run. The restored test object matched original bytes, and the newly linked binary
has its own recorded hash rather than an assumed deterministic original hash.
Raw original/diagnostic failures remain outside source. The bounded report is
`native-readiness-20261012T003845Z/diagnostic-v1/d03-main-native-diagnostic-actual-restored.md`
under the current-main Task evidence root,6109B SHA
`9a633852f07b5e9a66954ec57a4a215fafe3e184c1cdc7db9bb39b0e6cf3997e`.

This is also a real running-Host ordering window: a continuous callback need
not drain the newly queued controls before the immediate Bank attempt. The
source revision changes only the existing `prepare_and_publish` admission
boundary. The engine's `events_pending` return precedes consuming the immutable
Bank or assigning a generation, so only that refusal may retry the same prepared
Bank within the original absolute request deadline. Cook and Pattern preparation
occur once; no Facade command, UUID or current-Truth query is resent to infer
success. Expired admission returns typed timeout, retaining known commit and
existing fail-closed state rules. Nonpreserving requests retain their existing
cancellation/settlement policy, but an owned settlement cannot extend this new
admission wait beyond the absolute deadline. All other publication refusal paths
and the exact newly accepted generation ACK remain intact.

The existing native OneShot driver gains one finite128-frame control-drain
permit and its completion wait retains the original2s limit. Enqueued telemetry
only schedules a callback. These scopes have one serialized mutation producer,
with replay service/other dispatches/manual callbacks outside the scope; the
completion check rejects an unexpected enqueue count. No count proves Bank
eligibility or ACK authority. An optional existing FakeCoordinator seam waits
for that callback to finish before its original synchronous ACK render, avoiding
concurrent `engine.render`. The complete ContinuousAudioDriver and both #2004
completed-callback observations are unchanged.

The original PCM/Assign-history/replay/delayed-ACK journeys use that finite
progress boundary. Both original accepted-Bank failure fixtures explicitly
assert one accepted candidate pending1/current old generation before missing or
wrong ACK; the timeout clock starts advancing only after this actual admission,
with the original30s budget unchanged. A distinct no-admission-progress case
accepts no Bank, enters running failure closed with the durable commit intact,
then reopens through a fresh owner and proves complete kept Truth/materials and
positive stereo128-frame PCM. The original main Pad Delete/replay case gains
only the same callback setup; all replay/live-voice assertions remain.

The complete188 registration union/order and every existing assertion/journey
remain; the one additional admission case makes the revised static census189,
not an actual execution result. All14 main-added Pattern bodies, seven-mode
loops, OneShot bounds/overlap, kernel4108>4104, non-FIFO residency, reclaim/reload,
Pattern successor/snapshot/publication/recovery legs remain required. Four
original frozen sources (Bridge, SDK, types and SDK tests) remain byte-identical;
only Control/native-test/owning Portal/this plan changed in this revision.

The isolated Task stays on exacta5bc. Foreign Root externally advanced first
9ffd→a5 and later a5→02b7445; actorUNKNOWN, no worker foreign mutation. These are
separately recorded observations, not original foreign HEAD/index conservation.
The accepted current foreign clean02 baseline, old dirtyD03 and five stashes
remain guarded. No stage, commit, push, PR, Release/deployment or cleanup.

This revised source has not been compiled or tested. Whole original dev and
native-ASAN three targets/registrations, genuine old-handler PCM RED plus exact
fresh-mtime source restoration and actual full rebuilt dev/ASAN checks, whole
Portal, ownership77/ledger15/stage checks, current-head review/shipping and final
committed-head canonical full13/10 batch-only plan remain UNRUN/HOLD. Root will
admit each next concrete execution boundary; the original failed checkpoints
remain failed. V1 MINOR settlement debt and later Creator/hearing acceptance
remain open.

## Additional finite fixture progress (2026-10-12, source only)

Root's independent read-only review of the frozen publication-race candidate
identified two remaining admission/ACK fixture cycles. Native-null Assign runs
after D16 audio activation, so it now uses the existing finite `assign_live`
control-drain seam. Its complete Truth/material/null and original silent128-frame
far side remain unchanged.

The two non-FIFO running Assign legs previously scheduled a OneShot callback
only after Bank acceptance, while admission needed their stop/preview controls
to drain first. Their existing OneShot Bank transition now explicitly requests
sample-control progress: the same driver first renders one control-drain frame,
then retains the original one-frame Bank acknowledgement loop. These callbacks
are sequential on the same driver; its original completion and overlap rules,
exact newly accepted/applied generation observations and2s wait remain intact.
Both legs check completed sample controls and the exact expected enqueue count;
telemetry remains wakeup only, never Bank/ACK authority. One frame before
admission and the original one-frame ACK preserve the96-frame old-kernel lease;
no128-frame progress callback flushes it. All strict4108>4104 quotas, active-voice,
prior-Bank retention, rejection/outcome/reclaim/reload legs remain unchanged.

The finite direct-Assign/import-helper source census found no additional concrete
accepted-Bank fixture needing this seam: other calls are before activation,
already have independent callback progress, or deliberately exercise refusal or
pre-admission quota/deadline failure. The non-FIFO rejected candidate still
rejects at the existing aggregate quota before Bank admission, and its later
original128-frame reclaim callback remains. This is source classification, not
runtime acceptance or proof that execution cannot uncover another defect.

Only the declared native test and this additive plan description change in this
repair; production/Bridge/SDK/types/SDK-test/Portal bytes remain frozen. The
complete original188 cases/order/CHECK predicates and every far-side leg, plus
the189th no-progress test, remain required. Prior eight-file source cuts, failed
native evidence, original contradictory proposal and its DATA-only full3
restoration correction remain preserved. The new whole-eight freeze and exact
16-step proposal need renewed independent Source review and physical native
admission; all revised execution, Portal, stage/shipping and V1 debt stay
UNRUN/HOLD.

The fresh foreign Root observation advanced02b7445→493c82b on unrelated paths,
actorUNKNOWN, with no declared-eight overlap. Root explicitly made foreign
HEAD/branch/raw-index equality non-gating: these observations preserve negative
evidence, not foreign-state conservation or approval of another actor's change.
The original false data-guard failure is retained; no foreign reset/restore or
write occurs. Own exacta5/branch/index/declared-eight/outside-input guards, old
dirtyD03 bytes/head/index/staged state and protected evidence/stashes still
require preservation. This changes no product check or acceptance obligation.

## Whole-query Project projection repair (2026-10-12, source only)

The independently admitted corrected16 native window stopped at original dev
stage4. Configure, serial three-target build and exact three-registration
discovery each returned0; whole dev CTest returned8 with2PASS/1FAIL/0skip.
Control threw `[json.exception.out_of_range.403] key 'project' not found`;
Realtime Session and Performance Bridge passed. The complete raw receipts,
actual rebuilt objects/binaries and frozen fixture-progress source remain in
the external evidence cut. Stages5–16, including ASAN and the old-handler PCM
mutation/restoration, were never run. This failure is neither a new full native
PASS nor the intended causal PCM RED.

Read-only statement order and the existing Application Facade implementation
locate the first erroneous projection after the strict destination stereo128
PCM and exact Bank-generation assertions in the first D03 case. The shared
`inspect_project` helper returns the whole query envelope, whose authoritative
Project is `result.project`; its root `project_revision` remains a separate
field. No stack marker was emitted, so this source location follows from call
order and the concrete envelope shape, not elapsed-time inference.

Root admitted only this test/plan source repair. A finite census of all22
D03-owned cases identifies eight erroneous whole-envelope Project accesses in
six cases: destination PCM/source-slot retention (two), postcommit deadline
(one), accepted-Bank ACK timeout (one), admission timeout without a new Bank
(one), Bridge preparation rejection (two), and expired preclaim cancellation
(one). Each assertion now selects `result.project` before its original whole
Truth equality, retained Asset/Pad identity or material-count predicate.
These eight CHECK expressions are explicit projection exceptions; their text
is changed and must not be reported byte-identical. Reversing just those eight
projection additions reproduces the complete prior native source bytes.

The common helper Contract, correct inner-result fixture/reopen projections,
root revision checks, expected Truth/playback/material identities, all PCM
predicates, generation/deadline/quota constants and call order remain unchanged.
All189 static cases and their registration order remain; every other case body
and CHECK expression is unchanged from the prior cut, including all14 main-added
bodies, seven-mode loops, completed callback observation, strict non-FIFO lease,
reclaim/reload and Pattern/publication/recovery legs. This is a source inventory,
not a runtime passed-case count. The other six declared source files remain
byte-identical to the fixture-progress cut.

Freeze a new whole-eight cut, exact projection-exception census, complete
source/native input maps and the proposed original16 steps for independent Root
review. The existing PCM predicate/failure lines1179/1180 stay unchanged; this
repair adds no lines to the native test. No default lookup, skip, softened
assertion, helper Contract change or product behavior change is introduced.
All execution on this repaired source is UNRUN/HOLD pending separate Root
admission. Whole Portal, stage/ownership/ledger checks, shipping, final committed
head full13/10 plan, V1 MINOR and later Creator/hearing obligations remain open;
the earlier failed stages and their negative evidence remain preserved.

## Version Management

Version impact: additive Web Runtime Platform/SDK public API **MINOR settlement
debt**, owned by parent V1. No version allocation or manifest edits here; do not
claim product-code impact:none. Native public ABI, Project schema, Facade,
existing protocol version and Contract IDs remain unchanged. Identity, dependency
closure, Product Build/Assembly and immutable snapshot settlement belong to the
later explicitly scoped V1 Task. No guessed identities, Build, tag or Release.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform
Reason: document the additive typed producer, known durability versus Runtime
publication, queue/owner and failure authority in the current owning module page.
Existing manifest-derived identities stay derived. No source diagram boundary
changes or permanent snapshot is created by this Task; whole Portal check remains
required before commit.

## Pitfall Impact and completion boundary

Use existing symlink, fresh-artifact restoration, uncommitted snapshot protection,
journey, ownership, absence-positive-control and lane-verdict guidance. Product
regressions express this behavior; no new process pitfall is established yet.
A qualifying ledger delta outside these eight files requires Root scope admission.
Source-ready report is an intermediate active-Dispatch checkpoint, not completion.
Root independently reviews complete combined source and real results, admits
atomic Conventional Commit and shipping under current protection, and gives final
Task disposition before worker_done. No cleanup or release is implied.

## Selected main dependency refresh (2026-10-12, source only)

Root accepted the independent review of the frozen a5 Project-envelope cut:
12657B SHA08e935cc62555bcff9b0643d6d9eabcf71537f86f003ce30b0bca2bb394da66d,
with no new P1/P2. This accepts that source review, not native execution or
shipping. The original dev4 actual8/2PASS/1FAIL/0skip and all later unrun steps
remain preserved. Eight explicit CHECK projection exceptions and189 static
registrations remain the source inventory; no143-case count applies here.

Root then admitted only a baseline refresh to the selected fresh main
`7df1af16df5e6d864ca7968626d63f84a5d9cb63`, citing its own actual fetch0 at
04:13:59–04:14:02 UTC. Worker inspection confirmed a5 is its ancestor, the whole
a5→7df range has31 changed paths with zero declared-eight overlap, and each
declared path's upstream blob/mode or absent-plan entry is unchanged. Immediate
pre-FF guards bound the exact a5 own branch/index/current8/outside inputs,
pristine10 real symlinks, old dirtyD03 and five stashes; no external work was
stashed, restored or reset.

The actual own-branch `git -c merge.autoStash=false -c core.symlinks=true merge
--ff-only 7df1af16df5e6d864ca7968626d63f84a5d9cb63` returned direct exit0.
HEAD is now7df, parent `65c38f0b746bc5c99241f7bd7febcb03139b40ac`, tree
`ee2755ed11a13722a1a0b21e1582e477d0dd53ea`, on the same
`feat/d03-assign-main-integration` branch. Raw index changed as expected to
SHA333096da91d03bc62cedead701d3dc56cecf7ed6d5bd35e6f32a7b06214fc9f8;
the staged diff remains empty. All eight dirty feature file bytes were exact
immediately after FF; this appended plan section is the only subsequent feature
change. The inspected post-merge hook is standard Git LFS only; no product
verification hook or install ran. This is an own source-base FF, not a PR merge
or permission to mutate shared Root/main/other local or remote branches.

Issue-done §0 dispositions were written to the external pre-FF report before
the base or plan edit, using exact7df owning source and successor history:

| Refreshed premise | Evidence and disposition |
| --- | --- |
| Registration, retained inventory, domain/storage identity and owner admission | No Facade/domain/store/protocol changes in the31-path range; original positive controls remain delivered and must not be reimplemented. |
| Runtime publication, Bridge classification and typed ASSIGN SDK | Seven owning upstream base blobs/modes remain exact to a5, so these gaps remain on7df; the seven accepted local feature sources implement the same remaining producer scope, without a new donor or semantics decision. |
| Pattern/#2004 callback and native acceptance union | Owning native file and base167/main-added14 bodies are unchanged; local189 registrations and eight explicit projections remain exact. New combined execution is required, not inferred from that census. |
| #2037 AudioRuntime live gates | Actual7df header/CPP and tests deliver M1: coherent mask pair through the bounded master-control queue; neutral default/start/stop state, Voice live_gate1.0, multiplication skipped at1.0, audition exclusion, Bank replacement retains gates. This changes the shared public layout/render dependency, so all new native artifacts must use7df. D03's seven frozen files make no enqueue_pad_gates call; default-neutral compatibility is a source rationale, not a borrowed M1 PASS. |
| Bank admission, sample controls and lifetime | Original early nonconsuming events_pending refusal stays before Bank move; D03 current-Truth publication, strict Bank ACK/control progress/deadline/quota and every far side remain required against7df. No gate reimplementation or extra queue is added. |
| Consumer/product boundaries | No Creator/Assign decision or retained-material semantics change in the range. #2037 relates to the retained #1822 scope and delivers M1 only; Creator ASSIGN, umbrellas, V1 and hearing remain separate. Remote Issue state is not newly observed in this narrow source refresh. |
| Governance/CI successors | Actual history includes #2030 case-arm recognition, #2032 required actual-result ordering and independent CI fixes. Read current issue-done§0 and changed skill/pitfalls; observe each required terminal result sequentially. Unrelated changes introduce no universal strict-update/full-CI gate or extra execution authority. |
| Ownership/version/Portal | Exactly eight local files;31 upstream paths have zero overlap. Remote writers remain unknown. V1 additive SDK MINOR debt and required owning Portal route remain, with no manifest/allocation/Build/snapshot/Release/deployment/cleanup. |

Freeze a new external main7df cut with complete source8/manifest, this plan-only
delta, whole source diff, exact7df outside-eight paths, honest complete/native
input maps and new own HEAD/tree/index/oldD03/stash/link guards. Preserve every
a5 cut/review/raw failure/proposal and12 old built artifacts without rewriting;
those artifacts were not rebuilt for7df. Seven feature source byte sequences
including CPPdf0e and native3242dc remain exact. Bind the same proposed original16
steps to this actual dependency tree, retaining full3 selectors at4/8/14/16,
original120/360/2s budgets,189 registrations/eight projection exceptions,
stereo128/Bank+1/quota4108>4104, unique1179/1180 PCM RED and exact fresh-mtime
restoration/full3 far sides. No new tool, helper, assertion or test is invented.

All combined7df verification is UNRUN/HOLD pending Root baseline review and
separate original16 execution admission. Existing Node/Type results remain
their exact original source boundaries only, never combined native/full debt
clearance. Configure/build/CTest/ASAN/mutant/Portal/extra diagnostics/stage/commit/
push/PR/PR merge remain HOLD. This Task and Dispatch stay ACTIVE.


## 2026-10-12 playback-schema fixture revision — Source-only / execution HOLD

Root msg_9773c112042a separately admitted one Source-only fixture correction at
own HEAD `7df1af16df5e6d864ca7968626d63f84a5d9cb63`, branch
`feat/d03-assign-main-integration`, empty index SHA
`333096da91d03bc62cedead701d3dc56cecf7ed6d5bd35e6f32a7b06214fc9f8`.
The only changed paths in this revision are the declared native test and this
existing plan. The other six complete files, including production CPP
`df0e53224b2ccf9f00f34dcf1f5785d4104f2490ccf36460a579f2e588ad3a2b`,
remain exact. This entire previous38047B plan prefix remains byte-identical.

The immediately preceding original combined7df dev window actually returned
configure/build/discovery/full-three direct exits0/0/0/8. Control emitted
`[json.exception.out_of_range.403] key 'playback' not found`; Realtime Session
and Performance Bridge passed,0skipped CTest registrations. Later Control
journey legs were unexecuted; no unique runtime case/stack or per-case passed
count is inferred. Original stages5–16 remain STOPPED/UNRUN, no mutant was
applied and no rescue/restore/retry occurred. The frozen failed window, prior
two failures, twelve prior and thirteen current actual artifact archives stay
preserved outside the build graph, never build donors.

The independent complete cause review at
`main7df-source-refresh/independent-playback-schema-cause-review` is14808B SHA
`c2a5328c434c3b7f409d651069476e30862e610e462cf7e7f7e266af777f6750`;
its whole-parsed receipt26135B SHA
`eec22ee978591e935766579d44c4d737c18ee7e8b9d2d3031652cdacbbe9a8a5`.
Current Facade Project inspect returns a Pad summary without playback. The
existing Sample inspect returns the complete canonical playback. Three new
fixture bodies incorrectly copied playback from the Project summary and
fabricated that absent field in expected Project. This is a fixture/schema
mismatch; the exception does not establish a new producer/Facade/API gap.

Only these three complete native case bodies change in this revision:

| Case | Retained public Project comparison | Independent complete Sample playback far sides |
| --- | --- | --- |
| assignment_history_restores_whole_truth_pcm_and_reopens | Exact whole actual summary; only real revision/target asset changes | Capture actual default X and nondefault gate/-600 Y at6; source/target at assign7, Undo8, Redo9 and fresh reopen9 |
| assignment_post_commit_deadline_retains_identity_and_truth | Exact whole summary at known committed7 and identity retry | Capture X/Y at6; complete source/target playback after commit-but-unpublished7 and identity retry7 |
| assignment_admission_timeout_keeps_commit_without_a_new_bank | Exact whole summary after terminal committed7 and reopened owner7 | Capture X/Y at6; independent complete source/target playback while Control is failed and after fresh reopen7 |

One private local `inspect_assignment_playback` helper in the declared native
file creates a fresh existing Application and issues only the existing raw
`sample.inspect` query with operation/absolute same own project_path/exact
bank-pad slot. It validates the genuine three-key Facade envelope, exact six
Sample result keys, root and inner expected revision, slot, Asset identity and
playback object; callers compare the entire playback JSON. It does not call
Control success helpers on this raw envelope, use failed Control dispatch,
parse bundles, add a product projection, infer Runtime recovery or resend an
Assign. Existing observer load/recovery behavior is unchanged; the read is
authoring Truth, not a Runtime publication receipt.

Three invalid expected-summary playback writes are removed; every original
literal CHECK comparison remains and22 strict complete playback CHECKs are
added in the three cases. The X/Y capture checks independently fix the
original fixture defaults; the expected reset result matches delivered Domain
Assign semantics and does not decide arbitrary source-Pad parameter copying.
There is no contains/default/value/catch, narrower gain-only or PCM-only
replacement. Whole Project summary/history/artifact/stereo128 PCM/session/
reopen/Bank/no-progress/current-Truth/identity/typed error far sides remain.
Shared inspect_project and fixture truth helpers are unchanged.

Current189 zero-argument registrations and order stay exact. Relative to the
immediately preceding accepted native521963B SHA
`3242dcfadb2f4a83f5f67f2fa577c5a6bfaa3ce11e607c6b0f773173312cc552`,
only the above three test bodies differ; the other186 complete bodies are
byte-identical. Relative to the pre-envelope F cut, the cumulative exceptions
are the real seven-body union, with the other182 whole bodies exact. The
original eight result.project CHECK corrections remain exact; no assertion,
mode loop, timeout, job/case count or journey leg is deleted. The14 main-added
whole bodies, strict7 modes, completed #2004 callbacks, OneShot2s, one-frame
ACK/96-frame lease,4108>4104 quota/reclaim/reload and Pattern legs remain.
Static registration/CHECK counts do not establish runtime passed-case counts.

Version Management for this fixture-only revision: no additional product API
or identity/version allocation. The owning D03 additive Web Runtime/SDK MINOR
settlement debt V1 above remains open; this does not change the Task's product
version-impact declaration to none. Documentation impact remains required at
`/core/modules/web-runtime-platform`; current owning Portal bytes and derived
identities are unchanged. No Build/snapshot/Release/deployment/cleanup.

The external cut `playback-schema-source-revision` freezes the full eight
source files, complete whole-eight diff and only-two-file delta, all189 whole
function/body/CHECK comparison records, current3423/332 input maps, exact
source/index/oldD03/stash guards and updated prospective original16 proposal.
The strict original positive stereo128 PCM case body is unchanged but moves
by the one inserted helper; the proposal binds its actual new predicate and
failure lines from the source, never stale1179/1180 numbers. The prospective
old-handler mutant and exact CPP fresh-mtime restoration boundaries remain;
no mutant was applied or built in this Source-only revision.

All new native/helper/dev/ASAN/causal/restoration/Portal/Node/Type/full checks
are UNRUN/HOLD. Root retains separate independent Source review and serial
physical-host execution admission; P1 owns its current admitted M1 slot. The
original full16 commands, full-three selectors4/8/14/16, dev120/ASAN360 and
OneShot2s budgets are not reduced. Current candidate must earn its own actual
rebuilt evidence and preserve each failure. Stage ownership77/ledger15/diff,
atomic commit/current-head review/shipping and final committed-head full13/10
batch-only plan remain later boundaries. Task/Dispatch ACTIVE, no worker_done
until Root final disposition, no generic success based on current Truth or an
unknown durable receipt.

## 2026-10-12 shared-platform fixture Source correction

Root `msg_a549b1044352` admits one SOURCE-ONLY correction on fixed
`7df1af16df5e6d864ca7968626d63f84a5d9cb63`, same ACTIVE Task
`task_d39374a2afe6` / Dispatch `ctx_38f4d937a560`. Only the native test and
this append change. The preceding44984 bytes, SHA256
`35211359ac73bb7f7fcd814357bcad5334a4fa6e99a578b7f2d0087dabc1332b`,
remain exact. The six other producer/SDK/Portal files, common constructors,
Project/History/PCM/OneShot helpers and product/storage/locking code remain
unchanged. The external child is `shared-platform-fixture-source-revision`.

The prior playback-schema original16 execution is FAILED, not resumed or
relabelled: its stages1–4 naturally returned0/0/0/8. At
06:51:36.055689–06:51:39.024138 UTC, CTest PID/PGID47922 returned8; Control
failed with `exact response key count mismatch` on the raw Sample
`IO_ERROR` / `storage_condition: project_busy` envelope. Realtime Session
and Performance Bridge passed; zero CTest registrations were skipped. The
raw stdout2626B SHA256
`3768ebcd3eba7f62871ca827d6905b573ea8f4ae78754393039a0d21ffc462e4`,
stderr, four complete direct receipts, CTest metadata and actual13 failed
artifacts remain independently preserved outside the build graph. All own
groups naturally emptied. Stages5–16 remained UNRUN; no ASAN, mutant,
restoration/rescue, retry, timeout change or Source edit occurred within
that window. Later Control legs were unexecuted. The actual failed dynamic
case/index and executed native-case count remain UNKNOWN; the error has no
case marker, stack or assertion line. Static direct call2/history's first
playback observer is a Source candidate, not an observed runtime identity.

Root FULL-read the author8553B diagnosis and independent14163B review,
SHA256 `bff26b057719b00ceecbe379ce5fcfc2fb30eea50ba78b3227ad1a1ed815e9ce`.
The independent review confirms a reachable private fixture P2, without a
new product-storage defect or concurrency contract. The old helper creates
a fresh Application from common config whose storage_platform is null.
That gives it a separate default NativeProjectStoragePlatform and a
separate weak writer-state map, while Control retains its project writer.
ProjectStore.load permits a busy metadata observer, but nonnull
sample.inspect also reads the Artifact through read_artifact, which requires
writer acquisition. A separate platform cannot alias the retained native
writer; its nonblocking kernel flock can produce the observed project_busy
Sample error. The old first strict raw key check is native1137, not1139.
The unchanged public Project summary's omitted playback remains omitted.

RetainedAssignmentFixture now owns one default shared storage platform,
declared and initialized before runtime. Its fixture-local construction
method copies the existing common config, sets that existing field and
calls ControlRuntime::create with unchanged kWebLimits and the existing
success check. The constructor and exactly the two repaired history and
admission-timeout reopens use that method. The private playback helper takes
a copied shared pointer and builds a FRESH Application from the same
common config with that field set; it still queries raw sample.inspect.
All22 existing observations gain only that platform argument. Other
arguments, observation order, exact root/inner key sets, root/inner revision,
slot/Asset identity and complete playback comparisons remain. Both baseline
X/default and Y/gate-minus600 payloads, source retention, Undo/Redo/history
once/session, artifact bytes/hash, stereo128 PCM and failed-owner/noBank/noACK
checks remain. No assertion, render, wait, retry, response fallback,
summary/default/receipt-derived playback or bundle parser is added or removed.

This is one serial fixture's use of existing same-platform NativeWriterState
alias policy. The platform map is weak; the fixture stores no extra lease.
Fresh observer leases and Applications are scoped to each observation. The
fixture keeps its platform pointer and copies it into config, so runtime is
destroyed before that member; the pointer alone cannot retain an old kernel
lease. The failed admission owner is retained through both pre-reopen
playback observations and the terminal-trigger refusal, then reset before
the fresh owner. The history owner still closes and resets before reopening.
Both new Controls legitimately acquire their normal writer through the same
fixture-local platform. Other fixtures and foreign-project observers keep
their own platforms; no common factory or global storage instance changes.

An acquired alias means ProjectStore.load takes its existing recovery and
scavenge branch. The finite premises are explicit: these three cases use
pattern_transport=false and start no Sequence, Performance or recording
session; imports use the existing byte-backed asset.import path, with no
incomplete segmented Sample staging. Every observation follows the owning
dispatch or publish scope's return, after a known committed revision. X and
Y remain retained in current Project assets through Assign/Undo/Redo, so
recovery retains both WAVs without depending on a different Application's
in-memory Undo retention. The fresh observer's AuthoringHistory is separate
and does not reset the owning history/session. Existing owner truth() already
loads through that platform. These are Source fixture premises, not new
residue observations or a general independent cross-owner read API; widening
the helper to active staging or journals requires a different review.

The source inventory remains189 direct calls plus the separate strict
seven-mode loop (190 textual call sites in main). All186 other direct case
bodies, whole main/order and completed-callback/OneShot2s/quota/lease/Pattern
legs remain byte-identical. Reversing only the22 added arguments, two
construction substitutions, new fixture method/member/initializer and
private helper edit restores the preceding whole native bytes. The complete
PCM case remains3477B SHA256
`a9cbfd835ab0b8b04644735a0850fee4ddb0daab15662345a02b4f15e0b9a3ed`,
with predicate1208 and actual macro failure line1209 unchanged. Existing
helper checks remain; the new constructor success check is Source-only.
No runtime passed-case count is inferred from this inventory.

Version Management: this private fixture correction allocates no version or
identity and introduces no additional product API. The owning additive
Web Runtime/SDK MINOR settlement debt V1 remains open; product Version impact
does not become none. Documentation impact remains required at
`/core/modules/web-runtime-platform`; the owning Portal source and derived
identities remain unchanged by this repair. No Build/snapshot/Release,
deployment, global setup or cleanup is in scope.

All new candidate native/dev/ASAN/causal/restored/Portal/Node/Type/full checks
remain UNRUN/HOLD. N13 owns the admitted M1 light slot; Root must review the
frozen whole-eight diff, minimal two-file delta, three whole cases/all22
sites, lifetime/order proofs, unchanged outside inputs and diff --check,
then separately admit a concrete serial native window. The original15271B
full16 proposal SHA256
`b43205b5da24299d121e110bddf5f2e952646c44f0a6a6f7406594beb660fbd4`
remains the execution-plan reference: full original three targets/registrations
at4/8/14/16, dev120/ASAN360/OneShot2s, actual rebuilt old-handler PCM RED and
fresh-mtime exact CPP restoration followed by real dev/ASAN rebuilds. It has
not been executed on these new native/plan bytes; future admission must bind
the new8/3423/332 identities and current tools/artifacts without borrowing an
old passkey or rerunning old causal mutants merely for counts. Source check
does not authorize product/helper execution. Ownership77/ledger15/stage,
atomic commit/current-head review/shipping and final committed-head full13/10
batch-only scheduling remain separate. Task/Dispatch stay ACTIVE; no
worker_done until Root's final disposition.

## Source-only progression: ASSIGN publication wait scope, 2026-10-12

This entry preserves the complete preceding52963B plan prefix, SHA256
`cc06d9243067f628e79e2498531d61e7752e076875b98973e5b0612ed78d636b`.
Historical source admissions, failures, proposals and unexecuted obligations
above retain their original identities; they are not new candidate passes.

The shared-platform fixture source received Root's serial native admission
`msg_b6c825754e6f`. Its actual original commands1–4 returned0/0/0/8:
dev configuration, the three-target serial build and exact three-registration
discovery succeeded, then the whole original dev selection failed. Control
failed44.77s at `control_runtime_test.cpp:2566` in
`test_exact_payloads_and_facade_owned_project_journey`, where the existing
`sequence.record.status` success assertion received HOST_STATE_INVALID with
message `operation is unavailable` and empty details. Realtime passed0.09s
and Performance passed1.22s; the complete CTest selection was2 passed,1 failed,
0 skipped,46.10s. No native per-case passed count or dynamic case index is
inferred. Stages5–16 were not executed; no ASAN, causal mutation or restoration
was attempted. The failed binary, rebuilt native object, actual graph/link
records, complete raw command receipts and CTest logs remain retained.

The bounded failed-stage receipt is83111B SHA256
`e7f512a0f126feec7c1a17c89609710ee2fbdeaca266b29d67dd2eee5b575e00`;
the source/read-only diagnosis is12996B SHA256
`cfcdb9cb2746c9336da6fdb78d2853706547af5aed3964bbb96f0a27ab43617b`.
Both live outside tracked source under the shared-platform source evidence
cut. Root admitted read-only diagnosis in `msg_b09fd55cdca6`, then independently
reviewed the entire report, its actual guard receipt and the2699B proposal
SHA256 `e4c87efa663e573e14b2fb276ab1ee89304bf655332ac6cf449bbf2a660250e6`.
Root reports its independent12859B review SHA256
`dcf66dc9c0fc8801a601fe95994dad624f167436817599448067a30cd21f5966`.
The Source-only answer to the single durable question `msg_afd8fc7c04d7`
admits exactly that proposal's five private CPP deltas and this factual
append. It admits no execution, retry, mutant application, commit or shipping.

The actual response and assertion are runtime evidence. The causal branch
trace is static: `sequence.record.status` remains a registered Facade query,
and the complete relevant query routing and Sample commit methods are exact
between the7df base and inspected d21 main. The existing capture journey uses
the fake coordinator without a rendering callback; its commit can leave
stop/preview control events pending. This Task widened the common
`prepare_and_publish` path from one Bank publication attempt to an
unconditional events_pending wait. On this existing no-render path that can
produce HOST_TIMEOUT, which the unchanged Sample result handler uses to seal
the running owner before the following Sequence status query. No additional
branch instrumentation was executed, and no exact30s branch duration was
measured. The defect belongs to this Task's widened waiting policy, not an
operation-kind mapping change or a new product concurrency decision.

The applied correction adds a default-false private wait policy to
`prepare_and_publish` and `sample_mutation_result`, forwards that policy, gates
the existing events_pending loop on it, and opts in only the known-committed
ASSIGN result. The CPP now has264566B SHA256
`92bf64c70362e7921bc345869e1423182bfcead7c3af6c5e3f1806f49802e061`.
Every existing caller keeps its original one-attempt publication behavior.
ASSIGN retains the same prepared Bank while its stop/preview controls drain,
the existing deadline, actual acknowledgement and current-Truth publication
handling; no Facade resend, automatic command retry, new queue, public API,
header or host-owned Truth is introduced. This source correction has not yet
demonstrated a repaired runtime result.

Fresh pre-edit guards returned0 and bound all eight source files, exact7df
HEAD/parent/tree/branch, empty staged set and raw index SHA256
`333096da91d03bc62cedead701d3dc56cecf7ed6d5bd35e6f32a7b06214fc9f8`.
They rechecked3423 complete source inputs,332 native inputs, all ten actual
pristine Git120000 links, all old D03 source/index bytes and five protected
stashes. The frozen38-payload cut, current failed36 artifacts including mtimes,
both thirteen-artifact failure archives and actual/retained CTest logs were
exact. The pre-edit guard is18403B SHA256
`4d0cc24144d8224a2eaff0338b2b8ddcae8bef0dea2b5191e7a147cdc3aeb3b5`.
The correction changes only this CPP and this append. The other six complete
files, including native526920B/e7aa, remain byte-identical. The native189 direct
registrations plus separate strict seven-mode loop, whole Sequence tail,
PCM predicates1208/1209, all original assertions and120/360/OneShot2s budgets
remain. Root checkout/ref/index/config are foreign concurrent observations,
UNKNOWN/NONGATING; no restoration or mutation of them is performed.

Root's refreshed/live main observation is
`a4923f20f78ba6780d1265882669b8a00a762de4`. Our direct read-only diff from the
previously inspected `d21ea97c71da281f89ac78238f6fcceb8b03e638` to that exact
commit is empty for complete Control CPP/native, Application CPP and
RealtimeEngine CPP. Root explicitly retains the working7df base for this
bounded repair. New-main integration is an explicit later debt; there is no
rebase, fetch, copied live Root source or foreign mutation in this step.

The frozen new Source8/3423/332 maps and prospective only-old-ASSIGN-handler
reduction rebind the original complete16-stage proposal to this92bf producer
and unchanged e7aa native. The original15271B proposal restores df0e and is
historical, not an exact future execution admission. The new proposal keeps
all original executable argv, selections and budgets: complete three-target
dev and ASAN builds/discovery/runs, only the authenticated original ASSIGN
handler replaced for the causal reduction, a fresh actual rebuilt failure at
the unique positive-left128 PCM predicate1208/macro1209, then exact92bf
fresh-mtime restoration and actual rebuilt whole dev/ASAN checks. No reduction
or restoration is applied now. Wrong/earlier RED, an unexpected exit, graph or
source drift, missing real Bridge, omitted far side or a skip remains a stop
condition; no weakening or generic last-child success is accepted.

Root's replacement-user-AGENTS notification `msg_b63f66797789` supersedes the
earlier generic requirement to run all13/all10 complete lanes locally before
ordinary shipping. Ordinary PRs retain Task-relevant verification and explicit
covered risks/results, current-head review, conflict and conversation
protection. Selected batch_only lanes do not create a blanket local full-lane
obligation; deferred lanes remain unverified and cannot clear complete
candidate debt. This changes no declared owning integration/restart/stress
test or journey: D03's original16 stages remain required. A canonical final
committed-head lane inventory remains a Root scheduling input, not evidence
that any deferred lane passed.

Version Management: additive Web Runtime/SDK API MINOR settlement debt V1
remains open. This private policy correction allocates no version or identity;
it does not turn the owning product impact into none. Documentation impact
remains required at `/core/modules/web-runtime-platform`, whose owning page
is already among the eight declared paths; derived identities are retained.
No Product Build, immutable snapshot, Release or deployment is allocated.

All verification against this new CPP/plan cut is UNRUN/HOLD, including the
original16 native stages, current whole SDK/protocol and Type owner checks,
and whole Portal check before commit. Old SDK/native/Type receipts retain
their exact old-source boundaries; the old-v2 A1/A5 negatives remain negative.
Root must independently review the new actual two-file and whole-eight diffs,
Source maps and concrete16-stage bindings, then separately admit a serial M1
window. Ownership77/ledger15/stage checks, atomic Conventional Commit,
current-head review and authorized shipping remain later stages. No
installation, root/sudo/global change, foreign process action or cleanup is
admitted. Task/Dispatch remain ACTIVE; no worker_done before Root's final
Task disposition.

## Proposed-only source integration checkpoint: merged replay helper #2070

This section records the exact source integration specification. Applying it
requires Root independent review; it admits no verification or shipping.
It preserves the complete preceding61294B plan/6ae45191f1d09f6af3b8385164772efe24db2546e6c6d5b0f13b8308068c79bf.
Root followups msg_b32a2996b6de/msg_b408be57d459/msg_fc3dff70f2bf require
the admitted92bf producer Source freeze and separate independent review of
exact43f41d2f1cf0f8294568e9964c058d141421aa46 helper integration before
future original16 verification. Prior Source report12880B/193c6f26 and its
64-payload freeze preserve the old guards and failures, never current passes.

Exact43 main native472912B/342fc36 changes only the complete
dispatch_transport_after_replay helper and adjacent comment relative to the
7df native base. The proposed integration replaces only this exact span
inside this Task's526920B/e7aa native file. Actual main43 has167 direct
registrations and a separate strict seven-mode loop; its174 statically
expanded count is not174 direct bodies. Current Task has189 direct calls
and the same loop:167 main plus22 Task direct registrations,196 statically
expanded, runtime count UNKNOWN/UNRUN. All190 registered-plus-mode complete
function bodies and entire main order remain exact to frozen Task Source.
Existing Task body differences from upstream are separately enumerated;
the new helper proposal changes none of those bodies or assertions.

The helper has three actual direct Play/Stop/Record-after-Replay callers.
Their complete success/publication, playing/recording, target Pattern,
voice, retained Truth and event assertions remain. The separate timeout
refusal case and all other test bodies remain unchanged. The upstream delta
changes31 lines in one helper, never an invented31-function executed count.

The merged helper retains the original two-second AbsoluteRequestDeadline
and two-second wait_until. After the nine-FX prefix and original absence of
publication assertion, it renders explicit128-frame quanta until done or
next Pattern acceptance is observable. It requires success if already done,
real accepted publication, nine FX drains and zero queued gestures, neutral
Filter engaged/frozen/hold state, exact Pad-gate applied/accepted sequence
and zero mute/solo masks. It retains the final128-frame callback, join,
success, replay stopped and selected Pattern far sides. It preserves the
merged scheduling when the last reset callback already consumes publication;
no budget, caller journey, native registration or product behavior weakens.

Only the declared native test path and this factual append would change.
Producer92bf, Bridge, SDK/types/tests and owning Portal bytes remain exact.
No whole-file donor, FF/rebase, Facade/adapter edit, extra path, historical
helper execution, index/ref/stash/build/config/foreign mutation is proposed.
Later local origin/main changes are enumerated separately and have zero
Source8 overlap; current remote freshness is not inferred. Separately owned
reset adapter implementation is not copied. Later dependency integration
and current-head review remain explicit Root dispositions, not old passes.

Prospective Source8/3423/332 and original16 must bind the whole native to
this exact merged-helper union. Only the authenticated old-a5 ASSIGN-handler
mutant and exact92bf CPP restoration remain; restored native must retain
this helper and every complete189 direct body, never olde7aa overwrite.
Original16 argv, three whole dev+ASAN targets, dev120/ASAN360/serial1,
OneShot2s, actual rebuilt unique PCM predicate1208/macro1209 RED and
fresh-mtime CPP restoration with actual rebuilt whole dev/ASAN GREEN stay
required. No mutant, restoration, build or verification is applied here.
All new native16/SDK/protocol/Type/Portal checks remain UNRUN/HOLD until
Root's separate Source and execution dispositions.

Version Management: additive Web Runtime/SDK API MINOR V1 settlement debt
remains; no actual version allocation, manifest or identity change.
Documentation impact: required at /core/modules/web-runtime-platform;
owning current page stays in Source8 with derived identities retained.
Replacement user AGENTS retains Task-owning verification and explicit
risks/results; deferred complete lanes remain unverified without a generic
all13/all10 local shipping gate. No Release/deployment/cleanup/install,
root/sudo/global operation, index/commit/push/PR/shipping is admitted.
Task/Dispatch remain ACTIVE; this specification admits no execution or
settlement, and Root retains independent source review and scheduling.

## Original16 dev failure and observed fixture publication boundary

The helper-integrated exact Source8 Original16 window returned direct exits
0/0/0/8 for dev configure, serial three-target build, original three-registration
discovery and whole three owning native tests. ControlRuntime failed at the
unchanged Sequence overlay publication counter (`control_runtime_test.cpp:2864`,
`final_pattern.applied_publications == 3`); Realtime and Performance Bridge
passed, with two passed/one failed/zero skipped registrations. The original
actual publication value and internal passed-case counts are UNKNOWN. Complete
stdout/stderr, PID/PGID/time/argv/env/wait receipts and failed artifacts remain
under `current-main2070-helper-source-integration/native-execution-original16-20261012T1714Z`
outside source; prior negative cuts remain immutable. Steps5–16, current SDK,
protocol, Type owner and whole Portal are UNRUN; no mutation/rescue occurred.

Read-only owning-source analysis identifies a test observation boundary:
fixture ASSIGN now publishes current Truth's stopped Pattern before this
Sequence journey begins; stopped `snapshot.reload` then publishes its own view,
and audio start retains the cumulative Pattern application counter. The
Sequence journey still owns exactly three applications: its explicit reload,
the settings replacement overlay applied after750 callbacks, and the clean
Stop publication applied after1000 more callbacks. The release overlay is
superseded exactly once by settings. The absolute constant previously also
encoded a fixture with zero publications. The repair observes fixture accepted/applied counters before and after the
unchanged import/ASSIGN helper, strictly requiring exactly one acceptance and
one application in preparation. It then retains that observed after-value
before this journey's snapshot reload and strictly requires it plus3. It changes
neither3 to a guessed4 nor equality to a bound and keeps the complete reload,
record begin/input/settings/stop journey, exact committed revisions and
publication frames, voices1/2/3, overlay transitions, superseded==1 and all
750+1000 completed callbacks. Other189 complete registered-plus-mode bodies,
all189 direct calls, the strict seven-mode loop and exact43 replay helper remain
byte-identical; CPP92bf and all product behavior remain unchanged. The source
attribution is not dynamic causal proof or a new passed result.

This source-only revision preserves the eight-file Task scope, owning Portal
impact and additive API MINOR settlement debt V1 without version allocation.
Future verification still requires a separately admitted fresh serial original16
dev/ASAN/actual rebuilt PCM RED/fresh restore run on the complete updated
native source. No assertion, timeout, budget, target, job count, mode, test or
far-side deletion is authorized; no Source/build/execute/commit/shipping result
is inferred from this analysis.

## Original16 dev bank reclamation failure and observed fixture Bank boundary

The current observed-Pattern-fixture Source8 Original16 window returned
actual direct0/0/0/8 for dev configure, serial three-target build, exact3
registration discovery and whole3 native tests. ControlRuntime failed at
`control_runtime_test.cpp:5468`, `after.reclaimed_banks ==
before.reclaimed_banks + 1`; Realtime and Performance Bridge passed,
2P1F0skip, whole61.02s. Original actual reclaimed counters and internal
passed-case counts remain UNKNOWN. Complete raw commands/logs/waits and
36 actual failed artifacts with mtimes remain outside source under
`sequence-overlay-counter-native-execution-original16-20261012T1904Z`,
with its139-payload immutable cut and all earlier negative evidence.
Steps5–16, current SDK/protocol/Type/Portal remain UNRUN; no mutant,
rescue, retry, new Source correction or shipping followed that window.

Bounded read-only source attribution identifies an incomplete fixture
accounting adaptation, not an established production reclamation defect.
The exact7df main case has current_generation==1 and close-reclaimed+1;
old frozen-v2/current Task case already changed the generation to2 while
retaining the +1 reclamation. Project creation/import do not publish a
Bank; known-commit ASSIGN now publishes one stopped Bank, then the unchanged
snapshot.reload publishes a second. The preparation reclaim precedes the
second publication, while the first is still current. Applying reload
retires the first; Host Close retires its current Bank and the existing
reclaim sweep frees both eligible Banks and refunds their reservations.
Current release_runtime_banks and the whole Engine are exact to7df main.
This predicts two eligible Banks from source but does not invent a printed
actual+2 or dynamic causal proof.

The proposed owning test observes accepted/applied/reclaimed telemetry
around the unchanged import/ASSIGN fixture, requiring exactly one acceptance,
one application and no reclamation. It then requires exactly one further
acceptance/application and no intervening reclamation for explicit reload,
keeps the existing current_generation==2 assertion, and strictly accounts
Close as the observed retired fixture publication plus the original current
Bank +1. It keeps equality and the full exact Close response, zero current
generation, unchanged accepted/applied counters, empty subsequent reclaim
count/bytes and restart/sample-unavailable/zero-voice/invalid-event/Stop
far sides. No explicit early reclaim, rendering, deadlines, callback pump,
new product policy or weakened bound is added. Other189 complete bodies,
all189 direct calls,7-mode loop and prior observed-Pattern case remain exact;
product CPP92bf and the other six complete declared files are unchanged.

This external candidate is not applied or tested. Any Source application
and fresh original16 dev/ASAN/actual-built uniquePCM RED/fresh92bf restoration
requires separate Root admission with unchanged original argv/env/targets,
serial1, dev120/ASAN360 and OneShot2s. The updated native identity must remain
fixed through any later CPP-only mutation/restore. Task scope remains eight
files, Documentation impact required at /core/modules/web-runtime-platform,
additive API MINOR settlement debt V1 with no version allocation/manifests.
No product verification, staging, commit, shipping, Release/deployment or
cleanup is inferred; Task/Dispatch remain ACTIVE pending Root disposition.


## Accepted current owning verification (2026-10-12T21:28:41Z)

The preceding failed and UNRUN entries are historical cuts. Root accepted
the current owning native Original16 and all nine SDK/Type/Portal commands
after separate resource admissions; this section records those actual results
and does not relabel earlier failures or claim the whole Goal is complete.
The tested product/test/Portal files remain exact at the seven-file cut
CPP92bf, Bridge464fde, SDK06248e, types62cbba, nativecf666, SDK-testc0dd57
and Portal863cf5. The owning branch is feat/d03-assign-main-integration at
base7df1af16df5e6d864ca7968626d63f84a5d9cb63; this append changes only this
already declared plan.

- Native Original16: initial and restored dev/native-ASAN each ran the
  complete three owning registrations with real Bridge linking, actual
  3P/0F/0skip, original120s/360s, serial1 and OneShot2s limits. The CPP-only
  historical ASSIGN handler was actually rebuilt and produced the unique
  original stereo128 PCM assertion failure at control_runtime_test.cpp:1209
  (CTest direct8). Exact92bf restoration used a fresh mtime newer than the
  mutant and all measured CPP objects; both dev/ASAN CPP variants were
  actually rebuilt before full-three GREEN. No assertion, callback leg,
  timeout or count was weakened. Static189 direct calls+strict7-mode loops
  and190 full bodies are preserved; internal executed-case count is UNKNOWN.
- Current Node26.8.1 SDK syntax direct0; whole runtime_session.test.mjs
  actual174/174 PASS and whole protocol.test.mjs actual38/38 PASS, both
  zero fail/cancelled/skipped/todo. The11 ASSIGN cases and all main cases
  retain explicit target/owner/caller identity, actual Host tail, typed
  publication authority and immutable unknown-receipt/no-auto-resend rules.
- Existing own TypeScript7.0.2 noEmit with the complete owning Creator config
  exited0 and listed595 actual input paths, including the public SDK
  declaration. This is type acceptance, not a Creator UI or browser suite.
- Own stable locked Portal install direct0, with existing npm11.19.0 recorded
  transparently against retained npm@10.9.3 declaration; no tool/config
  upgrade. Whole scripts/docs-site.sh check direct0: actual176/176 tests,
  zero fail/cancelled/skipped/todo;52 pages,10 diagram sources/20 outputs,
  existing derived facts/snapshot, typecheck,2 Host/4 Release projections,
  full static build and50 rendered routes/internal links valid. Advisory
  npm lifecycle and Node ExperimentalWarnings remain in the raw receipts;
  no bypass, retry, permanent snapshot allocation or publication followed.

Bounded original commands/natural waits/source/object/binary bindings and
full streams are outside tracked source in the D03 evidence root: native
report15519B/SHA2567c00d275c2d5dc16b7d4894e149f2dba43726eb5760891edcef844371b181d2e
and278-payload cut; current nine report12813B/SHA2560a61c902569be148575513eb644bb600b89d87edebfda4a460a95213fc5e2450
and66-payload cut. Each original command has its own direct exit; success is
not inferred from a final child. Foreign Runner overlap/point observations
are honestly retained, without a global-exclusive or performance claim.
Old worktree/stashes/resources and all original negatives remain preserved.

Ownership77/ledger15, complete declared staged diff, atomic Conventional
Commit, exact-current-head independent review and protected shipping remain
unexecuted here and require the known Task queue release. Canonical final
committed-head full13/10 is a scheduling inventory/deferred complete-candidate
debt, not a universal ordinary merge gate or PASS. Creator ASSIGN picker,
occupied confirmation/cancel, browser/hearing/physical and other Goal work
remain separate. Documentation impact remains required at
/core/modules/web-runtime-platform; additive API MINOR settlement debt V1
remains, with no identity allocation/manifests, Release/deploy or cleanup.

## Current-head review F1 remedy: bounded Source phase (2026-10-12)

The accepted verification above belongs to its exact source cut. Subsequent
ordinary metadata verification passed the original ownership77/ledger15 suites,
and the exact eight files were committed as8955c46fe13c956e930c156842d5468c4bef37b7
and pushed to PR2107. Authentic current-head review run38314567765/attempt1
completed with review_wait eligible=true, diagnostics empty, and two unresolved
findings; eligibility alone did not authorize merging unresolved conversations.
The initial pending review_wait direct1 and later eligible direct0 receipts,
the whole two-thread collection and all earlier negative evidence are retained.

Root independently rejected F2's missing-Runtime-fields premise: cancellation
after a known ASSIGN commit only skips stop/preview controls; it does not return
the raw Facade response. sample_mutation_result always constructs
runtime_revision/runtime_published, and the handler updates the result with
them. The existing post-commit deadline test asserts the exact eight-field
result, HOST_TIMEOUT, durable identity/Truth and explicit same-command replay.
No Source change addresses this incorrect premise; the reason still needs an
actual recorded review reply and thread resolution after the admitted stages.

F1 is partially accepted. Every public dispatch installs the original absolute
deadline, and the existing no-callback admission test proves typed timeout
without a new Bank; the claim of unbounded real-clock waiting is incorrect.
However, the ASSIGN-only events_pending retry repeatedly calls Engine
publication/control observation while no callback drains its committed
controls. Yield alone supplies no retry pacing. The bounded remedy requests
sleep_for(min(1ms, max(0, absolute deadline - clock_now()))) between those
nonconsuming publication attempts. It preserves the existing deadline check
before waiting and checks that same deadline again after waiting, before
another publication attempt. The requested sleep duration is bounded; scheduler
overshoot is not claimed absent. The wait limits repeated CPU work and does not
release the logical Bridge dispatch or pump, or establish a measured CPU result.

The original30s/caller deadline, one prepared Bank, retained known commit,
typed timeout/no-new-Bank result, other callers' single publication attempt,
existing Bank acknowledgement loop and all acceptance assertions remain.
No attempt cap, recooking, durable command resend, private queue, schema,
SDK/type/Bridge change or new product semantics is introduced. This revision
changes only control_runtime.cpp and this already declared plan; the other
six declared source/test/Portal files remain exact to the accepted cut. The
189 static native direct calls, strict7-mode loops and190 full test bodies are
unchanged; these are source inventory, not executed-case counts.

Root admitted only this bounded Source phase while the consumer owns the
local product-verification window. New CPP native verification is UNRUN:
after resource admission, rebuild the original three owning targets serial1
for dev and native-ASAN, then run all three registrations through the original
whole CTest commands, preserving dev120s/ASAN360s and OneShot2s. Their existing
post-commit deadline, admission timeout, late control drain, acknowledgement,
real Bridge and all far-side assertions cover the changed publication path;
no assertion, test selection or timeout is reduced. Prior exact-cut native
GREEN/actual-built PCM RED remain historical evidence, not PASS for this CPP.
Unchanged whole SDK174/protocol38, Type595-input and Portal176 receipts remain
separate evidence. New native results, final source review, Task metadata,
safe own-branch atomic-commit revision, exact-head independent review, actual
finding dispositions/conversation checks and protected shipping remain pending.
No build/test, staging, amend, push, review reply, resolution or merge is
authorized in this Source phase. Canonical full13/10 remains scheduling debt;
Creator consumer/browser/hearing, V1 MINOR settlement and all previously
declared unexecuted Goal obligations remain distinct. Documentation impact
stays required at /core/modules/web-runtime-platform; no new Portal fact or
version/identity allocation, Release/deployment or cleanup is introduced.

## Actual F1 owning native results (2026-10-12T22:52:49Z)

Root resource-release msg_01d1a5716732 admitted the original six necessary
commands for the frozen CPP77a45b/plan37aa cut. All six naturally exited0,
without retry, reconfigure, mutation, assertion or timeout changes. Actual
dev and native-ASAN builds recompiled both production/testable CPP variants
and relinked all three targets. Original discovery confirmed all three
registrations and original120s/360s budgets; OneShot2s and serial1 remained.
Whole dev CTest actually passed3/3, zero failed/skipped,95.67s; whole ASAN
passed3/3, zero failed/skipped,211.41s. Both complete raw streams and every
direct child exit were read; expected refusal diagnostics are retained.
Four actual CPP object identities/mtimes and both18-file artifact sets bind
the tested executables to new77a45b and real Bridge linking. Unchanged Bridge
and native-test objects are reused without claiming they recompiled. Static
189 direct calls/strict7-mode loops/190 full bodies remain source inventory;
internal executed-case count is UNKNOWN. All six own groups ended naturally,
the final live observation found no group members, and the window is closed.

Complete receipts/Source/native332/tool10 identities and old-D03/five-stash
guards remain outside tracked source in current-head-review-f1-native-original6:
report7560B/SHA2560dcdf7bf1c2961d7f3e2b03a9645e62eb6850ab3af447499aeef1b04dffa0482,
closure summary11045B/SHA25652771217e4c4e38777c57434056b6bdc77a51130c53dade9ea34592fa816b726
and85-payload immutable cut. A preparation-only metadata probe exit1 for an
incorrect old artifact-map filename is retained; correcting only the external
DATA filename preceded all product commands and caused no Source/config/cache
change or product retry. Earlier failed native/SDK/review receipts remain
historical evidence. New native does not establish Wasm/browser, CPU metrics,
hearing/physical or Release acceptance; existing unchanged-owning-input
SDK174/protocol38, Type595 and Portal176 results remain separate.

This factual append changes only the declared plan after window closure.
Standing Task authority now covers the ordinary atomic own-branch commit
revision, exact-lease push, authentic new-head review, actual F1 fixed/F2
reasoned-reject dispositions, resolved conversation/live protection/conflict
checks and guarded squash. Those shipping operations remain pending here;
the old8955 review cannot clear new-head review debt. Full13/10 scheduling,
Creator consumer/browser/hearing and V1 API MINOR settlement remain distinct;
Documentation impact stays required at /core/modules/web-runtime-platform,
with no version/manifests/Build/snapshot allocation, Release/deploy or cleanup.


## Current-main ASSIGN / W1 source union (2026-10-13T00:18Z)

The previous D03-first shipping premise is superseded. Live W1 PR #2083
actually merged at 2026-10-12T23:58:08Z as
f11746f8e1c6b56e344bbe69701a51fb67ddc8c5. A fresh own fetch completed with
direct exit0 at00:08:21Z and binds that exact main. Its21-path change overlaps
seven of this Task's eight declared paths: CPP, Bridge, SDK, types, Native
test, SDK test and the current owning Module page. The complete relevant
89392B/SHA256335eaa0956324f8ac27a9074008075107e1658836a477f3492b8143246bbd4b5
upstream delta was read. All nine owning policy inputs remain byte-identical;
no new product decision, protocol or Task file is introduced.

Root's actual blocking ask reply (direct0, tool756412) admits SOURCE-only
integration in the existing isolated worktree onto exact f11746f8. Branch
feat/d03-assign-main-integration now has that source base and an empty staged diff;
Task-authored working changes remain exactly seven modified files plus this
Task-added plan. This source phase creates no new Task commit. The original
clean atomic D03 head7d44a1c26cde191a0dbc8d34963257f4f138c169, parent7df1af16
and treeb221c72a are retained by the task-local safety ref
refs/task-safety/task_d39374a2afe6/pre-w1-7d44-20261013T0013Z and the finite
original-source/patch cut. All prior raw receipts and the four actual review
replies/resolutions remain preserved. Neither old-head Bot eligibility nor
resolved old discussions supply review of a future integrated head.

Each relevant source file merges its existing D03 delta with current main.
External-byte git merge-file diagnostics naturally exited0 for each of the
seven files, with zero lexical conflict, before the owning source integration.
These diagnostics prove no product behavior. ASSIGN's complete SDK assignPad
and normalizePadAssignment functions remain byte-identical to7d44; its known
commit stop/preview ordering, SampleMutationResult/current-Truth publication,
precommit no-stop admission, nonnull retained SDK UUID/native null compatibility,
immutable caller command/revision receipt, captured target/material/owner,
real Host30s tail and exact owner recheck remain. No automatic resend/retry
or inference of commit success from current Truth is introduced.

W1's two live operations remain in the Native validator/dispatch and Bridge
registry. Its canonical opaque sequence validation, headered event/begin shape,
Facade live-control adapter, public types, bounded live-input window,
reserved release/cleanup behavior, headered Core/capture dual-ready ACK,
epoch/sequence accounting and replay contracts are retained. Seventeen complete
W1 SDK functions, including pump/submit, binding/capture, headered begin/event,
live query/control, stop/launch and close, equal current main byte-for-byte.
Their queue is inherited W1 behavior; this Task does not create a private
ASSIGN queue or replace Host-owned protocol admission or Core Truth.

All190 original D03 full Native test bodies are byte-identical to7d44. The
new W1 headered live-control test body equals current main in full. Static
current-main168/original-D03189/integrated190 direct call inventories are an
exact set union with unique registrations. Existing strict7-mode bodies,
completed callback observation, non-FIFO overlap/lease4108>4104, PCM/material,
Record, quota/deadline, reclaim/reload, Pattern successor and publication/
recovery far sides remain. Native PR #2070's complete replay-reset helper and
preceding comment are byte-identical in main, original D03 and this union,
including Filter/Pad gate neutrality and accepted Pattern callback evidence.
Static JavaScript test declarations are163/main,170/old and174/union; generated
or executed test totals on this new source are UNKNOWN. No assertion, timeout,
job count, registration, test or journey leg is deleted or weakened.

The original four actual findings were disposed before this source refresh:
F1 fixed with bounded ASSIGN-only pacing; F2 rejected because complete Runtime
fields are always constructed; F3 rejected because sleep lies outside the
budget-cap conditional; F4 rejected because current-Truth publication has
pre-prepare cancellation and pre-publication deadline guards. Running timeout
can still close trigger admission, seal the Session and mark Runtime failed
under the existing Sample failsafe. Known commit before snapshot.rejected is
not evidence of Bank publication and no zero-Runtime-side-effect claim is made.
The actual replies precede their resolutions; original authenticated review
38320745639/2 and distinct independent full-eight/four-finding reviews are
historical acceptance of7d44, not review of this uncommitted union.

Three metadata negatives are retained: the earlier empty-upstream-delta premise
failed because Native2070 was already present; its full owning-body proof
corrected the premise. The next guard failed when shared main advanced to W1;
that changed premise caused this admitted source phase. The integration script
then stopped at a FileNotFound baseline check because this declared plan is
Task-added and absent from main; seven source files and the safety ref were
already preserved, and only the saved exact plan bytes were restored. There
was no reset retry, product invocation or foreign restoration. All ten Git120000
entries were actual pristine links before integration and remain exact links;
only command-local core.symlinks=true was used. Fresh old-D03 head/index/status,
source bytes/mtimes/link targets and all five stashes remain exact.

### Remaining owning acceptance on the integrated source

Every new integrated product result is UNRUN. Old SDK174/protocol38/type595/
Portal176 and dev/ASAN3/3 results remain historical owning-input evidence. Root
will review the complete eight-file source diff and admit concrete stages
sequentially. No Node, TypeScript, Portal, CMake/CTest, install, rebuild, causal
mutation, commit, push, new review or merge is authorized by this source phase.

Prepared commands copy the actual original argv and recorded environments in
current-main-w1-source-integration-20261013T0013Z/
minimal-owning-verification-commands-v2.UNRUN.json (19785B/SHA256
4bc848a8fa191488c92ba814f16dfa6be4b813290461835e19d12faa1d830a4e).
They retain the following owning gates and the defects each catches:

- SDK syntax and whole runtime_session.test.mjs catch merged syntax, ASSIGN
  identity/typed publication/ownership/actual Host tail regressions and W1
  bounded-window/headered-ACK regressions; whole protocol.test.mjs catches
  wire registry/shape and actual admission-tail regressions. No focused filter
  or skipped test is proposed.
- Original TypeScript noEmit/Creator project/listFiles validates both additive
  public producer APIs against the real current owning project, with exact
  actual input inventory captured anew. It does not establish consumer UI.
- Whole scripts/docs-site.sh check validates the current owning Module facts,
  inherited W1 diagrams, derived identities, links and full static/type/test
  conjunction. Existing locked own dependencies are preserved; no install is
  proposed because Task manifests/lockfiles are unchanged.
- Original serial1 dev build/discovery/whole-three CTest, then native-ASAN's
  original three commands, rebuild the actual merged CPP/Bridge/control and
  Performance targets. Registrations remain host.web_control_runtime,
  host.web_realtime_session and host.web_performance_bridge. Original
  dev120s/ASAN360s and OneShot2s remain; actual source/object/binary/real-Bridge
  bindings and every far side must be observed. No standalone configure is
  proposed. Task-authored CMake/header/preset/tool inputs are unchanged; the
  refreshed base inherits31 changed inputs in the original332-path verification
  inventory, including Facade headers and source, Performance producer/tests
  and derived Product identity. Tools10 remain exact. Existing dev/ASAN Makefile
  dependency lists include the current version and web-runtime identity inputs,
  so the admitted original build must observe its standard regeneration and
  fresh dependent compilation. A concrete configuration defect must be reported
  before an extra command. These inherited identities are read, never allocated
  or edited by this Task.

A unique new-base actual-built PCM reduction and fresh-mtime restoration,
when required, needs its own concrete admission; the retained old-handler RED
and rebuilt restoration remain historical and unrelated causal mutants are
not rerun for counts. Ownership77/ledger15 and staged whole-eight/diff checks,
then a single Conventional Commit, own exact-lease push, authentic exact-head
review, actual new findings/dispositions, current protection/conflicts/complete
conversations and guarded squash remain pending, not authorized by this phase.
Full13/10 final clean committed-head lane plan is scheduling inventory only;
no complete lane, packaged Wasm/Web/browser, hearing/physical or consumer ASSIGN
acceptance is inferred. Independently owned Perform PR #2109 may ship while
this union is source-only; a later main advance requires a relevant-premise
check, not an invented strict-update or universal full-CI merge gate.

Root follow-up msg_481dbffaa69a records a separately owned inherited W1
capture-stop-handle gap: headered begin discards the bound tap handle and Core
stop does not itself stop that tap. Independent assessment and the minimal
SDK/type/test/Module follow-up are queued after D03 because their paths overlap.
This Task preserves W1 source, performs no repair or unrelated verification,
and makes no resolution or capture-consumer acceptance claim.

Version Management remains additive Web Runtime/SDK SemVer MINOR settlement
debt V1; no manifests/version identities are allocated. Documentation impact
remains required at /core/modules/web-runtime-platform and the owning page
retains both producers with current derived identities. No Product Build,
permanent snapshot, Release/deployment, Channel or cleanup is performed.


## 2026-10-13 — f117 integrated owning results and ordinary delivery

This section supersedes the last source-phase UNRUN status only for the eleven
original commands actually admitted and executed below. It preserves all93389B
of the preceding plan (SHA2568795c1ecbb6bb9b58754b56f72741442894c2e05d6df546a6360a40a61b46ce8),
all historical negatives and their exact-source receipts. Root's actual
blocking-ask replies admitted first3, Type, whole Portal and native6 separately;
the final native-next-stage reply3430B/SHA25630d55861608af28df93554e5326592e528d6be3a7448e3751f96cf443997415d
was received at02:10:39UTC. Root independently read and accepted each actual
cut, including complete native build/verbose/discovery/terminal records,
current332 inputs/tools and all124 payloads439156382B.

### Exact tested source and current-main disposition

The tested source was the uncommitted owning union on branch
`feat/d03-assign-main-integration`, HEAD/base
`f11746f8e1c6b56e344bbe69701a51fb67ddc8c5`, parent
`9534841424c04399bd0e94341ba96d38dd3dcbe4`, base tree
`a235bd866eb3f4ef85230688fee645e0c7e0dcb8`.
Frozen Source8 was1610630B, canonical aggregate SHA256
`c2a308908ca674c9c4115be77611510b8f2a6b29a287f5fc2e73a26ef6c23c7b`;
index479496B/SHA256576473c6e14e2b61b8cf60d8f6c1b023358beaf0407fb164e5f3207fd890cd4c,
7M plus the declared untracked plan, empty stage, all10 genuine120000 links.
All Source8 bytes/mtimes, index/status and native332/tool10 guards matched
before and after each admitted command. This factual plan append changes only
the plan; seven product/test/Portal files remain the exact tested bytes and
mtimes. Actual result identity must not be rebound to a later untested source.

Fresh own `git fetch origin main` naturally returned0 at02:11:55UTC. Actual
main was368045df5df8eac1af44e31a9a4e6f1f1133666e, parent25b8875478396df39ff0882c223c4c11bdf98806.
Perform PR #2109 is actually merged as25b887 and was already dispositioned;
new PR #2110 is actually merged as368045 and changes only its own plan and
the Creator accessibility focus-order expectation. Its complete3134B delta
SHA256441303fa05c51e3244ffa035e2ef8f146e5c764c557ab5863302f8c431783da2
was read; the first Pad assertion remains. Combined main advance has9 paths,
zero Source8/policy9 overlap. All nine actual main policy inputs match the
already read owning policies. Root independently confirmed this disposition
in msg_8be5df8f7110; f117 union remains the Task target without unrelated
rebase or test repetition. The initial metadata guard still expecting25b887
returned actual wrapper1 and is preserved separately; no Source or product
command ran after that guard until the actual368 premise was resolved.
Any C1 proof mentioned by PR #2110's historical plan is not adopted here as
current C1 evidence. These results describe the f117 owning union, not368 main
itself. Live PR #2107 still had the previously owned7d44 head at this checkpoint;
its old formal review cannot establish review eligibility for a new head.

### Eleven original commands: actual outcomes and covered risks

The exact argv/environment are frozen in `minimal-owning-verification-commands-v2.UNRUN.json`
(19785B/SHA2564bc848a8fa191488c92ba814f16dfa6be4b813290461835e19d12faa1d830a4e).
The filename is retained history; actual execution is established by separate
current raw receipts, not that prospective filename. All11 natural children
and their independently observed wrapper terminal exits were0, without retry,
new installs, standalone configuration, selector changes, signals or recorder
budgets. Original child-local environments/unsets and private temporary
parents were kept; every owned command group was empty at its checkpoint.

| Original command | Actual result | Owning risk exercised |
| --- | --- | --- |
| Pinned Node `--check packages/web-runtime-platform/web/runtime_session.mjs` |0|SDK syntax on the exact integrated producer.|
| Pinned Node `--test packages/web-runtime-platform/test/runtime_session.test.mjs` |178/178,0 fail/cancel/skip/todo|Full current SDK union, independent typed ASSIGN authority/identity/result validation, immutable receipt, actual protocol-tail admission and owner recheck, current APIs including W1.|
| Pinned Node `--test packages/web-runtime-platform/test/protocol.test.mjs` |38/38,0 fail/cancel/skip/todo|Full original protocol tail/callback/receipt machinery.|
| Original Node owning `typescript/bin/tsc --noEmit --project apps/creator-web/tsconfig.json --listFiles` |0;597 unique actual inputs|Current typed consumers and SDK surface; actual list includes411 node_modules inputs and two current N13 files beyond the historical595 list, verified against f117.|
| `/bin/bash scripts/docs-site.sh check` |0;177/177 tests|Whole current module documentation,52 docs,10 diagram sources/20 outputs,derived facts,release-docs,type check,changelog projections,static site and50 routes/internal links.|
| `cmake --build --preset dev --parallel 1 --target lmdj_web_control_runtime_tests lmdj_web_realtime_session_tests lmdj_web_performance_bridge_tests` |0|Actual standard regeneration, applicable current C++ compilation and real-Bridge linking.|
| Original exact3 `ctest --preset dev --show-only=json-v1 --no-tests=error -R ...` |0;3 registrations,120s each|Complete expected native ownership/labels/cwd/budget and actual Source/object/dep/link/binary binding.|
| Original exact3 `ctest --preset dev --parallel 1 --verbose --no-tests=error -R ...` |3/3;97.24s|Whole retained PCM/material/receipt/history/reopen/refusal/Record/recovery/Pattern/lease publication journeys.|
| Same original3-target serial build, `--preset asan` |0|Current address-sanitized production/testable runtime, all3 real Bridges and executable bindings.|
| Same exact3 JSON discovery, `--preset asan` |0;3 registrations,360s each|Complete owning ASAN registration and artifact provenance.|
| Same exact3 whole verbose test, `--preset asan` |3/3;222.25s|Same complete journeys under native ASAN, with no budget or assertion reduction.|

The unchanged exact3 regex is
`^(host\.web_control_runtime|host\.web_realtime_session|host\.web_performance_bridge)$`.
Dev actual executable times were94.49/0.84/1.90s; ASAN215.64/2.31/4.28s.
Both builds visibly Configured/Generated and compiled14 C++ rows, linking
4 static libraries plus3 executables per preset. The31 changed finite inputs
include non-C++ JS/types/product inputs; no claim that all31 were compiled.
Current production/testable Control Runtime, native test and all3 real Bridge
objects/deps/links/binaries are bound,18 actual artifacts archived per preset.
Internal executed native case count is UNKNOWN;191 complete bodies/190 direct
calls are static union facts, not a passed-case count. All190 old full bodies
plus the W1 body and current-main CPP/SDK functions remain preserved.

Every required far-side assertion remains: occupied Y-to-X stereo128 PCM and
exact Bank generation; complete retained material digest/length/bytes and
Truth; Assign/Undo/Redo/close/reopen; current-Truth replay after later edits;
same Asset/D16/native null; independent missing/foreign/stale/recording-owner
precommit refusal without stopping the live voice; postcommit quota/deadline/
Bank-admission/ACK distinctions, fresh-owner recovery, Bridge response-before-
event/lease cancellation-generation, overlap/nonFIFO/reclaim/reload/Pattern
successor. Strict7-mode loops, completed callback #2004, OneShot2s and kernel
lease4108>4104 retain their original bodies and budgets. No private protocol,
queue, Host-owned Truth, automatic command retry/resend or inferred durable
success is added. Native null compatibility remains; new typed assetId is a
nonnull UUID. The later Creator consumer owns explicit target A01-D16,
occupied-target confirmation and cancellation without mutation; it is not
rendered by this producer.

### Durable actual receipts and retained limitations

Under the external D03 evidence root, immutable current cuts are:

- `current-main-w1-first3-node-20261013T0049Z/first3-node-actual-report.md`,
  7524B/SHA2561be66718154e2fd8d17e3bb7883b8ce5846037b5f1de8244f9773e203934bd40;
  25payloads109214B, whole SDK178 and protocol38 actual stdout fully read.
- `current-main-w1-owner-type-20261013T0103Z/original-owning-type-actual-report.md`,
  6749B/SHA25664e21ba222ec6d55316b237a5f8db49f3251e1cd82bed7c1206acae0201a6363;
  18payloads753878B, all597 actual listed inputs and original tool/config identities.
- `current-main-w1-whole-portal-20261013T0115Z/whole-Portal-actual-report.md`,
  7632B/SHA256777ebb4b435a75da3117639bcfac259e0c2b72c07e880659fce26313dc9774df;
  18payloads466911B, full stdout/stderr and223 bounded inputs. All7 localStorage
  ExperimentalWarnings are retained; whole natural exit is0. Actual existing
  npm11.19.0 differs from declared npm@10.9.3 and is reported, not relabeled.
- `current-main-w1-native-original6-20261013T0135Z/native-original6-actual-report.md`,
  9330B/SHA2566322bd90ddcc266a9eef257bf4581e584cf7ed9b901fa6abcc2a8672519e95c2;
  124payloads439156382B. Manifest26276B/SHA2565b3230e5b2e1724f8e4790d791fd10bca5c79e3402fcf10429d308f8a1323341,
  complete raw6 command receipts/logs and actual36 artifacts. Root acceptance
  1744B/SHA256be2f0bf88438513cc134ad347f3498c0a7eed9939499812b6e40f7386530df9e.

Root's explicit minimization disposition adds no new-base uniquePCM mutant
as an ordinary shipping prerequisite: rebuilt current full owning journeys
passed, old complete bodies/implementation were independently Source-reviewed,
and no new red gate/cause requires mutation diagnosis. New-base causal remains
UNRUN; historical7d44 causal RED/restoration remain old-source evidence and
cannot be presented as current causal PASS. No original PCM assertion or
budget is weakened. Historical A1 typed-authority and A5 bypass reds and every
failed native/helper/review stage stay retained, without unrelated mutant
repetition for counts.

Fresh post-native old-D03/stash guard6532B/SHA256c9c2c1fea8a93f27233fa532de4f44740ace77591cb909a17445737f7ebffc54
matched complete prior custody: old head8769907/index0f815,all8 bytes/mtimes,
7M+plan/empty stage,10 links and all5 stash OIDs. No old/source/index/build/
stash or Root checkout mutation/cleanup occurred. Root live checkout state
remains UNKNOWN/non-gating. First3 metadata assembly KeyError is retained and
corrected externally without product repetition; Type's two additional actual
inputs are identified separately from the prospective595 list.

Source-append/stage/ownership/commit/push/new-head review/protection/conversation
results are later checkpoints, never inferred from these11 exits. Ownership
must run AFTER staging the added plan, using original `ci_change_scope_test.py`
and `ci_pitfall_ledger_test.py`, with actual counts and direct exits. Pitfall
impact: none for the product change; strict product tests express its invariant,
and no qualifying shared-ledger process repair belongs to these8 paths.
An actual qualifying new ledger need would require a declared scope change.
Canonical final committed-head complete13/10 ownership plan remains for Root
scheduling; all full lanes are UNRUN. W1 queued/inflight P2 and capture ownership,
N13/Numeric, S6/BPM/R-H/D5, Creator ASSIGN/Wasm/browser, physical/hearing and
broader retained Issues remain separate unclosed acceptance, not accepted risk
or this producer's PASS. Closing those gaps requires their actual owning
Source and complete corresponding runtime/browser/device/operator evidence.

Version impact remains additive Web Runtime/SDK API MINOR settlement debt V1;
no version identity, manifest or Product Build is allocated. Documentation
impact: required; affected route `/core/modules/web-runtime-platform` was
updated in the exact tested owning page. Portal facts derived the existing
2.0.95.0 andf117 identity; a local check creates no permanent snapshot.
This Task grants no Release/deployment/cleanup/root/sudo/global/foreign-process
change. Every new committed head needs its actual independent review and live
protection/conflict/conversation evidence before guarded squash.
