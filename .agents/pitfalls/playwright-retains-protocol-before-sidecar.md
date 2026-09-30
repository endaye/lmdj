---
id: playwright-retains-protocol-before-sidecar
area: web-host
status: absorbed
recurrences:
  - date: 2026-09-30
    occurrence: https://github.com/endaye/lmdj/pull/1699
    observed_by: Codex (GPT-6)
exit: gate:tests/platform/web/project_io/webkit_protocol_timeline_test.mjs
---

# Filtered diagnostic output does not bound an upstream runner's retained stderr.

## Why

The WebKit proof sidecar filtered raw protocol traffic to a small navigation
timeline, but Playwright 1.62.1 first forwarded worker stderr through IPC and
retained every chunk in TestResult. A complete suite exhausted the runner's
default heap before the outer filter could help. An independent real-runner
probe reproduced retained bytes with the same navigation timeline.

## How to apply

The sidecar sets `PW_RUNNER_DEBUG=1` only for its child to inherit worker stderr
directly into its pipe. Ordinary stderr remains in the proof log, but no longer
in individual test/trace attachments. The exit gate runs the locked real runner
and asserts zero retained stderr, intact navigation events and preserved failure
status. Rerun it when upgrading Playwright; do not increase heap or drop browser
cases to conceal upstream retention.
