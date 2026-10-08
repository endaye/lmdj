# Build 87 current-policy candidate evidence

## Problem and scope

Build 87 remains the exact P1 protected-main candidate
`5abc52106728f463768210eb4186777a0b44ad7f`, Product `2.0.87.0`, tag
`lmdj-v2.0.87.0`, canary publication with the `web-hosts` profile. The complete
R1 candidate result passed under its original scope policy. After PR #1858
changed the prospective policy, the release audit correctly refused that older
reference for a new release. PRs #1867 and #1872 repaired the independently
confirmed controller transport failure without reducing writer authentication,
the shared retry budget, selected suites, or release gates.

This evidence-only Task binds the supported same-target R2 candidate request,
`p1-release-build87-5abc-20261007-r2`, only after canonical verification of its
complete original artifact chain and all 16 suites. It preserves the historical
R1 pass and failures, frozen target, immutable snapshot, approved changelog,
and owner-accepted retained-distribution risks in #1860 and #1861.

## Declared files

- `docs/release-evidence/release-intents.json`: replace only Build 87's
  `merged_main_run_id` and `batch_test_evidence` with the authenticated source.
- `docs/release-evidence/lmdj-v2.0.87.0-canary-release-intent.md`: record the
  current qualifying source and retain historical and deferred evidence.
- `docs/plans/2026-10-08-build87-current-policy-evidence.md`: this Task boundary
  and verification record.
- `.agents/pitfalls/documentation-impact-means-portal-pages.md`: record the
  corrected Portal impact declaration recurrence.

No Product source, approved notes, immutable snapshot, release assets, tag,
Release, deployment, or promotion changes belong to this commit.

## Verification and acceptance

1. Independently verify R2's original origin and admission controller artifacts,
   exact executor event/control/attempt, complete verdict/execution/needs bundle,
   authenticated API jobs, current policy agreement, main ancestry, and all 16
   passing suites with no verification debt. A pending or summary-only result
   does not qualify.
2. Parse the updated ledger through the canonical release model; compare the
   entire ledger against its original bytes and prove that only the two declared
   fields of the selected entry changed. Check the approved changelog and notes
   digests, target and snapshot are unchanged.
3. Run the existing release model/batch binding suites and path ownership test,
   then `scripts/docs-site.sh check` for the projected release facts. Run every
   selected batch-only lane on the committed head and retain its emitted pass
   key in the Pull Request.
4. Ship one Conventional Commit through current-head independent review,
   conversation/conflict/protection checks, and guarded squash merge. Keep
   #1864 related until the later fresh exact-tag remote audit actually passes.
5. From reviewed main, run `scripts/release.sh audit --remote --tag
   lmdj-v2.0.87.0`. A passing audit is #1864's final recovery assertion and the
   prerequisite for separately verified release transitions.

Execution evidence: canonical verification of executor `37676506324/1` passed all 16 suites without debt. The actual event is `schedule`, the control is `f095c098ffee24ee141bc7c0c8310aa43d14824e`, and the canonical reference SHA-256 is `61351e67c0490a679a1638d399a264beb4ea20b7618b64fa29c84aad4bdb17eb`. Canonical ledger preservation checks passed. The existing release model (28), batch binding (14), and path ownership (77) tests passed; `scripts/docs-site.sh check` passed its build and all 49 routes/internal links. Committed-head batch-only evidence and independent review follow through the Pull Request. The later post-merge exact-tag audit remains a separate acceptance assertion.

## Version Management

Version impact: none. This Task updates release qualification evidence for the
already allocated Build 87. Product, Assembly, Module, Host, Contract, Provider,
and Model identities and immutable snapshot bytes remain unchanged.

## Documentation Impact

Documentation impact: none

Reason: the refreshed operational qualification reference changes no current
Portal content or projected Product identity. The public release pages follow
actual publication in their own evidence Task. Existing Portal source references
were checked against the diff; the build and route/link check passed.

## Pitfall Impact

Pitfall impact: recurrence — the first PR declaration incorrectly equated a
release-evidence edit with a current Portal page change. The Documentation impact
gate correctly refused it. This Task records the eighth recurrence in
`documentation-impact-means-portal-pages`, retaining its existing skill exit,
and validates the corrected body against the complete changed-file list before
pushing a fresh head.

The initial committed-head Deploy Contract attempt failed because the inherited
PATH contained the literal relative entry `~/.dotnet/tools`. A failing source
setup test passed with an absolute command-local PATH. The complete lane must
be rerun on the corrected committed head using the same Python and Node tools;
no gate, test, timeout or suite selection is relaxed.

## Authority and deferred acceptance

The Owner authorized #1864's implementation Git chain and the complete Build 87
release/deployment sequence. Each release transition still requires its own
verification; this evidence commit performs none of those transitions.
Physical browser/device/hearing journeys remain deferred in #1851–#1854, and
the accepted local proof failures in #1860/#1861 remain failures. This Task
asserts neither physical acceptance nor stable promotion.
