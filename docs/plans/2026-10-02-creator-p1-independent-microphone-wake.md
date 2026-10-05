# P1 microphone wake independent of playback

Independent review R8 proves a granted microphone take never starts on touch or
pen while playback is suspended, even when the document already has valid user
activation. The Host incorrectly delays acquiring its separate microphone
Context until release, then aborts it without recording. Attempt microphone
resume synchronously on the actual press and let the browser enforce permission;
only master capture waits for the playback Context. Preserve cold playback's
legal release wake and complete cleanup for pending or refused microphone resume.

## Declared files and verification

- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/capture/pad_capture_sources.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/pad_capture_sources.test.ts`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-02-creator-p1-independent-microphone-wake.md`

Retain the independent actual-module touch/pen RED. Verify native synchronous
capture intent, pending/refused playback independence, cancelled resume resource
cleanup, zero material on refusal, and unchanged master acquisition/stop barriers.
Run complete Creator unit tests, TypeScript, current portal and staged scope.
Independently rerun the fixed actual App callbacks and four capture modules.
Chromium sticky activation, WebKit transient activation and physical microphone
acceptance are distinct; this Task assumes no cross-browser equivalence.

## Version Management

Version impact: deferred to coordinated P1 candidate settlement.
Reason: fix Host capture timing without changing a public Contract or allocating
a Product Build in this Task.

Documentation impact: required
Affected portal page: /hosts/creator-web/
Reason: record independent capture wake and browser-refusal cleanup, and correct
the primary touch/pen admission model in the current source facts.
