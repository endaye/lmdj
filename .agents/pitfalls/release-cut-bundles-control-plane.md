---
id: release-cut-bundles-control-plane
area: ci-release
status: open
recurrences:
  - date: 2026-09-02
    occurrence: https://github.com/endaye/lmdj/pull/520
    observed_by: claude-fable-5-1
exit: none
---

# A release cut Pull Request that also carries control-plane or feature changes is excluded from the Integration Queue and chases a busy `main` by hand until the queue-free merge lands.

## Why

The Integration Queue is the only merge path that syncs `main` and
squash-merges without a human re-syncing after every intervening merge. A
Pull Request touching `ci.yml`, `scope_policy.json`, or the queue and gate
scripts is control-plane and must use the ordinary protected path, which under
`strict` branch protection requires the head to contain current `main`. When a
Build allocation, its snapshot, new deploy workflows, release scripts, and a CI
routing fix are bundled into one Pull Request, that whole bundle inherits the
exclusion. Every unrelated Pull Request that lands first flips it to `BEHIND`,
forces another sync merge, and reruns CI; the snapshot itself never moved, so
the chasing is pure integration cost that a two-Pull-Request split avoids.

The instinctive remedy, a long-lived `develop` or `release/*` branch, does not
remove the race; it relocates it and breaks the exact-`main` tag, CI-evidence,
and snapshot-provenance invariants that `version-management.md` depends on.

## How to apply

Follow the Release cut rule in `docs/governance/git-workflow.md` §6. Land
control-plane changes and every feature or infrastructure change as their own
Pull Requests first. Keep the cut Pull Request to allocation material only
(`version.json`, `assembly.json` and `assembly.lock.json` when identity changes,
the immutable Portal snapshot, and the release-evidence document) so it is
queue-eligible, then label it `merge:queue` and label nothing else until it
lands. If a cut Pull Request is found to carry control-plane paths, split it
before labelling rather than chasing `main`. No gate exists yet; a candidate is
a `PR Gate` check that rejects a `products/lmdj/version.json` Build change in
the same Pull Request as any control-plane path.
