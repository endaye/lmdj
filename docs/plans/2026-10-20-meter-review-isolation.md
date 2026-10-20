# Meter review isolation fixes (#2430)

One follow-up implementation Task on the published feature branch, one new
Conventional Commit; no rewrite of source7101f104 or original Draft history.
Refreshed main remains6ca4c9cf78471c337668ec1642d23610f49f9fb2; Task parent
7101f1049d234ef5b7d6fa67257149c858a6f18b. Live exact-head GLM review5587698462
(run39450488872 attempt2) has two unresolved findings; it is not a clean review.
The first failed provider attempt remains historical evidence, not approval.

## Refreshed finding dispositions

F1 https://github.com/endaye/lmdj/pull/2430#discussion_r4327049345:
ACK of a valid foreign owner is required to drain the shared bounded token,
but its postMessage failure currently latches protocol-error on the current
owner. Still outstanding: contain failure to the named owner, retaining old
ACK attempts and current-owner ACK failure semantics. No resend or packet change.

F2 https://github.com/endaye/lmdj/pull/2430#discussion_r4327049365:
The pinned Chromium151.0.7922.34 source FireProcessorError is restricted to
construction/process/missing-process fatal states, then dispatches ErrorEvent;
real browser proof already observes trusted error. Keep both native event names,
without browser-agent sniffing. The concrete false trigger is a synthetic
generic error event: DOM dispatchEvent marks it untrusted, yet current code
permanently fails/reconnects the tap. Filter that path to browser-trusted events.
The unit fixture models the trusted callback explicitly; only the existing
actual-render-throw packaged journey proves a native event and real audio.

Primary sources:
- https://dom.spec.whatwg.org/#dom-event-istrusted
- https://webaudio.github.io/web-audio-api/#dom-audioworkletnode-onprocessorerror
- https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.34/third_party/blink/renderer/modules/webaudio/audio_worklet_node.cc
  (downloaded source SHA256574ff4f5c76f2c24209b298fb56d7c0f50e2f926b9b0f5e2bbdb144e1086335d).

## Exact declared files

- docs/plans/2026-10-20-meter-review-isolation.md
- packages/web-runtime-platform/web/performance_master_capture.mjs
- packages/web-runtime-platform/web/runtime_session.mjs
- packages/web-runtime-platform/test/performance_master_capture.test.mjs
- packages/web-runtime-platform/test/runtime_session.test.mjs

## Verification

First add independent owning regressions and observe both RED on7101 product
code. Then fix, run complete owning/SDK Node selections, strict SDK/Creator types,
dependencies/ownership and complete Portal source facts checks. Keep existing
current-owner ACK failure, capture/stop and native duplicate recovery cases.
New synthetic-event absence checks wait for the async chain's far side.

Repeat all four semantic controls/restoration and full SDK after changes; do not
reuse old source receipts as current-head proof. Commit only verified declared
files, then rebuild/package the clean new head and run the unchanged complete
normal+actual-render-fault journey with the original budgets, true native trusted
error and direct-monitor PCM far-side assertions. Earlier source7101 graph/alias
negative evidence remains bound to that cut. No timeout, threshold, selection,
original journey leg or production fault hook changes.

Push follow-up commit, retain both live threads for automatic repair recheck;
inspect its real receipts before merge. Do not hand-resolve a fix to bypass it.
Current-head independent review, actual conflicts/conversations/live protection
and guarded squash remain required. No merge until these pass.

## Version Management

Version impact: none beyond the existing additive Platform MINOR debt in#2237.
Correct owner/fault isolation; no public shape, packet, clock/graph/gain,
Native ABI, persistence, identity, Product/Assembly/Build or snapshot change.

## Documentation Impact

Documentation impact: none.
Reason: implementation now conforms to the existing current Portal isolation
and native-failure facts; no route/diagram/API change. Complete Portal check is
still retained for the documented source facts affected by this fix.

Pitfall impact: none; both product rules are captured by owning regressions and
the actual-render journey. Existing polling-alias record/escalation unchanged.
Owner partial-unfreeze scope and frozen paths retained. No auto-merge, manual
release/tag/Runtime deploy/Channel or agent Git cleanup.

## Precommit verification, 2026-10-21

Both newly added regressions failed on the unchanged7101 implementation, then
passed with the fix. Complete owning448 and full SDK603 PASS with zero skips;
four semantic mutations each RED1, byte-identical fresh-mtime restoration each
GREEN, followed by full SDK603 PASS. Direct strict SDK and Creator tsc, four
JS syntax checks and dependencies PASS. Complete Portal check PASS:179 tests,
53 pages and51 routes/internal links. Two initial guessed npm scripts did not
exist; those command failures remain diagnostic and were replaced by the
existing direct tsc commands, each actual exit0. No product/test weakening.

Precommit refresh still6ca4c9cf78471c337668ec1642d23610f49f9fb2; all seven
applicable governance hashes unchanged. Both reviewed premises remain exactly
as dispositioned above; no intervening implementation or successor merge.
Packaged new-head browser proof and independent repair review remain pending.
