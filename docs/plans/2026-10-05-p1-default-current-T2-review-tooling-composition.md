# Default streaming with current T2 review tooling

## Problem and Task

The checked default-streaming head `378a5609f5d5e44d4f38d04d72b167e7a83ca54a`
contains the corrected offline inventory portal but retains the previous T2 review
tooling. Compose actual current T2 `ec85ac924953fa59e308acb58b6b3169e61108f9`
through a real two-parent merge. It imports the already integrated diagnostics
archive/reader-provenance fixes and their declarations; no Product Source changes.
Newly observed Main `57f8803599a2eedee0312582971125a3596840f3` is read for current
governance, but no strict-update obligation or unimported Source is claimed.

## Declared files

- `.agents/pitfalls/review-input-generated-bytes-exhaust-limit.md`
- `.github/workflows/pr-review.yml`
- `docs/plans/2026-10-05-p1-slot-main-portal-provenance-composition.md`
- `docs/plans/2026-10-05-p1-slot-main-review-artifact-composition.md`
- `scripts/ci/review_wait.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `tests/build/ci_review_wait_test.py`
- `docs/plans/2026-10-05-p1-default-current-T2-review-tooling-composition.md`

## Verification

Run original complete review reader and workflow suites plus ownership75 after
staging. They catch artifact producer/consumer and latest-provenance admission
regressions and uncovered paths. Inspect whitespace and authenticate every
preexisting entry outside the declared imports against378; all seven imports
match exactec85 mode/blob. Inspect real ordered parents, committed files/tree
and clean source; derive current complete-PR keys and validate the actual body
before normal FF push. Source/lower/whole/adoption evidence from previous heads
retains its own identity; no old key or report is relabeled current.

The initial merge was attempted before worktree creation finished and refused its
owned index lock before modifying Source. Creation finished normally; the exact
pristine Source was revalidated and the supported merge completed. No lock was
removed and no Product verification ran during that refusal.

## Version Management

Version impact: none. Existing Product/Module/Host/Provider/Contract identities
and immutable snapshot bytes are exact378; this Task allocates none.

## Documentation impact

Documentation impact: none
Reason: only existing Main review control-plane bytes and their declaration plans
are composed; no current portal page/diagram/source fact/identity changes.

## Acceptance boundaries

Current committed full selected obligations and independent review remain
required. Subsequent capture/System composition, coordinated T8 identities and
whole-P1 browser/offline/physical/hearing acceptance remain unfinished. This Task
initiates no release, Creator production deployment or Channel promotion.
