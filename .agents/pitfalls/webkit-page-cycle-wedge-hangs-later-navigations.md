---
id: webkit-page-cycle-wedge-hangs-later-navigations
area: web-host
status: absorbed
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
  - date: 2026-09-27
    occurrence: https://github.com/endaye/lmdj/actions/runs/36320748849
    observed_by: Claude Code (Opus 5.5)
exit: gate:tests/platform/web/toolchain/playwright_webkit_abort_patch_test.mjs
---

# A navigation timeout does not identify its cause; locate it in the protocol exchange before attributing it to a page, a page count or host load.

## Why

Between 2026-09-20 and 2026-09-24, Linux WebKit `page.goto` hangs in the Project I/O proof
([#1570](https://github.com/endaye/lmdj/issues/1570)) were blamed in turn on
the page being loaded, reuse of a fault-suspended page (#1578, retracted),
about seventy-five page cycles (a real macOS r2336 defect, fixed upstream in
WebKit r2352 per
[playwright#42385](https://github.com/microsoft/playwright/issues/42385#issuecomment-5545690086),
not the Linux r2361 cause) and runner load. Idle `/proc` snapshots and traces
without a frame commit could not decide between them.

The failure-only protocol timeline from #1607 decided it on its first
recurrence (run 36320748849). WebKit created the provisional new-process
target for a fresh page's COOP navigation and then cancelled its load. Its
`Playwright.provisionalLoadFailed` reached the client 2 ms before the old
process's document `Network.requestWillBeSent`. The locked Playwright 1.62.1
client (unchanged on upstream `main`) drops that abort when the main frame has
no pending document yet. So `goto` waited for a commit that the engine had
already cancelled, until the 600-second test timeout.

## How to apply

`tests/platform/web` postinstall patches the locked client to replay such an
early failure when its document request starts. The patch is bound to 1.62.1
and to exactly one site per edit, and it fails closed otherwise. The gate
replays the recorded order through a fake WebKit pipe browser: the unpatched
client must time out and the patched one must reject at once. The Project I/O
spec retries only that engine cancellation, only on WebKit, and only on a page's
first navigation while it is still at its initial `about:blank`, once, with a
`webkit-engine-cancelled-first-load` annotation. Do not widen that condition.
If Playwright is upgraded, the patch check fails: re-derive the patch or confirm
upstream fixed the ordering, then rerun the gate. For any other hang, read the
retained `webkit-protocol-timeline.jsonl` first. Do not raise timeouts, add
general retries or change page lifecycle on a guess.
