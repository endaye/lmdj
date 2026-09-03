---
id: release-cut-bundles-control-plane
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/pull/520
    observed_by: claude-fable-5-1
  - date: 2026-09-03
    occurrence: https://github.com/endaye/lmdj/pull/541
    observed_by: Claude Code (Opus 5)
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A Pull Request that bundles a control-plane path with any other work is excluded from the Integration Queue and chases a busy `main` by hand until someone merges it queue-free.

## Why

The Integration Queue is the only merge path that syncs `main` and
squash-merges without a human re-syncing after every intervening merge. A
Pull Request touching `ci.yml`, `scope_policy.json`, or the queue and gate
scripts is control-plane and must use the ordinary protected path, which under
`strict` branch protection requires the head to contain current `main`. Every
unrelated Pull Request that lands first flips it to `BEHIND` and forces another
sync plus a full CI rerun, so the chasing is pure integration cost that a
two-Pull-Request split avoids.

First seen as a release cut: #520 bundled a Build allocation, its snapshot, new
deploy workflows, release scripts, and a CI routing fix into one Pull Request,
and the whole bundle inherited the exclusion while the snapshot itself never
moved.

The instinctive remedy, a long-lived `develop` or `release/*` branch, does not
remove the race; it relocates it and breaks the exact-`main` tag, CI-evidence,
and snapshot-provenance invariants that `version-management.md` depends on.

**The recurrence widened the entry past release cuts.** #541 carried no release
material at all — a `tools/needle-spike/` technical validation, one research
document, four open-question files, and a single `scope_policy.json` line
classifying the new directory. That one line made the whole Pull Request
control-plane. It also felt mandatory, which is why the bundling looked
unavoidable: `tests/build/ci_change_scope_test.py` fails on any tracked path
that no routing rule classifies, so the new directory could not ship without
its rule. The rule can ship *before* the directory, though — a routing rule for
a path that does not exist yet classifies nothing and breaks nothing, and that
ordering dissolves the bundle.

The cost was concrete. Full CI on this repository runs about 185 minutes, over
half of it queueing behind the `lmdj-native-heavy` concurrency group, while
`main` took 2, then 12, then 16 commits during successive attempts. Three
rebase-and-rerun cycles never converged, and the Pull Request landed only when
a human merged it with the `strict` requirement bypassed — `enforce_admins` is
`false`, so that escape exists, but it discards exactly the up-to-date
guarantee `strict` is there to provide.

## How to apply

Before opening a Pull Request, list its paths against the control-plane set in
`docs/governance/git-workflow.md` §5. If it touches any of them **and** anything
else, split it: land the control-plane change as its own Pull Request through
the ordinary protected path, then reopen the remainder, which is queue-eligible
and usually selects far fewer lanes. When the control-plane change is a routing
rule for paths the same branch introduces, land the rule first and the paths
second; they do not need to be atomic.

For a release cut specifically, follow the Release cut rule in
`docs/governance/git-workflow.md` §6 and keep the cut Pull Request to allocation
material only.

This exits to a skill section rather than a gate. The mechanical check —
reject any Pull Request mixing control-plane and non-control-plane paths —
fails the settled-invariant criterion: a control-plane script legitimately
changes alongside its own test under `tests/build/`, so the gate would refuse
correct work. The candidate narrower gate from the first occurrence, rejecting
a `products/lmdj/version.json` Build change in the same Pull Request as any
control-plane path, remains eligible and would have caught #520 but not #541.
