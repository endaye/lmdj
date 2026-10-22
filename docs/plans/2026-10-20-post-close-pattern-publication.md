# Bound post-Record-off Pattern publication (#2395 / #2112)

## Task, authority and premises

Current isolated branch: `fix/post-close-publication-main`.
Current integration and Task base: `84136533c3d1575084b4b4667e905b1a183fa237`.
The original diagnostic began on `fix/post-close-pattern-publication` above
Draft #2426 / `2d1fcabedb31c95387380ed5d3154d634f5d5ba4`, against the historical
`8126d401bae8681caca98af32594458edc4be9ba` main. That dirty worktree remains
preserved; its findings are retained below with their original boundaries.
The owner permits development/commit/push/Draft and ordinary PR integration
after current-head review. Workflow, release-tool and release-evidence paths
remain excluded; no release/deployment/Channel/cleanup action is added.
No subagents. Keep C4's full COUNT-IN journeys and the #2396 withdrawal intact;
#2394's metronome decision is separate, not settled by this Task.

Live #2395 is OPEN with no comments. Its original 39160288846 evidence reports
the consumed-ticket response and a following short inspect timing out after
Record-off, although the close committed. Preserve those observations and
the fixed1000ms short-request budget; do not call an inspect timeout a refused
effect or erase the original ticket. #2394 is also OPEN, not fixed here.

Verified source presence on main and the stack tail: Host
`transport_continuation_step` arms `publish_pending` on durable close, then
the next step performs `project.inspect` and `prepare_project_pattern` on its
serialized caller. The latter invokes Facade `prepare_runtime_snapshot`,
which loads Project Truth then cooks the Runtime Snapshot. The C3 merge
#2373/8c1ee714 changed terminal selection to actual Native current Pattern;
retain that correction, actual F and original COUNT-IN A/S0/e1/e2.

No open successor claims to fix this path. The tail's worker-owned recording
metadata reader is a positive existing async capability, but its actual
handler is for saved Performance audio metadata; post-close preparation still
uses the synchronous path. This bounds the unimplemented premise; it does
not choose a replacement API or presume where the elapsed time is spent.

## Current verification and final declared scope

Complete Native Host PASS85.574s; complete ASan/UBSan Host PASS196.757s.
All six new Task cases pass TSan (2.901–3.432s each), retaining every1000ms
request and whole Truth/reopen leg. Complete Host TSan failed at unchanged480s;
that full-check debt remains visible. Related Store/Facade/tempo integration
and four stress tests:26/26 PASS36.666s. The complete-Asset mutation compiles,
fails precisely at the detached INVALID_PROJECT assertion, then exact-source
restore with fresh mtime and actual producer rebuild passes the full Facade
registration4.539s. Latest complete Portal PASS58.613s (179 tests,53 pages,
51 routes/links,10 deterministic diagrams). Real Wasm/OPFS runs after the clean
source checkpoint; its exact-head receipts belong in the resulting Pull Request.
No shipping/completion claim; a clean local source checkpoint is permitted
only after Native/Portal prechecks, to satisfy the official Web packager.

The final Task owns exactly these paths (incremental declarations below record
when each path was admitted):

- `docs/plans/2026-10-20-post-close-pattern-publication.md`
- `packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp`
- `packages/web-runtime-platform/src/control_runtime.cpp`
- `packages/web-runtime-platform/test/control_runtime_test.cpp`
- `packages/application-facade/include/lmdj/facade/application.hpp`
- `packages/application-facade/src/application.cpp`
- `packages/project-io/include/lmdj/project_io/project_store.hpp`
- `packages/project-io/src/project_store.cpp`
- `tests/core/facade/web_runtime_limits_test.cpp`
- `tests/platform/web/count_in/creator_count_in_opfs.spec.mjs`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `apps/docs-site/docs/core/modules/project-io.mdx`
- `apps/docs-site/docs/platform/web-runtime.mdx`
- `apps/docs-site/diagrams/application-facade.architecture.json`
- `apps/docs-site/static/diagrams/application-facade.svg`
- `apps/docs-site/static/diagrams/application-facade.html`

