# Master FX deadline accounting proof

## Task and premises

Base: `96802c0f8764d04cbf3d3c913e82292a01284ac9`, tree
`12447580f3cb82cb1df9077560cc12e8dbffe72a`. Authenticated main read on
2026-10-11 still names this object. The two real timing loops start the CPU
clock before reading host counters: sampler work is included in render elapsed.
The parser has no validity witness and delta subtraction permits unsigned wrap
on decreasing counters. Both defects remain outstanding at this base.
No historical receipt measures sampler duration, so this Task does not explain
historical overruns or establish host causation. I2a remains failed separately.

Exactly two declared files:

- `tests/core/audio/master_fx_stress_test.cpp`: private measurement, parser and
  delta validity plus deterministic witnesses in the existing executable.
- `docs/plans/2026-10-11-master-fx-deadline-accounting-proof.md`: this plan and
  actual proof outcomes.

No product code, registration, compiler policy, deadline or timeout changes.
No public helper. Every complete render, including queue drain and initial
128-trigger preparation, remains inside the measured interval. Host samples
bracket CPU start/render/CPU end; no estimated cost is subtracted. Same endpoint
CPU is necessary for attribution but cannot prove absence of migration.

## Minimum verification and defects caught

Use the existing Debug/O0 dev preset and target
`lmdj_master_fx_stress_tests`, serially on the isolated Linux worktree.

1. Rebuild a shared historical-order helper and deterministic sampler witness;
   run `ctest --preset dev -R '^audio.master_fx_stress$'`. Require a new exact
   50,000 versus 3,050,000 ns failure to demonstrate sampler contamination.
2. Correct both real loops through that same private helper. Exercise actual
   parser/read failures, exact CPU matching, valid zeros, unknown/mismatched
   CPU and each decreasing accounted counter. Invalid windows attribute zero
   before arithmetic. Render 2,666,667 ns must produce one unattributed overrun;
   exactly 2,666,666 ns must not overrun. Valid positive delta retains attribution.
3. Independently rebuild and run before-clock, after-clock and validity-guard
   mutations. Each must fail its own deterministic assertion. Restore corrected
   bytes with fresh mtime and successfully rebuild after each mutation.
4. Run the unchanged full registration once after all restores. It retains the
   strict 2,666,666 ns deadline, zero unattributed overruns and 180 second timeout.
   On failure, preserve results and stop without retry or commit.
5. Only after that owning gate passes, build the remaining original stress
   targets and run `scripts/core.sh test dev stress` without de-selection.
6. Before a commit, check the two-file staged list and whitespace and run
   `python3 tests/build/ci_change_scope_test.py` against the staged new plan.

All six original calls remain in their original order:

| Scenario | Retained observable guards |
| --- | --- |
| Eight FX gesture sustain | 128 frames, 48 kHz, 10 seconds, 3750 callbacks; finite PCM, processed voice, conservation and zero unattributed overruns |
| Full 128-voice kernel plus eight FX | 5 seconds, 1875 callbacks including first preparation; finite PCM, started voices, full pool and deadline |
| Full pool with tone and three EQ stages | Entire scenario and safety assertions; existing optimized-only timing policy |
| Typed filter refusal | Queue-full/invalid refusal and accepted/applied conservation |
| Typed/legacy concurrent churn | Independent concurrency, deterministic flood, finite/bounded PCM and coherent state |
| Restart Filter ACK epochs | Stop/restart, reset state, sequence and epoch assertions |

Raw build output, waits, compiler flags, dependencies, linked-input identities,
sources, artifacts and failure outputs are retained outside tracked source in
Task-owned evidence. Deterministic PASS does not replace native acceptance.
Root owns subsequent committed-head batch-only evidence and independent review;
this dispatch does not push, open a PR, merge, release or deploy.

## Version Management

Version impact: none. Test-only measurement correction changes no public ABI,
manifest, product identity or implementation. Existing Audio ABI MAJOR debt
remains separate and unresolved.

## Documentation Impact

Documentation impact: none. Internal stress measurement and this proof plan
change no Portal product behavior, public boundary, projected identity, source
diagram, test tier, registration, command or timing policy. No Portal build is
part of this Task.

## Pitfall disposition

