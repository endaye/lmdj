# Recording Pattern switches: Host producer and existing SDK

Parent: #2112 / #2233, S3 C3. This Task supplies the Host producer; Creator
controls and packaged/physical acceptance remain C4. CI controls, release,
Runtime deployment, Channel promotion and cleanup are outside this Task.

## Integration hold (2026-10-18 owner instruction)

Main is frozen for the current release. Continue development, owning checks,
atomic verified commits, push and Draft PRs in one Git stack, with C3 as its
root and C4/successors based on the preceding feature head. Do not merge or
enable auto-merge, even if review/checks pass. Only an explicit owner notice
ending this freeze revokes the hold. The nine earlier non-CI merges, through
#2365/aa476632, precede this instruction; C3 remains uncommitted at the hold.
No release/deployment/Channel/cleanup action is added by the stack instruction.

## Premises and dependency

Refreshed integration main is `616b1db47d4331e534afd572ff708ed85d55fd61`.
Live #2233 is OPEN with no comments; the only open related PR is #2365, the
C2c producer dependency rather than an existing Host successor. This isolated
worktree starts at its verified head `89866ce29fbb30935d7cf7113a09ec3c69a83e45`.
Its review/merge is pending at Task start. Re-resolve its actual merge and
restack this Task before shipping; a dependency head is not evidence of main
integration. Governance bytes match the already-read current main rules.

Resumption refresh: main is now `3792b36951ff4d63d6b8fbe2a1c4f965088983e7`.
C2c actually landed as #2365/aa476632 with identical producer files; #2371
changes CI runner admission only, without delivering a Host successor or
changing the read governance. No related open successor PR exists. Keep the
original C2c dependency head explicit until this verified Task is restacked;
the owner hold above prevents shipping from progressing into merge.

Positive controls: selected Native SNAP publication, retained move-only C1
leases/actual observations, C2b exact durable segment replay, C2c two-record
input/segment/cutoff ordering, original S7 caller/physical ownership, and the
existing SDK request/strict decoders. Do not recreate these capabilities.

The missing source sites at this base are:

- `pattern.transport.switch` refuses every recording request. Its wire is
  already `{pattern_id, request_id, snap?}` and its SDK method already exists.
  `request_id` remains advisory; null activation is actual current-target
  withdrawal, never an asynchronous preparation acknowledgment.
- The Host retains only the latest queued/predecessor authority, sufficient
  for playing selection but insufficient for every recording S through I/O
  acknowledgment. The Native lease, not current telemetry, is the evidence.
- The Host's foreign-publication check also sees its own controller overlay.
  Use the port's exact remembered ownership when the controller withdraws that
  overlay; do not classify every same-Pattern publication as owned.
- Service, close publication and exceptional retirement do not yet account for
  retained switch leases. I/O owner disposition must progress before Native
  quiescence, which scans the very pins the Host must release.

Before implementing, correct one stale D0 premise using current settled
authority: `SequenceJournal::begin` and `begin_performance_draft_locked` both
reject a different active recording kind; `Application::performance_begin`
also rejects an active Sequence session. The approved 2026-10-10 switch
decision adds ordinary Perform Launch without requiring Performance recording;
it does not authorize simultaneous recording Journals. Prove mutual exclusion
in both directions, retain existing Performance-record Launch/clock/event
semantics, and correct D0's hypothetical shared co-record publication. Ordinary
Perform Launch during Pattern recording is the same C3 producer as Sequence.
No new generic Native publisher or second preparation protocol is required for
an inadmissible co-record state. This resolves implementation premises and
preserves the existing concurrency rule rather than deciding a new one.

## Declared files

One reviewable Task, fourteen exact files:

