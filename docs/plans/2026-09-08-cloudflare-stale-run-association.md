# Cloudflare stale run association

Relates to #968 and #922.

## Task

GitHub refreshes an old run's nested PR head after a push while keeping the
run's own build SHA immutable. Authenticate repository, workflow, event, pilot
branch and PR number; query the live PR and return superseded when closed or
moved. Only a currently publishable head proceeds to exact association-head
validation. No deployment/status operation is allowed before those checks.

Declared files:
- `scripts/ci/cloudflare_preview_publish.py`
- `tests/build/ci_cloudflare_preview_publish_test.py`
- `.agents/pitfalls/fake-tool-stub-strictness.md`
- this plan

Verification: run the publisher regression red/green, all four Preview Python
suites (55 tests), staged ownership and diff checks. A read-only real GitHub API
probe must classify build 34224803448 as superseded. After trusted-main delivery,
use the third and final authorized hosted attempt to rerun that original old
build; its fresh workflow_run must mark superseded and preserve current-head
success. This is the same pilot PR, not a new budget or broader activation.

No new gate, timeout increase or reduced publication validation is introduced.
The fake API omission bumps the existing pitfall; broader escalation #726 remains
open. Live failure run 34225091683/2 remains historical failure evidence.

## Version Management

Version impact: none; internal metadata interpretation only.

## Documentation Impact

Documentation impact: none; restores the already documented stale-completion
behavior without changing current Portal pages or generated source facts.
