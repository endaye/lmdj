---
id: branch-code-audits-main-authority
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/pull/564
    observed_by: claude-fable-5-1
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/issues/572
    observed_by: claude-fable-5-1
exit: gate:tests/build/release_promotion_test.py
---

# A remote release audit run from a branch that tightens the closed policy or ledger schema reads protected `main` with the branch's parser, fails closed on `main`'s documents, and used to report that as a network or credential `external-error`.

## Why

`audit --remote` deliberately takes its authority from protected `main`: it
fetches `main`, checks out that exact tree, and parses `tools/release/policy.json`
and the intent ledger from there. The parser, however, is whatever the operator's
checkout contains. Both documents are closed schemas that reject unknown or
missing fields, so a branch that adds a required policy section, or a ledger
field `main` does not yet carry, cannot parse `main`'s documents at all.

The failure surfaced twice on one day. Preparing `1.0.41.0` from the branch
that isolated the two signing-role keyrings (PR #564) reported
`[external-error] canonical Git/GitHub projection is unavailable or incomplete`
with `incomplete sources: git-remote, github-api`, which points at tokens and
connectivity; `gh auth status` and `git ls-remote` were both healthy. Designing
Channel promotion (Issue #572) added a required `promotion` policy section and
reproduced the exact same message for the exact same non-reason. The broad
`except Exception` in `audit()` collapsed a `ReleaseModelError` into the outage
finding, so the real cause never reached the operator.

The mirror image is documented in [[release-authority-fetch-credentials]]:
there a genuine credential gap was also reported as `external-error`. Together
they show that one catch-all code for "the remote projection failed" hides
three unrelated causes.

## How to apply

`audit()` now reports a `ReleaseModelError` raised while reading the authority
tree as `[conflict] canonical release authority does not satisfy this checkout's
closed policy or ledger schema; land the schema change on main first`. When you
see it, the remedy is procedural, not environmental: merge the schema change to
`main`, then run the audit and any dependent mutation from `main`. Design
documents for release-control changes must say so explicitly, as the Channel
promotion spec does in its first-use section. Never widen the branch's parser to
tolerate `main`'s older documents to make a local audit pass; the closed schema
is the invariant.
