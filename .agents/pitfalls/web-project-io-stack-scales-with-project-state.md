---
id: web-project-io-stack-scales-with-project-state
area: core
status: absorbed
recurrences:
  - date: 2026-09-30
    occurrence: https://github.com/endaye/lmdj/pull/1699
    observed_by: unknown
  - date: 2026-10-01
    occurrence: https://github.com/endaye/lmdj/pull/1717
    observed_by: Claude Opus 5.5
exit: gate:tests/platform/web/project_io/project_io_web_conformance.spec.mjs
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

Absorbed by #1720. Every native action in the Project I/O Web conformance reports
its stack high-water mark, and the spec fails any action over half the Web
stack, with `why` and `remedy`. This runs in the `web_toolchain` lane, so run
that lane whenever a Pad or Project field grows. If it fails, keep
`ProjectState` off the deep frames: use the heap, references or `noinline`
phases. Locate the cost with `em++ -O3 -fstack-usage`, using the Web build
flags against `origin/main`.
