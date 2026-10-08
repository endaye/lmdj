---
id: macos-git-launch-overhead
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-14
    occurrence: https://github.com/endaye/lmdj/commit/66c00a6649b9926b282eb70982b78b4c3b34ece6
    observed_by: Codex
  - date: 2026-10-08
    occurrence: https://github.com/endaye/lmdj/pull/1876
    observed_by: Codex
exit: skill:.agents/skills/lmdj-review-ci-triage/SKILL.md
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

Follow the **macOS real-Git lane timeouts** procedure in
[`lmdj-review-ci-triage`](../skills/lmdj-review-ci-triage/SKILL.md): profile the
unchanged failure, prove original-executable equivalence, justify a command-local
adjustment by measured cost, then require the complete original lane to pass.
This judgment belongs in a skill, not a universal performance gate.

The first investigation's temporary symlink changed the exec path/templates;
its apparent passes were not equivalent-environment proof. In the second
occurrence, three passing shards (1,398 cases) preceded a 1,200-second worker
timeout, and a profile was deliberately interrupted. Slower shell/native
wrappers also remained negative diagnostics. [PR #1876](https://github.com/endaye/lmdj/pull/1876)
subsequently records a complete 1,865-case pass using the verified original Git
directory with unchanged cases and bounds. Preserve all earlier failures;
that later pass does not turn them into successful runs.
