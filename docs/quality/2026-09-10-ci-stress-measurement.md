# `master_fx_stress` measurement record

Status: diagnostic record for #666, recorded 2026-09-10. This is an
investigation artifact, not a product or CI configuration change. It does not
change the deadline, overrun threshold, selected host, runner image, or host
kernel configuration, and three quiet passes would not close #666.

## Scope and authority

The current Issue is [#666](https://github.com/endaye/lmdj/issues/666), and
the umbrella work is [#1089](https://github.com/endaye/lmdj/issues/1089).
This record uses the latest Issue evidence, especially
[comment 5565033840](https://github.com/endaye/lmdj/issues/666#issuecomment-5565033840),
and preserves earlier interpretations as superseded hypotheses rather than
proof. It records observations and the next causal experiment; an `area:core`
measurement fix or a runner change requires a separately approved task.

## Evidence inventory

| Evidence | Exact revision / run | Observation | Status |
| --- | --- | --- | --- |
| Original Contabo failure | source `67ff1ad508131b05a670328c6baa18979e7e94aa`; [run 33905688022](https://github.com/endaye/lmdj/actions/runs/33905688022) | `core-stress` failed `audio.master_fx_stress` at line 148 after 0.26 s; sibling native job was serialized by the capacity queue; staging was a co-tenant. | Observed failure; host-cause attribution unresolved |
| Same-revision ci-only-host failure | source `67ff1ad5` as reported in Issue evidence; [run 34005676158](https://github.com/endaye/lmdj/actions/runs/34005676158) | `netcup-lmdj-linux-04` failed the same assertion after 0.08 s, despite no staging co-tenant. | Observed failure; did not prove product causation |
| Same-revision quiet-host result | source `67ff1ad5` as reported in Issue evidence; [run 34008747015](https://github.com/endaye/lmdj/actions/runs/34008747015) | `netcup-lmdj-linux-02` passed while nearly idle. | Observed pass; correlation only |
| Baseline timing measurement | source `0cfdd1b1` (the Issue's #692 measurement) | Uncontended macOS: mean callback about 36,000 ns; worst values 82,042 / 122,458 / 142,875 ns; deadline 2,666,666 ns. | Headroom context, not Linux causal evidence |
| Netcup inventory | inventory source `1338e3fcc5c65c12d12857018ede8ed8c8960804`; [run 34082715344](https://github.com/endaye/lmdj/actions/runs/34082715344) | Ubuntu 24.04.4, kernel `6.8.0-137-generic`, KVM; both accounting options not compiled in; aggregate 5 s `steal` delta 43, `softirq` delta 22. | Confirmed host observation |
| Contabo inventory | inventory source `1338e3fcc5c65c12d12857018ede8ed8c8960804`; [run 34083082565](https://github.com/endaye/lmdj/actions/runs/34083082565) | Ubuntu 24.04.4, kernel `6.8.0-138-generic`, KVM; both accounting options not compiled in; aggregate 5 s `steal` delta 0, `softirq` delta 18. | Config confirmed; steal leg inconclusive |

The failing source's current assertion remains
`callback_overruns.load(...) == 0` in
[`master_fx_stress_test.cpp`](../../tests/core/audio/master_fx_stress_test.cpp).
The test measures each render window with `CLOCK_THREAD_CPUTIME_ID`, and its
diagnostic output reports aggregate overrun count, mean callback CPU time, and
worst callback CPU time. Those measurements are useful for triage but do not
identify which callback overran or what happened on its CPU during that
callback.

## What the inventory establishes

Both hosts run KVM guests with `CONFIG_IRQ_TIME_ACCOUNTING` not compiled in.
Therefore the test's thread-CPU measurement cannot be treated as a pure
measurement of callback work: interrupt time can be charged to the running
thread. On Netcup, `CONFIG_PARAVIRT_TIME_ACCOUNTING` is also not compiled in
and aggregate steal time accrued during the inventory window, so the accounting
configuration is compatible with steal time being charged to a running task.

The Contabo `steal` counter was zero since boot in the inventory result. That
is not evidence of zero contention or zero steal: the counter may be
unavailable/not exposed, so this host's steal leg is unmeasurable. An absent or
unpopulated counter is not zero contention. Likewise, aggregate `irq`,
`softirq`, and `steal` deltas over five seconds do not prove that any specific
callback was charged with those events.

The narrow supported conclusion is therefore: on these hosts, the test's
assumption that thread CPU time is immune to every host-side scheduling or
interrupt accounting effect is false. The measurements make accounting
misattribution plausible, especially on Netcup, but they do not prove that the
original Contabo overrun was caused by steal or interrupt time.

## Superseded hypotheses and disposition

The early Issue framing treated sibling CI contention, then the staging
co-tenant, as the explanation. The same-revision failure on Netcup and pass on
a quiet Netcup host superseded the first reading: the evidence is consistent
with total host load, but it does not identify staging as the cause.

The next comment briefly called the two-host failure a deterministic product
defect. The subsequent quiet-host pass superseded that attribution. The
macOS/#692 headroom measurement also does not prove that Linux host load is
irrelevant; it was a different host class and did not measure guest accounting.

None of these older statements is retained as causal proof. The current
record has two separate observations: accounting flags are off, and aggregate
host counters were observed. Neither observation alone connects an event to an
individual callback.

## Next causal experiment

First run the unchanged failing revision `67ff1ad508131b05a670328c6baa18979e7e94aa`
as the baseline, with the existing deadline and test command. That original
binary cannot emit the per-callback fields proposed below. Collecting those
fields therefore requires a separately authorized instrumentation patch or an
external tracer; this record does not implement either. Record the exact
diagnostic revision and patch (or tracer version), prove that both arms use the
same resulting binary, and retain a no-instrumentation observer-overhead
baseline so instrumentation itself is not mistaken for the cause.

With that separately authorized diagnostic revision, collect a per-callback
trace containing callback index, thread CPU start/end, wall-clock start/end,
CPU identity, and before/after per-CPU steal, hardirq, and softirq counters
where the kernel exposes them. Record kernel config and counter availability
before the run, and retain the raw trace with the run URL, original source SHA,
diagnostic revision, patch/tracer identity, and binary digest.

Use paired runs with the same diagnostic binary, sample, toolchain, CPU
affinity, and environment: a quiet control and a deliberately busy condition
that is observable and bounded. Do not call a run a control if its per-CPU
counters are unavailable. A callback-level coincidence between an overrun and
a counter delta is association evidence only: coarse counters, timing
alignment, and observer perturbation cannot establish causation. Causal proof
requires a controlled intervention (for example, accounting isolation or an
equivalent controlled host condition) that removes or changes the suspected
accounting source while holding the callback binary constant. Without that
intervention, report the result as inconclusive even when the callback-level
coincidence repeats. A quiet pass remains only a correlation point unless the
paired busy condition reproduces the signal and the intervention separates it.

Stop the experiment without changing the gate if any of these occurs: the
source SHA or binary differs between arms; the counter source is absent or
cannot be mapped to the callback CPU; the busy condition is not bounded or
cannot be reproduced; instrumentation changes scheduling enough to invalidate
the comparison; or the run would require a threshold, timeout, host-image,
runner-routing, or kernel-configuration mutation. Report such an outcome as
inconclusive, not as zero contention and not as a product verdict.

## Version and documentation impact

Version impact: none — this is an investigation record and allocates no
Product Build, Module, Provider, or Contract identity.

Documentation impact: none — this file is not an Architecture Portal page and
does not change a current portal source fact.
