# P1 first native touch packaged proof

Extend the existing complete progressive Bank A journey with its first real
Chromium touch, before any document activation. Observe native pointer events,
the original AudioContext construction/resume and real transport voice notifications. Do not
replace audio, fake readiness or change browser autoplay policy.

## Declared files and verification

- `tests/platform/web/creator/creator_web_default_streaming.spec.mjs`
- `docs/plans/2026-10-02-creator-p1-native-first-touch-proof.md`
- `.agents/pitfalls/playwright-evaluation-grants-user-activation.md`

Prove trusted touch down has not created a playback context, resumed or triggered audio; trusted touch up
resumes and admits exactly one matching started voice while object two is still
blocked. First-leg DOM and state reads explicitly use CDP `userGesture: false`: ordinary
Playwright evaluation, locator waits and DOM trace snapshots can grant the document
activation under test. Disable only DOM trace snapshots while retaining failure
action/network/source traces. Assert the
real unactivated state before any native touch.
Keep all sixteen verified slots, persisted identity, no redundant
download and manual-Project reload legs. The retained pre-repair wake-on-down
source must fail inside this journey against its freshly rebuilt distribution;
refresh source mtimes, rebuild the corrected source and require the complete
journey to pass. Retain build exits
and both logs. The full Creator lane runs on the final clean committed candidate.
The observer-only constructor proxy returns the original native AudioContext;
it does not replace the context, autoplay policy or admission results. Preserve
the earlier fixture-precondition failures and the initial non-discriminating
resume-only pass separately from the causal construction-on-down failure.
This is Chromium native-event/audio execution evidence, not Safari or iPad
physical acceptance.

## Version Management

Version impact: none. Only packaged browser verification changes; public
Contracts and product source bytes are unchanged.

Documentation impact: none
Reason: directly verify the documented first-touch behavior without changing
portal facts or projected identities.

## Streaming Task adoption

T5 adopts this driver boundary after Source 5777cb7f was rebuilt through the
stable Creator entry point on a clean tree. Run the entire progressive journey
against that unchanged distribution, including reload and manual Project
reload. The causal construction-on-down RED from 248 and corrected native
GREEN from cc are retained; this adoption makes no new physical acceptance
claim and changes no Product source. Recompute the committed Creator key.
