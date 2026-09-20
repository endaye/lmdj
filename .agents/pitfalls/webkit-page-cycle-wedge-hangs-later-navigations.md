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
exit: none
---

# A `page.goto` that hangs until the test timeout late in a long browser test is the browser wedged by page open/close cycles, not the page being loaded.

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
`web_toolchain` suite (#1570) each hung a different navigation in that region:
a fixture page, an admission step, a recovery step. Each hang was read as a
defect in whatever that page was about to do, and the two real WebKit
findings in the same runs (an unclosed writable committed on teardown; see
[`unclosed-opfs-writable-commits-on-webkit-teardown`](unclosed-opfs-writable-commits-on-webkit-teardown.md))
made that reading plausible. The URL in the error names the victim, not the
cause; the cause is how many pages the test had already opened and closed.

Both causes stay open under
[#1570](https://github.com/endaye/lmdj/issues/1570), which tracks the WebKit
navigation hangs in the `web_toolchain` lane.

## A second cause with the same symptom: a page whose document is wedged

Parking a page on `about:blank` returns immediately even when the document it
replaces can never finish tearing down. The Wasm test host stopped at a fault
point holds a worker suspended forever inside `stopAtFault`; on Linux WebKit
the page that carried it is never served another navigation, so the next
`goto` on that reused page hangs until the test timeout. The `/proc` snapshot
taken at one such timeout (batch run 35496737811) shows the cause is not load:
every thread of the browser, network and three web processes sits in
`futex_wait` or `poll`, with 58 GB of memory free, 32 GB of unused `/dev/shm`
and a load average of 3.7. The browser is idle and simply never answers.

Chromium and macOS WebKit tear the same document down and keep serving the
page, so only the Linux lane fails, and only for tests that wedge a document.

## How to apply

When a Playwright navigation hangs for the full test timeout on WebKit, count
the pages the test has opened and closed in that browser before blaming the
page: probe with a plain HTML page — if it hangs too, the browser is wedged.
Keep a long test under the threshold by reusing pages: a navigation to
`about:blank` tears the document down as a close does (its OPFS handles,
leases and workers go with it), so park closed pages and hand them out again
rather than opening new ones; `trackedPage` in the conformance spec does
this. Park only a page whose runtime reached a terminal state — the spec
checks `window.lmdjProjectIoWeb` is absent or `complete` — and close a wedged
one for real, or the pool hands back a page the browser will never serve. Do not raise the test timeout, retry the navigation, or split the test
merely to stay under the count. No deterministic gate fits: the wedge lives
in the browser build and its threshold moves with the host, so this stays
open with `exit: none`.
