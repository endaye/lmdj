---
id: facade-surface-test-budget-headroom
area: core
status: open
recurrences:
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/444
    observed_by: Codex GPT-5
  - date: 2026-09-05
    occurrence: https://github.com/endaye/lmdj/issues/566
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-16
    occurrence: https://github.com/endaye/lmdj/issues/1389
    observed_by: Kimi (agent)
  - date: 2026-09-19
    occurrence: https://github.com/endaye/lmdj/actions/runs/35419357786
    observed_by: Claude Code (Fable 5.1)
  - date: 2026-10-10
    occurrence: https://github.com/endaye/lmdj/issues/1965
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-14
    occurrence: https://github.com/endaye/lmdj/issues/2238
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-14
    occurrence: https://github.com/endaye/lmdj/issues/2261
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-15
    occurrence: https://github.com/endaye/lmdj/issues/2286
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-15
    occurrence: https://github.com/endaye/lmdj/actions/runs/38776156275
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-16
    occurrence: https://github.com/endaye/lmdj/issues/2283
    observed_by: Codex (GPT-6)
  - date: 2026-10-17
    occurrence: https://github.com/endaye/lmdj/actions/runs/38984377212
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-18
    occurrence: https://github.com/endaye/lmdj/actions/runs/39107252620
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-26
    occurrence: https://github.com/endaye/lmdj/actions/runs/40120366652
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-31
    occurrence: https://github.com/endaye/lmdj/actions/runs/41027926505
    observed_by: Claude Code (Opus 5.5)
exit: none
escalation: https://github.com/endaye/lmdj/issues/657
---

# A fixed wall-clock test budget can pass locally yet become a deterministic CI timeout once normal Runner variance consumes the headroom it never had.

## Why

The Sequence and Sample Facade surface binaries accumulated many durable-file
and Project mutation scenarios behind one component registration each. A recent
successful coverage run already used 25.10 and 20.05 seconds of their 30-second
budgets. The next main coverage run and an unrelated Pull Request run then timed
out both binaries at 30 seconds on two separate Linux runners, while the same
binaries remained fast locally. Product assertions did not identify the
problem: only the historical CI budget evidence showed that the aggregation,
not either product change, had exhausted normal execution variance.

The shape is not native-specific. On 2026-09-05 the same failure reached a
Python harness: `apps/creator-web/test/deploy_command_test.py` allowed a spawned
deploy subprocess a fixed 15 seconds to reach its post-publish sentinel. Both
signal subTests failed together on `actions-runner-02` while four shards of the
same suite contended for one shared self-hosted host, minutes after the exact
same job passed on `main` and while the full suite passed locally. A budget that
every local run confirms is exactly the budget nobody re-examines.

## How to apply