## Initial diagnostic-only scope (historical)

The initial feedback-loop change owns exactly:

1. This plan.
2. `packages/web-runtime-platform/test/control_runtime_test.cpp`.
3. `packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp`
   (read-only conformance observation, not a fake completion).
4. `packages/web-runtime-platform/src/control_runtime.cpp`
   (the observation implementation only until the red loop is established).

Amend this declaration before editing any additional implementation or Portal
file. Do not add a workflow, binary, universal gate, capacity or timeout change.

## Feedback loop and investigation

First run the unchanged owning Host test baseline. Add a filtered invocation
of the existing binary for the post-close regression, while preserving its
full default registration and every original case. A real Store decorator
holds one selected Project/artifact read after real Native F and durable close;
it delegates the actual read after release and records thread/path/entry facts.
The public short inspect must finish within its existing1000ms budget while
that read remains held. A bounded test-owner release/join prevents a failed
assertion from abandoning a live thread. Never fabricate a Snapshot, Journal
ACK, Native receipt, expected revision or clock advancement.

Exercise the actual current Pattern and real caller state after release, plus
whole Truth/reopen and original asset identities. Use separate held-read paths
to distinguish initial Project inspect from preparation/Artifact work. Record
the actual command and failing assertion before hypotheses or implementation.
Then rank falsifiable causes, measure/instrument only those boundaries and
update the scope from evidence. No "fix" consisting of a longer deadline,
operation exemption, disabled test, omitted journey or synchronous join on the
control lane is admissible.

## Executed diagnosis (2026-10-20)

- Unchanged main-tail owning Host baseline: build PASS and complete
  `host.web_control_runtime` PASS (83.35 s). This is a baseline, not a fix.
- The initial harness build failed because the absolute deadline type is
  nested under `ControlRuntime`; corrected before the actual probe. An early
  `project.json` read selector never entered and produced two vacuous green
  runs. These are harness failures, not product or liveness verification.
  The authoritative Project load reads `manifest.json`.
- The corrected real-read gate fails for both ordinal 1 (`project.inspect`)
  and ordinal 2 (Snapshot preparation), each showing `read_entered=1`,
  `on_control=1`, `in_original_short_budget=0`. Reduce the fixture from four
  Patterns to one, retaining real press/release, Native F, durable close and
  original 1000 ms short inspect: both still fail (2.531 s / 1.417 s process
  duration). Each child returns exit 1 after bounded release and thread join.
- Ranked falsifiable hypotheses were shown before further probes: duplicate
  synchronous Project loads (removing the first alone leaves the second);
  Snapshot preparation dominates (measure the two stages separately); shared
  storage serialization (a worker move would still block short observations).
- Native unheld profile, same real recording/whole-Truth/reopen journey, three
  PASS runs: Project inspect 10.640/10.866/11.285 ms; Snapshot preparation
  12.402/12.854/12.924 ms; Engine publication 15/19/18 microseconds; total
  23.059/23.740/24.228 ms. Both Project stages are material on this machine;
  publication itself is negligible here. This does not measure original Wasm
  runner latency, prove a worker is safe, or choose its ownership design.
- Temporary `[DEBUG-2395]` timing and unheld diagnostic mode were removed;
  both saved WIP files restored byte-identically with fresh mtime and actual
  producer/test rebuild PASS. Keep the deterministic red regression. A fix,
  shared-platform nonblocking proof and real Web RPC composition remain
  outstanding; do not commit/push this incomplete diagnostic Task or restore
  COUNT-IN UI on the strength of these measurements.

## Remaining verification boundary