- `packages/web-runtime-platform/src/control_runtime.cpp`;
- `packages/web-runtime-platform/test/control_runtime_test.cpp`;
- `packages/web-runtime-platform/web/runtime_types.d.ts`;
- `packages/web-runtime-platform/test/runtime_session.test.mjs`;
- `apps/docs-site/docs/platform/web-runtime.mdx`;
- `apps/docs-site/diagrams/web-runtime-platform.architecture.json`;
- `apps/docs-site/static/diagrams/web-runtime-platform.svg`;
- `apps/docs-site/static/diagrams/web-runtime-platform.html`;
- `apps/docs-site/docs/core/modules/application-facade.mdx`;
- `apps/docs-site/diagrams/application-facade.architecture.json`;
- `apps/docs-site/static/diagrams/application-facade.svg`;
- `apps/docs-site/static/diagrams/application-facade.html`;
- `docs/design/2026-10-18-recording-pattern-switch-segments.md`;
- `docs/plans/2026-10-18-recording-switch-host.md`.

No wildcard, wire/Journal format, existing public port vtable/layout, new test binary,
CI mechanism, coverage exclusion, deadline or capacity increase is declared.

## Implementation and ownership

Keep at most two Host cells holding the actual Native lease and C2c ticket.
Reserve before synchronous Facade Snapshot preparation; preparation, retained
Native publication and bind stay in one serialized control turn. Abandon only
unbound refusal. A successful publication remains owned through final Native
observation plus exact durable ACK (or real final cancellation), then reset
the pin before consuming its Core ticket. Third-capacity/material refusal is
before Native effect. Keep existing queued-repeat, replacement, claimed
predecessor/current-target withdrawal and selected SNAP behavior within that
bounded capacity.

Copy each exact Native observation before control drives inputs/segments and
again after I/O completion. Latest playing selection remains independently
driven by strong Native observation. Continue servicing the lease cells after
the latest pending switch disappears; include them in pending/shutdown
accounting. Retain unknown work and original input/caller identities. Record-
off republishes the actual terminal current Pattern. Real failed authoring
remains failed; actual worker disposition, original consumers, physical holds,
pin release and final Native quiescence remain separate obligations.

Hosts prepare through Application Facade and never parse Project bundles or
resolve a Product Pattern Slot themselves. No lease/Engine/PCM enters I/O.
Original COUNT-IN A/S0/e1/e2 is not rewritten to the later ordinary Pattern.
Creator remains gated until its own C4 Task and complete journeys.

## Verification

Lowest owning producer proof: existing native `host.web_control_runtime`
binary/registration, with actual Engine, retained publication, production
controller and real worker/Store/Journal. Cover A→B→A with acknowledged return
material and complete Truth/reopen; two actual boundaries in one callback
while I/O is held; third refusal before effect; original pre/at/post-S input,
source physical release; selected replacement/withdrawal; own overlay versus
foreign publication; actual prompt F, S=F cancellation and actual terminal
republish; exact unknown reply/retry; original count-in evidence and real
failed-resource retirement. Legacy metadata and sequenced Native input proofs
remain explicitly distinct. Preserve every far-side assertion and budget.

Use the existing SDK runtime-session suite for unchanged request payload,
selected SNAP, recording/current/pending observations and original caller
ownership. Prove the existing two recording kinds' mutual refusal and the
positive unchanged Performance-record Launch route. Build the changed Wasm
producer with the pinned toolchain and exercise its owning Host proof;
Creator packaged consumer/device acceptance remains C4/#1221, not supplied
by C++ or DTO tests. Run affected C2c component/stress, dependency/ownership,
official diagram generation, complete Portal check, and final PR declaration.

A rebuilt omitted observation/input-order barrier must fail a real premature
write/missing source-target assertion. Restore saved working producer bytes
with fresh mtime, confirm compilation, and rerun the unchanged owning tests.
Any new registration/gate requires its concrete caught defect and no reduction
of existing invariants. Complete unexecuted candidate/sanitizer/platform lanes
remain explicitly unverified; selected full ownership is not execution proof.

## Version Management

