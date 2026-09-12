# R3c.4: verify rendered release changelogs through the existing Portal smoke

Status: locally verified implementation, stacked on evidence patch producer
`a77339af`; not pushed, merged or production-exercised.

## Scope

Extend the stable `scripts/docs-site.sh smoke BASE_URL` entry point used by the
existing Git-triggered Cloudflare deployment for both version Preview and
production. Load the existing validated Python projection and compare the
index and every recorded release page's rendered text, category structure and
link targets with that frozen source. Compare actual content, not just matching
digest strings: a page retaining labels but changing notes must fail. Rendering
uses the already locked MDX compiler (now a declared direct dependency).

Only Docusaurus heading navigation and whitespace formatting are normalized;
missing/duplicate documentation roots, hidden inline content, executable
elements, altered categories, identities, digests and links fail. HTTP GETs are
HTTPS-origin-only, credentials omitted, no redirect following, exact 200 HTML,
10-second timeout and 8 MiB decoded-body ceiling. Errors expose no response
body or transport detail. Successful receipts bind route, source and rendered
content hashes plus observed HTTP bytes/hash. A failed route never gets a
successful receipt. This is static HTML content proof, not visual/browser or
deployment ownership proof; normal snapshot/asset smoke remains intact.

The build checker uses the same comparator on generated HTML before upload.
This local result never substitutes for the two real HTTP observations. No
new deployment trigger, secret, upload or Environment rule is introduced.
Existing Cloudflare evidence still owns exact Git/Worker version correlation;
its Preview and production observations retain the validated per-page receipts
from the smoke subprocess, with exact source revision and URL checks.
the release driver must later authenticate that evidence and the merged
publication PR before accepting changelog_site and admitting Host deployment.

Declared files:

- `apps/docs-site/scripts/lib/release-site-smoke.mjs`
- `apps/docs-site/scripts/smoke.mjs`
- `apps/docs-site/scripts/check-build.mjs`
- `apps/docs-site/test/release-site-smoke.test.mjs`
- `apps/docs-site/package.json`
- `apps/docs-site/package-lock.json`
- `scripts/cloudflare-portal-deploy.py`
- `tests/build/ci_cloudflare_portal_deploy_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-changelog-site-smoke.md`

## Verification

Run new Node tests, existing smoke/changelog tests, lockfile install check,
full Portal check, staged ownership and independent review. The local HTTP
fixture exercises actual streamed responses: failed site→same-source retry→
verified pages, with GET-only observations throughout. Assert actual notes
changes fail even with retained digests, each identity/link mutation fails,
status/MIME/redirect/size/encoding failures get no receipt, and untrusted error
details do not escape. Fixture transport is HTTP loopback under an injected
fetch; the production entry requires HTTPS without exceptions.

No real release/deployment is performed. New-version browser rendering, real
public HTTPS, authenticated deployment receipt admission and the complete
release driver's recovery journey remain separate acceptance obligations.
This change does not loosen existing tests, timeouts or release gates.

Results: new Node smoke tests 15/15, existing-and-new Cloudflare deployment
fixture tests 15/15, staged ownership 74/74, Python compilation and offline
lockfile resolution passed (exit 0). Full Portal check passed 139/139 tests,
production build and 47 routes/internal links including the built release
index's content comparison (exit 0). Logs:
`/tmp/lmdj-release-smoke-tests-v3.log`,
`/tmp/lmdj-release-smoke-deploy-tests-v2.log`,
`/tmp/lmdj-release-smoke-scope-v2.log`,
`/tmp/lmdj-release-smoke-docs-check-final.log`.

An additional isolated real Docusaurus build rendered the Python fixture's
index and version page; both passed the content comparator (exit 0). Retained
script and output: `/tmp/lmdj-release-smoke-docusaurus-fixture.mjs` and
`/tmp/lmdj-release-smoke-docusaurus-fixture-v3.log`. First iterations failed
because the minimal fixture lacked its navbar home route, then in static
generation while sharing the installed modules/cache across temporary sites.
Added the fixture home and disabled webpack cache only in this temporary
fixture; production cache policy and broken-link checks were not changed.
Earlier logs remain in the same prefix without a suffix and with `-v2`.
This is real local theme rendering, not a public HTTPS or browser acceptance.

Independent reviewer `/root/release_journal_review` found two false positives:
arbitrary hash-link content was ignored and the documentation root's hidden
attribute was missed. Strict direct-heading/fragment/glyph checking and
root/ancestor concealment checks fixed both, with regression tests. Final
review found no further actionable finding across all ten files and reran the
15 Node and 15 deployment fixture tests. These source invariants are expressed
by regressions; no new process-only pitfall entry was added. The stack remains
local behind PR #1266.

## Version Management

Version impact: none

Reason: internal Portal verification tooling; no Product Build, Assembly,
Module, Provider or public Contract change and no immutable snapshot mutation.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document content smoke integration without claiming production proof.