Required before shipping: discriminating parent red, affected owning tests,
full default Host registration, actual Wasm/SDK short-request composition and
the original failure/recovery/retirement/caller/Truth legs. A Core-only or
source-only change does not prove the original Web RPC symptom fixed. Select
integration/stress/sanitizer checks when the measured fix changes lifetime or
concurrency. Preserve unavailable complete/platform/device lanes as unverified.
Stage only the final declared files, run new-path ownership after staging and
on the committed range, inspect diffs/commit list/final clean status. Draft
review is pending, never waiver or merge evidence.

## Version Management

Version impact: Application Facade MINOR and Project I/O MINOR for additive
public APIs; Web Runtime Host PATCH for bounded post-close preparation.
Accumulate these in #2237, retaining higher same-domain debt. No public concrete
object/vtable layout, wire Contract or persistence shape changes. No Product,
Assembly, Build, manifest, tag or immutable snapshot allocation in this Task.

## Documentation Impact

Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /core/modules/project-io/
/platform/web-runtime/
Reason: public detached preparation API, complete-Asset committed read option,
post-close ownership and terminal result disposition. Update the Application
Facade source architecture diagram and its two official generated outputs.


## Current main resumption (2026-10-22)

Actual base `84136533c3d1575084b4b4667e905b1a183fa237`. All prior #2112 ordinary PRs have now integrated;
#2395 and #2394 remain OPEN and no current open PR delivers this path. Current
source still performs both real Project reads on the serialized control caller.
Keep the original dirty2d1 WIP unchanged; its three-file diagnostic patch and
plan were archived by SHA before applying them into this isolated current-main
worktree. Initial declared files remain the same four paths above.
First rebuild and rerun both unchanged1/2 read-gate negatives at this actual
base, with real close/F/currentPattern,1000ms inspect, bounded release/join and
full Truth/reopen. Historical native stage timings do not prove Web root cause
or safety of a replacement. No source fix or passing liveness claim yet.


## Fix scope after current-base negatives

Both unchanged read-gate cases reproduce at84136533: real read_entered=1,
on_control=1, original1000ms response unavailable; exit1 at2.623/1.428s.
The first Project query is redundant for preparation but removing only it
leaves the second blocking read. Existing facade-owned metadata readers are
the positive pattern for detached read state, not permission to share mutable
Application or AuthoringHistory with a new worker.

Chosen boundary: add a Facade-vended detached Runtime Snapshot preparer over
the exact configured storage platform. It owns private ProjectStore/history,
uses existing inspect_committed (no recovery/scavenge), existing complete
Artifact integrity and identical cooker/quota rules, and returns an immutable
Snapshot carrying real Project/Pattern/revision. It acquires/releases every
lease in its actual caller realm. The captured platform and immutable request
can outlive Application; no Runtime, Engine, mutable Project or shared history
is borrowed. Keep the ordinary prepare_runtime_snapshot path unchanged.

Host owns one post-close preparation cell per retained engagement. A worker
owns only that detached callable, request and heap result; control polls an
actual returned flag and joins only after real preparation/reader destruction.
After validating current Project/Pattern/generation, control alone publishes
Engine state. A failed publication retains the close completion for retry with
a fresh worker-prepared derived view; read/preparation failure keeps it outstanding. Lifecycle
barriers retain actual pending/worker custody; no synchronous I/O join on the
short control lane or fake shutdown witness. Test first-move source gates
against actual held reads, including stopped/failed/retired ownership.

Amended declared scope (before these implementation edits):
- This plan.
- packages/web-runtime-platform/include/lmdj/web_runtime/control_runtime.hpp
- packages/web-runtime-platform/src/control_runtime.cpp
- packages/web-runtime-platform/test/control_runtime_test.cpp
- packages/application-facade/include/lmdj/facade/application.hpp
- packages/application-facade/src/application.cpp
- tests/core/facade/web_runtime_limits_test.cpp
- tests/platform/web/count_in/creator_count_in_opfs.spec.mjs
- apps/docs-site/docs/core/modules/application-facade.mdx
- apps/docs-site/docs/platform/web-runtime.mdx

