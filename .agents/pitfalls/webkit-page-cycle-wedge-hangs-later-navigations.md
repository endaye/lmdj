---
id: webkit-page-cycle-wedge-hangs-later-navigations
area: web-host
status: open
recurrences:
  - date: 2026-09-20
    occurrence: https://github.com/endaye/lmdj/issues/1570
    observed_by: Claude Code (Fable 5.1)
  - date: 2026-09-20
    occurrence: https://github.com/endaye/lmdj/pull/1578
    observed_by: Claude Opus 5 (1M context)
  - date: 2026-09-22
    occurrence: https://github.com/endaye/lmdj/issues/1570
    observed_by: Codex (GPT-6)
  - date: 2026-09-24
    occurrence: https://github.com/endaye/lmdj/pull/1607
    observed_by: Codex (GPT-6)
exit: none
---

# A navigation timeout does not identify its cause; bind a browser workaround to the measured build and platform.

## Why

The locked Playwright WebKit build (r2336, Playwright 1.62.1) stops serving
navigations after roughly seventy-five `newPage()` + `close()` cycles in one
browser instance. From then on every `goto` on any new page hangs until the
test timeout and Playwright reports `page.goto: Target page, context or
browser has been closed` only after tearing the browser down. Measured on an
M1 with `/preflight.html` alone: pages 0–74 load in about 180 ms each, page 75
never loads; the same on a persistent and on an ephemeral context, with
tracing on or off, with or without OPFS or a Wasm host. One page navigated 150
times in three seconds. The UI process meanwhile grows from ~30 to ~70 threads
and its main thread sits in screencast frame encoding and WindowServer capture
IPC, which is load, not the cause: tracing off moved the wedge by one page.

`project_io_web_conformance.spec.mjs` opens a fresh page for nearly every
step so that each Wasm host starts from a fresh document. Its longest test
opens sixty to a hundred pages, and three consecutive batch runs of the
`web_toolchain` suite (#1570) each hung a different navigation:
a fixture page, an admission step, a recovery step. Each hang was read as a
defect in whatever that page was about to do, and the two real WebKit
findings in the same runs (an unclosed writable committed on teardown; see
[`unclosed-opfs-writable-commits-on-webkit-teardown`](unclosed-opfs-writable-commits-on-webkit-teardown.md))
made a shared-cause attribution plausible. The page-count probe established a
macOS r2336 defect; it did not establish the cause of the Linux r2361 failures.

The unresolved Linux signature stays open under
[#1570](https://github.com/endaye/lmdj/issues/1570), which tracks the WebKit
navigation hangs in the `web_toolchain` lane.

A complete local Project I/O WebKit run on the Linux x64 netcup host reproduced
the remaining r2361 signature on 2026-09-24. A shared `DEBUG_FILE` captured
other workers' protocol packets and was rewritten after the failed case; its
`Playwright.navigate` reply cannot be attributed to the hanging navigation.
An idle `/proc` snapshot and trace without a frame commit still do not prove
whether that browser received the command. Capture the entire worker stream
through a single sidecar and retain a failure-only timeline instead of relying
on a shared, worker-owned raw protocol file.

## Retracted attribution: a page whose document is wedged

The #1578 hypothesis attributed the Linux hang to reusing a page whose Wasm
worker was stopped at a fault point. Run `35510660533` contradicted it: the
previous document had completed normally, and the next navigation still hung.
The sleeping `/proc` threads establish neither an unserved navigation command
nor the cause of a deadlock. Preserve that failed hypothesis as history, not
as an instruction to change the test lifecycle.

Upstream [Playwright #42385](https://github.com/microsoft/playwright/issues/42385#issuecomment-5545690086)
identifies the macOS page-count defect as window animations with the display
asleep, fixed in WebKit r2352. The selected OPFS browser is r2361; r2336 is the
separate locked client browser. The original page-count measurement does not
justify pooling pages in the OPFS recovery suite on Linux.

## How to apply

When a Playwright navigation hangs for the full test timeout on WebKit, count
the pages the test has opened and closed in that browser before blaming the
page: probe with a plain HTML page — if it hangs too, the browser is wedged.
Verify the actual browser executable and platform against the upstream fix
before applying a workaround measured with a different build. Recovery tests
must really close the page when the journey names a page-close interruption;
do not replace it with navigation merely because both can release a handle.
The conformance suite now directly checks that lifecycle boundary.
Do not raise timeouts or retry for green. This entry remains open under the
existing escalation [#1570](https://github.com/endaye/lmdj/issues/1570): neither
an idle process snapshot nor a passing macOS run resolves the remaining Linux
navigation signature. The full suite reproduced it once locally, while its
preceding run and a 120-page cycle probe passed; there is no deterministic
reproduction of the signature yet, so `exit: none` remains accurate.
