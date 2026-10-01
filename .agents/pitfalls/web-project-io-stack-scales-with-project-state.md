---
id: web-project-io-stack-scales-with-project-state
area: core
status: open
recurrences:
  - date: 2026-09-30
    occurrence: https://github.com/endaye/lmdj/pull/1699
    observed_by: unknown
  - date: 2026-10-01
    occurrence: https://github.com/endaye/lmdj/pull/1717
    observed_by: Claude Opus 5.5
exit: none
---

# Growing a Pad or Project field silently grows Project I/O's Web stack demand until a deep path overflows.

## Why

`ProjectState` stores all 64 Pads inline, and Project I/O's load, flush, rebase
and recovery paths hold several `ProjectState` values per frame once `-O3`
inlines their helpers. Every byte added to a Pad therefore costs roughly 64
bytes per live copy, along call chains that already used about half of the Web
stack. Native builds have megabytes of stack and never notice. Only the
batch-only `web_toolchain` conformance has `STACK_OVERFLOW_CHECK`. The Web
Runtime Host has none, so there
an overflow shows up as unrelated `null function` traps across Creator and Host
journeys.

## How to apply

- When a Task grows `PadPlayback`, `PadSlot`, `ProjectState` or another value
  that Project I/O copies, measure its wasm32 `sizeof` before and after.
- Compare the deep Project I/O frames with
  `em++ -O3 -fstack-usage` on the Web build flags (`flags.make` and
  `includes_CXX.rsp` under `build/web/toolchain/project_io`), against `origin/main`.
- Run `web_toolchain`, `creator` and `web_runtime_host` locally before merge.
  Read a `null function` trap in those lanes as a possible stack overflow
  first.
- Do not bound one test frame with `[[gnu::noinline]]` and move on: the
  product paths share the same budget.

This stays open with `exit: none` until
[#1720](https://github.com/endaye/lmdj/issues/1720) reduces the copies or lands
a frame-size gate on the Web build of `packages/project-io`. #1720 is the
escalation Issue for this second recurrence.
