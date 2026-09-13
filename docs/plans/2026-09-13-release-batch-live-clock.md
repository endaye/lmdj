# Keep complete candidate evidence fresh through verification

Status: local delivery integration of original `d71f2e20`, based on the local
publication-effect delivery `ff9f9d78`. This Task has not yet been shipped.

## Scope

Declared files:

- `tools/release/batch_evidence.py`
- `tests/build/release_batch_evidence_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-batch-live-clock.md`

Keep the default clock live across reader reuse. Recheck each artifact after
download/decoding and all three origin/admission/verdict deadlines after actual
complete candidate validation. Retention is local to one verification. Explicit
fixture clocks remain supported. Historical published provenance still reads no
ephemeral artifacts and supplies no fresh candidate verdict or release authority.

## Verification

Use the actual complete candidate verifier, temporary Git, actual reducer and
the full sixteen-suite fixture bundle with fake GET and a controlled live clock.
Establish a valid baseline; mutate only reuse time, download time, earlier-origin
expiry during a later download, or time at final job validation. Assert refusal
after each boundary, and historical published mode after retention separately.
Run the complete existing suite, related contracts, staged ownership, Portal
check and independent review. This suite is already discovered by the Deploy
contract's `release_*_test.py` pattern; add no new general required gate.

The four negative cases were rerun on unchanged source in this delivery and
failed with missing refusal (4 failures, 5.823s, exit 1). Original-stack logs are
historical only. The corrected complete suite passed 73/73 (84.481s), exit 0.
Related actual effect 17/17 (17.586s) and Site evidence 22/22 (9.827s) passed.
Configure dev passed; the three registered effect/dispatch/Site contracts passed
3/3 in 58.73s with unchanged individual timeouts. These are not the batch suite
or a complete product CI execution.

Locked npm ci under Node 22.22.2 and Portal check exited 0; retained logs are
`/tmp/lmdj-batch-clock-delivery-deps-v1.log` and
`/tmp/lmdj-batch-clock-delivery-docs-v1.log`. Independent four-file review found
no actionable clock defect, rerunning the five new cases 5/5 (7.398s), not the
full 73-case suite. Ownership preflight remains required before commit.

## Version Management

Version impact: none

Reason: internal release evidence consumer only; no Product or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document complete-candidate retention and the historical boundary.

## Acceptance boundaries

No real CI dispatch, retention change, signing, release or deployment is performed.
This is not complete unattended-release acceptance. Separate inherited passive
reader concerns (Git ambient configuration and bounded ZIP decoding) need their
own causal reductions and fixes; this clock Task does not claim those guarantees.
Pitfall disposition: directly executable lifecycle regressions, no process entry.
