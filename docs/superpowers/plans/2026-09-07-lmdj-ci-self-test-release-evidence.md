# T7 — Complete self-test evidence for exact release candidates

Date: 2026-09-07
Status: implemented and independently reviewed; local release/CI/skill and exact-tree
Linux portal checks pass. No live release rehearsal performed.
Branch: `feat/ci-self-test-release-evidence`
Task commit: `feat(release): verify complete self-test evidence for exact candidates`

## Authority and boundary

Implements T7 of the CI capacity redesign plan and spec §7.1. This Task changes
release verification code only; it does not run release audit, hydrate, prepare,
tag operations, publish, deploy, promote, allocate a Product Build or edit intents.

The merge of this consumer and `prospective_ci_protocol=self-test-v1` policy is
the prospective cutover: every releasable intent must cite complete new evidence.
Old 14-lane full scope cannot be a fallback. The old producer entry may remain
until a separately authorized real producer/consumer rehearsal, but its continued
existence does not grant prospective release authority. Manual self-test evidence
works before the scheduled producer cutover. No live proof is claimed here.

## Implementation

- Resolve the recorded numeric run directly; target SHA is not necessarily the
  control SHA and is not a run-list query key under the new protocol.
- Validate canonical repository, stable workflow ID/path and metadata identity,
  main branch, completed successful run/attempt and verdict job. Dynamic names
  are display only. Control and target each need main ancestry; control must
  descend from producer deployment PR #757, squash
  `22247897e9163a3f34e15f564bec133419d1f177`.
- Read policy as data at trusted control and current main. Require the current
  applicable complete 16-suite protocol and reuse the producer's closed validator
  for schema, exact identity, complete jobs, status and canonical digest.
- Consume exactly one immutable target/run/attempt artifact with bounded ZIP
  size, duplicate-key rejection, independent repository/control binding and valid
  retention. Redirected blob GET receives no GitHub Authorization header.
- Owner-reviewed intents may optionally record closed `self_test_evidence` facts;
  new candidates require them. They bind control, attempt, request kind, policy
  and digest to existing exact target/run ID. New plan digests bind the reference.
  New publication markers use `lmdj.release-plan-marker.v2` and explicitly retain
  the complete CI reference, which fresh remote audit compares to the intent.
  Legacy v1 markers cannot substantiate newly appended self-test references.
- Published old rows keep legacy read-only semantics. Published new references
  remain independently checked against immutable tag/signature/Release/assets/plan
  marker; expiry never rewrites historical publication. A self-asserted ledger
  disposition alone is not proof of publication.
  New published history reads its exact recorded attempt, so later reruns do
  not rewrite it; prospective verification still checks the latest attempt and
  cannot hide a newly failed rerun behind a formerly successful attempt.
- Missing/expired evidence requests a new dispatch on main for the same target,
  then separately reviewed intent update. The current producer rejects reruns;
  do not combine successful jobs from different attempts or infer a pass.

## Declared files

`tools/release/{ci_evidence,github_api,self_test_protocol,model,audit,prepare,transitions}.py`,
`tools/release/policy.json`,
`tests/build/release_{self_test_evidence,ci_evidence,github_api,model,audit,prepare,transitions,skill}_test.py`,
`.agents/skills/lmdj-release/SKILL.md`,
`docs/governance/version-management.md`,
`docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md`,
`apps/architecture-portal/docs/operations/version-and-release.mdx`, this plan.

## Verification

New test first failed on the missing verifier interface before implementation.
Run all `release_*_test.py`, shared self-test contract tests, release skill
validation and portal check before shipping. Original scope-protocol regression
fixtures explicitly model pre-cutover policy; separate current-policy integration
tests must prove no legacy prospective bypass and fail before any mutation.

Verified on the supporting T4 stack `f27f7e3d3b24e8ee19cea48eb0ef1a5cb1f7d4af`:
320 release tests, 135 self-test protocol tests, 11 release-skill tests and the
skill-creator validator pass; the 18 current-evidence and 30 API tests are also
run independently. The earlier base's two Product snapshot-witness failures
disappear on this stack; no signature/proof requirement was weakened.
Independent review reproduced and closed the historical-audit marker-binding
defect using a separately constructed remote v2 marker, expired artifact and
later failed rerun, and checked zero remote mutations. It also checked canonical
attempt-job pagination without the unsupported latest-filter query.

After staging, all 66 scope/ownership tests pass. A Linux verification worktree
mirrored all 20 staged files with apply_patch; matching Git tree hashes proved
the validation input was identical. Portal install completed in 15 seconds;
the complete portal check passed 65 tests, 37 current pages, all 10 source
diagrams and 20 rendered outputs, Product snapshot verification, typechecking,
production build, and 42 routes/internal links. The initial documentation check
identified an internal marker schema name as a Product Contract; only that
portal wording was clarified, with no validator, manifest or test weakening.

Actual producer/consumer candidate rehearsal remains a separate remote
acceptance step, not implied by these local results. No new release operation
or live read-only release audit was run as part of this implementation.

Remote acceptance is separate and not executed by this Task: a real complete
same-target verdict, referenced only after validation, and read-only candidate
verification. No local fixture or API mock is a claim that GitHub publication,
artifact upload or candidate rehearsal has occurred.

## Version Management

Version impact: none — CI evidence/control-plane policy, not Product, Module,
Host, Provider or Contract identity. No release intent or snapshot changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/version-and-release/
The release skill update follows skill-creator's narrow navigation guidance;
the governance owns the protocol and authority rules. Daily testing does not
mean daily publication; tests do not gate PR merge; release remains manual.
