---
id: scope-policy-top-level-admission
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-25
    occurrence: https://github.com/endaye/lmdj/pull/307
    observed_by: unknown
  - date: 2026-08-25
    occurrence: https://github.com/endaye/lmdj/pull/305
    observed_by: unknown
  - date: 2026-08-28
    occurrence: https://github.com/endaye/lmdj/pull/367
    observed_by: Claude Code (Opus 5)
exit: gate:tests/build/ci_change_scope_test.py
---

# A Change Scope routing rule does not admit its top-level directory; `known_top_levels` is a second, earlier gate, and omitting it silently runs full CI forever.

## Why

`_evaluate_ready_paths` in `scripts/ci/change_scope.py` tests the first path
segment against `known_top_levels` before it consults `rules` at all, and an
unlisted segment adds `unknown top-level: <name>` to the full-upgrade reasons
regardless of how precisely a rule routes the path. Adding a route therefore
looks complete and behaves as if no route existed.

Two rule additions shipped that way on the same day. #307 gave `LICENSE` an
exact `docs_static` route, and #305 gave `.agents/` a prefix `docs_static`
route; neither admitted its top level. The failure mode is silent because the
run still passes -- it just runs all fourteen lanes. It surfaced only on #367,
where three Markdown files under `.agents/pitfalls/` produced mode `full` with
`unknown top-level: .agents` as the sole reason, at 11.4 minutes of wall clock
against the 3.5 minutes the same tree costs when classified correctly.

The sibling escalation input already had a gate --
`test_every_tracked_path_has_explicit_ownership_or_full_rule` checks `rules`
and `full_rules` against `git ls-files` -- so the omission was invisible
precisely where a reader would expect to find it enforced.

## How to apply

The invariant is settled, mechanically decidable, and deterministic, so it
exits to
[`test_every_tracked_top_level_is_admitted_by_the_policy`](../../tests/build/ci_change_scope_test.py),
which derives the expected set from `git ls-files` and names both the reason
and the two files to edit. When you add a top-level file or directory, or route
one that already exists, update `known_top_levels` in
`scripts/ci/scope_policy.json` and `TOP_LEVELS` in
`tests/build/ci_change_scope_test.py` in the same commit as the rule. A route
without an admission is not a route.
