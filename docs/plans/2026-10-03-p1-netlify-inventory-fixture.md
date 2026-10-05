# P1 Netlify inventory fixture ordering

The current P1 complete Deploy Contract proof found that the mocked inventory handler replies before changing its Site pointer. A subsequent real HTTP Site read can consequently return the old pointer, so the existing strict before-draft refusal journey accidentally reaches the later before-publication refusal. This is a fixture ordering defect, not evidence that the production pointer protection failed.

## Declared files

- `apps/creator-web/test/deploy_command_test.py`
- `apps/web-runtime-host/test/deploy_command_test.py`
- `docs/plans/2026-10-03-p1-netlify-inventory-fixture.md`

## Verification

Use a controlled threaded HTTP response boundary to require the next Site read before the inventory handler returns. Both unchanged original tests must fail on the original fixture at their strict inventory-refusal assertion and pass after moving the controlled pointer mutation before the published response. Keep every original assertion, including absence of draft creation, and every original budget. Execute both complete deploy command suites plus staged ownership and whitespace checks before commit. On the clean committed candidate run the complete current Deploy Contract lane without caching; retain the original Linux failure and both controlled counterexamples. This isolated Task changes no production deployment command, release identity, real remote service or runtime behavior.

## Version Management

Version impact: none. Only the HTTP fixtures and their plan change; no Product Build, module or Host manifest is allocated.

Documentation impact: none. Fixture ordering does not change documented product, deployment or architecture behavior; the production pointer checks remain unchanged.
