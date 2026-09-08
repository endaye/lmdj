---
id: rspack-cache-stalls-corrected-mdx-build
area: ci-release
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/commit/c5cbf6161320d2ddec1d8e3f76d051e591590726
    observed_by: Codex
exit: none
---

# After a failed MDX compilation, a retained local Rspack cache can accompany a stalled corrected build; preserve it and compare a cold build before changing source or gates.

## Why

The Host-changelog Task based on the linked main baseline first failed because
its generated MDX used an HTML comment. Correcting the comment and compiling
both empty and populated pages in a regression test succeeded, but subsequent
production builds stopped producing output in Rspack. One was stopped after
4m45s with about 12s cumulative CPU; a same-command retry showed the same shape.
Phase logging completed site loading/config generation, not bundling. A separate
clean pre-change worktree built successfully in about 10s with its existing cache.

After stopping the exact owned process, moving only this Task's approximately
159MB Rspack cache to a retained temporary directory allowed the unchanged
corrected source to build cold in about 15s and pass 44 route/link checks. This
is a local cache-associated observation, not proof of a particular corrupt
object, an upstream defect, or a general CI capacity baseline. The linked commit
is the Task's starting point, not a claim it introduced the failure.

## How to apply

Keep the real compiler error separate from a later stall. Correct source errors
with a regression, then inspect progress/CPU and enable phase logging before
assuming a slow full test or increasing budgets. When testing the cache
hypothesis, stop only the verified owned build process and move its exact
ignored Rspack cache out of the way; preserve logs and the cache for inspection.
Do not clean another session's worktree or weaken minification, snapshots,
routes, tests or link checks. A killed process is not a successful build, even
if its signal handler exits zero: require complete build and far-side checks.

`exit: none`: this is one local environment observation; cache-associated
stalling is not deterministically inferable from product source. No automatic
cache deletion, retry loop or new global gate is justified.