The defects and their strictness are expressed directly by the test. No new
process-ledger change is needed. Follow fresh-mtime rebuilt mutation proof,
independent oracle and complete acceptance-journey rules; no coverage reduction
or substitution of historical evidence.

## Results

Outcome: FAILED / retained uncommitted. No retry, commit, full stress-tier run,
push or shipping. The corrected owning registration failed, so step 5 was not
admitted and staged ownership checks were not reached.

- Historical-order fresh build: exit 0; CTest exit 8 at the new exact assertion,
  expected 50,000 ns versus observed 3,050,000 ns.
- Corrected build and each of three restored builds: exit 0 with actual source
  compilation. Every restoration used fresh mtime newer than the mutant object.
- Before-clock mutation: exit 8, `before_only.elapsed.count() == 50'000`,
  observed 3,050,000 ns.
- After-clock mutation: exit 8, `both_samplers.elapsed.count() == 50'000`,
  observed 7,050,000 ns.
- Invalid/decreasing guard removal: exit 8, unique `invalid-after false-wrap`
  assertion. The counter-validity witness rejects before unsigned arithmetic.
- Corrected full original registration: CTest exit 8, 2.65 seconds total;
  deterministic witnesses passed and scenario 1 completed all assertions.
  Scenario 2 completed 1875 renders and passed finite PCM, then failed its
  zero-unattributed assertion at line 689: 19 unattributed overruns, 2 attributed,
  mean 1,086,667 ns and worst 11,507,762 ns. Its later started-voice/full-pool
  assertions were not reached. Scenarios 3–6 were not reached.

The fresh corrected binary SHA-256 is
`880fbc69c946c1a8c4dd23226e1299e8bf02f7b069c0edbe59e3ab57d277999f`.
All restored builds reproduce it. Raw commands, exit receipts, sources,
`.o.d` contents, flags, linked-input identity union, artifacts and CTest output
remain in `/home/en/lmdj-task-evidence/task_998bede6d4ac/` on the Linux host.
This proves measurement strictness, not full native stress acceptance, historical
host causation, resolution of I2a, Audio ABI debt or completion of the Goal.

Proposed separately authorized follow-up: capture per-quantum render-only
elapsed time, endpoint CPU and raw counter validity around this exact full-pool
scenario, distinguishing initial preparation from sustained work without
changing the deadline, flags, render contents or attribution predicate. No such
probe or rerun is authorized by this failed Task's remaining evidence work.

## 2026-10-12 authorized resume

User requested completion of the remaining worktrees. Refreshed integration
base: `c2de40b6471a40b830980d6ce88fdb600988437c`. The original base
`96802c0f8764d04cbf3d3c913e82292a01284ac9` remains historical. Exact
source/history inspection finds no intervening change to this stress test.
The sampler-contaminated interval and unchecked counter subtraction are still
outstanding. The two declared files and all original verification remain.

The original FAILED registration, three rebuilt mutation REDs and diagnostics
remain retained. The ERF diagnostic on `59da4245ff659ee1ffa2b9cf8e81f44bbc65a196`
failed at Eight-FX callback 3164: C=9,974,218 ns, Engine RAW span=27,882 ns;
resource advancement occurred before the Engine frontier. These probes add
work and cannot establish physical causation or authorize subtracting cost.
The diagnostic overlays will not become the production gate.

Import only the minimal prior measurement repair into a fresh owned worktree.
Rebuild all three deterministic mutations and their restored source on this
base, then execute the unchanged complete registration once. This is fresh
integration verification, not retrying old artifacts until green. A nonzero
result stops native acceptance and shipping; retain it with the prior history.
Only a passing complete registration admits the original complete stress tier.
No change to compiler, workload, deadline, timeout, attribution or assertion.
Version and Documentation impact remain none for the reasons above.

Resume evidence: `/home/en/orca/evidence/worktree-resume-20261012/`.

### Resume outcome: native FAILED, shipping stopped

Fresh configure/build exit 0; three rebuilt before-clock, after-clock and
invalid-guard mutations each exit 8 at the intended deterministic assertion.
Every corrected restoration compiled with fresh mtime and produced the same
linked binary. The complete original registration executed once, exit 8: one
unattributed Eight-FX overrun among 3,750 callbacks, mean 27,603 ns, worst
10,736,253 ns, deadline 2,666,666 ns, zero attributed overruns. It stopped at
`callback_overruns == 0`; later five scenarios remain UNREACHED. No native
rerun, full stress-tier pass, commit or shipping. The physical cause remains
UNKNOWN; prior diagnostic frontiers cannot be assigned to this new event.

