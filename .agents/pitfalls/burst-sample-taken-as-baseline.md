---
id: burst-sample-taken-as-baseline
area: ci-release
status: open
recurrences:
  - date: 2026-09-05
    occurrence: https://github.com/endaye/lmdj/issues/591
    observed_by: claude-code/opus-5
exit: none
---

# A CI timing ratio measured from one run, during a day this project was itself saturating the queue, was carried for two days as the repository's normal load and used to size a workstream.

## Why

#591 step 6 proposed moving native Core work to netcup. Every other step in
that Issue was opened or closed on measurement, and this one was too: one full
run on 2026-09-03 spent **137 minutes queueing against 41 executing**, a factor
of 3.3, recorded in the Issue as "queueing dominates the wall clock" and used
to rank the step as the largest remaining lever.

Re-measured on 2026-09-05 across 42 heavy job runs over 24 hours, the same
ratio was **251 minutes against 302** — 0.83. Queueing was never dominant. The
3.3 was recorded on a day this project was pushing Pull Requests continuously
through a repository-wide serial capacity group, so the number described *the
measurement session's own load* and nothing else.

The failure is not that the sample was small. It is that the observer was the
load. A single-run figure taken while you are the only writer to a shared
serial resource measures your own concurrency, and it will always overstate
queueing relative to a quiet repository. Nothing about the figure looks wrong
in isolation: it is a real reading of a real run, it was cited with its
provenance, and it survived two days of planning attention precisely because it
was already labelled "measured".

The cost was contained — the step stayed open rather than being executed, so
what was spent was planning attention and one probe workflow — but the same
error applied one step earlier would have provisioned a second host to solve a
problem the repository does not have.

## How to apply

- Before a timing ratio sizes a workstream, ask **who generated the load during
  the sample**. If the answer is "this session's own Pull Requests", it is a
  burst reading, not a baseline, and it belongs in the Issue labelled as such.
- Take the baseline over a window wide enough to contain quiet periods — a day
  of runs rather than one run — and record the run count alongside the figure.
  A ratio without an *n* cannot be re-examined later by anyone, including its
  author.
- Re-measure before acting, not only before deciding. A justification recorded
  days earlier is a hypothesis about the present; the query that produced it is
  cheap to run again, and #591 shows the answer can invert.
- When a re-measurement contradicts a recorded justification, close the step on
  the new reading and keep both numbers in the Issue. The pair is the useful
  artifact; replacing the old figure hides that the estimate was ever wrong.

No mechanism exits this entry. "Is this sample representative" is a judgment
about the load that produced it, not a property of the data, so it is not
mechanically decidable and cannot become a gate under the admission criteria.
If a second workstream is sized from a self-generated burst, escalate to a
planning section in `.agents/skills/issue-list/SKILL.md`, which already owns
parallel-workstream judgment.
