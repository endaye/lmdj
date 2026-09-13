# R2b: sequential release transition driver

Status: locally verified protocol driver, stacked on durable journal `bd7d523d`.

## Scope

Connect the journal to a trusted backend protocol for the complete ordered
candidate, verification, intent, changelog, preparation, tag, Draft, publication,
published record, doc-site changelog, Runtime, Creator, promotion and final
verification sequence. The driver holds the journal lock across adapter calls.
An adapter must authenticate the original authority and current protection,
perform supported transitions with conditional identity checks, and independently
verify far-side evidence. Returning from execute is never success evidence.

Resume revalidates every saved receipt; no local complete flag is authoritative.
An unresolved intent may only be confirmed with exact verified evidence. Even
positive absence cannot justify replay of an ambiguous write. Read-only preflight
failure before intent creation is retryable by resuming the same request. A
service loop can poll pending work later; this driver does not spin or retry
mutations. Exceptions from writes produce a safe unknown result without leaking
upstream exception strings. Crashes preserve intent for reconciliation.

Declared files:

- `tools/release/orchestration_driver.py`
- `tests/build/release_orchestration_driver_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-orchestration-r2b.md`

Production adapters and the public CLI/service are subsequent integration work,
not implemented by this protocol driver. In particular a fake fixture is not
authentication, signing, complete CI, GitHub publication or deployment evidence.
This Task makes no external release mutations and does not waive review.

## Verification

Run `python3 tests/build/release_orchestration_driver_test.py` and the existing
journal suite. The separate filesystem fixture checks every named transition,
reopen, publication crash, missing/changed receipt, site-pending/Creator failure,
authority revocation, policy changes, malformed observations and unknown writes.
It preserves already-created artifacts across recovery and asserts no duplicate
publication, no skipped website step and no promotion after a failed Host.

Register the driver suite in CMake; existing deployment CI discovers
`release_*_test.py`. Run staged ownership, Python compilation, Portal check and
independent review. No test budget, threshold or gate is relaxed. Storage/API
fixture acceptance does not establish R5 live end-to-end acceptance.

Results on 2026-09-13: driver 13/13, journal 19/19, release model 28/28,
release skill 13/13, staged ownership 74/74; Python compilation and Portal check
(46 routes and internal links) passed. All commands exited 0. Independent review
of the final implementation and tests found no actionable findings. No new
pitfall entry: fault behavior is expressed directly by the regression tests.

### Delivery verification after R2 merge

R2 PR #1268 merged as `db0888670950bfa47a2486b861caef0d3d8977f1` after
authenticated review, recorded dispositions on both review discussions and
guarded squash. This R2b Task was replayed from `41e15c82` onto that main
without conflicts in `feat/release-driver-delivery`. The new write-side journal
capacity guard and its two regressions are retained unchanged.

- Driver: 13/13 in 0.244s; journal: 21/21 in 0.209s; both exit 0.
  Logs: `/tmp/lmdj-driver-delivery-tests.log` and
  `/tmp/lmdj-driver-delivery-journal.log`.
- Registered CTest: journal and driver both passed, 0.87s total, exit 0;
  `/tmp/lmdj-driver-delivery-ctest.log`.
- Model 28/28, release skill 13/13 and Python compilation passed.
- Staged ownership 74/74 in 7.903s, exit 0;
  `/tmp/lmdj-driver-delivery-ownership.log`.
- Independent complete five-file review found no actionable finding and
  independently reran driver 13/13 and journal 21/21, exit 0.
- Full Node 22 Portal check: 116/116 tests, production build and 46 routes /
  internal links passed, exit 0; `/tmp/lmdj-driver-delivery-portal.log`.
  Inspected the actual operations HTML for the driver paragraph and explicit
  fixture / production-adapter limitations. PR body lint and documentation
  impact declaration passed.

The driver crash case raises BaseException; actual subprocess death is covered
by the companion journal suite, not by a real publication. The backend fixture
uses separate filesystem artifacts. Final evidence remains the responsibility
of the trusted backend; this Task does not supply production authentication,
candidate/CI/signing/GitHub/Site adapters or the public CLI/service. No actual
release or deployment was performed. Earlier 19-test journal counts remain
historical, not substituted for the current 21-test result.

## Version Management

Version impact: none

Reason: internal release controller only; no Product, Assembly, Module, Host,
Provider or public Contract identity changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish implemented sequential driver from outstanding real adapters,
CLI, deployment and live acceptance.
