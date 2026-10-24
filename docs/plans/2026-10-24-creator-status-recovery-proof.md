# Creator manual Runtime recovery page proof

Parent: #2112. Partial delivery for #2229.

## Premises at the integration base

Base: `d818d99f66cfd1e6f733ea1923bd44194cc52441`.

- Delivered: #2448/#2450/#2451 provide Retry-only guidance, one pending
  takeover notice and complete short-landscape recovery actions. The current
  App, error panels, takeover coordinator and owning tests retain those fixes.
  Do not implement them again.
- Delivered: `creator_web_sample_editor.spec.mjs` walks Duplicate ID recovery
  and the complete Sample save/prepare/reopen journey. Its resource-limit
  receipt is genuine; the COOK_FAILED delivered to the consumer is explicitly
  normalized by the fixture. It proves that consumer path, not a Native
  COOK_FAILED or a recovery policy for other error codes.
- Delivered: `creator_web_lifecycle.spec.mjs` proves one automatic replacement,
  including actual old Native owner retirement. It has no manual Retry runtime
  action. The complete Creator spec inventory contains no such action;
  `runtime_context.test.tsx` and `workspace_shell.test.tsx` are positive
  controls for its existing component-level coverage.
- Outstanding: a packaged page journey from an exhausted automatic allowance
  through the manual recovery button, including supported short-landscape
  geometry, actual keyboard activation, diagnostics, disabled mutation actions,
  real close/reopen and complete persisted Project/Asset identity.

## Task and declared files

One test-only Task, one Conventional Commit:

1. `tests/platform/web/creator/creator_web_status.spec.mjs`
2. `docs/plans/2026-10-24-creator-status-recovery-proof.md`

No product, SDK, owner policy, deadline or recovery behavior changes. The
failure notification seam is explicitly reduced consumer evidence. It must not
manufacture Native responses or terminal-owner receipts. All requests continue
through the original transport, and each replacement must observe the actual
old transport's positive terminal release before its factory is invoked.

## Acceptance journey

Run at 648×364 and 1440×900 with the official ordinary package:

1. Boot and import the official nonempty Project fixture; read complete Truth,
   revision and every persisted file's path, length and SHA-256.
2. Inject a typed SDK failure notification. The ordinary automatic replacement
   must open exactly one fresh Runtime, after the old Native owner retires.
3. Before that Runtime has reached stable running, inject a second notification.
   It must retain a readable terminal error and the manual retry action. Check
   the notice and action are within the viewport, the action is a real hit
   target, Project mutation stays disabled and System diagnostics remains
   reachable. No automatic third Runtime is allowed.
4. Focus the actual Retry runtime button and press Enter. The original Native
   owner must retire before exactly one third factory; the Project must reopen
   with identical complete Truth and persisted file inventory.
5. Reload and reopen the retained Project, comparing complete Truth and file
   identity again. Persist the pre-reload probe by path, with screenshots and
   geometry, so successful line-reporter runs retain evidence too.

The test catches an unavailable or clipped recovery action, a keyboard action
that never reaches its handler, a replacement that outruns its original Native
owner, or recovery that mutates saved Project/Assets. The existing lifecycle
journey remains the independent genuine timeout proof. Neither journey proves
physical owner loss, Safari/iPadOS behavior or subjective audio acceptance.

## Verification

- Baseline: five complete owning files, 367 tests PASS. Existing CSS-parser and
  Node localStorage warnings remain visible in the retained log.
- Baseline packaged selection: complete takeover (7), lifecycle (6), Sample (2)
  and accessibility/inventory (2), 17 PASS in 137.495 seconds. The initial
  missing-Sample-fixture run (15 PASS/2 setup FAIL) is retained separately.
- New spec: Node syntax; the two complete new journeys with default line
  reporter and retained path attachments; complete original 17-case selection.
- New-file ownership after staging and again on the committed range; PR body
  lint and documentation declaration; independent current-head review and live
  conflict/conversation/protection/freeze checks before guarded squash merge.
- Reuse the official ordinary producer `3dbcfeb414437aea19c5e0230fafee7e31c21e5c`.
  The entire product source is identical to this base: only the #2484 test and
  plan differ. Verify all ten distribution files, fixture digests and observer
  hashes. This Task creates no new product build or candidate/full evidence.

### Recorded results

The two new complete journeys pass with the default line reporter (10.476
seconds), independently of the earlier JSON-reporter run (11.361 seconds).
Both named JSON files and their framework copies are byte-identical, as are
the two screenshot pairs. Both probes show exactly three generations, the two
declared reduced notifications, and genuine positive Native terminal release
at each replacement factory boundary. Each compares the complete revision-3
Truth and all nine persisted files after manual recovery and after reload.
The 648×364 notice is within x176–624/y150–332; its retry action is 44 CSS px
high and is the actual center hit target. No page errors occurred. Audio
endpoint observations are built-in at both ends with no warnings.

The first new-spec run failed both cases at an incorrect expected copy string
(`Choose Retry runtime.` versus the actual `Choose Retry runtime to restart
it.`). That test-authoring failure and both traces are retained; it is not a
product regression or discriminating RED proof. Only the expectation was
corrected, with no deadline or recovery behavior changes. The original 17-case
result remains bound to its unchanged test inputs and identical product source;
it is not presented as a combined 19-case run. Precommit main refresh is still
the exact integration base above.

## Version Management

Version impact: none — tests and plan only; no manifest, API, ABI, Product Build
or immutable snapshot allocation. Existing #2237 debt remains.

## Documentation Impact

Documentation impact: none — no Architecture Portal fact or product behavior
changes. This plan records acceptance coverage and its limits.

## Pitfall disposition

Apply the existing journey-completeness, synthetic-side-effects and successful
attachment-retention procedures. No new process failure is introduced; the
new test itself owns the behavioral regression boundary. Preserve all earlier
negative evidence and candidate/device gaps.
