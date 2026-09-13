# Bind review eligibility to complete observed bodies

Status: delivery integration of original `cc9157b3` onto actual inventory
squash `203737adb0558cc836a6e5d6743ce7a4607aedec`. Historical original-stack
evidence below is not current delivery verification.

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

## Historical original-stack verification evidence

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

## Delivery integration and verification

Import only the body-observation Task, preserving inventory delivery's new
cross-thread numeric comment identity check. Do not import unrelated historical
`4b46cb14` failure-artifact fixture changes: current main's review workflow does
not upload `collection-failure.json`. Thus the current eligibility/binding
suite discovers 67 tests versus the original stack's 69, with no test removed
from this delivery's actual main base and no selected test skipped.

Initial delivery verification: reader/binding 67/67 (0.397 seconds), inventory
22/22 (0.014 seconds), PR 36/36 (0.118 seconds), managed 17/17 (0.337 seconds),
all exit 0. Independent full six-file review found no actionable finding and
reran the same four populations (67/22/36/17), all exit 0. Staged ownership and
top-level admission passed 74/74 in 6.676 seconds. Registered inventory CTest
passed 1/1 in 0.15 seconds under Python 3.14.7, retaining its 30-second limit.

A read-only live bridge used the actual eligibility reader, actual canonical
GitHub collector and actual binder on open PR 1286 at head
`8bc77608b470686bbbea741693598a51a2a8b3f7`, repository ID 1286600062. It linked
review ID 5190983232 to API author ID 41898282 across REST/GraphQL, with 5263
UTF-8 bytes and SHA-256
`790a8db9cbeac62ee31c4f9c5d7b1faea00860fbcc52ad9edea096b90e410653`.
Inventory digest: `aded24244eec86c9f64f01be5d84a2550dfdde28cfdba7d246e7f968ecd62ef2`.
Eligibility digest: `09fbee3c73ee3589e1c9f38e210cfef9c2947d6a2ef782baffb6c7d917e96809`.
No unlinked reviews/comments, threads or closing references were present.
Only identity/count/digest output was emitted, not review bodies or credentials.
This establishes current API compatibility and actual reader composition, not
live multi-page drift, owner attestation, finding disposition, effective
protection, historical review acceptance or complete release acceptance.

The eligibility/binding suite additionally passed 67/67 under Python 3.14.7
in 0.449 seconds. With locked Node 22.22.2 dependencies, full Portal passed
144/144 tests, 47-page metadata, 10 diagrams/20 outputs, snapshot consistency,
typecheck, production build and 47 routes/internal links; exit 0. No Product
Build, snapshot, tag, Release or deployment was created by this development Task.

After PR 1286 merged, rebase onto actual squash `203737ad` without conflicts;
the entire resulting tree matches pre-rebase delivery `009dfce7`. Repeat the
reader/binding 67/67 and inventory 22/22 suites, both exit 0. The Portal result
above covers the identical source tree; this final plan update only records
base and verification facts.
