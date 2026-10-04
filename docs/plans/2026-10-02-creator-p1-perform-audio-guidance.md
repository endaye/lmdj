# P1 Perform capture recovery guidance

Independent R12 review of committed source 4a8edfa8446e802a14e45ba9bdde2b3b68778de0 reproduced both typed master-capture failures in the actual PerformSurface and PerformController. Record remained disabled, no Activate audio button existed and recording was not submitted, but the displayed next step still requested generic audio activation. Both independent DOM cases failed their executable Pad-action assertion. Preserve those RED logs and artifacts; the zero-test dependency-setup failure is separate evidence.

Replace the guidance for tap-initialization-failed and tap-processor-failed with the actual action: reload the page, play a Pad to start audio, then record. Preserve error-state admission, diagnostics, raw-code hiding and the master-capture lifecycle. No activation button is restored.

## Declared files

- `apps/creator-web/src/state/error_messages.ts`
- `apps/creator-web/test/error_messages.test.ts`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-02-creator-p1-perform-audio-guidance.md`

## Task verification

Run the complete error catalogue, PerformSurface and audio lifecycle suites, TypeScript, staged ownership tests and complete portal check. The two permanent real-surface cases assert the actual next step for each native failure code, Record disabled, no obsolete activation button and no begin call. The independent unchanged DOM assertion must then pass against the new committed Source, with fresh imported artifact timestamps and actual exit status.

Recompute the new committed-head lane keys. The previous 0ecd browser passes and 4a8 source/portal passes are historical receipts, not approval for modified inputs. Current-head independent review, full selected changed-input proofs and all live conversation/conflict/protection checks remain required. Physical microphone/tap failure and Safari listening acceptance remain unexercised.

## Version Management

Version impact: none. This corrects user guidance without changing any API or identity; existing P1 version debt remains in the explicit coordinated settlement Task.

Documentation impact: required
Reason: the current Creator Perform capture recovery instructions must name the musical audio-start action.
Affected portal pages: /hosts/creator-web/
