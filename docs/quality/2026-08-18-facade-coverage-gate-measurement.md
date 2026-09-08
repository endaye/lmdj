# Application Facade Coverage Gate — Measurement Record, 2026-08-18

Evidence for triage item C1. Produced by Task 1 of
[`2026-08-18-lmdj-facade-coverage-gate-stabilization.md`](../plans/2026-08-18-lmdj-facade-coverage-gate-stabilization.md).

The measurement **invalidated that plan's premise, its proposed fix, and
finally the triage item itself**. No floor was changed and no source was
committed on the strength of the original plan.

## Environment

| Field | Value |
| --- | --- |
| Source revision | `3b416a23` (`main`) |
| Local host | macOS `26.6.1` (`25G76`), Darwin `25.6.0`, arm64 |
| Local command | `scripts/core-coverage.sh check`, repeated on an unchanged tree |
| CI reference | Ubuntu runner, run `31955538797`, revision `801fa450`, jobs `95185530769` and `95690337280` (same job re-run at the same revision) |

macOS and Ubuntu do not measure the same file set: `CMakeLists.txt:112-117`
adds `lmdj_audio_coreaudio_tests` and `lmdj_native_audio_probe` to the coverage
objects under `APPLE`. Local and CI totals are therefore not directly
comparable, and each platform's floor evidence must come from that platform.

## Finding 1 — the nondeterminism is in branches, not lines

Five consecutive local runs on an unchanged tree:

| Run | Lines | Line % | Branches | Branch % |
| --- | --- | --- | --- | --- |
| 0 | 3422/4070 | 84.0786% | 991/1472 | 67.3234% |
| 1 | 3422/4070 | 84.0786% | 993/1472 | 67.4592% |
| 2 | 3422/4070 | 84.0786% | 994/1472 | 67.5272% |
| 3 | 3422/4070 | 84.0786% | 994/1472 | 67.5272% |
| 4 | 3422/4070 | 84.0786% | 993/1472 | 67.4592% |

Per-file comparison across the retained `summary.json` of every run: **no
facade file's covered-line count varies**. Exactly two files vary, and only in
branches:

| File | Covered branches observed |
| --- | --- |
| `src/application.cpp` | 759, 760 |
| `src/c_api.cpp` | 67, 68 |

Both are reached by `facade.c_api_stress`
(`packages/application-facade/CMakeLists.txt:184-188`, `TIER stress`,
`LABELS abi concurrency`), so the noise source identified in triage is
correct — but it moves the branch measurement, not the line measurement.

### What that means for risk

| Metric | Floor | Measured | Margin | Varies |
| --- | ---: | ---: | ---: | --- |
| Lines | 84.00 | 84.0786% | **0.0786 points** | no |
| Branches | 64.00 | 67.4592–67.5272% | 3.4592 points | yes, ±1 branch |

The metric that varies has ~3.46 points of headroom, so its ±0.07-point
movement cannot reach its floor. The metric with almost no headroom does not
vary. One facade line is worth 0.0246 points, so the line gate breaks on
roughly **four lines** of newly uncovered code.

The line gate is therefore **too tight**, not noisy — a different defect from
the one triage recorded, and one the plan's fix does not address.

## Finding 2 — the proposed fix does not run

Applying the plan's change — replacing the coverage preset's
`exclude.name: ^audio\.realtime_spsc_stress$` with
`exclude.label: ^stress$` — fails immediately:

```
coverage module signature count does not match object count:  32 != 33
```

`lmdj_application_c_api_stress_tests` is itself a coverage object
(`CMakeLists.txt:109`). Excluding its test produces no `.profraw`, and the
object/signature pairing check at `scripts/core-coverage.sh:164` fails closed.

The existing name-based exclusion works only because the sibling binary
`lmdj_realtime_engine_stress_tests` is **not** in the coverage object list. The
two stress tests are not symmetric, so the plan's claim that a label exclusion
"unifies an existing precedent" is wrong.

Making the exclusion work would additionally require removing
`lmdj_application_c_api_stress_tests` from the coverage object list — a second
change, with its own consequences for how `src/c_api.cpp` is measured, and it
would still only address branch noise, which is not the live risk.

The preset was restored; nothing from this experiment is committed.

## Finding 3 — Ubuntu, the platform that enforces the gate, is deterministic

The retained Ubuntu job at `801fa450` was re-run **at that same revision**, so
both measurements observe identical source on identical hardware and toolchain.

| Ubuntu job | Run | Lines | Branches |
| --- | --- | --- | --- |
| `95185530769` | `31955538797` | 3413/4061 = 84.04% | 1031/1542 = 66.86% |
| `95690337280` | `31955538797` (re-run) | 3413/4061 = 84.04% | 1031/1542 = 66.86% |

**Both lines and branches are identical.** The branch variance seen locally on
macOS does not appear on the Ubuntu runner at all.

