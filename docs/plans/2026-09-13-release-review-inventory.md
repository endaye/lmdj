# Complete publication PR review inventory

## Scope and defect

The managed publication PR requires a trusted review gate, but current-head
eligibility explicitly leaves findings, conversations and closing relations
unevaluated. Reading only that result or the first page cannot supply the gate.
Add a read-only, exact-head GraphQL collector for every submitted/pending review,
issue comment, review thread and each thread's comments, plus qualified closing
Issue identities. Preserve older-head, dismissed, outdated and resolved content;
these flags do not establish a disposition.

Use fixed query documents and canonical GitHub transport, closed operation
selection, bounded complete pagination and two identical full observations.
Every page binds the same open PR/head/repository; nested comments bind their
thread and PR. Refuse partial GraphQL errors, truncation, duplicates, cursor
loops, changing counts/content and exhausted budget. Return private input data
and its digest, never a merge approval or a public log of review text.

Declared files:

- `tools/release/review_inventory.py`
- `tools/release/github_api.py`
- `tests/build/release_review_inventory_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-review-inventory.md`

## Verification

Production collector and HTTP client over fake GraphQL responses: pagination
at all levels, old/dismissed/resolved findings retained, nonempty closing
inventory, exact source binding, partial errors, duplicate/loop/truncation,
same-count edits, head changes, budget and transport rejection. Rerun PR and
managed-controller regressions, staged ownership and Portal check. Read-only
live collection on an existing PR verifies query compatibility, not review
eligibility, mutation, historical-merge proof or release acceptance.

Remaining integration: authenticate current-head eligibility, evaluate actual
finding dispositions and effective protection, retain/revalidate historical
review receipts, and assemble the production release backend. Two matching
reads detect observed drift but are not a GitHub transaction or TOCTOU lock.

### Verification result

- Inventory 21/21, exit 0: `/tmp/lmdj-review-inventory-tests-v1.log`.
- PR controller 23/23, managed transition 16/16, GitHub API 39/39 and staged
  ownership 74/74, all exit 0: `/tmp/lmdj-review-inventory-{pr,managed,api,scope}.log`.
- Portal 139/139, production build and 47 routes/internal links passed, exit 0:
  `/tmp/lmdj-review-inventory-docs.log`.
- Independent read-only review inspected all six files, found no actionable
  finding and independently reran inventory 21/21, PR 23/23 and managed 16/16.
- Live canonical GitHub read-only check collected PR 1266 at exact head
  `c8fab3b67b6abe3bff708b5563acfc84b0e9e671`: all four inventories empty;
  canonical inventory digest
  `acdc8bb0ee3daf2f8ab4b420f06e1cbb56eea890ac45d0b778a4023e59ff8bd3`.
  This is not review approval. A separate read of an existing PR 1243 thread
  returned two inline comments; both passed the production node validator.
  These tool transcripts prove actual query/field compatibility only, not live
  multi-page or concurrent-edit behavior, historical acceptance or a merge.

Pitfall disposition: the input collection invariant is expressed directly by
the pagination/identity/drift regressions; no separate process-only entry.
No GitHub mutation, provider call, signer use, release or deployment occurred.

## Version Management

Version impact: none

Reason: internal read-only release review input; no Product or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish complete review inventory from eligibility and approval.
