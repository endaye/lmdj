# Observed headered recording sequence

## Premise and scope

Issue #2133 remains outstanding at integration/worktree base
`692d2ac18397190f71a54ce0297e5e0a54cee5ab`. C1's real transport observation
shows launch reservation next=3, acknowledged status next=4, then SDK input
expected=3. The status projector never adopts the observed cursor. Core's
internal ACK admission and native oracle already establish the advancement;
this Task does not change that ledger or retry contract.

Use status only for the same active session, Performance and epoch. Adopt a
monotonic cursor so delayed status cannot roll it back. Subsequent
inputs retain their original identity and resolve expected at dequeue.

## Declared files

- `packages/web-runtime-platform/web/runtime_session.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`
- `docs/plans/2026-10-13-performance-observed-recording-sequence.md`

## Verification

Run the new SDK oracle RED before the source fix, then the complete Runtime
session and Performance protocol Node suites. Cover acknowledged status to
next input, delayed snapshots, mismatched session/epoch. Run new-file ownership and PR declaration checks. C1 separately reruns
the complete packaged launch-to-Pad/Filter journey; its failed original run is
retained. This Task alone does not establish packaged or physical acceptance.

## Version Management

Version impact: compatible Web SDK PATCH debt, no Product Build allocation.

## Documentation impact

Documentation impact: none. The existing authoritative status and opaque Core
cursor contract is unchanged; this fixes the SDK consumer implementation.

## Pitfall impact

Product logic with direct regression coverage; no process-ledger entry.

## Results

The new matching-ACK regression failed before the fix (`1` sent instead of
`2`). After the fix the complete Runtime session and Performance protocol
selection passed 193/193. The stale status and mismatched session/epoch cases
retain the current cursor. The browser failure remains pending C1 integration.
