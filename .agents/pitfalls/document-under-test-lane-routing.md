---
id: document-under-test-lane-routing
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-29
    occurrence: https://github.com/endaye/lmdj/pull/421
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/pull/520
    observed_by: Codex
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/pull/685
    observed_by: claude-code/opus-5
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/pull/707
    observed_by: claude-code/opus-5
exit: gate:tests/build/ci_change_scope_test.py
---

# A test that asserts on a document's content is a gate over that document, and nothing links the two, so the document routes to `docs_static` while the test that validates it never runs.

## Why

Change Scope routes a path by what the path *is*, not by what reads it. A
Markdown file therefore lands in `docs_static` even when a test opens it and
asserts line by line on its contents. The routing rule and the reading test sit
in different files with no reference between them, so the obligation is
invisible at both ends: the rule author sees a document, and the test author
sees a test.

Three tests had accumulated eleven such documents.
`tests/build/web_runtime_public_deployment_docs_test.py` asserts on
`docs/design/2026-08-08-web-runtime-public-deployment-design.md`
with `assertIn("Release ZIP 未修改", source)` and similar, while that document
routed only to `docs_static`; `apps/architecture-portal/test/stage7-review-remediation.test.mjs`
read six more from the `portal` lane, and `tests/build/release_skill_test.py`
read two governance pages from `ci_contract` and `deploy_contract`. Editing any
of them ran neither the assertion nor the lane holding it.

None of this surfaced, because the Integration Queue upgraded every merge to
`full` and ran the missing lanes anyway. The gap was real for the whole life of
the Pull Request and invisible at merge. It became load-bearing the moment
[`2026-08-29-focused-merge-evidence`](../../docs/prd/decisions/2026-08-29-focused-merge-evidence.md)
decided to relax that upgrade, which is why closing it is sequenced ahead of
the relaxation rather than tracked as follow-up.

This is the second obligation the scope policy carries beyond its own rule
list; the first was
[`scope-policy-top-level-admission`](scope-policy-top-level-admission.md),
where a rule did not admit its own top-level directory.

The absorbed gate failed and was repaired in the same change. #685 added a
lint that reads `.agents/pitfalls` and lives in `ci_contract`, while the ledger
routed to `docs_static` only -- the exact shape above -- and the gate's scan saw
neither the `.agents/` prefix nor a directory read. An advisory review caught
that gap before the gate did. Widened to `.agents/` and made directory-aware,
the gate then surfaced five more it had never seen: `ci_pr_body_lint_test.py`
asserting on a ledger entry, three tests asserting on
`.agents/skills/issue-done/SKILL.md`, and `release_skill_test.py` -- in the
`deploy_contract` lane, not `ci_contract` -- asserting on
`.agents/skills/lmdj-release/SKILL.md`. None ran when those documents were
edited. `.agents/` as a whole now also selects `ci_contract`, and the release
skill additionally selects `deploy_contract`. The fourth occurrence was
`.claude/commands/pr-review.md`: two `ci_contract` tests assert on the vendored
review prompt, while the prompt routed to `docs_static` alone, so amending it
ran neither. The gate's own scan was the reason it stayed invisible -- it read
`docs/` and `.agents/` and had never looked at `.claude/`. Both are widened
here: a document tree that a test reads is in scope for this gate wherever it
lives, and the exit is only as good as the paths it scans.

## How to apply

The invariant is settled, mechanically decidable for literal paths, and
deterministic, so it exits to
`test_every_document_a_test_reads_reaches_that_test_lane` in
[`tests/build/ci_change_scope_test.py`](../../tests/build/ci_change_scope_test.py),
which scans the tests' real read sites and names each document, its missing
lanes, and the test that reads it.

When you make a test assert on a document, add an exact rule for that document
in `scripts/ci/scope_policy.json` carrying the lanes that hold the test. Rules
are additive, so the new rule needs only the lanes the document does not
already get. The scan reads literal paths only: a path built at runtime is
invisible to the gate, so a dynamically located document still needs its rule
written by hand.
