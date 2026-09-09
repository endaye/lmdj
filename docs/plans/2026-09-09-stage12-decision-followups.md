# Stage 12 decision follow-ups and Issue decomposition

Date: 2026-09-09. Relates to #467 and #471; parent #472.
Status: C-Q1–C-Q5 direction confirmed; precise Contract allocation and Candidate
design follow-ups below remain explicit. No production implementation in this Task.

Authority: [confirmed decision](../prd/decisions/2026-09-09-stage12-byte-boundary.md),
[Capability plan](2026-09-08-lmdj-stage12-capability-implementation.md),
[Candidate design](../design/2026-08-31-lmdj-stage12-candidate-adoption-lineage-design.md).
This dated addendum controls readiness over the older drafts.

## Baseline and scope corrections

Inspected base: 07fead58. Project v4 schema and domain project.hpp already contain
Asset.lineage with resample and soundset_install variants. Reuse that carrier;
do not create a second model or wait again for its original placement decision.
Historical Stage 10/11 Issue references are coordination pointers; recheck live
ownership rather than treating all old OPEN statuses as current blockers.

B1 (#960) and B2 (#973) merged. Merge state is not proof of every planned
acceptance item; later harness Tasks must review the actual tools they consume.
No production execution, provider quality result or checkpoint selection follows
from those two tool PRs.

## R1 — close the exact #467 descriptor and allocation inventory

Type: design review; ready to prepare now. Parent #467.
Files: existing Capability design, existing Capability implementation plan,
existing Stage 12 Issue drafts; a new dated decision file for approved constants.
No active source edits.

Produce a closed proposed descriptor with every capability.v2 required field,
binary profile ID/version/path, output ID/version, optional fields, parameter
ranges, canonical bytes, error ownership, platform tokens and granted permissions.
Use §10.5 values as proposals, not already allocated identities.
Explicitly show supported/measured platforms separately and match every policy
token to its consumer. User direction C-Q1–C-Q5 is settled; only previously
unpresented exact public choices require a decision.

Verification: compare with contracts/capability/lmdj.capability.v2.schema.json
and SDK descriptor fields, link exact source consumers, run docs-site check.
Acceptance: no blank mandatory constants and no inferred permissions; record
approval of the complete descriptor before K1. This is the remaining #467
review deliverable, not a new unbounded architecture project.

## K1–K5 — preserve the existing implementation boundaries

The exact declared files and tests remain in the linked Capability plan.
The following is the publishable dependency/acceptance summary for child Issues.

| Task | Dependency and outcome | Required acceptance |
| --- | --- | --- |
| K1 Contracts/conformance | R1; formal capability instance, binary WAV profile and slice-points schema | Every required descriptor value approved; positive/negative contextual vectors and schema validation; current Contract Portal routes truthful |
| K2 SDK byte custody and complete migration | K1; fresh ABI/dependency allocation and current shared-file owner coordination | All Providers/mocks/call sites migrate; owned inputs, aggregate budget and retained lease; typed source/sink/domain failures; output validator before terminal; kill/restart visibility evidence |
| K3 unregistered slice reference Provider | K1/K2 | Real Registry/AttemptStore invocation with unseen algorithm fixtures, unchanged smoke corpus, invalid inputs and byte replay; no fixture-hash special cases |
| K4 product registration and identity | K3, measured evidence, explicit inclusion decision, fresh allocation | Generated lock/registration/runtime identities agree; current Portal and immutable Build snapshot; split K4a identity and K4b clean-source snapshot as the original plan requires |
| K5 owner resolver and Host journey | K4, approved owner API, exact post-K4 file inventory | Host → Facade → owner → SDK → validated terminal → inspect → restart → inspect, with identity/hash/length assertions and zero Project mutation on refusal |

No current numeric version is hand-allocated by this plan. K2 excludes JobRecord,
CandidateIndex and plural result changes. If later L1 requires an incompatible
SDK API, allocate against then-current manifests; do not reuse a version number
already shipped. K4/K5 are gated planning children until their exact inventories
are refreshed, not immediately executable Issues.

## R2 — reconcile and decide #471 before Candidate implementation

Type: design review; ready in parallel with R1. Parent #471.
Files: Candidate design, this follow-up plan, a new dated Candidate decision file.
Read-only sources: domain project.hpp, Project v4 schema, SDK AttemptResult and
terminal ledger, Facade resample and Sound Set install/quota paths.

Produce concrete alternatives and recommendations for:
- Whether one structured output produces many Core recipe candidates without
  changing Provider result cardinality, or whether plural Provider results are
  truly required. Resolve the draft's SDK 2.0.0 overlap before allocation.
- Slice recipe interval construction: leading material before first onset,
  final tail/EOF, no-onset input, nonempty half-open ranges and stable candidate
  IDs. C-Q2 onset-only output does not answer these product questions.
- Job retry ordering, when an old active set is superseded, concurrent successful
  Attempts, cancellation and crash between terminal and index publication.
- Duplicate candidate/target requests, repeated adoption/idempotency, source
  replacement/revision conflict, and whether expiry exists at all. Do not
  introduce wall-clock expiry implicitly; discarded/superseded are not expired.
- Required lineage fields and authority per variant, preserving both existing
  resample and soundset_install records without redundant truth.
- Preview read-only guarantees; explicit Pad targets and all-or-nothing quota
  simulation, including same Artifact resident on multiple Pads.

Verification: reviewed transition/failure matrix with observable far-side
assertions; exact field mapping against current code; docs-site check.
Acceptance: decision record covers all questions above, or explicitly splits a
deferred feature out while preserving a complete first slice adoption journey.
Pattern Merge and Project Bin remain separate product questions.

## L1–L5 — proposed Candidate implementation Issues

These child Issues can retain the work but remain blocked on R2; draft API names
below are descriptive proposals. Each implementation must first declare exact
files, lowest-tier named tests and fresh version/Portal allocation on current main.
Do not mistake these source-boundary inventories for an executable final file list.

| Task | Proposed source boundary | Dependencies | Acceptance and verification |
| --- | --- | --- | --- |
| L1 Candidate/Job identity and store | provider-sdk and owning Workspace layer; provider component/durability tests | R2, K2 terminal semantics; decide result cardinality before API change | Validated terminal publishes a stable candidate view; ordered Job history; restart reproduces the view; no index entry from incomplete/failed Attempt; terminal bytes remain immutable |
| L3 capability adoption lineage | authoring-domain project model/codec, Project Contract, project-io round trips, schema conformance | R2 | Reuse Asset.lineage; exact required source/capability/provider/model/parameters/Attempt/revision/range evidence; resample and soundset_install fixtures survive load/save; no second field |
| L2 atomic adoption and quota | application-facade command plus domain helpers, facade adoption/quota component tests | L1/L3 and approved recipe rules | Explicit targets, deterministic ordering, preflight all affected Banks/generation; one revision on success; any failure leaves all Project/Pad/Asset state unchanged; source retained; repeated adoption follows R2 |
| L4 lifecycle and recovery | owning Candidate store/Facade, component plus independent-process crash tests | L1, R2; L2 for adoption race tests | Discard/supersede tombstones survive restart; old terminal and attempt history unchanged; unavailable bytes refuse; no GC on discard; expiry only if separately approved; interruption after each durable transition has far-side inspect assertions |
| L5 preview and Host/Creator journey | application-facade public surfaces, thin Hosts, creator-web, relevant Host and browser journeys | K5, L2/L4 | Preview changes no truth/revision; select results and explicit Pads then adopt once; stop/reload/reopen and refusal legs verify state; no automatic Bank fill or overwriting recorded Pattern events |

Order is L1/L3 → L2 → L4 → L5, despite retained L labels; L1/L3 may run
in parallel only after checking shared schema/CMake/manifest/Portal ownership.
L1 must land its own minimal durable read/recovery evidence; L4 extends lifecycle,
not postpones all crash safety until a later PR.

## Parent acceptance

Published child Issues (2026-09-09; dependencies above remain applicable):

| Task | Issue |
| --- | --- |
| K1 | [#1033](https://github.com/endaye/lmdj/issues/1033) |
| K2 | [#1034](https://github.com/endaye/lmdj/issues/1034) |
| K3 | [#1035](https://github.com/endaye/lmdj/issues/1035) |
| K4 | [#1036](https://github.com/endaye/lmdj/issues/1036) |
| K5 | [#1037](https://github.com/endaye/lmdj/issues/1037) |
| L1 | [#1038](https://github.com/endaye/lmdj/issues/1038) |
| L2 | [#1039](https://github.com/endaye/lmdj/issues/1039) |
| L3 | [#1040](https://github.com/endaye/lmdj/issues/1040) |
| L4 | [#1041](https://github.com/endaye/lmdj/issues/1041) |
| L5 | [#1042](https://github.com/endaye/lmdj/issues/1042) |

#467 stays open until R1 completes and K children have reviewable approved
implementation boundaries. #471 stays open until R2 and the exact implementation
plan/decision acceptance are complete. Creating children is not completion of
either parent. #472 additionally requires measured Provider and product evidence.

## This documentation Task

Declared files:
- Create docs/prd/decisions/2026-09-09-stage12-byte-boundary.md.
- Create docs/plans/2026-09-09-stage12-decision-followups.md.
- Modify the two Stage 12 design files and the Capability implementation plan
  only to link this dated status addendum.

Checks: local relative links; docs-site check (retained source facts);
ci_change_scope_test after staging; staged diff whitespace and PR body declarations.
New gates: none. Pitfall impact: none; no process mechanism changed.

## Version Management

Version impact: none for this Task: retained decisions/plans only.
Future K/L implementations require exact manifests, dependency pins and Contract
allocation before commit. L3 may require a successor Contract for the closed
union; the original Asset.lineage carrier remains authoritative.

## Documentation Impact

Documentation impact: none for this Task: no current Portal availability or
manifest identity changes. Future Tasks declare required current routes for
SDK, Contracts, Facade, Providers, Hosts and Assembly as actually affected.
No Product Build, snapshot, release, deployment or Channel is allocated here.