Version impact: Web Runtime Platform additive feature MINOR debt in #2237.
The existing public SDK/wire shape is retained. Prior C2c Facade MINOR and
Native MINOR debts remain owned by their actual changes; do not allocate them
twice or lower a higher domain impact. No Product/Assembly/manifest allocation
or immutable snapshot is part of this Task.

## Documentation impact

Documentation impact: required. Update `/platform/web-runtime/` and
`/core/modules/application-facade/`, both owning source diagrams and official
generated outputs for Host retention, actual ACK/resource ownership, the
existing recording mutual exclusion and pending Creator acceptance. Correct
the D0 implementation premise in the same Task. No source-only proof is
described as Creator/device acceptance.

## Initial development evidence (historical)

C2c dependency is now actually merged as #2365 /
`aa476632440fd76bb1e99776725a719c75b4378d`. All fourteen landed files match
89866ce2; its original current-head review and complete coverage pass. The
C3 worktree remains based on the identical verified producer commit until
this Task is complete and can be restacked as one verified commit.

The first Host implementation owns two actual leases, copies observations
through durable/resource completion, reserves before the synchronous Facade
Snapshot, and includes retained switches in service/lifecycle accounting.
The existing recording-refusal journey now positively switches an empty take
to B, keeps recording, completes real Record-off/Stop and preserves whole
Truth; its original stopped-refusal leg remains. The complete original
`host.web_control_runtime` registration passes (75.33s). This initial proof
does not yet supply the declared multi-switch/input/fault/reopen journeys,
SDK/Wasm/Portal checks, review or complete C3/C4 acceptance.

## Host regression findings and dispositions

The A→B→A producer journey exposed a claimed source overlay. General Native
cancellation truthfully keeps its audio-local slot until the old Bar, so using
that cancellation in switch reservation could accept a Beat successor that
waited behind the old Bar. The Host port now scopes reservation to Native's
atomic **unclaimed** cancellation. A claimed overlay returns the public busy
reason before Snapshot/publication; the test proves no publication/cancellation
effect, drives the actual overlay/Journal ACK, retries, and proves return A's
acknowledged note really plays. Stop retains its existing claimed cancellation.
Only the four literal producer busy reasons are returned at this operation;
the generic storage sanitizer stays unchanged.

The S=F Stop journey exposed a separate close republication still waiting for
a Bar while transport was stopped. Close now uses the existing immediate
publication capability when stopped, with the actual current Pattern. Playing
Record-off retains its existing policy. The test checks actual Native queue
consumption on the following callback, not just the Host's accepted flag.

Normal count-in caller evidence and typed input completion are independent.
The held writer refuses count-in consumption while segment/close is unknown;
after real close, normal e1/e2 consumption does not spend the original release
ticket, which is separately inspected/consumed. Failed owner retirement keeps
its stricter real disposition/consumer/physical/quiescence boundary. No new
recording concurrency or all-owners gate was inferred from the normal DTO.

## Verification receipts

The complete existing `host.web_control_runtime` registration passes with all
six new producer journeys and unchanged older cases (80.83s). New journeys
cover acknowledged A→B→A/audio/reopen, B/C in one callback with a real held
append and post-write reply loss, third pre-effect refusal and real physical
releases, original COUNT-IN e1/e2 with prompt F while the writer is held,
both recording-kind refusals, current-target withdrawal/repeat, S=F absence,
and genuine interrupted-rebase failure through real owner_lost disposition,
Native pin release/quiescence and unchanged Truth/reopen. Full vectors and
whole Project JSON are compared, including the empty B revision fact.

The rebuilt latest-selection-only Host mutation fails with CTest exit 8 at
`test_recording_switch_host_keeps_both_native_facts_behind_real_io`, on the
far-side wait for B's real `admission-switch` append entry (line 14387 in this
source). Latest C was actually applied; omitting B's retained observation
prevents its durable transition. Logs and exit receipt remain under
`/tmp/lmdj-2233-c3-latest-only-red-*`. Saved production bytes were restored
with a strictly newer mtime than the mutant object, and compilation of the
restored producer was explicitly confirmed. The restored unchanged owning selection
passes as recorded below. No watchdog was widened.