Owning checks: both real-read negatives/greens, complete Host test registration,
Facade limits/identical Snapshot integrity, affected lifetime integration/stress/
sanitizers, actual Wasm/SDK/OPFS original RPC and retirement/Truth/reopen legs,
full Portal and changed-path ownership. No Native-only completion claim.
Version impact: additive Facade API MINOR and Host PATCH debt, deduplicated
with existing same-domain debts in#2237 while retaining every higher debt.
No object/vtable/Contract/persistence shape, manifest or identity allocation.
Documentation impact: required
Affected portal pages: /core/modules/application-facade/ /platform/web-runtime/
Reason: detached preparation and actual post-close ownership/liveness boundary.
All original failures,1000ms deadlines, hiddenCOUNT-IN withdrawal and#2394
product decision stay separate. No frozen release/workflow/evidence path.


Implementation refinement before Project I/O edits: existing inspect_committed
deliberately skips complete asset-byte verification for selector reads. Snapshot
preparation must retain ordinary load's verification of ALL assets, including
unassigned ones, while performing no recovery/scavenge. Add the overload
inspect_committed(bundle, verify_asset_bytes) and preserve the old no-argument
behavior. This reuses the exact existing load_project verification and quota
path instead of duplicating integrity or introducing unbounded byte copies.
Additional declared paths: packages/project-io/include/lmdj/project_io/project_store.hpp
and packages/project-io/src/project_store.cpp. Version impact includes additive
Project I/O API MINOR debt, no concrete object/vtable change. Existing Store
checks and detached Facade corruption/limits remain required. The first compile
stopped on ProjectId vs Host string comparison; no runtime test ran from that
failed build. Retain the failure, correct the typed comparison, then rebuild.


First async observation: ordinary short request now returns within1000ms while
real read_entered=1 on_control=0, but the full fixture failed at its unchanged
sixteen-callback settlement loop. Tagged boundary probes showed preparation
still pending, not a reader/publication error: its old idle witness covered
only the Journal executor. Keep all16 callbacks and its existing two-second
per-leg bound; additionally wait for the new actual preparation return before
advancing each callback leg. No deadline is extended or leg omitted. Remove
all tagged probes. Native can consume a view on publication refusal, so retry
retains the pending close completion but re-prepares a fresh derived view on
the worker instead of reusing a moved-from object. OriginalEngine publish/
reclaim and exact currentPattern/Project ownership remain authoritative.


Diagram impact (declared before edits): the Application Facade architecture
diagram already describes the single durable Journal worker. Preserve that
owner and distinguish the new isolated Snapshot reader in its labels/cards.
Additional exact files: apps/docs-site/diagrams/application-facade.architecture.json,
apps/docs-site/static/diagrams/application-facade.svg and
apps/docs-site/static/diagrams/application-facade.html. Generate these outputs
through the official diagrams command, inspect them and run complete Portal.

Native integration so far: both held-read complete journeys PASS (0.983/0.447s),
Facade ordinary/detached exact/+1 quotas and outliving Application PASS; added
unassigned-Asset corruption preserves ordinary INVALID_PROJECT behavior. Full
Host first found a caller test consuming count-in after recording=false but
before actual publication completion; strengthen the wait with the existing
publication_pending field and same original deadline. A later64-render-leg
fixture also needs the actual preparation-return witness before each original
callback. Keep intentionally early Journal-only cutpoints unchanged. Full Host
and Web composition remain pending, not promoted by these focused passes.


Additional documentation declaration before edit:
apps/docs-site/docs/core/modules/project-io.mdx, route /core/modules/project-io/.
The overload's complete-Asset option is public Project I/O API and must be
documented alongside the existing selector-only read. Cooker source confirms
the positive control: it resolves assigned Pads and deliberately skips empty
Pads; it cannot substitute for validating retained unassigned Asset bytes.
The new corrupt-unassigned-Asset regression therefore catches a real loss of
ordinary load integrity, rather than merely mirroring the new overload.


