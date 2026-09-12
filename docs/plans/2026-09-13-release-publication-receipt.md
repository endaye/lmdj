# R3c.2: collect exact verified Release publication records

Status: locally verified implementation, stacked on portal projection `64c13a9f`;
not pushed, merged, or production-exercised.

## Scope

Expose `scripts/release.sh publication-record TAG RELEASE_ID PLAN_SHA256` as an
external read-only collector. It uses the same complete published verifier,
including signed exact tag, full CI evidence, asset inventory/digests, canonical
intent and frozen body. The verified API projection supplies numeric Release ID
and published_at; the local clock is never substituted. The resulting canonical
JSON entry is validated by the doc-site publication consumer's existing schema.

Retain optional published_at in the GitHub API projection without requiring it
for historical verification. The record collector requires a valid actual date.
Compare the initial and fully verified final Release projections and intents:
re-drafting or changing metadata/authority mid-verification cannot produce a
published result or receipt. Publication transitions themselves continue to
allow the normal Draft→published timestamp change.

The command does not edit ledger/publication files, create a Release, publish,
deploy, or claim the site is online. Existing context construction refreshes
canonical Git authority locally, as for other stable verification commands.
The reviewed evidence-PR updater, online site smoke, forced new-release admission
and complete real-driver/service wiring remain unfinished.

Declared files:

- `tools/release/github_api.py`
- `tools/release/transitions.py`
- `tools/release/publication.py`
- `tools/release/cli.py`
- `tests/build/release_publication_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/governance/version-management.md`
- `docs/plans/2026-09-13-release-publication-receipt.md`

## Verification

Run publication tests, existing transitions/GitHub API/changelog binding tests,
staged ownership, Python compilation, Portal check and independent review.
The journey covers prepare→Draft→publish fixture→collect→same-record resume→
portal projection; external mutation counters and exact assets/tag/body/ledger
must remain unchanged during collection. Faults cover missing or malformed API
date, Draft, body drift and re-drafting/date drift between observations. CLI
must emit one canonical record, not a release/site completion status.
Mock API and signing fixtures are not production authentication or acceptance.
No gate or timeout is loosened.

Results: publication 10/10, transitions 66/66, GitHub API 39/39,
changelog binding 13/13, release skill 13/13 and staged ownership 74/74 passed
(exit 0). Python compilation passed. Full Portal check passed 124/124 tests,
production build, and 47 routes/internal links (exit 0). Evidence logs are
`/tmp/lmdj-receipt-{publication-final,transitions,api,binding,docs-check}.log`.
Independent reviewer `/root/release_journal_review` inspected the complete nine
files and found no actionable finding; it reran publication 10/10 and previously
transitions 66/66 and API 39/39. No production API or signing was exercised.
The re-draft/date race is expressed by regression tests, so it adds no separate
process-only pitfall entry. Shipping remains stacked behind unmerged PR #1266.

## Version Management

Version impact: none

Reason: internal read-only release interface; no Product Build allocation,
Module, Host, Provider or public Contract identity changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document record collection and distinguish its verification from the
unimplemented evidence-PR and public-site transitions.
