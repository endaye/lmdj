# Full-batch release evidence activation — Task B proposal

Status: design reviewed; B1 merged as #837, main
`2b8a44e275942e8e37be0d70e0c101cfd9b335b5`. Root authorized B2 local
implementation of the seventeen files below; the coordinated C1 window has
ended and B2 shipping still requires current-head review. Earlier HOLD statements
below are historical stage records, not current claims about Task A/B1.
Base for this draft: Task A plus reviewed follow-up
`761f2cef36e1a1f098287ed25b6487b2d1e67dda`. Both remain held from shipping.
The original draft did not activate a policy. B2 now changes only local policy
and consumer code; it does not edit intent data, select a tag, dispatch tests,
audit a Release or authorize any release/deployment transition.

## Actual source baseline and authority

Read-only GitHub API observations on 2026-09-08:

- repository `endaye/lmdj`: numeric ID `1286600062`;
- `self-test-report.yml`: workflow ID `352307416`, path
  `.github/workflows/self-test-report.yml`, active;
- actual main: `c2932ab2fcf43f6643bbd78a160a8ec1b4eb9eaf`.

The first merged control containing both the incremental controller artifact
and actual reusable executor entry is
`24ee0c4f79e0fe21a89be8813cb0566948583aa4` (#806). Its source contains
`batch-controller-<run>-<attempt>` and passes the durably claimed request and
executor into Core CI. Earlier #803 deployed the callee, #804 the runtime;
neither alone supplied this complete entry. Use #806 as the proposed trusted
producer lower bound, verified against main ancestry again at implementation,
not a guessed future Task A/B squash SHA. This permits earlier authentic
producer observations without claiming they passed. The original bootstrap
actually failed; no full-passed platform evidence is asserted here.

The configuration belongs in reviewed current `tools/release/policy.json`,
never in a model-produced reference. Add a closed `batch_evidence_source` with
`repository_id`, `workflow_id`, `workflow_path`, `producer_revision`. Live API
must still match the exact identifiers and current protected-main authority.
Existing canonical authority loaders already read policy and ledger from
protected main for prospective operations; preserve that boundary.

Current inert JSON policy identity (read from this exact baseline):
scope digest `bc6834ca20b75872c42c92c3e5c5ac1fcc3d515889f4544cb37aff27620ea1c6`;
inventory revision `57d0371b8ae372d6c2799e229804e3560125b726ecb83bb868d3b30404ec74ed`.
These are observations, not new permanent allowlists. Recompute all three
policy documents at frozen control, actual executor and applicable main;
require exact equality and the separately release-owned sixteen-suite set.

## Closed reference and import boundaries

Intent adds `batch_test_evidence`, mutually exclusive with `self_test_evidence`.
It requires the existing `merged_main_run_id` (actual executor) and exact
`target_revision`; neither can be inferred from an artifact's self-assertion.
Retain Task A's complete request, actual executor control, attempt and all three
digests, and add `executor_event` with the closed set `workflow_dispatch`,
`push`, `workflow_run`, `schedule`. Both actual API views must match it.

This is a prospective expansion of an **inactive** internal reference schema:
no existing activated batch reference or published v3 marker is rewritten.
The queue's request kind is not its executor wake event. In particular a
candidate enqueued by a dispatch may be admitted by a later scheduled tick.
Never reuse the old audit's request-kind-to-event inference for this protocol.

Introduce `tools/release/batch_reference.py` as a pure standard-library
schema/parser/error boundary. It imports neither `model`, `github_api` nor CI
runtime. `model` and `batch_evidence` both depend on it; `github_api` must not
import `batch_evidence`. Keep the release-owned canonical lane constant in
`github_api` for this Task, preserving the acyclic dependency:

`model -> batch_reference`; `github_api -> model`;
`batch_evidence -> batch_reference + github_api + shared pure CI validators`;
`ci_evidence -> model + github_api + batch_evidence`.

Do not duplicate request parsing or job/macOS validation. Preserve the shared
`scripts/ci/batch_evidence_validation.py` single implementation. Model storage
must defensively preserve the nested request rather than exposing caller-owned
mutable dictionaries through a merely shallow MappingProxyType. Canonical
serialization must retain strict boolean/integer identities.

## B1 — inactive binding prerequisites

One implementation Task/Conventional Commit, after Task A is available.
Declared files:

- new `tools/release/batch_reference.py`;
- `tools/release/batch_evidence.py`;
- `tools/release/model.py`;
- `tools/release/github_api.py`;
- `tests/build/release_batch_evidence_test.py`;
- `tests/build/release_model_test.py`;
- `tests/build/release_github_api_test.py`;
- this plan.

Extract the pure parser, add executor_event and strict source policy model,
and recognize future `complete-test-v2` without changing current policy data.
Under every old protocol (`self-test-v1` and `ci-scope-v2`), reject batch
references at model/entry admission;
they must not fall through to old scope merely because self_test_evidence is
absent. Tests may explicitly use a future-policy fixture. Existing self-test
and historical legacy intent parsing retains its old semantics.

Provide a narrowly scoped GET-only GitHub adapter for the consumer's actual
branch/workflow/run/attempt/jobs/artifact-inventory paths and ZIP download.
Use the existing release client's authenticated request and trusted artifact
redirect policy, stripping credentials from signed-URL redirects. Do not use
an unrestricted URL pass-through or instantiate Runtime. If necessary factor
the existing `_download_artifact` byte transfer into a helper in the same API
file; do not manufacture a partly fake artifact projection to call it.
Fixture checks must exercise real HttpResponse/status/redirect handling, not
replace the final consumer decision. Wrong redirects, content types, transport
errors and missing credentials remain failures, without raw signed URL output.

Lowest-tier checks: parser/model and typed HTTP transport tests; full actual
consumer chain through the production HTTP adapter with temporary real Git,
not just Task A's JSON-returning callable. Preserve all Task A regressions.
No current release entry point accepts new evidence after B1 alone.

## B2 — explicit current policy and permanent binding

One implementation Task/Conventional Commit after B1 review.
Declared files:

- `tools/release/ci_evidence.py`;
- `tools/release/batch_evidence.py` (separate prospective/history interfaces);
- `tools/release/batch_reference.py` (root-approved removal of stale inactive docstring only);
- `tools/release/policy.json`;
- `tools/release/prepare.py`;
- `tools/release/audit.py`;
- `tools/release/transitions.py`;
- new `tests/build/release_batch_binding_test.py`;
- `tests/build/release_self_test_evidence_test.py`;
- `tests/build/release_model_test.py` (root-approved current-policy assertion migration);
- `tests/build/release_skill_test.py`;
- `.agents/skills/lmdj-release/SKILL.md`;
- `docs/governance/version-management.md`;
- `docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`;
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx`;
- `apps/architecture-portal/docs/operations/version-and-release.mdx`;
- this plan.

Set current prospective protocol to `complete-test-v2` with the authenticated
batch source above. A releasable intent must have exactly one accepted sixteen-
suite reference: old self-test-v1 or new full-batch reference. No reference is
unverifiable, simultaneous references conflict, and old fourteen-lane scope
is never a fallback. An old protocol selection cannot silently accept new
batch evidence. Existing native manual `ci.yml` input is `target` (not the
internal CLI's `target_revision` spelling); correct that skill guidance without
executing it or changing any workflow.

Pass the existing `PrepareContext.repo_root` / `AuditContext.repo_root` explicitly
to batch verification: never infer it from the target worktree or attach mutable
Git state to GitHubClient. `verify_release_ci` returns an authenticated executor
projection together with its closed outcome; `_verify_ci` keeps refusing every
non-ok result before building/signing or remote mutation.

Prepare's `ci` preserves real executor run/event/head/conclusion, intent target
and the entire batch reference. New reference selects marker v3; old self-test
selects exactly v2; legacy published history retains v1. Both marker readers
accept the three named schemas with exact closed fields, but demand the one
appropriate to that intent. The canonical v3 CI block binds `executor_event`
explicitly; canonical comparison rejects rehashed mixed identities. A v1/v2
marker never proves a newly added batch reference. No existing marker, Release
body or intent data is migrated in place.

For prospective candidates, all Task A source/controller/claim/three-file/API
job/policy/retention checks apply and the latest attempt must still be 1.
Only for `Disposition.PUBLISHED` new-batch history, add an explicit read-only provenance
interface: authenticate its recorded attempt, source, target and frozen event,
not a later rerun. Do not require temporary origin/admission/verdict artifacts
or unchanged current policy forever. The reviewed permanent reference plus
exact v3 marker is only one leg: actual immutable tag, signer, Release and asset
validation must still succeed. No `published` string or marker alone creates
history. Do not implement this by broadly skipping prospective checks whenever
an artifact is missing, or by treating all non-releasable dispositions alike.

Tests must drive actual prepare/audit/transition orchestration through the new
consumer and HTTP fixture, with far-side plan/marker assertions. Explicitly
cover both valid old16/new16, no-ref/old14 rejection, mixed schemas, distinct
target/control, queued executor events, expiry, later reruns, missing actual
published state, wrong signer/assets and v1/v2/v3 replacement attacks. Existing
legacy/self-test tests stay; frozen old markers must remain byte-compatible.
No real signing key, tag/Release mutation or remote release audit is part of
these tests. Retain ordinary full CI contracts, ownership, Portal check and
documentation-impact tests before commit.

## Boundaries and acceptance

### B1 local implementation evidence

B1 implements only the eight declared prerequisite files. The pure parser
owns the prospective closed reference and source schema, including the explicit
four-event executor identity. Both latest-run and exact-attempt observations
must match that event; request kind is not a substitute. The model stores a
deeply immutable reference with canonical JSON serialization and rejects it
under either old protocol. The real policy file and every intent are unchanged.
The production GET adapter restricts its routes, preserves the old artifact
size bound, and strips credentials before following approved download redirects.

Local verification: 68 batch-consumer, 23 model and 39 GitHub API tests pass;
the complete release test discovery passes 405 tests. The original exact UTF-8
canonical-byte and slash-safe-name assertions remain intact. The acceptance
fixture drives real temporary Git, controller snapshots, three-file ZIPs and
the production HTTP adapter through final full verdict verification; it also
asserts that all three redirected artifact requests omit Authorization.
HTTP requests are fixtures, not a real successful full-batch O1 acceptance.
The complete CI contract discovery passes 1,424 tests without skips using the
pinned actionlint 1.7.12 binary. Portal check reports 54 passing and three failing
checks caused by unavailable glob, gray-matter and cheerio dependencies; this
is a disclosed local verification gap, not a portal pass.
After staging the exact eight declared files, all 66 ownership tests and
the staged whitespace check pass.

No new process recurrence is claimed: the local parser and adapter invariants
are expressed by regression tests. The existing fake-tool-stub-strictness
escalation (#726) and real full-passed O1 gap remain open. B1 is a local-only
prerequisite; B2 activation, permanent v3 marker integration, current policy
change and shipping still require their separate authorized steps.

The trusted-controller snapshot is a durable-claim **attestation**, not latest
Issue Journal replay. Missing, expired or non-admission snapshots fail
prospective verification. No Issues permission or write API is introduced.
No scheduler/probe/workflow file is in either implementation Task's ownership.
T5 source changes belong to their assigned agents and are coordinated by root.

Task A remains HOLD. This draft is not approval to activate B2 or to ship either
Task. Actual new full-passed evidence and consumer acceptance remain an O1 gap;
the observed bootstrap and TSan failures cannot satisfy that leg. A later
explicitly authorized exact full test and read-only consumer run must verify
the complete real chain, without performing release/tag/deployment operations.

## Version Management

### B2 local activation implementation

This Task starts from main `16e822775d6357861ba37e5a93314ab8995e5d61`
(#838, immediately after B1 #837) in its own
`feat/ci-batch-release-activation` worktree. It changes exactly the
seventeen declared B2 files. The current policy becomes `complete-test-v2` with
the previously observed repository/workflow/path/producer lower bound; no
release-intent data, product/version identity, workflow or runner state changes.

The existing consumer now returns its authenticated executor projection with
the independently recomputed verdict. The separate published mode only reads
recorded first-attempt provenance and never claims fresh full coverage from
that path. The release route permits it only for `Disposition.PUBLISHED`;
actual audit still checks immutable tag, signer, Release, assets and v3 marker.
New candidates still require latest attempt one, retained original controller
attestations and three-file evidence, real API job identities and current policy.
No reference or two references cannot fall through to old fourteen-lane scope.
Old self-test v2 and legacy v1 markers are not rewritten.

The new binding journey uses real temporary Git and the production read-only
HTTP adapter through prepare, audit and transition orchestration. Far-side
assertions inspect the actual local plan, canonical digest and v3 body marker;
they reject absent tag/Release, wrong signer, altered assets, old markers,
target/event drift, missing/expired evidence and later attempts for candidates.
Recorded published history remains valid after ephemeral deletion and a later
failed rerun, but not permanent proof drift. Fake signing/profile/GitHub
mutation adapters remain confined to temporary fixtures; no actual release
operation or remote release audit is executed. The successful fixture chain
is not a real platform full-passed O1 candidate acceptance.

The skill-creator instructions require a narrow skill change: only the full
evidence subsection is updated, including the real manual `target` input.
All per-mutation authorization, exact-tag audit, publication/deployment and
history boundaries remain intact. `quick_validate.py` and meaningful skill
contracts are run, alongside the full release, CI, staged ownership and Portal
checks. The current portal routes are updated in this Task; existing source
diagrams do not depict this CI-reference protocol and need no unrelated edits.

No new pitfall recurrence is claimed for fixture construction errors corrected
during this Task; production invariants are captured in behavior tests. The
existing #726 fake-tool-stub escalation remains open. Real full-passed batch
acceptance, B2 shipping and all release/tag/deployment actions remain separate
unperformed boundaries.

Staged verification: 66 ownership tests and whitespace checks pass; complete
CI discovery passes 1,514 tests without skips using actionlint 1.7.12. All 11
skill contracts and skill-creator `quick_validate.py` pass. Portal check reports
54 passes and three missing-package failures (glob, gray-matter, cheerio), no
skips; this is a disclosed verification gap, not a Portal pass.
The source-policy revalidation initially rejected the model's MappingProxy
and the real binding journeys went red. Passing a detached JSON copy to the
same strict parser fixes that incompatibility; a dedicated regression still
rejects unknown keys, wrong workflow paths and boolean numeric identities.
Final release discovery passes all 425 tests without skips, including 14 new
batch-binding journeys, 19 old self-test evidence tests and all unchanged
legacy release/prepare/audit/transition regressions. The final binding fixtures
also keep artifact expiry relative to the production clock, rather than
silently expiring on a fixed calendar date. Root independently reviewed the
working diff and ran 14 binding, 19 old self-test and 23 model tests; final
commit review remains required before shipping.

### B1 fresh-main integration evidence

Task A has since landed as #833, main
`8ce36564e90a2b53b0a57b5e20ec96a552639dab`. B1 is now a separate local
integration Task based on that SHA, not a bundled Task A/B2 release. Its seven
implementation/test files and the original design/B1 plan content are identical
to reviewed `21bb708ce213633fde5199b146c26839d10ee98d`; only this integration
record is new. The historical HOLD and earlier verification statements above
describe their original stage, not a claim that Task A is still unmerged.

Fresh-base checks pass: 68 consumer, 23 model, 39 GitHub API, 18 old self-test
release and 16 legacy release tests; full CI discovery passes 1,474 tests
without skips using actionlint 1.7.12. Staged ownership passes all 66 tests,
and the exact eight-file whitespace check passes. The earlier 405-test release
discovery belongs to original B1; it is not presented as rerun on this base.
Portal check again reports 54 passes and three missing-package failures
(glob, gray-matter, cheerio), no skips. Current policy and intent data remain
unchanged. Root must review this exact integrated head before shipping; the
real full-passed O1 and B2 activation gaps remain open, with no tag, Release,
remote release audit, publication, deployment or dispatch performed here.

Version impact: none

Reason: internal operational reference/model and release CI proof selection;
no Product Build, Assembly, Module, Contract, Provider or Host identity changes.
No intent data, existing signatures or historical release bytes are edited.

## Documentation Impact

This design draft and B1: Documentation impact: none — inactive prerequisites,
no current operation changes. B2: Documentation impact: required.

Affected portal pages:

- `/operations/testing-and-proof/`
- `/operations/version-and-release/`

B2 must update current documented behavior in the same Task as activation;
it creates no Product snapshot and does not authorize publication or deployment.

Design Task declares only this plan. Staged whitespace and ownership checks
pass (66 ownership tests). Its local docs-static advisory check does not run
product tests or confer release evidence. Implementation and real full-passed
candidate acceptance remain separately verified legs.