An external bounded clock calibration executes 20,000 measured empty-loop
intervals and zero Engine calls. Its single run records a 5,090,084 ns Thread
CPU interval against the same 2,666,666 ns threshold; endpoint CPU is 15/15,
RAW frontiers are 641 ns / 5,089,424 ns / 721 ns. The executable exits 0 because
it collects observations, not product acceptance. This demonstrates a deadline
exceedance without Engine code; it does not identify the physical cause, prove
host attribution, or clear any MasterFX/full-stress failure. Source, build and
run receipts are retained as `clock_frontier_calibration.cpp` and
`clock-calibration*` in the resume evidence directory. No product gate changes.

## 2026-10-13 authorized completion boundary

The user explicitly requested handling every remaining worktree and its branch,
including authorized PR/merge or safe cleanup, with parallel agents. Root owns
the shared heavy-work window; this Task waits until the Sequence owner's full
stress execution has ended and Root grants the next exclusive window.

Refreshed integration revision:
`9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`. The stress source, Audio Runtime
and CMake/preset inputs are unchanged from the previous resumed
`43f41d2f1cf0f8294568e9964c058d141421aa46`; no successor delivered the
measurement correction or a deadline fix. The previous FAILED results and
their UNREACHED scenarios remain acceptance failures. The working test's
complete source is unchanged, SHA-256
`0927cef1a890cdd7279e4f4c63a6f6d88c82880f0e9d22095ee2e5f171cabc35`.

This is one newly authorized, resource-isolated current-main acceptance
boundary. The date, explicit resumed authorization and freshly inspected
resource window differ from the previous run; no source defect or historical
physical cause is inferred from that difference. Configure and serially build
the exact dev target from a fresh build directory, retain verbose compile/link
commands and identity/flag receipts, and execute the unchanged complete
`audio.master_fx_stress` registration exactly once. No retries follow a
failure. Only a pass admits the original complete 15-entry stress selection;
that complete run also executes once and retains every actual result.

The 2026-10-12 rebuilt deterministic mutation proofs remain source-bound
historical evidence for the byte-identical private measurement/parser/guard
code. The fresh complete registration must execute both strict witness bodies
and all six original native scenario calls. No narrower selector, altered
clock, attribution fallback, extra native probe, optimized policy, threshold,
timeout, workload, scope or assertion is introduced. Today's ASan evidence
does not replace this Debug/O0 deadline acceptance: sanitizer timing is disabled
by the existing CMake policy.

Original draft custody before updating this plan: named retained stash
`c985adf1ae6bd5d08bc066c8580e2d12c6b23027`, verified independent bundle and
complete exact-byte snapshots under
`/home/en/orca/evidence/worktree-finish-20261013/master-fx/`.
The two declared files, Version impact: none, and Documentation impact: none
remain unchanged. Shipping still requires the original owning acceptance,
declared-file/whitespace and new-plan ownership checks, independent exact-head
review, live protection and guarded merge. Cleanup still requires complete
retention and a clean inactive exact target. The four historical diagnostic
variants remain independently retained; this minimal repair does not silently
discard or adopt their instrumentation.

## 2026-10-13 final worktree completion authorization

The user now explicitly authorizes completing necessary non-main work and
discarding verified obsolete/useless drafts. Four layered one-off diagnostic
variants have been classified as abandoned, retained in a verified complete
Git bundle with source/patch/plan copies and inode-preserved ignored artifacts,
and removed using non-forced worktree removal plus local `branch -d`. They are
abandoned diagnostics, not merged implementations. Their failures and original
observations remain in recovery custody; this does not erase deadline debt.

The minimal measurement/parser repair remains necessary. At refreshed main
`73fc1c7bf0cd2f0a7f52cef481d0746ff032dd22`, the owning stress test still starts
the CPU interval before its host sampler and still permits invalid/decreasing
counter subtraction. No successor has delivered these defects. Owning source,
build inputs and applicable governance are unchanged from the retained cold
build's explicit base `9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`; all 497
recorded compiled dependency/artifact identities were rechecked unchanged.
This is owning-target input equivalence, not full current-main verification.