On Ubuntu the line margin is 0.0433 points above the 84.00 floor, and one
facade line is worth 0.0246 points, so **two lines** of newly uncovered code
break the gate.

## Finding 4 — the failure C1 describes is not reproducible

Triage's Stage 8 observation (83.94% failing, then 84.04% passing) could not be
tied to a retained run. The only failed `core-coverage` job in the scanned
history of `main` (`95171956153`, revision `a71b5e0a`) failed before reaching
the gate, for unrelated reasons, and printed no facade percentage.

Given Finding 3, two runs of the same revision on the enforcing platform cannot
disagree. The 83.94% and 84.04% observations must therefore come from
**different source states**, not from re-measuring one — which makes them a
real coverage change between commits, not gate noise.

## Finding 5 — anatomy of the 648 uncovered lines

Line-level `llvm-cov show` over the merged profile, aggregated by enclosing
function. 89% of uncovered lines sit on error/failure paths; the shape is 139
contiguous blocks in `application.cpp` of which only two reach 10 lines —
failure exits scattered through otherwise-covered functions, not untested
features. Largest concentrations: `read_verified_scratch` (42),
`validate_initial_pattern` (39), `write_verified_staging` (23), the error
envelope mappers (~37), the assembly loader's 13 validators (52 across
`assembly_loader.cpp`), the C ABI boundary (54 across `c_api.cpp`), and 52
occurrences of the per-API catch-all message "unexpected Application Facade
Host API failure" across 24 catch blocks.

Full tiering and the resulting work plan live in
[`2026-08-18-lmdj-facade-coverage-raise.md`](../plans/2026-08-18-lmdj-facade-coverage-raise.md):
Tier A (~200 lines, ordinary bad inputs), Tier B (~180 lines, fault hooks per
the project-io precedent), Tier C (~50–80 lines of deep defence, deliberately
not chased). 90% needs +242 lines; Tier A plus a throw-injection hook crosses
it.

## Finding 6 — Ubuntu is NOT deterministic: Finding 3 was undersampled

**Correction, 2026-08-19.** Finding 3 concluded from a single re-run pair that
Ubuntu reproduces exactly. A same-tree counter-example has since appeared.

PR #188's head commit `f58d19f2` and the squash that merged it, `93b7d3f2`,
have the **byte-identical tree** `ab136c3039c15d3bf48b6a28657264315c9807c9`.
Their Ubuntu coverage runs disagree:

| Run | Covered | Total | Percent |
| --- | ---: | ---: | ---: |
| PR head, job `95799138152` | 3526 | 4088 | 86.2524% |
| merged `main`, job `95832925202` | 3522 | 4088 | 86.1546% |

Identical totals, **four fewer covered lines** — exactly the ±4 the original
triage described, on the platform that enforces the gate.

So C1's core claim was right and this record's earlier rebuttal was wrong. The
error was sampling: one re-run pair reproducing proves that a run *can*
reproduce, never that it always does. The re-run may also have reused runner
state the fresh run did not.

What survives from the earlier findings: the local macOS branch jitter is real
(Finding 1), the label-exclusion fix still does not run (Finding 2), and the
83.94/84.04 pair still cannot be attributed to specific runs (Finding 4). What
does not survive is the claim that a failure at a thin margin is necessarily a
true signal.

**Consequence for the floor.** Against the lower observation, 3522/4088 =
86.15%: a floor of 86 leaves ~6 lines of headroom, inside a ±4 band; a floor
of 85 leaves ~47. The ratchet went to **85** for that reason, not to the
higher value the coverage alone would have supported.

## Conclusion

1. **The gate is not noisy on the platform that enforces it.** Two Ubuntu runs
   of identical source produced identical lines and identical branches.
2. **The local macOS branch variance is real but harmless**, and does not
   reproduce on Ubuntu. It cannot reach the branch floor, which has 3.46 points
   of headroom.
3. **The line gate was very tight: 0.0433 points, about two lines** — and
   Finding 6 shows the measurement varies by about ±4 lines, so that floor sat
   *inside* its own noise band. This is why the ratchet moved to 85 rather than
   to the highest value the measured coverage would support.
4. ~~**C1 as filed does not exist.**~~ **Withdrawn 2026-08-19 by Finding 6.**
   Ubuntu produced 3526 and 3522 covered lines from a byte-identical tree, so
   the measurement is nondeterministic on the enforcing platform after all and
   C1's premise holds. The rebuttal was undersampled: one reproducing re-run
   pair does not establish determinism.

What remains is not a defect but a policy question: **does a ratchet floor with
two lines of headroom carry the margin this project wants?** A tight ratchet
catches regressions precisely, which is what a ratchet is for; it also fails any
change that adds even two uncovered lines to this package.

`docs/quality/core-test-policy.md` rules that floors "must not be lowered merely
to make CI green" and that they "may rise after sustained behavioral coverage
lands". With the noise justification gone, lowering this floor would need an
argument about what the gate should catch — which is a decision, not an
implementation. **No threshold was changed.**
