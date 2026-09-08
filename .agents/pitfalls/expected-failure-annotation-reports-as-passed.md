---
id: expected-failure-annotation-reports-as-passed
area: product
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/674
    observed_by: Claude Code (Opus 5)
exit: none
---

# `test.fail()` counts an expected failure inside "passed", so a journey annotated as blocked reports the same summary whether the blocker is still there or the journey now runs — and the legs behind the blocker were never verified either way

## Why

The Stage 11 browser Sound Set journey
(`tests/platform/web/creator/creator_web_soundset.spec.mjs`) was written in
full against three known defects (#900, #901, #902) and both cases were
annotated `test.fail()`. The reasoning was sound and is recorded in the file:
`skip` would stop the legs running, `fixme` would drop them, and `test.fail()`
turns the lane red the moment the journey starts passing, so the annotation
cannot outlive the defects.

What it also does is report an expected failure inside the **passed** count.
When all three defects had landed, the first run of the unchanged spec printed:

```
  2 passed (13.7s)
```

That is two tests failing at their first assertion — the Bundle import — and
two tests walking five legs each to a real green, rendered identically. 13.7
seconds for two journeys that import a 767 KB Bundle at revision 66, fetch a
seven-Set Catalog and commit two installs should have been the tell, but
nothing in the summary says so, and Playwright prints no error for an expected
failure. Removing the annotations was the only way to learn which had happened.

The second half is worse and is the part that outlives the annotation. Legs 2
to 5 had **never executed**: their selectors and counts were checked by hand
against the surface component. Hand-checking finds selector typos. It does not
find arithmetic. Once the annotations came off, three defects surfaced in the
spec itself, none of them in the product:

* leg 1 expected one `/catalog/index.json` on the wire. There are two, because
  the surface lists on mount and the leg then clicks Refresh Catalog.
* leg 5 expected Bank B to hold 11 occupied Pads after installing an 11-slot
  Set. The proof fixture fills all 64 Pads, so it holds 16 before and after.
* the teardown helper guarded on `child.exitCode !== null`. A child killed by a
  signal reports `exitCode === null` and names the signal in `signalCode`, so
  the already-dead server read as running and `await`ed an `exit` event that
  had already fired — a 300-second hang after a journey that had passed in 8.8.

A fourth was a routing decision that could never have worked: the second case
was titled so the Creator gate's webkit slot would select it, but Playwright's
headless WebKit fails the Creator's OPFS preflight, so that slot could only
ever have reported it as an expected failure.

This is [[audit-axis-cannot-fire]] seen from the test runner's side: a
predicate that cannot distinguish "failed to measure" from "measured and found
nothing" reports the second when it means the first. It is the companion to
[[acceptance-journey-truncation]] — that entry is about a journey cut short on
purpose, this one is about a journey written in full whose tail has never run.

## How to apply

When a journey is annotated `test.fail()`, `xfail`, or any expected-failure
marker because a named defect blocks it:

1. **State in the file how far it has actually executed**, leg by leg, and
   which legs have never run. The Stage 11 spec did this and it was the single
   most useful thing in it — it is why nobody read the green summary as proof.
2. **Never read the runner's summary line as the status of an annotated case.**
   Re-run with the annotation removed to learn which side of it you are on;
   the summary cannot tell you and neither can the elapsed time on its own.
3. **When the blocking defect lands, budget for debugging the unrun legs**, and
   expect their bugs to be counting bugs rather than selector bugs. Before
   changing any expectation, establish whether the spec or the product is
   wrong, and say which in the report.
4. **Prove the new green is load-bearing.** Perturb at least one far-side
   assertion per newly-executing leg and confirm it turns red at that line with
   real product data on the received side. A journey that passes 8.8 seconds
   after never having run deserves that check.
5. **Check where the title routes the case.** A name chosen to match a lane's
   `--grep` is a routing decision; verify that lane's browser or runner can
   reach the surface at all, or the case is annotated-red forever.

No mechanism can decide this: a runner cannot know that an expected failure is
stale, and no deterministic check can tell a hand-checked assertion from an
executed one. It exits to review attention, which is why it is written down.
