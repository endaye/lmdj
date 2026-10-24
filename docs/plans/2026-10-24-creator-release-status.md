# Creator takeover release status

Parent: #2112. Partial delivery for #2229.

## Premises at the integration base

Base: `886ea7bcdf300d219564734837d79e30f35174b9`.

- Already delivered: #2448/#2450/#2451 and #2485 provide usable retry guidance,
  one requester-pending card, supported short-landscape actions and the manual
  Runtime recovery journey. Do not repeat those changes.
- Still outstanding: the holder sets `yieldedProject` before awaiting
  `onYieldRuntime()`. `yieldRuntime` immediately publishes phase `closed` while
  its original shutdown barriers and close may still be pending or return
  false. `TakenOverPanel` then says "Project open in another tab" and says
  changes are saved, without observing the release result or a new holder.
  The same claim remains after an unconfirmed close. Accepting a request is
  not proof of release or another tab's acquisition; requester cancellation
  after acceptance is a concrete counterexample.
- Still outstanding: `release-failed` includes an unclean close, rejection and
  the real release deadline. The requester copy "still closing" asserts a
  particular owner state that this outcome does not establish.
- Delivered: coordinator outcomes, release deadlines, safe replacement,
  cooperative handover and original complete take-back/reopen journeys exist.
  This Task changes their presentation only, not their policy or ownership.

## Task and declared files

One atomic behavior over seven files:

1. `apps/creator-web/src/app.tsx`
2. `apps/creator-web/src/components/takeover_panel.tsx`
3. `apps/creator-web/test/project_takeover_workspace.test.tsx`
4. `tests/platform/web/creator/creator_web_takeover.spec.mjs`
5. `apps/docs-site/docs/hosts/creator-web.mdx`
6. `apps/docs-site/docs/hosts/creator-interactions.mdx`
7. `docs/plans/2026-10-24-creator-release-status.md`

Track the holder's actual original close result as pending/released/unconfirmed.
Only a clean result may show the saved/released statement. None of these states
claims another tab already opened the Project. Preserve Continue here and its
existing exact-session close/replacement guard; do not add retry, reload or
owner-retirement policy. Preserve requester cancellation and all timeouts.

## Verification and complete journeys

- Mounted App: hold the original Session close, assert the pending release
  presentation, then resolve true/false and assert the corresponding exact
  result. Establish RED on the original implementation before the fix.
- Run the complete owning takeover/runtime/workspace/error files and types.
- Preserve all seven original real-browser takeover journeys and their legs;
  only update the holder's truthful released wording.
- Add genuine two-tab close-delay journeys: intercept and hold the original
  `host.close` request before forwarding it unchanged, preserving its original
  deadline. Prove Native still owns the Project, then exercise requester cancel
  or the real release timeout. Assert accurate holder/requester copy and usable
  actions, release the original request, recover and reload with complete Truth
  and persisted file path/length/SHA checks. The held request is a delivery
  delay, not a manufactured Native result. Unconfirmed holder results remain
  explicitly component-layer evidence.
- Build and package the official ordinary Creator source with pinned Node26 /
  Emscripten6.0.5; full Portal check, staged/committed ownership and PR checks.
- Refresh main premises before commit and guarded merge. Obtain independent
  current-head review, dispose findings and read all threads/protection/freeze.
  Full/candidate/device/hearing evidence and previous negative results remain.

### Clean-source packaging boundary

The official packager rejects a modified Git tree. The first packaging attempt
exited 2 for exactly that precondition, after the actual build/type checks,
369 owning tests and full Portal check passed; retain that result. Run the final
owning checks, staged ownership and diff checks, then commit this declared Task
to establish the clean source needed by the packager. Packaging and complete
real-browser acceptance follow on that exact clean commit before shipping or
declaring the Task complete. The commit is not packaging, browser, merge or
candidate evidence. Never conceal dirty source or bypass the packager check.

## Version Management

Creator Host PATCH impact: correct compatible user-facing status, no API, ABI,
Project Truth or persisted data change. Absorb within its existing higher
#2237 same-domain debt; no manifest, Build, Assembly or snapshot allocation.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/creator-interactions/

Document pending/confirmed/unconfirmed release and the absence of proof that a
new holder has opened. Preserve existing recovery and safety procedures.

## Pitfall disposition

The regression expresses a product presentation invariant, so no new process
ledger entry is needed. Apply existing complete-journey, synthetic-side-effects,
input-bound build and retained-path-attachment procedures. No frozen release
or CI control-plane file belongs to this Task.
