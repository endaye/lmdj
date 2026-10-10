# Pattern switch Core prerequisite

## Authority and current premises

Implementation tracker: [Core prerequisite #1983](https://github.com/endaye/lmdj/issues/1983).

This Task supplies the native prerequisite of S1 in
[Pattern switching and count-in](2026-10-10-pattern-switch-and-count-in.md).
The owner approved playing switching and the P10-D22 queue rule in
[the decision](../prd/decisions/2026-10-10-pattern-switch-while-playing.md),
PR #1971 merged at `c673399178197565fb68d15be79aa61e62dd913b`.
The implementation plan PR #1975 merged at
`e99eda3665b4ebee4781aa00266ed3ef929dc79d`.
Issue #1958 is closed as a product decision; neither PR implements this native
seam. Live open PRs #1929/#1936 do not implement it.

Fresh `origin/main` and isolated worktree base:
`4dde8e5e6b511c3ae2bd9c310f607f7d6148d2dc` (2026-10-10).
Branch: `feat/pattern-switch-core-prerequisite`.
The latest #1970 changes Creator reconciliation, not the native sources.
Before the first native rebuild, refreshed `origin/main` and fast-forwarded
this branch to `785d36db27dc44fde7cceb4f6cb6da0956a795e1` (#1982).
Its two documentation files reconcile existing acceptance; native/Facade
product sources are unchanged and no duplicate prerequisite was delivered.

Premises were re-resolved before implementation:

| Premise | Exact-base disposition |
| --- | --- |
| Audio-owned B and queued C already exist | Delivered: Engine Q/A mailboxes and fixed four-slot pool; reuse their ownership. |
| Transport can cut off both B/C | Outstanding: submit allows one exact generation and refuses the other at `realtime_engine.cpp:973–994`. |
| Claimed future B implies C next Bar | Outstanding for direct native publication: the future-frame branch reuses B's frame, and only a past-frame branch defers. Existing Performance computes its own following Bar. |
| Last transport receipt still identifies current generation | False after external switches. A stable B-current/C-pending command needs current B; refreshing generation alone does not repair a switch crossing Journal preparation. |
| Record can open on an actual cutoff target after that crossing | Outstanding: preparation is before submit and strict codec requires the exact receipt Pattern/generation. Preserve that guard. |
| No-info legacy ports need a new behavior | Already settled by #1403: retain default fallback and deterministic mismatch/error semantics. |

Independent source evidence and exact hashes are retained outside the worktree
in `playing-pattern-switch-bar-s1/independent-technical-design/` under the
parent's stopped-pattern-reselection evidence root. This Task adds no Host or
Project I/O implementation, persisted Contract, active-recording multi-switch,
count-in, compiler policy or clock-rounding change.

## T1 — bounded cutoff, claimed timing and receipt-bound opening

One reviewable Task and one later Conventional Commit. Declared files (14):

1. `packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp`
2. `packages/audio-runtime/src/realtime_engine.cpp`
3. `packages/application-facade/include/lmdj/facade/pattern_transport_controller.hpp`
4. `packages/application-facade/src/pattern_transport_controller.hpp`
5. `packages/application-facade/src/pattern_transport_controller_factory.cpp`
6. `packages/application-facade/src/pattern_transport_controller.cpp`
7. `packages/application-facade/src/pattern_admission_controller.hpp`
8. `packages/application-facade/src/pattern_admission_controller.cpp`
9. `tests/core/audio/realtime_engine_test.cpp`
10. `tests/core/facade/pattern_transport_controller_test.cpp`
11. `apps/docs-site/docs/core/modules/audio-runtime.mdx`
12. `apps/docs-site/docs/core/modules/application-facade.mdx`
13. `docs/plans/2026-10-10-pattern-switch-core-prerequisite.md`
14. `.agents/pitfalls/revert-proof-rebuild-skipped.md`

The Host S1 Task separately owns its producer, SDK, Host regression tests and
original plan update, and depends on this prerequisite. Declared scope expands
only after a concrete causal need is recorded and reported.

### Public interface

- `PatternTransportObservation`: exact current generation/Pattern/origin and a
  fixed array of optional `PatternReplacementAuthority` values in audio-owned
  then queued order; current is excluded and duplicates removed.
  `outstanding_cancellation` names a control-canceled token-zero audio-local
  slot until retirement; it is not a playable pending target. All outstanding
  authority values total at most two. Tagged origin/generation handoff fails
  closed rather than joining fresh current with a stale transport origin.
- `RealtimeEngine::pattern_transport_observation()`: returns an optional
  stable observation from live slot/token ownership, not latest-only telemetry.
  A raced observation is unavailable rather than guessed.
- `RealtimeEngine::publish_pattern_switch_view(view, replacement_authority)`:
  opt-in claim-safe 1-BAR publication, returns the actual generation/frame.
  General publication/overlay semantics remain separate.
- Transport command retains `pending_switch` and adds optional
  `pending_switch_predecessor`; every pending slot/token must be named exactly.
  Receipt retains old fields and adds bounded `switch_outcomes` with authority,
  decision and optional actual applied frame for each named publication.
- Facade public/internal audio port adds default `observe_transport()` and
  `supports_receipt_bound_opening()`; factory bridge forwards both. Defaults
  preserve old hosts; the new Host explicitly opts in and supplies live state.

### Native ownership and timing

Keep runtime generation, epoch, exact predecessor and all authority guards.
No initial-zero predecessor or unnamed Q/A publication is admitted. Fixed
command/receipt queue capacities stay one; no audio allocation, lock, mutable
Project state or unbounded queue is introduced. A named applied predecessor
that becomes retiring still has an applied outcome; it is not canceled/freed
as though it had never sounded. Applied frame evidence is audio-owned and
tagged by the exact immutable publication generation; neither reclaimable state
nor a default/previous slot frame proves that the current generation applied.
A control-canceled claim crossing its frame before a queued cutoff is consumed
remains canceled, including after reuse of a previously applied slot. Hold
receipt evidence until exact ack and count
cancellation once, including control-canceled audio-local entries.

Unclaimed replacement preserves its boundary. A successor to an audio-owned
publication uses a strictly following Bar, even when its predecessor's frame
is still future. Recompute on Q→A CAS races. The callback must consume an
already queued successor in time if one callback crosses its apply boundary;
no invented callback-size restriction substitutes for the returned frame.

### Record opening and truthful failure state

Only the explicitly capable, nonrecording Host uses receipt-bound opening.
A stable exact observation with no pending publication can retain the ordinary
prepare-before-submit path, because all publications share its serialized
control owner. A pending publication requires read-only owner/revision/Pattern
preflight, native command acceptance, then Journal begin/prepare/activation
against the actual retained receipt. An active recording retains its single-
switch settlement behavior and never silently retargets.

A known preflight conflict performs no audio submit or durable mutation. A late
IO failure after accepted cutoff exposes pending/error with recording false;
it preserves the actual canceled B/C outcomes, receipt and partial owned
Journal. It is not a no-effect synchronous refusal. This technical failure
ordering is explicitly accepted for the new capability; future writes cannot
be promised by a read-only preflight. Do not republish canceled switches or
ack early to hide it.

Revalidate the original expected revision; never substitute a newer revision.
Foreign, incompatible or differently targeted existing Journals are retained,
not deleted/relabelled. On uncertain IO, validate the actual owned durable step
and use exact codec replay rules; never overwrite a damaged suffix. Retry the
same receipt/epoch and partial progress. Preflight checks an already present
Journal's bars/fingerprint against the loaded current Pattern before any audio
submission, matching the late owned-step compatibility check. Only a matching
empty prebegun header is eligible: existing legacy input/capture/flush prefixes
are retained and refused without audio submit. Post-cutoff unknown-response
retry still validates this operation's actual prepare identity and receipt;
its own partial admission is not incorrectly rejected as preexisting work. Default no-info
ports retain their existing deterministic failure. Default `fence_timeout_ms` is 5000 ms; the
coordinator aggregate `10` is `first_watermark`. Capture one deadline for the
new opening and preserve it across late preparation and retries. The defaulted
internal Clock is shared by actual request capture and admission owner. Its real
coordinator fixture crosses receipt delay, unknown prepare response, exact retry
and the 4999/5000 ms boundary; no public Host test-clock API is added.

## Verification and acceptance

Lowest-tier rebuilt artifacts: `audio.realtime_engine` and
`facade.pattern_transport_controller`; existing `facade.pattern_transport` and
`facade.performance_engine_adapter` are compatibility companions.

Each new fact has a distinct failure assertion and, after the parent's native
window opens, a freshly rebuilt RED/mutation and GREEN receipt:

1. B audio-owned plus C queued: Stop accepts both, cancels both at actual cutoff,
   current A survives, no revival, no audio allocation, counters conserved.
2. Omitting either authority refuses with no effect or epoch spend.
3. Wrong second id/frame/generation and duplicates refuse independently.
4. B applied/C pending uses exact current B and preserves it for Stop/fence.
5. Cutoff racing apply records actual applied frames, including retiring B.
6. Early claim well before B: C returns next Bar and audio applies both without
   further control service; Q→A CAS race and multi-boundary callback companion.
7. Record opening snapshot crossed by real Engine apply: Journal/fence and
   persisted input name receipt B; A remains unchanged.
8. Known revision/owner failure submits no audio and preserves pending switches.
9. Late begin failure retains real cutoff outcomes, pending/error, recording
   false and no ack for that pending command; actual storage failure is not a fake receipt.
10. Partial prepare/activate/uncertain-IO retries complete exact steps once;
    wrong existing owner/Pattern and late expected-revision conflict stay honest.
11. One original deadline survives receipt wait and retries (fake monotone clock,
    unchanged configured limits); no new window is created by late prepare.
12. Legacy single-authority, zero predecessor, own-current, receipt replay,
    no-current-info error and active-recording settlement guards still pass.

Keep complete Record → input → Record-off → persisted Project far-side checks.
The gate defect is an uncut pending successor, a returned frame not honored by
audio, or a Journal whose target does not match its actual admission receipt.
No coverage, timeout, tier, stress budget or owned lane is reduced.

During the parent's frozen full/stress Asan run this agent may edit production
and prepare tests, but runs no native build/heavy/browser checks and makes no
commit/push. After the parent releases the window, personally rebuild all
Task tests, retain actual statuses and assertion lines, run the applicable
Portal check and owned lanes, then ship under `issue-done` and current-head
review. An unexecuted proof remains an explicit gap; neither static source nor
another architecture's benchmark supplies a pass key.

### Executed native verification (2026-10-10)

At refreshed source base `785d36db27dc44fde7cceb4f6cb6da0956a795e1`, personally
configured Debug and rebuilt these five targets with the dev preset and original
CTest bounds: `lmdj_realtime_engine_tests`,
`lmdj_pattern_transport_controller_tests`, `lmdj_pattern_transport_tests`,
`lmdj_pattern_admission_tests`, `lmdj_facade_performance_engine_adapter_tests`.
The five named CTest entries passed. The first frozen source run took 13.678 s;
after isolating the owner preflight fixture, the five entries passed again in
13.428 s. Compile-only fixture mistakes are retained as failed setup logs and
are not behavioral RED evidence.

Twenty distinct production-cause mutations were detected by assertions inside
the corresponding facts, each after a successful fresh rebuild; each restore
also compiled the changed translation unit and passed its original CTest entry.
They cover bounded admission, second authority frame/id/generation, canceled
pending ownership, bound origin, claimed following Bar, same-callback successor,
retiring applied outcome, the legacy zero predecessor, receipt-bound target,
known revision and foreign owner, retained late-IO command ownership, owned
partial replay, recording only after ack, preflight fingerprint/bars/legacy
prefix and the original deadline. Known revision was re-proven after isolating
its fixture; neither its owner nor revision rejection can be masked by a
cross-Pattern guard. Both real pending generations stay outstanding, and the
complete existing Journal remains unchanged on the refused path.

Receipts retain exact source/test hashes, artifact hashes/mtimes, actual build
and test exits, logs and discriminating assertion locations outside Git under
`lmdj-followup-evidence/2026-10-09-monitor-output/stopped-pattern-reselection/`
`playing-pattern-switch-core-prerequisite/native-verification/` and
`playing-pattern-switch-core-prerequisite/causal-mutations/`. The earlier
same-second rejected restore remains separate from its successful repeated
proof. The Record crossing journey retains actual input, Record-off, reopened
Project revision and the actual Pattern events; it is not shortened to a
recording-state assertion. These Task-specific receipts are not batch pass
keys, and do not establish Linux Asan, coverage, stress, Web Host or device
acceptance. The complete Portal check passed in 58.080 s, including tests, document and
diagram validation, release/snapshot projection, typecheck, optimized build and
50-route/internal-link checks. The ledger schema suite also passed. Before
commit, refreshed `origin/main` still names the same `785d36db` base; no
intervening producer, consumer or acceptance change exists. Selected exact-source
batch lanes remain pending in the parent's resource schedule.

### Independent-review cutoff classification follow-up

Before commit, independent source review identified that a canceled audio-owned
slot can become reclaimable after its callback passes command consumption and
crosses the canceled activation frame. Frame-only evidence then misclassifies it
as applied. The actual reduced regression paused the existing claim hook,
canceled B, submitted Stop/fence, resumed that same callback across B's frame,
and consumed cutoff only in the next callback. All four combinations of action
and fresh/reused applied slot failed the new truthful-outcome assertion after a
successful fresh build: alleged applied frames were default 0 or the previous
generation's 8, while the actual new B never applied. Other four compatibility
entries passed. Receipt `native-verification/initial-20261010T102518Z/` retains
actual exits, source hashes and the failure at the new fact (line 1276 then).
This is behavioral RED, separate from the earlier setup failures.

The repair adds a fixed audio-owned generation witness alongside each slot's
applied frame. Only an actual apply records the matching generation/S, and
cutoff requires both the exact tag and S&lt;F. It does not infer apply from
reclaimability or reset historical evidence from the control lane. The existing
real-retiring-B regression remains the positive control. This adds only within
the declared Audio header/cpp/test and Portal/plan files and the already
identified MAJOR ABI debt; no identity is guessed. The five targets rebuilt
successfully in 20.993 s and all five CTest entries passed in 16.051 s
(`native-verification/initial-20261010T102736Z/`). Removing the exact generation
witness then produced rebuilt RED at this new fact, and restoring it compiled
and passed. Repeating the true-retiring-B counter-mutation on the repaired source
also produced its own assertion RED and restored GREEN. Total causal receipts
now cover 21 distinct causes with 23 passing rebuilt RED/GREEN runs; historical
setup/restore failures remain separate. The final restored source's complete
Portal check passed in 51.370 s with the changed Audio source fact, 176 tooling
tests and all 50 routes. Receipt `portal-verification/20261010T103301Z/` retains
the actual exit 0, unchanged 14-file source inventory and log digest
`dba2df43c7d72900dcde0f102cd35fc94ea9733ccf1cf20224b816037e480370`.
The ledger schema suite passed again. The precommit refresh still identifies
`785d36db27dc44fde7cceb4f6cb6da0956a795e1` as live main, with no intervening
producer, consumer or acceptance change. Batch-lane evidence remains pending.

## Version Management

Audio Runtime and Application Facade owe MAJOR debt at the coordinated Goal
version settlement: new Engine/command/receipt layout and public port virtual
methods are a staged native ABI break under `version-management.md` §6. The
Host-only plan's earlier MINOR assumption does not cover this newly identified
native prerequisite. Old source consumers retain defaults, but old binaries
are not compatible replacements. The independent V1 Task must settle matching
Module/Assembly identities, rebuild coherent consumers, allocate the required
new BUILD and freeze its immutable snapshot before supported package delivery,
replacement of an existing ABI package or team-test Product Build allocation.
No Product Build, Assembly or persisted Project Contract identity is allocated
or guessed by this source slice; manifests remain derived through the normal
version workflow.

All eleven selected batch-only lanes must first run against the actual
committed Core inputs. The package lane retains its original command, selectors
and assertions. Its generated archive and adjacent manifest/checksum stay
isolated as private verification evidence: record the actual declared versions,
source revision and outstanding new ABI debt. This test does not settle that
debt or establish binary compatibility. Do not upload, issue, distribute or use
the artifact as a supported replacement; no borrowed pass key or accepted-risk
entry substitutes for a selected lane.

The order is complete selected Core batch verification and current-head review,
guarded source integration into actual main, then independent V1 settlement from
that refreshed integrated source. V1 reruns its selected lanes, including
package, on its actual changed inputs. The Core's private package proof is not
V1's package proof or a Product Build allocation. This follows testing/allocation
separation in `git-workflow.md` and the source-first cut and identity rules in
`version-management.md`; it preserves the ABI debt and every verification gate.

### Documentation Task — clarify verification and delivery sequencing

The parent independently checked the official policies and actual package
producer. The earlier unqualified "before package" sentence was an additional
technical sequencing assumption in this plan, not a user product requirement.
It incorrectly made private package verification depend on a later source-first
version cut. This correction makes the test and delivery boundaries explicit;
it neither waives package verification nor permits delivery with unsettled ABI
identities.

Declared files: only `docs/plans/2026-10-10-pattern-switch-core-prerequisite.md`.
The preceding Core implementation Task retains its fourteen-file scope;
production, manifests, Portal pages and tests remain unchanged. Lowest-tier
verification is the staged single-file diff/whitespace check, canonical
`docs_static`, PR body lint and declaration-only checks. Inspect the complete
committed PR range again after this separate docs Conventional Commit; all
eleven batch-only lanes remain selected and pending until actually executed.
The old `b03bf51e` independent technical binding remains historical evidence;
the new head needs its own binding and formal current-head review.

Version impact: none for this documentation Task; the Core's MAJOR debt above
remains. Documentation impact: none for this documentation Task because it
corrects only this plan's execution order, without changing Portal source facts.
Pitfall impact: none for this documentation Task; the existing recorded
fresh-artifact recurrence and its exit remain unchanged.

## Documentation Impact

Documentation impact: required
Affected portal pages: `/core/modules/audio-runtime/`, `/core/modules/application-facade/`.
Update actual API ownership, timing and asynchronous opening failure behavior.
Run `scripts/docs-site.sh check` before commit in the coordinated Portal window.

## Pitfall Impact

The product defects are expressed by lowest-tier regressions. The native
mutation verification encountered one recurrence of the already absorbed
`revert-proof-rebuild-skipped` process pitfall: GNU Make 3.81 skipped a restore
written in the same second as the mutant artifact. The artifact freshness guard
rejected that exit-zero build, retained its failed receipt, and counted no
GREEN. The parent approved the fourteenth declared file to record this actual
recurrence. The repeated proof waits more than one second, stamps fresh source,
checks the actual compile line and artifact hash/mtime, then runs the restored
test. The existing skill exit, gates and budgets are unchanged.
