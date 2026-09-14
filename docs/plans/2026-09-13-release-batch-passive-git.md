# Keep batch provenance Git reads local and canonical

## Scope

Declared files:

- `tools/release/batch_evidence.py`
- `tests/build/release_batch_evidence_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-batch-passive-git.md`

Build on the live-clock Task `434caf20`. The consumer claims passive reads from
an existing complete checkout, but currently inherits ambient Git configuration
and permits partial-clone lazy fetches. Isolate the subprocess environment and
forbid every transport independently of Git's support for GIT_NO_LAZY_FETCH.
Do not fetch missing objects, execute source, change shared Git configuration or
make live GitHub/host requests. Missing provenance remains unverifiable.

## Verification

First run actual-Git causal regressions on unchanged source: ambient GIT_DIR
must not select another repository, and a real filtered clone missing a blob
must not contact a loopback HTTP observer. Establish that ordinary Git does
contact that observer, then exercise the actual consumer entrypoint and require
zero requests and still-missing local objects. Remove only GIT_NO_LAZY_FETCH
from its child environment to independently test the protocol prohibition.
Run the complete batch suite, related consumer tests, ownership, Portal and
independent review. Preserve the clock regressions and published-history path.

ZIP bounded decoding remains a separate known follow-up; this change does not
claim that resource boundary or full release acceptance. No general CI gate,
timeout change, external credentials, release, deployment or retention change.

## Version Management

Version impact: none

Reason: internal read-only provenance transport; no Product or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: state the verified local-only Git evidence boundary.

## Verification results

The unchanged-source two-case reduction failed with one error (ambient GIT_DIR
selected the empty foreign repository) and one failure (a real HTTP request
escaped from the partial clone), 1.515s, exit 1. After the fix, both passed in
1.402s. The full batch suite passed 75/75 in 63.410s; related batch binding
14/14 in 20.501s and dispatch evidence 34/34 in 7.320s also passed. All green
commands exited 0. Full-suite output: `/tmp/lmdj-batch-passive-git-tests-v1.log`.

Independent complete four-file review found no actionable finding and reran
the two real-Git regressions 2/2 (1.435s); it did not repeat all 75 tests.
No external host/provider was accessed: only temporary local Git and loopback
HTTP were used. Staged ownership passed 74/74 (11.395s); locked npm ci and
Portal check under Node 22.22.2 exited 0, including 144 tests and 47 routes.
Logs: `/tmp/lmdj-batch-passive-git-scope-v1.log` and
`/tmp/lmdj-batch-passive-git-docs-v1.log`.
Pitfall disposition: executable reader invariants, not new process knowledge.
