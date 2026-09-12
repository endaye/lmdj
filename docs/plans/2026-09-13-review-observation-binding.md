# Bind review eligibility to complete observed bodies

## Scope

The release review gate must connect the existing current-head eligibility
verifier to the complete GraphQL inventory. Numeric review/comment IDs alone
do not establish that both readers observed the same text. Add UTF-8 SHA-256,
byte length and API author identity to each eligible evidence item, then bind
every such item to exactly one complete-inventory object. Preserve unlinked
reviews/comments and thread/closing counts for subsequent disposition checks.
Bind repository numeric identity and GraphQL User/Bot author database IDs too;
same-name objects are not a substitute for the identities verified by REST.

This is an observation binding, not stronger authentication of a review's
free-form footer, semantic disposition, effective protection, historical review
acceptance or merge authority. A caller must use the real trusted eligibility
verifier and collector, not pass self-declared JSON as authority. The binder
never returns a merge-eligible flag and cannot replace the remaining gate.

Declared files:

- `scripts/ci/review_wait.py`
- `tools/release/review_inventory.py`
- `tests/build/ci_review_wait_test.py`
- `tests/build/release_review_inventory_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-review-observation-binding.md`

## Verification

Actual eligibility reader with retained artifact fixtures; then bind its
output to a GraphQL-shaped full inventory. Cover automated review and owner
records, exact UTF-8 byte identity, same-ID body changes, wrong author/head,
missing observations and preservation of unlinked content. Existing inventory,
PR, managed-driver, ownership and Portal regressions remain applicable.
No provider call, GitHub write, release or deployment is part of this Task.

## Version Management

Version impact: none

Reason: additive internal observation fields and binding only; no Product or
Assembly change and no relaxation of review eligibility.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: clarify what the complete-text observation bridge proves and leaves open.

## Verification evidence

Independent review identified a real cross-API representation mismatch. A
read-only comparison of PR #1243 thread comments returned GraphQL Bot login
`github-actions`, database ID `41898282`, versus REST `github-actions[bot]`,
ID `41898282`, type `Bot`; the owner returned `endaye` / `4829591` in both.
These observations establish API shape compatibility, not historical review
eligibility. No provider request or GitHub mutation was made.

The new Bot projection test failed against the original binder (69 tests,
one error: `body author differs`). Only authenticated automated evidence now
accepts the REST `[bot]` suffix difference. Numeric author identity is still
mandatory; owner records receive no suffix normalization. The three new tests
cover the success case, wrong numeric ID, and owner rejection. Current reader
and binding tests: 69/69, exit 0. Raw local logs:
`/tmp/lmdj-review-binding-bot-red.log` and
`/tmp/lmdj-review-binding-tests-v3.log`.

Pitfall disposition: no separate entry. The regression tests fully express
this API representation invariant, including its negative boundaries; no
additional process rule is needed.

Final local verification: eligibility/binding 69/69; inventory 21/21; evidence
PR 23/23; managed PR transition 16/16; staged ownership 74/74, all exit 0.
Portal check exited 0 with 47 routes and internal links valid. Logs are
`/tmp/lmdj-review-binding-{tests,inventory,pr,managed,scope}-v3.log` (the
eligibility log uses `tests-v3`) and `/tmp/lmdj-review-binding-docs.log`.
The independent reviewer re-ran all four Python behavior suites and confirmed
the Bot finding fixed with no remaining actionable findings in this six-file
Task. This is local independent review, not an owner-adopted GitHub attestation.
Full release acceptance and the production semantic/protection gate remain
unimplemented; these tests do not claim those downstream transitions passed.