The restored unchanged owning selection passes 3/3 (89.21s): Core component
2.26s, original 48-segment stress 5.22s, complete Host 81.73s. SDK passes all
400 tests, including both new recording selection/refusal cases. Dependency
verification passes. Official diagrams and the complete Portal initially pass
(179 tests, production build, 50 routes/links). A final documentation check
also preserves the unrelated S6 raw-PCM/device acceptance debt rather than
clearing it from the new S3 producer evidence.

The entire fourteen-file WIP was preserved as stash
`99883da34a3f731eb9a5e8086e0058b50a2be872` and
`refs/codex/2112-c3-wip-20261018`, with a separate original-base reference.
It was safely restacked from the equivalent C2c review head onto actual main
`3792b36951ff4d63d6b8fbe2a1c4f965088983e7`; every file's SHA-256 was compared
before/after and all bytes matched. No incomplete implementation commit,
merge, main mutation or cleanup occurred. Final docs/Wasm/ownership and Draft
PR review are still to be recorded before declaring this Task verified.

## Queued Record-off regression

The old ordinary `pattern.transport.request` guard treated both Record-on and
Record-off as a new admission. After recording switches became admissible,
this incorrectly refused Record-off while the successor was queued. The
expanded S=F journey proves the real rejection (exit 8, line 14552;
`/tmp/lmdj-2233-c3-record-off-pending-red-*`) before changing the guard. Only
Record-on retains the pending-switch refusal; Record-off reaches the existing
Native fence and ordered C2c closure. Both Stop and Record-off must cancel a
switch at F=S with no target Truth, then finish their distinct playing/stopped
republication and actual Stop/reopen legs. The original begin-refusal journey
remains unchanged.

The first complete Web Host proof passed on the preceding producer bytes
(SHA-256 `ad8afe32a8007ebc1230471dd824807b681c8ec6435020f187c2b6ec03a6ba04`):
31 audio conformance cases, byte-identical clean product builds, owning native
Host suites and Chromium 41 passed/1 skipped. WebKit reported the actual
`opfsSyncAccessHandle`/`opfsWritableReplace` capability limitation: 2 passed,
15 skipped, not full WebKit acceptance. MacBook Pro Speakers were observed by
the existing wrapper. The retained receipt marks this as before the queued
Record-off correction; it is not final-head proof. Final owning verification
must include the corrected guard and expanded journey before commit.

## Retained replay and exact Host boundaries

The ordinary Record-off correction now passes the entire Host registration
(82.64s). A further completed-command retry after a later C selection exposed
the same old begin guard intercepting Core replay validation (exit 8 at the
then-current line 14584; retained logs
`/tmp/lmdj-2233-c3-retained-replay-red-*`). The guard now excludes a retained
CommandId while delegating the complete payload to Core. Exact old Record-off
returns `replayed` without another publication; changing the same ID's epoch
is refused and creates no Native epoch-3 receipt before the real Stop. This
lookup grants no new admission authority.

The expanded native Host registration then passed (83.90s). It retains both
the one-callback B/C history case and an exact-S input variant: Native consumes
C and its original input at S while B's real worker append is held. Post-S
input remains a separate variant. Complete C event vectors/reopen, physical
releases, empty B revision, real append reply loss and all original budgets
remain. A same-Pattern foreign immutable test publication is refused by exact
generation ownership before effect, then canceled by the actual Stop; whole
Truth/reopen remains unchanged. It deliberately does not borrow the runtime's
retained writer with a second Facade. The production Host still prepares
Snapshots only through its own Facade.