Root coordinates a brief pause in compilation by the other two current agents
for one newly authorized execution of the complete original strict native
registration. Requiring every external process to be absent is not an
additional permanent acceptance gate. Capture visible competing activity and
the actual execution/clock/source/flags/results; do not infer causation from
process presence. The original Debug/O0, REALTIME=1, OPT=0, zero unattributed
overruns, 2,666,666 ns deadline, 180-second registration and all original
scenario calls are unchanged. Only an owning native pass admits the original
complete stress selection. No repeat of the same failed native test follows.

If the original registration fails, retain it and investigate a separately
bounded causal question with a reduced external clock/scheduling experiment.
That experiment must have an explicit new evidence objective, preserve the
owning acceptance failure, and make no global system, threshold, workload,
timing-policy or scope change. Unprivileged visibility and causal limitations
remain explicit. Neither external calibration nor a deterministic witness
can replace the complete original acceptance. Shipping continues only after
all original required Task verification passes.

Finalization evidence:
`/home/en/orca/evidence/worktree-finalize-20261013/master-fx/`.
The same two declared files and Version/Documentation impact: none remain.

### Final completion boundary: native FAILED, causal observations retained

The unchanged owning registration executed exactly once as the ordinary en
user: 2026-10-13 05:57:17.873126Z--05:57:20.806025Z, CTest PID2581116,
actual exit8. Both deterministic witnesses and the complete first Eight-FX
scenario passed by control-flow evidence. The full 128-voice/eight-FX second
scenario completed all1875 renders and then failed `overruns == 0`: 17
unattributed and 4 attributed overruns; mean1,181,288ns, worst12,296,607ns
against unchanged2,666,666ns. Its later assertions and the four later scenarios
remain UNREACHED. Full original stress was not admitted. No original native
retry, Task commit, PR, merge or original deadline/policy change followed.

A single bounded external zero-Engine observation completed 3750 rows in
4.471s (compile separately1.165s). Default affinity and child-only single-CPU
arms each recorded20 deadline exceedances,17 without a positive per-vCPU
counter delta; maxima12.801486ms and12.080252ms. The pinned arm's20 exceedances
had no observed AUX migration or context-switch increment. CPU remained within
the containing RAW envelope, TSC stayed monotonic and the two clock-query
boundaries were at most18.278us. A sampled long interval occurred in the fixed
arithmetic body, even with zero Engine calls. Pinning is a causal control here,
never a product gate strategy or proof of hypervisor causation.

Read-only metadata then established an existing lawful noninteractive sudo
policy and a working owned-process PMU route, while ordinary UID1000 remained
denied by perf_event_paranoid=4. No capability, sysctl, kernel, CPU-frequency or
runner setting changed. Guest cgroup/system.slice/orca service observations
reported no throttling; the root cgroup has no cpu.max file, retained as an
actual unsuccessful read rather than an invented quota value.

One new PMU observation used the same521,867-iteration arithmetic body under
sudo solely for its own counters: compile1.165s, collection06:28:13.007820Z--
06:28:15.473454Z/2.466s, actual collection exit0. That exit means1875 rows were
captured, not native acceptance. Actual PID/TID2607937, UID/EUID/GID/EGID0,
SCHED_OTHER/nice0,16 allowed CPUs and
`0::/system.slice/orca-serve.service` were recorded. Root privilege differs from
the original en native run and this observation cannot replace it.

The four grouped guest-visible hardware events were user cycles/instructions
and kernel cycles/instructions, IDs4/5/6/7; type0 and config0/1, with
exclude_hv=1, appropriate user/kernel exclusion, exclude_host=exclude_guest=0,
inherit=0, pinned=0, GROUP/TIME_ENABLED/TIME_RUNNING/ID read_format15. Every
row had a positive group window with equal enabled and running deltas; raw
before/after values and IDs are retained. The18 timing spikes (16 without a
positive host counter delta) were7.081--11.119 times the ordinary median CPU
duration, but total user+kernel cycles only1.008--1.069 times the ordinary
median and total instructions only1.00063--1.00407 times it. The largest row
had CPU11.108191ms/RAW body11.225368ms,3,735,653 cycles versus ordinary
median3,594,292 and7,864,997 instructions versus7,841,015.

