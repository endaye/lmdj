---
id: viewport-resize-resolves-before-page-refit
area: creator
status: open
recurrences:
  - date: 2026-10-15
    occurrence: https://github.com/endaye/lmdj/pull/2299
    observed_by: unknown
  - date: 2026-10-15
    occurrence: https://github.com/endaye/lmdj/actions/runs/38776156275
    observed_by: Claude Code (claude-opus-5-5)
exit: none
---

# A Creator spec that reads layout right after `page.setViewportSize` can measure the previous viewport, because the call resolves before the page's `resize` handler refits the console.

## Why

Playwright resolves `setViewportSize` once Chromium accepts the new metrics.
It does not wait for the page's `resize` event. The Creator console refits only
in that handler (`main.tsx` `fitStage`), and the touch-workspace modal
re-anchors from it. On the CI hosts the next geometry read still saw the old
fit: the Project list measured a console from the previous viewport (#2268),
and the capture trim panel kept its 1440x900 box inside a 1280x720 viewport,
so `elementFromPoint` missed every hit point below the fold. A comparison of
two elements that are both stale (dialog against anchor) agrees and does not
detect the race. Locally the handler usually wins the race, so the spec looks
stable.

## How to apply

After any mid-test resize, wait for `window.innerWidth/innerHeight` to equal
the requested size and then for one `requestAnimationFrame` before reading
geometry, bounding boxes or hit points (`resizeViewport` in
`creator_web_hardware_layout.spec.mjs` and `creator_web_capture.spec.mjs`).
Escalation for a shared helper and a sweep of the remaining specs:
https://github.com/endaye/lmdj/issues/2304. The entry stays open until that
mechanism lands.
