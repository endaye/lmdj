---
id: safari-webdriver-action-without-input-completion
area: web-host
status: open
recurrences:
  - date: 2026-10-03
    occurrence: https://github.com/endaye/lmdj/issues/1671
    observed_by: Codex (GPT-6)
exit: none
---

# A successful Safari WebDriver action receipt does not prove a completed native input or a responsive next command.

## Why

Real iPad Safari 27.0 returned success for Element Click and pointer Actions
while an independent button probe received no completed click. A repeated grid
tap flushed the first trusted pointerup but left an extra pointerdown. A later
drag's performInteractionSequence returned success, then the next
resolveBrowsingContext had no response. No post-drag Truth could be obtained.

The [acceptance record](../../docs/quality/2026-10-03-sequence-grid-safari-acceptance.md)
retains the probe events and protocol. This differs from the locked Playwright
client ordering defect in
[webkit-page-cycle-wedge-hangs-later-navigations](webkit-page-cycle-wedge-hangs-later-navigations.md).
Similarity to [WebKit bug 322937](https://bugs.webkit.org/show_bug.cgi?id=322937)
is a diagnostic lead, not a proven root cause in this repository.

## How to apply

- Confirm input completion at the receiving page and read actual Truth after
  the action. A protocol success or unchanged screenshot alone is insufficient.
- If the next command hangs, retain its exact request/reply boundary before
  attributing the problem to the product, a device or load. Keep the last
  confirmed Truth and label subsequent state unknown.
- Separate trusted native input from JavaScript stand-ins and cleanup events.
  Keyboard activation does not accept touch dragging or hearing.
- After Safari restarts, distinguish a fresh isolated WebDriver store from
  reopening the same retained Project. Compare complete Truth within a retained
  session; keep cross-session and physical lifecycle rows open.

No deterministic gate or repository workaround is established at recurrence 1.
The external driver behavior and recovery are device-dependent, so this entry
remains open pending an evidenced mechanism; do not widen timeouts or infer a
product regression from the stalled query.
