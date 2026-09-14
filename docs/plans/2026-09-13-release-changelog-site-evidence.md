# R3c.5: authenticate retained Portal changelog deployment evidence

Status: delivery in progress on main `676874c3`; replay of `606f9bfe`.
Producer PR #1275 is merged. Production controller configuration is not enabled.
Results below are original-stack history, not this delivery's verification.

Current delivery baseline: 16/16 consumer tests passed. A real partial clone
with no ledger blob then reproduced implicit object hydration by `verify`
(the expected refusal was absent). Added `GIT_NO_LAZY_FETCH=1` and empty
`GIT_ALLOW_PROTOCOL` to the sanitized Git environment, matching the source
changelog reader's existing passive-read boundary. The regression verifies a
normal successful consumer first, confirms the clone's blob is absent, then
requires refusal and byte-identical object inventory. Consumer 17/17 now pass.
An additional real-Git regression confirms the empty protocol allowlist also
prevents hydration without Git's newer no-lazy-fetch flag (18/18 passed).
Independent review then reproduced two expiry defects: a reused consumer froze
construction time, and evidence expiring during download still returned success.
Both new regressions failed before the fix. Default time is now read live and
retention is rechecked after final run/main observations; explicit fixture time
remains deterministic. Delivery consumer tests pass 20/20, independently rerun
20/20 by `/root/release_journal_review` after full six-file inspection, with no
remaining actionable finding. CMake configuration and four selected CTest suites
(native changelog installer, site evidence, publication evidence, publication)
pass. API 39/39, batch evidence 68/68, page projection 7/7 and staged ownership
74/74 pass. After the dependency baseline advanced, a clean locked npm install
was repeated with Node 22.22.2 (the first used ambient Node); 27 existing audit
advisories remain (9 moderate, 18 high), with no audit fixes or dependency edits.
`scripts/docs-site.sh check` passes 144/144 tests, production build and 47 routes
and internal links. All reported delivery commands exit 0; the two pre-fix expiry
tests and the pre-fix hydration regression failed as expected. Raw delivery
command returns are retained in the agent execution transcript, not the older
log paths below. No real release, provider, remote artifact or live-site
acceptance is claimed; commit and current-head PR review remain pending.

PR #1276 review run `34743493795/1` on `b626ee10` published successfully.
Independent reproduction confirmed its ZIP resource-bound finding: a forged
small central-directory size permits an unbounded `archive.read` to inflate a
large stream before truncating to the declared size. The real-consumer regression
failed with a requested decompression limit of 1 GiB. Decoding now uses a bounded
member read and accepts only stored/deflated ZIP methods; BZIP2/LZMA's stdlib
decoders do not honor that output limit and are refused. The companion pagination
finding is false: an independent real `pages()` exercise returned 10,000 rows in
exactly 100 calls, pages 1 through 100; Python's range stop is exclusive.
Amendment verification passes: consumer 22/22, selected CTest suite 1/1 and API
39/39 (all exit 0). Independent `/root/native_output_review` inspected the three
amended files, independently ran 22/22 and replayed the forged stream: actual
decompression output is now bounded to 2,097,153 bytes instead of about 16 MiB.
No remaining actionable finding. Portal content/tooling is unchanged from the
delivery's full 144-test/47-route check; current-head PR rereview remains pending.

## Scope

Add a read-only consumer and closed GitHub GET transport. Reviewed controller
configuration supplies numeric repository/workflow identities and the minimum
trusted producer commit; no artifact may select them. Authenticate protected
main ancestry using real Git without executing source code or fetching objects.
Derive the complete expected page inventory and source hashes from the source
commit's ledger and publication records. The selected publication must match
the caller's freshly verified Release record and descend from its target.

Require the exact successful first-attempt main push, successful deployment
steps, unique unexpired artifact, API SHA256 matching bounded downloaded ZIP,
and exact safe member identity. Validate Preview/production URLs, Worker version,
every page's source/response identity and matching rendered-content hashes.
Reobserve run and protected main at the end. Incomplete run is pending; missing
observations are unverifiable; conflicting evidence never yields success.

The authenticated producer owns HTML comparison; this consumer does not
independently reconstruct rendered content from response hashes. It certifies
retained observations, not current live Worker state. Production backend
configuration, merged evidence-PR authentication, fresh live-site smoke and
driver admission remain required. No release, deployment, PR or signing action
is introduced. Append-only corrections and the complete run/resume journey are
still unfinished.

Declared files:

- `tools/release/changelog_site_evidence.py`
- `tools/release/github_api.py`
- `tests/build/release_changelog_site_evidence_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-changelog-site-evidence.md`

## Verification

Use real temporary Git histories and the production GitHub transport with
fixture API responses and ZIP bytes. Assert successful repeated reads do not
mutate Git, and independently reject identity, step, retention, archive, page,
publication and mid-observation state drift. API errors must not expose secrets.
Run API/batch/site regressions, staged path ownership, full Portal check and
independent read-only review. These fixtures do not prove real GitHub artifact
availability, public HTTPS state or release-controller operation.

### Original-stack verification history (not delivery evidence)

Initial fixture run failed because the synthetic ZIP response lacked the
required Content-Type; corrected the fixture, not the production check. Logs
remain `/tmp/lmdj-site-evidence-tests.log` and subsequent `-v2`/`-v3` logs.
Consumer tests passed 16/16, API regressions 39/39, batch evidence regressions
68/68, page projection 7/7, staged ownership 74/74 and Python compilation
(all exit 0). Independent reviewer `/root/release_journal_review` inspected
all six files, independently ran the 16 consumer tests, and found no actionable
finding. No remote API or provider was called during review.

The first Portal check used an incorrectly narrowed command PATH and selected
system Python 3.9, failing the existing StrEnum import. The rerun restores the
existing Python 3.11 PATH while selecting Node 22; no test/code relaxation.
Original failure remains `/tmp/lmdj-site-evidence-docs.log`. The existing locked
npm install reported 27 dependency advisories; no unrelated dependency changes
or automatic audit fixes are included. These are not resolved by this Task.

Full Portal rerun passed 139/139 tests, production build and 47 routes/internal
links (exit 0), retained in `/tmp/lmdj-site-evidence-docs-v2.log`. Other raw
results use `/tmp/lmdj-site-evidence-` with `tests-v3`, `api`, `batch`,
`projection` and `scope` `.log` suffixes. No suite was skipped to obtain these
results; real release/deployment acceptance remains unexecuted.

The Task's rejection invariants are expressed in regression tests; no new
process-only pitfall entry is needed. At that historical point, the stack remained
local behind PR #1266's unresolved review-adoption boundary; the user subsequently
merged #1266, and this delivery is based on the later merged producer #1275.

## Version Management

Version impact: none

Reason: internal read-only evidence verification; no Product Build, Assembly,
Module, Provider or public Contract identity changes and no snapshot mutation.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish authenticated retained observations from live-site proof.
