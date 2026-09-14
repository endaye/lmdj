# Complete publication PR review inventory

Status: delivery integration of original `18638172` on actual managed-PR squash
`cd11f5129d750169863e76ac7cf9a69ff6471bf8`. Original-stack results below remain
historical and do not substitute for current six-file delivery verification.

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

### Historical original-stack verification result

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

## Delivery integration and verification

Retain current GitHub client and all prior CMake registrations; the old-stack
CMake insertion conflict is resolved without dropping the Task verifier or
changing any timeout. Initial delivery tests passed inventory 21/21, PR 36/36,
managed transition 17/17 and API 39/39, all exit 0.

Independent complete six-file review found that two different threads could
contain comments with distinct node IDs but the same numeric comment identity.
A new single-fact regression changed only the second thread's `databaseId`;
the original collector incorrectly accepted it (1 failed, exit 1, retained tool
transcript). Add cross-thread numeric-ID uniqueness for ReviewComment objects
only, alongside existing node-ID uniqueness. Inventory then passed 22/22 in
0.014 seconds; independent re-review reran 22/22, confirmed the finding resolved,
and found no remaining actionable issue. API 39/39 and registered CTest 1/1
(Python 3.14.7, 0.11 seconds, unchanged 30-second limit) passed after the fix.

Staged ownership/admission passed 74/74 in 6.838 seconds. Locked Node 22.22.2
installation and full Portal check passed 144/144 tests, metadata for 47 pages,
10 diagrams/20 outputs, snapshot consistency, typecheck, production build and
47 routes/internal links, exit 0. No snapshot or Product identity was allocated.

The actual collector/client also performed read-only live query validation on
open PR 1285 at exact head `c141e693934df5c73340411ed5023c8e4faf206a`, repository
ID 1286600062: one review, zero issue comments, two threads with two comments,
zero closing relations; digest
`34e4d7c8fac0781d6ecc5f047db4ec32b852a1a6b56680d8959afe2aa2781cf1`.
This check preceded the numeric-ID fix, whose query documents did not change;
it proves current field compatibility, not live multi-page behavior or approval.
Review bodies were not emitted by this compatibility probe. Full production
review disposition/protection composition and release acceptance remain open.

After PR 1285 merged, rebase onto actual squash `cd11f512` without conflicts;
the complete tree is identical to pre-rebase delivery `c40e163a`. Repeat current
inventory 22/22, API 39/39, PR 36/36 and managed 17/17 (all exit 0); the Portal
result above describes the same source tree, not a different historical stack.

## Version Management

Version impact: none

Reason: internal read-only release review input; no Product or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish complete review inventory from eligibility and approval.
