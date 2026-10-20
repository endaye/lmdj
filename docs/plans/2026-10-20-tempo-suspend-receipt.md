# Retain the completed tempo receipt through ordinary audio suspension

## Task and authority

One corrective Task under #2235 / #2112, on `fix/tempo-suspend-receipt` in
its isolated worktree. Parent is Draft #2418,
`4146d70af14899449f68b3649c5e914c37a7d5bd`. Refreshed integration main is
`1581f3bd42616d36637b1d3131747bb51dee5f8e`. The owner's main freeze remains:
commit/push/Draft stack child are authorized; merge/auto-merge, Release/tag,
deployment, Channel promotion and Git cleanup remain held. Independent
current-head review remains pending. The unpublished Creator Task will follow
this correction in the same linear stack after its owning verification.

## Premise audit before edits

- Already delivered: B3's actual cancel/save settlement, original UNKNOWN
  command reconciliation, physical callback quiescence and fatal-owner retained
  lane. Preserve them; do not introduce a second save or a fake close receipt.
- Still outstanding: ordinary `audio.suspend` calls
  `settle_tempo_for_terminal()`, whose final `release_tempo_for_external()`
  resets `tempo_turn` before actual quiescence can publish its `source_lost`
  observation. The public SDK correctly retains its still-unsettled ticket;
  its next status receives `tempo_preview_stale`, so the Creator's pending
  cancel and subsequent Project/Play intent can remain blocked.
- Actual evidence: Creator's complete 17-journey selection at
  `cfcb572b53b11797400b827453cf051674ce16a0` passed 14 and failed 3. In the
  Project failure, real cancel returned `cancelling`, real Suspend returned
  `audio-suspended`, and the original status then refused
  `tempo_preview_stale`; no subsequent requested Project open was sent. The
  real suspension/resume journey separately failed to proceed to playback.
  Original traces and all earlier results remain archived. The other failure,
  metronome's first changed-tempo beat, remains the separate Creator Task.
- Missing coverage: the original Native ordinary-suspend/close test asserts
  Truth, Artifacts and physical join, then cold-reopens. It never observes the
  same completed ticket or begins a new turn in that same resumed Session.
- No successor correction exists in the refreshed live open-PR inventory.
  #2418 remains Draft with no auto-merge; main has not changed. All ten tracked
  symlinks in the new worktree are actual symlinks.

The product contract is already settled: actual source loss is a terminal
preview observation, unknown persistence retains the original command, and
only acknowledged/physically completed owner retirement permits reuse. No new
public operation, response shape, persisted Contract or concurrency authority
is introduced.

## Declared files

1. This plan.
2. `packages/web-runtime-platform/src/control_runtime.cpp`.
3. `packages/web-runtime-platform/test/pattern_tempo_preview_test.cpp`.
4. `tests/platform/web/audio/realtime_audio_worklet.spec.mjs`.
5. `apps/docs-site/docs/platform/web-runtime.mdx`.
6. `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`.

No SDK product-source change is declared. Add a further exact file only after
an evidence-backed amendment. One root writer owns these files. Heavy Native,
Wasm/browser and Portal windows run serially. Preserve the Creator worktree and
every unrelated worktree/dirty file.

## Implementation and acceptance

Use an explicit private release disposition to distinguish ordinary external
replacement, prepared-source rebase and terminal receipt retention. Terminal
settlement releases the real Facade binding but preserves the original typed
turn's completed outcome until the existing actual quiescence hook marks
`source_lost` with no applied clock. This is the producer's actual receipt;
the SDK must not manufacture it from an error code or timer.
Keep that one bounded source-loss receipt through later activation/preparation
until a successful new begin replaces it; the receipt contains no live Native binding.
Otherwise a late original observer could lose the receipt during resume too.
The first corrected run reaches resume and then refuses the fresh begin with
`tempo_source_stale`: ordinary quiescence also erased Control's actual prepared
source copy although the stopped Engine retains its Pattern for reactivation.
For a successful ordinary Suspend, keep that one already-derived immutable
source copy, while still releasing the Facade binding and all pending candidates
after the actual physical fence. Begin must continue to match its generation
against the real resumed Native source; never recook or relabel stale material.
Fatal/close cleanup retains its existing complete source retirement.

Exact repeated cancel and an already-issued known save may read their proved
terminal outcome. They must publish/write nothing. A fresh command, changed
payload, stale/foreign ticket, old set and new begin before audio resumes
remain refused. A new accepted begin replaces the old turn; no old ticket may
act on that successor. Preserve the original unknown-save reconciliation and
all physical retirement fences/deadlines.

Required far sides:

| Journey | Required observation |
| --- | --- |
| Applied preview -> Suspend | Real restored cancel outcome, actual joined/stopped audio, retained original `source_lost` with null clock, identical full Truth/history/Artifacts |
| Source-only pending -> Suspend | Cancellation intent retained, zero late audible preview, real physical join, original zero-preview source-loss receipt |
| Known save -> Suspend -> exact retry | Original command/revision and committed BPM retained; exact retry writes nothing; a different command cannot save |
| Lost save response -> Suspend | Actual original-command reconciliation, one durable revision/history entry, retained exact saved receipt, full Truth and Artifact identities |
| Resume -> next preview | Same SDK Session resumes actual audio and begins/sets/cancels a fresh ticket; original set cannot affect it; real PCM has the expected cadence |
| Undo / cold reopen | Full restored or saved Truth and exact Artifact digest/length, real output on the far side where applicable |

