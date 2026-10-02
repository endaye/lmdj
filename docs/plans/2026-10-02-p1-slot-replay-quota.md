# P1 slot install receipt replay at a full Bank

Task: fix the current P1 slot-install candidate without changing its Facade surface.

A user can install one default slot, clear its original Pad and assign the same
Asset to another Pad. When that Bank exactly fills its prepared-PCM quota,
replaying the original command currently charges another residency and refuses
before the Store can recognize its persisted receipt. The replay must return the
original receipt and leave the current Project Truth unchanged.

## Declared files

- `packages/application-facade/src/application.cpp`
- `tests/core/facade/soundset_install_quota_test.cpp`
- `docs/plans/2026-10-02-p1-slot-replay-quota.md`

## Implementation and verification

For slot requests with an expected revision older than the loaded revision,
leave replay recognition to the existing Store path. It holds the writer lease,
compares the complete persisted command identity, and rejects an unknown stale
command before mutation. Project revisions advance monotonically, so this path
cannot admit a new write after the Facade read. All current/future-revision
requests retain the existing complete per-Pad Bank and Project quota checks.
Whole-Set install policy behavior remains in its existing quota path.

The lowest-tier regression uses the real Facade, fixture WAVs, persisted receipt
and a Bank quota of 11,520 prepared bytes. Its complete journey installs, clears,
reassigns, replays, and compares current Truth. It also proves that an unknown
stale command, a changed identity under the original id, and a fresh over-quota
write all refuse without changing Truth. The test against unchanged 501cba3d
libraries fails at the replay success assertion. Rebuild the changed libraries
and run both Facade Sound Set binaries plus the Store install binary; retain
raw exit statuses and all prior failure evidence.

No new required gate or budget change is introduced. Shipping still requires
the committed candidate's selected batch-only lanes, current-head review,
conversation resolution and protected guarded merge.

## Version Management

Version impact: none. This corrects an unshipped P1 candidate's existing receipt
semantics, adds no operation or Contract, and leaves coordinated P1 Module and
Product version allocation to the integration Task.

Documentation impact: none. No portal route, documented operation shape,
architecture boundary or deployment configuration changes; this plan records the
internal defect and verification.

The defect is product logic represented by the regression, so it does not
qualify for a process pitfall ledger entry.