This narrows proportional additional guest-visible executed work as an
explanation for the external diagnostic's spikes. The PMU is virtualized;
instruction/cycle windows include small boundary reads, and counts are not
converted into time using an assumed frequency. No unique physical source is
proven, and no diagnostic event is assigned to the17 original native overruns.
The original native/full-stress acceptance failure remains open.

Current authority still includes the original Linux Debug/O0 Task requirements
and both owner decisions dated2026-09-16 and2026-09-19. The latter explicitly
routes formal Release stress to trusted bare-metal macOS because guest
subtick attribution is insufficient; it does not silently replace this Task's
explicit Linux gate. Automatically completing this Task requires admitted
same-input original-gate evidence on an available Linux target with usable CPU
accounting, or an explicit authorized disposition of its verification scope.
No new remote Linux connection or global host repair was established here.
The minimal source is retained ready for that boundary; its gate has not been
waived, and it has not been reclassified as an obsolete diagnostic.

All actual receipts, full CSVs, Source/specifications, counter settings and
limitations are linked from the finalization `result.json`.


## 2026-10-13 current-policy PR and merge continuation

The user now explicitly requests PR and merge of the necessary retained work.
The earlier hard-stop requirements, failures, unreachable assertions and their
receipts above remain historical facts; none is retrospectively marked green.
The present shipping procedure follows refreshed main
`d46d90319d14e96896134e1d65a59e3e8b05694b`, its AGENTS authorization,
`issue-done` and `lmdj-review-ci-triage`. Ordinary PRs retain Task verification,
independent current-head review, conflicts and conversation protection without
a global full-green or strict-update requirement. The triage skill requires
the SAME suite on clean origin/main before classifying an identical failure
as pre-existing/environmental; that proof is being collected independently.
No claimed baseline result or shipping disposition precedes its actual receipt.

Premise disposition at this exact main: both render timing loops still include
the before-sampler in their CPU intervals, and malformed/missing/decreasing
counter windows still lack the validity guard before unsigned subtraction.
The existing test source and the four linked Module inputs have no intervening
implementation change, so no successor has delivered these three repairs.
All 497 retained cold-build dependency/artifact identities were rechecked;
the owning tracked inputs agree with current main except for this declared
minimal test patch. The applicable governance and owning inputs have no delta
from the previous `73fc1c7b` audit. This establishes owning-input equivalence,
not a complete current-main pass.

The unchanged aggregate native registration previously stopped at the second
budget assertion. To observe every original main-level journey, an external
runner includes the complete owned test file verbatim and renames only its
main symbol, then invokes each of the two strict witnesses and six original
functions in separate processes. Every call, function body, workload,
assertion, deadline, accounting predicate and CMake macro remains unchanged:
Debug/default O0, REALTIME=1, OPTIMIZED=0, zero unattributed overruns and
2,666,666ns. Compile/link commands come from the actual owning target and
use only this worktree's cold-built four Module archives. Fresh compilation
and linking both returned zero; source, dependencies, flags, objects, archives
and the wrapper binary are bound in the new evidence.

Each original function will be called once. A failure remains a failure and
its remaining internal assertions remain UNREACHED; invoking the next original
function in a separate process only removes aggregate stop-at-first-fail
masking. Passing later functions cannot make the original registration or
complete stress suite pass. The unchanged previous three freshly rebuilt
mutation RED proofs remain bound to the byte-identical measurement/guard code;
this external runner changes no helper or tested source. No deadline or
workload is tuned to obtain a green result.

Task verification and any pre-existing deadline debt will be reported together
after the independent clean-main comparison and all eight actual observations.
Whether the resulting evidence supports an ordinary PR is assessed under the
current policy, with all outstanding risks retained for independent review;
no false aggregate PASS or automatic debt clearance is permitted. The original
full-tier requirement and its historical non-admission above are not silently
rewritten as successful execution. The Task still declares exactly the same
two files, Version impact: none and Documentation impact: none.

New source and execution evidence:
`/home/en/orca/evidence/worktree-pr-merge-20261013/master-fx/`.


### Verified comparison and explicit shipping-premise supersession

