# Deterministic candidate snapshot clean-filter safety proof (#1873)

## Outcome and scope

Make the existing real-Git snapshot safety test exercise a replaced command
whose clean filter has refreshed the index stat cache. Snapshot recovery must
still refuse the raw-byte drift before executing the replacement or another
snapshot command.

The ordinary filtered diff can refresh the index after its filter returns the
committed blob. A subsequent filter-disabled diff may then trust matching stat
data. Its non-empty output is not an invariant; raw bytes matching the tested
Git tree is the invariant already enforced by `verify_tracked_bytes`.

## Task and declared files

One `fix/release-snapshot-filter-1873` Task and one Conventional Commit:

- `tests/build/release_candidate_snapshot_test.py`: give the replaced script a
  deliberately old mtime before the filtered diff, so it is not a racy index
  entry. Assert both Git observations are clean, then require the unchanged
  raw-byte refusal, absence of the replacement's marker and unchanged command
  history. Use the actual Git filter and index, without sleeps or mocks.
- This plan.
- `.agents/pitfalls/git-clean-filter-stat-cache.md`: retain the Git boundary
  behavior and point to the deterministic regression.

No production release code, timeouts, source identities or UI files change.
The M1 agent's Pad colour and Desktop Final work stays independently owned.

## Verification

Lowest-tier proof: the named snapshot safety test. First add only the old-mtime
fixture to reproduce the old assertion failure, then correct the assertion.
Run the whole snapshot module and the companion publication workspace suite.
Temporarily replace the snapshot raw-byte verifier with an actual unfiltered
Git-diff check in an isolated test process: the named test must fail because
the replacement script executes. Restore the original verifier by ending that
process; no production file is edited for this mutation proof.

Run staged path ownership, pitfall and documentation checks. After committing,
run every selected batch-only lane and retain its exact-input evidence before
current-head review and guarded squash merge. The changed regression catches
a snapshot guard that trusts Git's stat cache instead of the raw source bytes;
it does not add a new required workflow check.

## Version Management

Version impact: none
Reason: only a release test fixture, its assertions and process documentation
change; no Product, Contract, Module, Host, Provider or Assembly identity changes.

## Documentation Impact

Documentation impact: none
Reason: no Architecture Portal page or documented product behavior changes.

## Pitfall Impact

Pitfall impact: new git-clean-filter-stat-cache

## Release Impact

Release impact: none
Reason: this Task does not select a candidate, dispatch a self-test, tag,
publish, deploy or promote a Product Build.
