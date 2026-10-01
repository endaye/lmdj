---
id: playwright-evaluation-grants-user-activation
area: creator-web
status: absorbed
recurrences:
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/pull/1741
    observed_by: Codex (/root)
exit: gate:tests/platform/web/creator/creator_web_default_streaming.spec.mjs
---

# Playwright evaluation can activate the document before a first-input audio proof.

## Why

The pinned Playwright Chromium execution path sends `userGesture: true` with
script evaluation. A normal `page.evaluate`, locator wait or action DOM trace
snapshot can therefore change the activation it intends to observe. A reduced
fresh-page run stayed inactive after navigation, then became active after a
locator wait. CDP-only reads still found an activated page with DOM snapshots
enabled; disabling those snapshots preserved the explicit cold precondition.
This belongs to the
test-driver boundary, not the product input controller. The first draft of the
P1 native touch proof observed an already activated document before its touch.
That draft is fixture evidence, not a product audio failure.

## How to apply

Use the enforcing packaged first-touch journey. Before its native input, read
readiness, DOM geometry and activation through CDP with `userGesture: false`.
Disable DOM trace snapshots for this journey while retaining action, source and
network traces. Keep its explicit unactivated precondition, trusted native pointer
assertions, native context construction/resume timing and matching real started-voice
assertion. Do not call ordinary
evaluation or activation-capable helpers earlier in this leg. Preserve the
remaining progressive download and persisted Project legs. Browser automation
does not establish physical Safari or iPad acceptance.