The final Portal and complete Wasm Host proof on the corrected producer
are recorded in the shipping receipt below; ownership/body checks follow. The parent-main freeze is unchanged. Submit this as the Draft stack
root; current-head independent review is pending while Draft (the trusted
review target excludes Draft/non-main targets). No eligible review, waiver or
merge authority is claimed; run the normal exact-head review procedure after
the owner ends the hold and each layer is ready/targets main.

## Terminal publication from the independent count-in polling path

A seven-journey reduction now drives the close solely through count-in inspect,
without any ordinary selection inspect/service after B actually applies. The
original e1/e2 still correctly name A/S0, but the old Host cached selection
republished A after a successful close. The real pending-Pattern assertion
fails at then-current line 14731, exit 8; logs and exit are retained under
`/tmp/lmdj-2233-c3-terminal-pattern-red-*`. The initial misplaced test fixture
failed compilation separately and is not that product reduction.

At publication, F has settled the retained switches. The Host now reads the
actual Native current Pattern, retargets its selection and prepares that view
through its own Facade; no-current remains pending rather than inventing a
view. This is independent of which short continuation endpoint finishes I/O.
The new seventh journey proves pending/current B, unchanged original A/S0
receipts, actual caller consumption, real Stop and whole Truth/reopen. The
complete unchanged Host registration passes after the fix (86.43s).

The preceding complete Wasm proof also passed on producer
`1060d9ca49e70d60269aaac415efb76a014bbb5c21bb2e9ca4be77950d90519d`;
that receipt predates this terminal-publication correction and is retained as
such. The shipping proof below must bind the corrected producer. No merge,
auto-merge, release, Runtime delivery, Channel or Git cleanup has occurred.

## Shipping verification

Final producer SHA-256:
`159fdf908bd29764de4fdb67be3fcb88280c7cba0381427196ba82d3e6113c87`.
Every one of the fourteen frozen Task input files matched its saved SHA-256
through the completed proof. Subsequent plan edits record receipts only.

- Complete `scripts/web-runtime-host.sh proof` exits 0 on these producer bytes:
  31 audio conformance tests; two byte-identical clean product builds; all
  three native Host registrations (the complete control-runtime suite 87.81s);
  Chromium packaged Host 41 passed/1 existing skip. The exact locked toolchain
  and real MacBook Pro Speakers observation were retained by the normal entry.
- WebKit truthfully reports unavailable OPFS sync/replace capabilities:
  2 passed/15 existing skips, not complete WebKit/device acceptance. No skip
  or budget was introduced for this Task.
- Standalone complete final native Host 86.43s passes all seven new journeys
  and their variants plus the original suite. Core switch component/stress
  remain unchanged and passed 2.26s/5.22s in the restored owning selection.
- SDK runtime-session 400/400, dependency verification, official diagrams and
  final complete Portal 179 tests/production build/50 routes/links all pass.
  Original reduction/failure logs and pre-fix complete proof receipts remain
  separately bound to their historical inputs; no old result is relabeled.

No new test binary or Core production source requires another coverage
inventory/complete coverage run in C3. Candidate/full sanitizer and other
platform lanes, Creator C4 packaged multi-switch journeys, independent Draft
review and physical/listening acceptance remain explicitly unverified.

The verified Task is one Conventional Commit of its fourteen declared files,
then push and Draft PR as the stack root. Main remains frozen; subsequent
Tasks branch from this head and target the preceding feature branch. Review,
retargeting and any integration require the owner to end the hold first.
No merge, auto-merge, release, Runtime deploy, Channel or Git cleanup.

Staged final path admission passes all 76 ownership tests (8.68s). Exact PR
closing-directive lint and declaration-only Portal impact checks pass. The
canonical automatic plan selects full mode/all thirteen lanes as ownership,
not as execution receipts. The refreshed integration main remains 3792b369;
all seven governing files match the read Task rules and no Host successor PR
exists. Commit/push/Draft PR are authorized; the explicit merge hold remains.