Use literal/manual frame oracles for PCM. Continuous callback threads own only
lifecycle/settlement facts, never a guessed wall-clock-dependent frame count.

## Verification

Before implementation, run the parent Node SDK suite and the existing Native
tempo target. Add a real Native same-owner regression first, preserve its
functional RED, rebuild after the fix and require the unchanged predicate to
pass. Run the complete original Native tempo executable plus relevant
ASan/UBSan and TSan lifecycle/stress coverage; run the complete original Node
SDK suite. No threshold, timeout, lane or original journey leg may be reduced.

Rebuild real Wasm through the owning Web Runtime entry point, run complete
owning Chromium tempo journeys and isolated real OPFS WebKit journeys, including
the new same-Session suspend/resume cases. Retain JSON/PCM evidence by file path
and read it back after execution. The Creator's own full 17-journey and complete
Creator proof remain required after it follows this parent; they are not
waived by a narrow producer PASS.

Run complete `scripts/docs-site.sh check`, staged/committed ownership checks,
exact-file staged diff checks and final branch/commit/status readback. A local
source freeze needed for clean-source packaging is not push/PR or completion
until its unchanged owning proof passes. No release/deployment or human hearing
claim follows from tests.

## Version Management

Web Runtime Platform compatible PATCH debt: repair an existing terminal
observation contract, without an operation, wire/DTO shape, ABI, persisted format
or public layout change. Deduplicate with existing same-domain MINOR/higher
debt in #2237. No manifest, Product/Assembly/Build identity, snapshot, tag or
Channel allocation.

## Documentation Impact

Documentation impact: required
Reason: clarify the existing terminal tempo observation through normal Suspend
Affected portal pages: /platform/web-runtime/ /core/modules/web-runtime-platform/

Existing architecture diagrams have unchanged components, sources and edges.
Update current source facts in the same Task after implementation.

## Execution receipts

Parent baseline: complete Node suite **744/744 PASS**, terminal 0; rebuilt
Native tempo selection **17/17 PASS**, terminal 0, including both original
stress registrations. The added actual same-owner terminal observation fails
at `pattern.tempo.preview.status` with `tempo_preview_stale` on the unchanged
producer (**functional RED**, CTest terminal 8). Preserve those baseline and
RED logs under `/tmp/lmdj-tempo-suspend-*` and the final immutable evidence.

The first corrected run retained the ticket and exposed the missing resumed
prepared source (`tempo_source_stale`, terminal 8). After retaining only the
actual immutable source for successful Suspend, the unchanged complete terminal
group passes (terminal 0, 4.45s), including source-only cancellation, exact known
and genuinely lost save receipts, same-owner resume/new turn and Undo/reopen.
This is Native evidence; real SDK/Worklet, sanitizers and the remaining owning
proofs are still required. No new PR/push.

The complete corrected Native tempo selection, including both original stress
registrations, passed **17/17**, terminal 0, 20.94s. The same-session Wasm
journeys are now declared and written for cancelled and already-saved turns:
actual pre-Suspend PCM, real context suspension, exact terminal replay, trusted
same-Session resume, new independently owned preview/restore, full Truth and
Artifact identities, saved Undo, physical page close and cold 120 BPM output.
JavaScript syntax and Git diff checks pass. Their execution is still pending.

The final complete Chromium AudioWorklet/failure selection passed **37/37**,
terminal 0, 2.2m, after strengthening the new old-ticket refusal leg to require
two independently predicted PCM quarters after that actual refusal. Both new
same-Session JSON receipts were read back with all four/five required legs;
the saved journey includes actual Undo before cold reopen. Complete original
Node SDK **744/744**, isolated OPFS WebKit **3/3**, and the pinned Emscripten
6.0.5 production Wasm rebuild pass. WebKit covers the existing executor and
saved-WAV journeys; the new Suspend PCM cases run on Chromium, not Safari/iPad.

Complete ASan/UBSan tempo **17/17** (55.55s) and TSan tempo **17/17** (142.57s),
including both original stress registrations, passed with terminal 0. No test
budget, timeout, assertion, selection or original journey leg was reduced.
The MacBook Pro Speakers output route was observed at both ends of the final
Chromium run with no warning; this is no human-hearing acceptance.

Precommit main refresh remains `1581f3bd42616d36637b1d3131747bb51dee5f8e`,
unchanged from the premise audit. Draft #2418 still has the exact declared
parent head and no auto-merge. Complete Portal, staged ownership and final
shipping readback remain pending at this checkpoint.

Final complete `scripts/docs-site.sh check` passed with terminal 0: 179 tests,
52 current pages, all 10 diagram sources/20 outputs, production build and all
50 routes/internal links. The staged new-file ownership suite passed **77/77**,
terminal 0, including explicit ownership/top-level admission of this new plan.
No qualifying process pitfall was added: the product lifetime invariant is
fully expressed by these regressions. Commit/push/Draft readback follows;
independent current-head review, integration and Creator/full candidate/device
acceptance remain separate and pending.
