---
id: macos-git-launch-overhead
area: ci-release
status: open
recurrences:
  - date: 2026-09-14
    occurrence: https://github.com/endaye/lmdj/commit/66c00a6649b9926b282eb70982b78b4c3b34ece6
    observed_by: Codex
exit: none
---

# Git launch overhead can exhaust a real-Git test budget on macOS

## Why

The witness source and PR journey groups at the linked base repeatedly timed out
under their unchanged 120-second bounds. A source-consumer profile recorded
2569 subprocess calls taking 52.485 of 55.625 seconds. On this machine,
`/usr/bin/git` took about 18 ms per launch, while the existing executable selected
by `xcrun --find git` took about 8 ms. Both reported Git 2.54.0 Apple Git-157;
alternating version, HEAD and filter-query probes returned identical outputs.
Repeated launches amplified an environment cost that is not apparent from the
test or controller source. Concurrent build activity alone did not explain it:
the original groups also timed out with both Portal rehearsals stopped.

## How to apply

Profile the unchanged failing group before changing fixtures or budgets. Resolve
the selected Git with `xcrun --find git`, verify its identity and compare actual
command output and launch cost against the current PATH entry. Do not assume
every machine has the same toolchain path or the same performance cause.

When justified by that evidence, use a private temporary bin containing only a
symlink to the already installed, selected Git, and change PATH only for the
verification command. Preserve Node/Python selection, Git config/filter guards,
writer FD inheritance, all cases and original timeouts. Run the entire failed
groups and retain their actual results alongside the original failures; a
microbenchmark or passing prefix is not acceptance. Record the exact PATH and
resolved executable. Do not change global PATH, xcode-select, system settings,
install another toolchain, or silently claim the original environment passed.

This entry remains open because environment-specific launch cost is not a
deterministic defect suitable for a universal CI gate. The retained diagnostic
and complete follow-up results are in
`docs/plans/2026-09-14-release-candidate-transition.md`.
