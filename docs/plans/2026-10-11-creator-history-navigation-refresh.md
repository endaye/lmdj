# Creator history refresh during page navigation

## Task and refreshed premises

Inspected integration source: `4a2b26f03a1e628882e907c92a9b9411b48e110d`.
The isolated branch is `fix/creator-overview-latency`. PR #1991's owned
inspection API and PR #1992/#1998's transport and Launch wiring are delivered
and must be retained. No open PR owned these files at the start inspection.

The original full Creator run at `6afae7ed` retained an Overview journey
timeout at 30 seconds. Four other original #1936 failures passed; they remain
subject to the final complete proof. A reduced diagnostic at `a98ae01c`
preserved the whole Overview and real-playing System journeys, original
budgets and two workers: both passed in 25.5 seconds. Its 274 native responses
included 21 history inspections totaling 3.303 seconds. This diagnostic does
not establish a complete-lane pass or resolve the intermittent timeout.

Still outstanding: App includes the active page in its history refresh key.
Switching a page clears the global Undo/Redo status and queues an inspection
even when Project, revision, Session and history authority did not change.
Reduce this observable readiness defect through the real App before fixing it.

Uncertain before the source change: page changes also accidentally refresh
after some authority changes. Independent source audit found that discarding
the last Performance recovery can change history admission without changing
Project revision or recording phase. Preserve this real invalidation explicitly;
audit the other Core history reasons before removing the page dependency.

The independent audit also found Slice's local authoring owner may fail after
unmount without reporting a diagnostic or revision to App. The real App
reduction issued adoption, left Slice, rejected the request, then navigated
again: the first conditional-refresh draft missed the authority read (expected
three inspections, observed two). Retain the old navigation fallback after
visiting Slice/Sound Sets for the remainder of the Session/Project. No request
settlement is inferred from that visit or from a successful inspection.

Transport publication can stay pending after phase becomes idle. The added
real App reduction retained the same stopped phase/revision/page and cleared
publication pending; the original observation condition did not poll again,
so history remained blocked. Preserve the existing 250 ms observation cadence
while this explicit pending flag is true, without changing transport commands,
busy controls or the reducer. This is the remaining history-authority producer
observation gap; a refresh-key input alone cannot observe its settlement.

## Declared files

One Task, one Conventional Commit, exactly four files:

1. `apps/creator-web/src/app.tsx`
2. `apps/creator-web/src/components/authoring_history.tsx`
3. `apps/creator-web/test/workspace_shell.test.tsx`
4. `docs/plans/2026-10-11-creator-history-navigation-refresh.md`

App changes are confined to history observation and refresh dependencies,
including observing the existing transport publication-pending signal until
settlement at the existing cadence.
Keep all recording, transport, revision, Session, focus and restore protections.
Do not remove history busy/inert guards or any projection refresh. The parallel
MASTER Task owns its independent monitoring callback and consumer props.

Separate page navigation from the authority key. A page change preserves an
already-ready history status when no client operation blocks it. A blocked or
unknown history still rechecks on page navigation, as does any page change
after a reported failure; its existing focus listener remains installed. The
current Session/Project's reported-failure signal is a conservative flag,
not a new error classifier or claim that a failed command did not commit. This
retains the earlier fallback for uncertain Sample abort
or lost authoring acknowledgements instead of claiming to solve their producer
settlement. Visiting a local authoring owner or observing a reported failure
keeps this fallback for subsequent navigation until Session/Project replacement;
it does not classify every late failure. Add explicit Performance recovery-pending and transport
publication-pending authority inputs, including recovery-list readiness, which can change independently of revision
and recording phase. Do not key on runtime frames or the complete status object.

Current-head independent review at `accf414a38896801d6f4ff773bff01c19cede2a1`
found that the retained Workspace diagnostic log survives Session/Project
replacement and immediately re-arms the hook's reset fallback. This is still
outstanding against refreshed main `5d31f21bb7b5f91014881c05b0ef7f4708c03b29`;
no successor implements this context boundary. This corrective Task declares
exactly `apps/creator-web/src/app.tsx`,
`apps/creator-web/test/workspace_shell.test.tsx` and this plan, as one
Conventional Commit; the history hook needs no change. Bind a failure signal to each current
Session/Project context while retaining all Developer diagnostic records.
A callback retained by a retired context must not mark a fresh context failed.
Returning to a previously opened Project starts a fresh context too. Preserve
same-context fallback after any new failure, without classifying its operation.

The independent exact-head review of `3ea54286d5fa83c47b7bca221a9aaa6f1f342156`
accepted the three context-lifecycle fixes but found a residual capture binding
P2. Pad capture's reusable commit deps and the Sequence capture phase callback
can start a new Project operation through current refs while retaining the
previous context's failure callback. This remains outstanding against refreshed
main `5d31f21bb7b5f91014881c05b0ef7f4708c03b29`. The next corrective Task declares
the same three files above, one Conventional Commit. Refresh these two bindings
when their owning failure callback changes; an already-issued operation keeps
its original callback. Do not resolve a late failure through a latest-context
ref. Reduce the defect through a new empty-Pad recording in another Project in
the same Session before changing App: after a committed but unpublished take,
ready history must recheck on navigation, disable Undo during the held read,
then restore ready Undo when that inspection completes. This component proof
does not establish trusted microphone input, audible output or browser proof.