Independent clean-main evidence is now complete at exact
`d46d90319d14e96896134e1d65a59e3e8b05694b`, with a new clean isolated
checkout and fresh original source, 11 stress binaries and four original Module
archives. The unchanged `bash scripts/core.sh test dev stress` selection ran
once, actual exit8, ending2026-10-13 11:21:24.797684Z: 14/15 passed and
only `audio.master_fx_stress` failed. That original aggregate stopped in
Eight-FX with2 unattributed overruns, no attributed overrun, mean63,459ns and
worst10,180,228ns against2,666,666ns. Its later functions were not reached.
This is a failed full-suite baseline, never a full-suite PASS.

The independently fresh clean-main supplemental runner then invoked every
original function once with unchanged Debug REALTIME=1/OPTIMIZED=0 policy,
workloads, bodies and180-second timeout. Functions1/3/4/5/6 passed; function2
failed its original kernel budget assertion with22 unattributed and3 attributed
overruns, mean1,291,907ns and worst11,909,015ns. Its later started-voice and
full-pool assertions remain UNREACHED. Final clean-main observation ended
11:23:41.707092Z. It used no candidate source, object or archive.

The corrected Task's eight independent invocations ran exactly once each,
2026-10-13 11:26:20.287719Z--11:26:26.937612Z, UID/EUID1000, original
affinity and no scheduling or system changes. Both new strict witnesses
returned0. All six original function bodies were entered: Eight-FX, full tone
pool, typed refusal, concurrent typed/legacy churn and restart ACK returned0;
only full128-voice/eight-FX kernel returned1. Its1875 renders completed and
finite PCM passed before the unchanged `overruns == 0` assertion failed with
19 unattributed and3 attributed overruns, mean1,177,012ns, worst11,830,297ns,
unchanged2,666,666ns deadline. Its later started-voice/full-pool assertions
still remain UNREACHED. The observation collector returned1. Original tone
policy remains OPTIMIZED=0 here; its safety journey passed, with no claimed
Debug tone deadline evidence. No failing function was retried.

Thus current clean-main and corrected Task have the same complete six-function
pass/fail pattern, including the same unchanged full-kernel budget assertion.
Numeric timings/counts differ and establish no unique physical cause. The
previous whole native FAILED result remains, and candidate full15 was not run.
The source-bound three rebuilt historical mutation sequences are each
build0 / intended assertion RED8 / restored compile0, against complete
corrected source SHA256
`0927cef1a890cdd7279e4f4c63a6f6d88c82880f0e9d22095ee2e5f171cabc35`.
Today's fresh wrapper dependency record includes that exact original source
and both new witnesses have now executed successfully. No helper/code input
changed to require a different mutation proof.

For this newly authorized PR, the old step4 hard stop and step5 prerequisite
for shipping are explicitly superseded as shipping premises under current
AGENTS, `issue-done` ordinary PR procedure and the triage skill's SAME-suite
clean-main rule. The Task delivers three test-accounting facts: sampler work
stays outside complete render CPU time, counter parsing accepts only valid
whole unsigned rows, and invalid/decreasing evidence cannot wrap into false
attribution. It does not implement an Engine deadline fix. Shipping verification
for these facts is the two strict witnesses, three source-bound rebuilt RED
proofs, owning-input equivalence, every original function's actual outcome and
the independently reproduced existing failure. Staged new-file ownership,
whitespace, declared two-file inventory and PR-body checks remain required,
followed by independent current-head review and live conflict/conversation
protection. A new Task-fact failure cannot be excused by this disposition.

This supersession changes no executable assertion, workload, threshold,
registration, timing macro or initial128-trigger work inside render. It clears
no native/full-stress/performance debt and establishes no release readiness.
The existing kernel deadline failure and its post-failure internal assertion
gaps remain open; closing them needs complete original-gate evidence on a
usable performance/accounting target or an actual separately scoped remedy.
Five original journeys and both new facts have actual successful observations;
no substitute observation is called an aggregate pass.

Exact baseline bindings and actual receipts are in
`/home/en/orca/evidence/worktree-pr-merge-20261013/baseline/`; Task bindings,
all eight receipts, source-bound mutation receipts and the independently checked
`clean-main-comparison.json` are in the sibling `master-fx/` evidence directory.
Version impact: none and Documentation impact: none retain the concrete reasons
above. The earlier one-off diagnostic discards remain abandoned, not merged.
