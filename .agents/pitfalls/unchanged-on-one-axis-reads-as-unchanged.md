---
id: unchanged-on-one-axis-reads-as-unchanged
area: core
status: open
recurrences:
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/issues/799
    observed_by: Claude Code (Opus 5)
exit: none
---

# A file recorded as "unchanged" for one obligation reads as unchanged for every obligation, and the promise nobody assigned to it never lands

## Why

#799's byte-path plan promised, in §3.5, that "the playback side effect
attaches to the existing `soundset.audition` in **the two Hosts that own an
engine**". Only one of the two was ever wired. `soundset.audition` on the
Native Host answered with the Set's geometry and played nothing, for a day, on
`main`, with every Task of that plan merged and green.

Nothing was hidden and nothing was stale. The plan's §4.3 Host table has a row
reading:

> `apps/native-host/src/main.cpp:130` | **unchanged.** `kSoundSetOperations`
> maps each name to a `FacadeSurface`, so a Host-only operation entered here
> forwards to a Facade that does not serve it and lands in the
> `attempt_inspect` fallthrough

Every word of that is correct, and it is correct about **one** obligation: the
registration of `soundset.audition.stop`. The Native Host had two obligations
in this plan — register nothing new, *and* play the bytes — and the row's
verdict column carries a single word for both. When Task 4 was later split
into 4a (Host wiring and the stop operation) and 4b (the Creator control), both
halves restated the verdict without its qualifier: 4a said stop is registered
"in **three** Host tables, not five", 4b said `apps/native-host/src/main.cpp`
is "**unchanged** by any Task here, for the reason §4.3 gives". So no Task's
declared-file list contained the Native Host, and a plan whose Tasks are the
unit of work cannot deliver a file no Task declares.

The split then propagated into the risk register, which is what closed the
loop. §9 item 3, "that the Native Host's audition actually plays", is recorded
as *accepted, narrowed*: "native audition is covered by table assertions, so
reachability rather than audibility". Reachability of a path that did not
exist. The sentence is only wrong if you already know the wiring is missing,
and the row that would have told you says `unchanged`.

Three properties made this survive review:

- **The reason was true, so it did not invite a second reading.** A false
  justification gets challenged. A true one about the wrong axis is worse: it
  answers the question a reviewer was going to ask, and stops them asking the
  next one.
- **A split along one axis inherits the verdict, not the reasoning.** Task 4a
  and 4b divide by *what surface changes*. §4.3's row was written under *which
  operation registers where*. Once the verdict is copied into a declared-file
  list, the axis it was decided on is no longer in the document.
- **Per-Task tests cannot see it by construction.** Every Task asserted what
  its own declared files do. A file that no Task declares is asserted by
  nobody, and the suite is exactly as green as if the work were done.

## How to apply

- When a plan promises a behavior in **N** places, give the count a home: a
  Task that names all N files, or N rows in a table whose columns are the
  obligations, not the Hosts. "The two Hosts that own an engine" is a
  quantified promise and needs a quantified check.
- Write a per-file verdict as *"unchanged **for X**"*, never bare `unchanged`.
  If the file has a second obligation in the same plan, the row needs a second
  line, because the next reader will inherit the word and not the scope.
- When splitting a Task, re-derive each file's disposition from the plan's
  behavior sections, not from the verdict column of the Task you are
  splitting. Ask of every file the plan mentions: which Task now owns it, and
  for which obligation? A file that lands in no Task's list is the finding.
- Distrust a risk-register entry that narrows a risk by naming the coverage
  that exists. "Covered by table assertions, so reachability rather than
  audibility" is only true if something is reachable; verify the mechanism
  before accepting the narrowing. See
  [`declared-gap-is-not-discharged`](declared-gap-is-not-discharged.md) for the
  sibling failure where the gap is named honestly and the defect lands in it
  anyway.

`exit: none` at recurrence 1. Whether a per-file verdict covers every
obligation the plan places on that file is a reading of prose against prose;
it is not mechanically decidable and so fails the gate admission criteria. The
nearest decidable sibling — "every file named in a plan's mechanism section
appears in exactly one Task's declared files" — would need plans to declare
those two lists in a machine-readable form the repository does not have. Until
then this exits to review judgement and to the `issue-done` §1 step that maps
each specified transition to a far-side observable, which is the step that
would have asked what observes native playback.