Keep the two Facade surface binaries partitioned by named scenario tables. Each
CTest registration must execute exactly one shard, while bare binary execution
must still traverse the union of every shard. The absorbed build gate compares
the binaries' declared shard counts with the registered CTest commands; add a
new scenario to one named shard and split again before any shard approaches its
component budget. `lmdj_pattern_count_in_tests` follows the same rule (#2238):
its deadline cases sleep past the real 1 s input and 5 s opening deadlines,
so each deadline family is its own registration rather than one more scenario
in a shard that is already near its budget. `lmdj_pattern_transport_segment_tests`
splits its real-SIGKILL recovery matrix by segment phase for the same reason:
adding the nonzero phase doubled one registration past its 90 s ASan budget.

`tests/build/facade_surface_sharding_test.py` still enforces that partitioning,
but it can only read C++ CTest registrations; it cannot see a wall-clock
deadline in any other harness. Everywhere else this invariant is guidance only.

Derive a test budget from the work it covers rather than writing one wall-clock
literal: a named per-unit allowance multiplied by a declared unit count, so the
number moves when the work does. Make the timeout message name the elapsed time,
the budget and its derivation, and the resource that never arrived, so a
recurrence is diagnosable from the run log without reading the harness. For a spawned child whose per-unit progress is observable, prefer a
no-progress watchdog over any wall-clock total: stream the child's transcript
and kill only after a bounded silence, so a contended host's slow-but-healthy
run passes while a genuine hang still dies with the in-flight unit named. The
PR-Agent integration child in `tests/build/ci_pr_agent_review_test.py`
(`run_child_with_watchdog`, #1389) is the reference shape: 120s of no test
progress kills the child; a total ceiling remains only against a child that
emits progress forever.

A CI job's `timeout-minutes` is the same kind of budget at lane scale. The
main batch Creator job grew from 33.6 to 35.3 minutes against its fixed 35
over one day and was then cancelled on every batch (#1965). Before
touching the budget, read the job's phase timings and remove work the
proof never consumes: that job compiled the whole native dev tree for one
fixture binary.
The same job was cancelled again from 2026-10-13 when its Chromium journeys
grew from 94 to 133 (~44 min of Proof, #2286). Overlapping its browser groups
on the 8-core M1 saved under a minute and multiplied timeouts: these
Wasm/AudioWorklet journeys are CPU-bound. Measure before assuming a browser
suite waits on real time; when no work can honestly be removed, the limit is
an owner budget decision (here 55 minutes), not an agent's.
The Linux `core-asan` job hit the same wall on 2026-10-15: ASan `full` took
1145.7 s, then the serial stress tier was cancelled at 16/17 with
`facade.candidate_store_stress` at 580.8 s and `facade.pattern_count_in_stress`
at 201.8 s (run 38776156275). The owner raised that limit from 35 to 55
minutes; making the dominant stress registration cheaper without weakening it
is #2306. Under a sanitizer, read each stress registration's own duration, not
only its Release time.

The macOS primary job repeated this shape in #2283: after #2272 had already
parallelized count-in rounds, M1 job `116906584110` still took 29m34s of its
30-minute budget with 100% ccache hits. Native ASan CTest consumed 1497.37 s;
both configure/build phases together took only 51.38 s. Faster compilation
cannot remove that test work. The owner calibrated this job to 40 minutes on
2026-10-16, retaining every test deadline and selection. Re-evaluate when any
M1 `Run macOS Core gates` step exceeds 35 minutes: optimize the tests next,
not the job limit. The remaining cost work belongs to #2306 and #2284.
The M1 Release stress job followed on 2026-10-16/17: twenty repetitions took
52.7 min on an idle M1 (run 38662185311), and runs 38962992372 and
38984377212 (the 2.0.112.0 candidate batch) were cancelled at 60 min while the
M1 also served other work (`facade.pattern_count_in_stress` 131 s vs 106 s,
`facade.candidate_store_stress` 57 s vs 47 s per repetition). The owner raised
that limit to 80 minutes with the repeat count unchanged; on a shared runner,
size a repeated job against its loaded per-repetition time. The cost work
remains #2284 and #2306.

Splitting into more registrations only helps a runner that executes them
concurrently, and the stress jobs do not: `scripts/core.sh test tsan stress`
and the Release stress job's `ctest -L '^stress$' --repeat until-fail:20` run
one test at a time, and the Release job multiplies each registration by up to
twenty. `facade.pattern_count_in_stress` ran 64 independent journey rounds in
sequence: about 185 s Release, so its twenty repetitions alone (3,700 s)
outran the 60-minute job, and over its 1,200 s TSan timeout in a 30-minute job
(#2261).
When repetitions are independent, run them in parallel child processes inside
the one registration, and keep real-deadline cases out of that contention.
Size the worker count by the threads each worker keeps runnable and by the
build's instrumentation, not by core count alone. On 2026-10-18 the 2.0.116.0
candidate's M1 ASan lane failed `facade.pattern_count_in_stress` after 288 s
(run 39107252620): eight ASan workers, each a spinning `wait_for` plus the
executor it waits on, shared four performance cores, and one settle missed
its fixed 3 s deadline, whose two slowest settles already take about 1 s in a
lone ASan round. The same binary had passed on the M4 Pro in 109 s. Sanitizer
builds now give each worker two hardware threads; the deadline and all 64
rounds are unchanged. The M1 is also a workstation: a loaded host fails even
the reduced worker count, so do not run local heavy work while it serves a
batch.
Before adding a stress registration, multiply its Release time by twenty and
measure it under TSan.
The M1 `macOS gates (primary)` job crossed its 40-minute limit on two
consecutive main batches (41005326341, 41027926505) with every test passing:
its native ASan CTest runs one test at a time and took 1999 s, of which
`facade.candidate_store_stress` took 405 s running 100 independent iterations
in sequence. Its iterations synchronize through pipes and exit codes and hold
no wall-clock deadline, so #2306 runs them as parallel slices (81 s on the
M1). `facade.pattern_count_in_stress` does not scale the same way: on the M1
its rounds stop gaining at about four workers, because the 1024-input journey
is bound by the per-input durable path walk and Journal reread (#2284).

Do not read a quiet `tests/quality/test_budget_report.py` as headroom. On
2026-10-14 a Linux coverage run of unmodified `main` timed out
`facade.pattern_transport_controller` (normally 14 s of 30 s) while
`facade.pattern_count_in` sat at 90% of its budget on every run, and the report
named neither: its registration pattern missed single-line `lmdj_add_test`
calls (#2238). The report now reads each call to its balancing parenthesis
and prints every test it found no budget for; a test in that list can never
reach the warning share, so read its CTest duration against its budget by
hand.

Prefer a
budget that is generous to one that is tight: an over-long budget only delays a
genuine hang, while a tight one fails a healthy run deterministically on a
contended host.

No repository-wide gate exists because violation is not mechanically decidable:
a scan can find every wall-clock literal but cannot distinguish a well-
provisioned budget from an under-provisioned one. Escalation Issue
[#657](https://github.com/endaye/lmdj/issues/657) tracks the mechanism, and
records that analysis so no later Task retries a source-scanning gate.
