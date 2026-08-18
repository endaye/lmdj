# Application Facade Coverage Gate — Measurement Record, 2026-08-18

Evidence for triage item C1. Produced by Task 1 of
[`2026-08-18-lmdj-facade-coverage-gate-stabilization.md`](../superpowers/plans/2026-08-18-lmdj-facade-coverage-gate-stabilization.md).

The measurement **invalidated that plan's premise and its proposed fix**. Both
findings are recorded here; no floor was changed and no source was committed
on the strength of the original plan.

## Environment

| Field | Value |
| --- | --- |
| Source revision | `3b416a23` (`main`) |
| Local host | macOS `26.6.1` (`25G76`), Darwin `25.6.0`, arm64 |
| Local command | `scripts/core-coverage.sh check`, repeated on an unchanged tree |
| CI reference | Ubuntu runner, job `95185530769`, run `31955538797`, revision `801fa450` |

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

## Finding 3 — the CI observation is real and unexplained locally

Triage records a Stage 8 Ubuntu run measuring 83.94% and failing, followed by
84.04% passing. Against 4,061 lines those are 3,409 and 3,413 covered — a
four-line difference, matching the ±4 triage described.

The retained Ubuntu run at `801fa450` measures:

```
packages/application-facade/: lines 84.04% (3413/4061, required 84.00%);
branches 66.86% (1031/1542, required 64.00%)
```

Five local runs did not reproduce any line movement. The difference between
platforms is unexplained by this measurement: candidate causes are the
toolchain (CI pins Clang/LLVM 18), the differing coverage object set, a
different source state at the time of the Stage 8 observation, or an
interleaving five runs did not hit. **This record does not claim Ubuntu line
counts are stable.**

## Conclusion

1. The line floor's problem is margin, not noise — 0.0786 points on a metric
   where one line is worth 0.0246.
2. The plan's fix is inapplicable as written and would target the wrong
   metric even if completed.
3. Whether Ubuntu line counts vary remains open and is the input the floor
   decision needs.

No threshold was changed on the strength of this record alone. The test
policy's rule stands: a floor moves only on a reviewed measurement, and this
measurement is not yet sufficient for the platform CI enforces.
