# Creator GROOVE current-Pattern cancellation — #2112 B01

## Scope and current premises

Owner: `groove_cancel` agent, coordinated by the #2112 Goal root. Isolated
worktree: `lmdj-goal-groove-cancel`; branch: `fix/creator-groove-cancel-current`.
Integration base and Task base, refreshed before editing on 2026-10-13:
`9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`.

- **Outstanding:** `PatternSelector` suppresses `onSelect` whenever the chosen
  ID equals current, even when `queuedIndex` names a pending switch. The
  current `SequenceTouchWorkspace` passes that queue, but the selector consumes
  the click. The new component regression observes zero owner calls before
  the fix. No successor changed this path after #1992 (`a98ae01c`). Live #2112
  and the open PR inventory were read before editing.
- **Already delivered:** App `selectSequencePattern` forwards playing requests
  through `requestTransportPatternSwitch`, then reconciles authority. The Host
  handles cancellation and an already-applied predecessor. Reuse those paths;
  do not duplicate them in a component or optimistically erase a queue.
- **Settled product rule:** the
  [2026-10-10 decision](../prd/decisions/2026-10-10-pattern-switch-while-playing.md)
  §4 applies current-Pattern cancellation to all selection entries. A racing
  predecessor may still apply; subsequent selection follows the real outcome.

## One implementation Task

When a queue exists, choosing current forwards the same selection intent as
other choices and closes the picker. When no queue exists, choosing current
only closes it. Cancel/Escape remain dismissal without a transport request.
Current and queued labels derive exclusively from the returned transport
projection. Recording/busy guards remain with their existing owners.

Declared files (no shared stylesheet, App, controller, SDK or engine edits):

- `apps/creator-web/src/components/touch_kit.tsx`
- `apps/creator-web/test/sequence_surface.test.tsx`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `apps/docs-site/docs/hosts/creator-interactions.mdx`
- `docs/plans/2026-10-13-creator-groove-cancel.md`

## Verification and far-side assertions

1. Component regression: current-with-queue calls the owner exactly once;
   closing does not change the queue before a projection arrives. Cancellation
   and an applied predecessor followed by a return queue both render the
   supplied authority. Current-without-queue, stopped-current, Cancel/Escape
   remain no-ops; focus returns to the trigger.
2. Run complete `sequence_surface.test.tsx` and
   `pattern_transport_actions.test.ts` plus Creator `tsc --noEmit`.
3. Packaged Chromium owning journey: stopped-current emits no publication;
   playing-current without queue emits no switch; queue B from GROOVE while A
   remains current; choose A and verify the native cancellation response;
   advance the real audio clock past the cancelled activation frame and verify
   A is still current without a queue or snapshot reload; Stop; reopen and
   compare complete Project Truth to its initial authored state.
4. The deterministic audio-race authority remains the unchanged native tests
   `test_transport_current_pattern_withdraws_both_exact_authorities` and
   `test_transport_current_pattern_cancel_race_requeues_after_predecessor_applies`
   in `packages/web-runtime-platform/test/control_runtime_test.cpp`. The
   component projection test does not claim to execute that native race.
5. Run `scripts/docs-site.sh check` for the changed portal facts. No new
   universal gate, timeout adjustment, runtime hook or acceptance shortcut.

Heavy build/browser/portal execution is coordinated with the root. Root
granted the B01 window after S6's original proof runner terminated (its failed
receipt stays with S6, not this baseline). The normal Creator packager requires
clean Git source. Root approved the existing K2a clean-source order:

1. All checks executable on dirty source — owning component/App tests, types,
   whole Portal, scope and whitespace — must pass before the local checkpoint.
2. Stage only the five declared files and create one local source checkpoint.
   This is not completion or permission to push while browser work is UNRUN.
3. Freshly build/package this clean source through the normal interface. Run
   the complete declared browser journey. Preserve failures, fix their cause,
   rerun affected checks and rebuild; keep one unpublished atomic Task commit.
4. Only after all Task checks pass may the Task enter current-head review and
   shipping. Root retains the final guarded merge.

Evidence so far:

- RED, before the fix: focused GROOVE component selection ran 6 tests; the
  two owner-call regressions failed at `sequence_surface.test.tsx:536` with
  zero calls, 4 passed. Tool receipt exited 1.
- GREEN: complete `sequence_surface.test.tsx` and
  `pattern_transport_actions.test.ts`: 2 files, 54 tests passed.
- GREEN: Creator `npx tsc --noEmit` exited 0.
- GREEN: four existing App owner/projection/snap/refusal/Stop regression
  selections in `workspace_shell.test.tsx`; 4 passed, 184 not selected.
- GREEN: browser spec syntax and `git diff --check`; change-scope policy
  regression suite 77 tests passed (rerun its required post-commit check
  before shipping the added plan).
- GREEN: whole `scripts/docs-site.sh check`, exit 0; 177 tests and 50 routes
  plus internal links. Receipt: `build/verification/b01/portal-check.log`.
- GREEN: fresh `scripts/creator-web.sh build` with the pinned Emscripten
  6.0.5 and four compiler jobs, followed by normal `scripts/creator-web.sh
  package`. No external Runtime artifact was reused.
- GREEN: packaged Chromium `creator_web_sequence.spec.mjs --grep 'GROOVE
  current selection cancels'`, complete four-leg journey, 1 passed in 16.6 s.
  Source checkpoint: `94e8324194e13c91546135d9e1cb84da23a13c14`;
  manifest SHA256:
  `c9fac783599749bda870b85275b1c45c203ace16a028cb2631b7f10de430c531`.
  The final commit adds only this evidence to the plan, retaining identical
  product, browser-test and portal inputs.
  Receipt: `build/verification/b01/browser-94e83241.log`; unique Playwright
  result slot: `b01-groove-94e83241`.
- Native race tests were inspected, not re-executed by this Task.

Fixture provenance: the checked-in
`tests/platform/web/deployment/creator_project_fixture.mjs` at the Task base,
source SHA256 `df718fc7b0dc08b6f806767a31ee55e0628b0e03c571ad79483310276f5facd1`,
decodes to 767554 bytes with SHA256
`66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`.
The normal bundle verifier accepted it. Its real v5 Project is
`00000000-0000-4000-8000-000000000001`, revision 66, BPM 120, with one empty
one-bar Pattern and one Asset across four Banks. The browser created the
second Pattern through the UI, committed BPM 40, then captured the full
authored Truth for cancellation/Stop/reopen comparison. Source and decoded
identities are retained in `build/verification/b01/fixture-identity.json`.

Scope of PASS: this Task's GROOVE wiring and its declared journey. The complete
Creator suite, WebKit/iPad/device/hearing acceptance and the umbrella's other
UI/capability work are not established by this focused result.

Pitfall disposition: product logic fully expressed by its regression test;
no new process/invariant pitfall entry is warranted.

## Version Management

Version impact: Creator Host PATCH debt for a compatible bug fix to its
already-approved interaction. No
Module API, ABI, Contract or persisted schema changes. Record this Creator
fix for the next identity allocation; this Task allocates no Product Build,
changes no manifest, and initiates no release or deployment.

## Documentation Impact

Documentation impact: required — `/hosts/creator-interactions/` removes the
old GROOVE exception and distinguishes dismissal, cancellation intent and
the authority's actual result. The portal check is required before commit.