## Lifecycle verification and retained failures (2026-10-22)

Current main recheck remains84136533c3d1575084b4b4667e905b1a183fa237;
open PR inventory is empty. This task is not committed, reviewed or merged yet.
Complete Native Host registration passed85.335s before the extra lifecycle
cases below. Full ProjectStore passed4.283s, ordinary/detached Facade limits,
outliving Application and retained unassigned-Asset corruption passed4.558s.
Full Portal passed68.853s,179 tests/53 pages/51 route/link checks; subsequent
terminal-disposition documentation requires a fresh Portal check.

Holding the real preparation read while requesting Suspend exposed an actual
Stop-receipt deadlock: publish_pending skipped controller continuation, leaving
its Native Stop reservation held against publication. Continue shutdown and
actual stopped transport receipts while preserving the unfinished preparation.
The held-Suspend/full Truth/cold-reopen case then passes1.270s; unchanged
held-read ordinals1/2 pass0.490/0.447s. Ordinary Stop also passes0.450s with
publication_pending retained during the held read, followed by actual publication.
No callback leg, e1/e2 receipt, Journal assertion or deadline is removed.

The direct-destruction case initially crashed. LLDB's actual backtrace locates
only the fixture destructor dereferencing its deliberately reset storage;
correct that null cleanup and strengthen custody proof instead of altering
product lifetime to mask the harness defect. After dropping Runtime and every
external platform owner, the blocked real reader alone retains the platform;
release through weak.lock, wait for actual platform destruction and cold-reopen
complete Truth. This passes1.215s; destruction stays within1000ms without joining
an unfinished preparation on Control.

The first expired-request probe had no physical callback-last-use witness;
its pending Native retirement was correct and is retained as a harness failure.
The corrected case uses the real OneShotAudioDriver callback and actual thread
join, installed before activation through the existing physical seam. It found
a separate terminal bug: worker returned and controller shutdown completed,
but retained controller error prevented close result collection. Tagged probes
show current Pattern still present; do not claim a cleared-Pattern root cause.
Collect/discard only after actual worker return on permanent Runtime failure;
do not publish a derived view, clear failed state or consume any other owner.
The corrected expired-request/full Truth/cold-reopen case passes0.971s, asserting
no new Engine publication and retaining the actual physical/caller barriers.
Temporary probes are removed. Full updated Host, sanitizers and real Wasm/OPFS
proof remain outstanding; these focused results do not close2395 or2112.


The ordinary and detached limit cases each retain the existing independent
exact/+1 byte, frame, Pad-bank and Project limits; agreement alone is not the
oracle. Their shared cooker skips unassigned Pads, so the additional real
one-byte corruption case explicitly requires INVALID_PROJECT on each route.
Before shipping, temporarily bypass only detached complete-Asset verification,
rebuild the actual Facade test and require its independent corruption assertion
to fail. Restore exact source bytes with a fresh mtime, rebuild, and require
the complete unchanged Facade registration to pass. Retain all receipts.


Latest complete Native Host registration passes85.574s, and the same complete
registration under ASan/UBSan passes196.757s. The optional monolithic TSan Host
run hits its unchanged480s timeout (exit8); its retained log reports no data race,
and a live stack sample showed existing repeated Sample mutation preparation.
This is a failed complete check, not a TSan pass or proof all remaining tests
would pass. Keep that full debt visible. Do not widen the bound or modify an
unrelated fixture to force completion. Execute every new Task case through the
existing filtered binary entrypoint under TSan, retaining all original1000ms
short requests, held real reads, real physical join and complete Truth/reopen.
These are affected-lifetime checks; they cannot relabel the full timeout green.


Pitfall impact: none — the synchronous-read defect, Stop receipt starvation and
terminal result custody are product logic expressed by real regression tests.
The avoided shared-cooker blind spot has an independent corruption oracle and
an executed fresh-build mutation proof. Existing storage-realm, rebuild and
complete-journey guidance was applied; no new process invariant was invented.