## Verification and acceptance

The lowest-tier regression mounts the real App and existing Session fixtures.
After history becomes ready, a pure page change must keep the rail's available
Undo state and issue no new authority read. Delay any unexpected read so a
fast fixture cannot hide the temporary unavailable state. A separate regression
must prove a real Performance recovery admission change refreshes history.
Also prove publication settlement without phase/revision/page change and the
late unmounted Slice adoption failure followed by navigation. These are distinct
authority facts, not evidence that Sample abort producer settlement was fixed.
Retain the existing history conflict, retry, focus, recording, recovery,
context-cancellation and Session replacement tests.

Reduce the lifecycle defect through the real App: report a failure, replace
the Project or Runtime Session, wait for fresh ready history, then delay any
unexpected inspection and assert that pure navigation keeps Undo available
without another read. Include returning to the same Project and prove that
a new failure in the fresh context still rechecks history on navigation.
These lowest-tier assertions must fail on the pre-fix source before the
context-owned signal is implemented.

Run focused regressions against the original implementation and retain their
actual assertion failures. Then run the workspace/history suites and Creator
TypeScript check. Stage the four files, run the existing path-ownership suite,
inspect non-main branch, exact staged list and cached diff check, commit, and
inspect committed files and clean status. Complete every selected batch-only
lane on the committed head without skips, timeout changes or risk waivers.
Keep the complete Overview journey, all five original failure journeys and
the new eighth deployment group. Review the actual current head before merge.

## Version Management

Version impact: Creator PATCH debt in the follow-up plan's V1 settlement;
this corrects unnecessary invalidation of existing history controls. No public
API, Contract, manifest or Product Build identity is allocated in this Task.

## Documentation Impact

Documentation impact: none — the existing public history behavior and Portal
control descriptions stay valid. This Task changes internal refresh triggers;
it adds no public operation or product identity.

## Pitfall Impact

Pitfall impact: none — the open Creator intermittent-failure entry was read.
Do not attribute the full timeout to contention or count the reduced pass as
closure. The product readiness defect is expressed by its regression tests.

## Progress

The authority audit and real App reductions are retained outside the worktree.
The original ready-history navigation and recovery-list reductions failed at
their intended assertions. The conditional-refresh draft's late Slice fallback
and publication observation failures are also retained. Workspace/history
suites now pass all 155 tests, including six new real App regressions. Creator
TypeScript passes after correcting test-query options and a mutable/readonly
fixture result type. Initial fixture-only phase assertions read Project's Audio
label rather than transport phase; those failures are retained separately and
do not count as a product reduction.

Removing just the publication history-key input and, separately, just its
observation condition each makes the settlement regression fail at the intended
available-Undo assertion. Restoring App with a fresh mtime and rebuilding the
test passes; no original timeout or journey leg changed. The independent
read-only audit inspected all ten Core history reasons, the Slice fallback,
focus/epoch ownership and publication observation. It does not replace formal
review of the final committed head.

Precommit main refresh remains `4a2b26f03a1e628882e907c92a9b9411b48e110d`;
PR #1936 is already merged as `9b4d80c9e5ed965f5776c0321cf166d9d1f289ce`.
This Task repairs remaining behavior and carries its verification debt, rather
than repeating that implementation. Complete proof, current-head review, merge
and the original #1936 acceptance closure remain open.

The corrective context-lifecycle Task retains the independent current-head
review and its accepted narrower P2. All three real App reductions failed at
the intended extra-inspection assertion on the pre-fix source: another Project,
returning to the same Project, and Runtime Session replacement. An initial
test-fixture mistake queried System-only diagnostics while System was closed;
that failure is retained and is not counted as a product RED.

The context-owned failure callback retains its own signal object, while the
Developer log still appends all records. Each fresh context's three regressions
now pass, including a new failure's conservative held inspection and eventual
ready Undo after it settles. The complete workspace/history suites pass 158
tests; TypeScript, 77 ownership tests and 15 ledger tests pass. No timeout or
journey changed. The prior integrated-head epoch-race finding has a recorded
independent source-based rejection; the new fix still requires its own commit,
complete Creator lane and current-head review before shipping.

The residual capture-owner reduction failed on committed `3ea54286` at its
intended navigation assertion (expected five inspections, observed four),
after a new Project's real App/PadCapture commit reported unpublished Runtime
preparation. Refreshing the reusable Pad deps and Sequence phase callback on
their context-owned publisher fixes this binding while preserving each
already-issued operation's original callback. The same regression now passes
its held-read, unavailable Undo and eventual ready Undo assertions. Complete
workspace/history suites pass 159 tests, and Creator TypeScript passes. This is
a controlled component recording proof, not real microphone/hearing evidence;
the Sequence binding also has source review, without claiming a separate new
Sequence capture RED execution. Exact-head complete Creator proof and review
remain required before merge.
