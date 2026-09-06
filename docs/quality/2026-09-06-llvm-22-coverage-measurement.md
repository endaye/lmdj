# Clang/LLVM 22 Toolchain — Measurement Record, 2026-09-06

Evidence for #693, the move of the pinned Core toolchain from Ubuntu's
Clang/LLVM 18.1.3 to Clang/LLVM 22 from apt.llvm.org. Two questions had to
be answered by measurement before the pin could land: whether the coverage
floors in [`core-test-policy.md`](core-test-policy.md) still describe the
tree when `llvm-cov` 22 does the counting, and whether a newer TSan runtime
tolerates the 6.8 kernel's 32-bit `vm.mmap_rnd_bits` without re-executing
itself — the one thing that could have made TSan run on a self-hosted host
without touching the host.

## Environment

| Field | Value |
| --- | --- |
| Host | `netcup01` (`ci-core`), 16 vCPU EPYC, Ubuntu 24.04, kernel `6.8.0-137-generic`, x86_64 |
| Toolchain | `Ubuntu clang version 22.1.8 (++20260714014902+ca7933e47d3a-1~exp1~20260714135019.80)`, `llvm-cov-22` / `llvm-profdata-22` 22.1.8, from `llvm-toolchain-noble-22` via `scripts/ci/host/install-llvm-toolchain.sh` |
| Reference toolchain | Ubuntu `clang-18` 18.1.3, the pin until this Task |
| Source revision | `feat/693-llvm-22-toolchain` at the commit named in each table |
| Coverage command | `CC=clang-22 CXX=clang++-22 PATH=/usr/lib/llvm-22/bin:$PATH scripts/core-coverage.sh check`, `ccache` disabled, in a fresh clone outside any runner service |

## Finding 1 — LLVM 22's TSan does not tolerate 32-bit ASLR entropy; it re-execs or dies

A minimal two-thread program with a deliberate data race, compiled with
`-fsanitize=thread` by each runtime, started ten times under the runner
units' hardening (`systemd-run -p LockPersonality=yes -p NoNewPrivileges=yes`),
first at the kernel default and then after
`scripts/ci/host/configure-sanitizer-aslr.sh`:

| runtime | link | `mmap_rnd_bits=32`: ran / FATAL / silent | `mmap_rnd_bits=28`: ran / FATAL / silent |
| --- | --- | --- | --- |
| GCC 13.3 `libtsan` | shared (GCC default) | 0 / 10 / 0 — `unexpected memory mapping` | 10 / 0 / 0 |
| clang-18 `libclang_rt.tsan` | `-shared-libsan` | 1 / 0 / 9 — exit 66, **no output** | 10 / 0 / 0 |
| clang-22 `libclang_rt.tsan` | `-shared-libsan` | 0 / 10 / 0 — `memory layout is incompatible, even though ASLR is disabled` | 10 / 0 / 0 |
| clang-18 and clang-22 | static (default) | does not link: `multiple definition of operator new` against `libclang_rt.tsan_cxx` | — |

Three conclusions, each answering a question #676 left open:

1. **The compiler major is irrelevant to whether TSan starts.** LLVM 22's
   runtime meets the 32-bit layout the same way 18's does — by trying to
   re-exec with `ADDR_NO_RANDOMIZE` — and `LockPersonality=true` turns that
   into a fatal error. Only the host's entropy setting changes the outcome,
   and at 28 bits every runtime starts every time. That is the Owner's
   decision recorded in the policy: the sysctl, not `LockPersonality=false`.
2. **Probe B″'s "10/11 tests fail in 0.01 s with no diagnostic" is
   explained.** clang-18's shared runtime dies silently when the layout does
   not fit, and fits by chance about one time in ten. A single run of that
   configuration is therefore not evidence either way.
3. **22 is still worth having for TSan.** Its failure mode is an honest
   `FATAL` with the cause named, where 18's is an empty log. See
   [`sanitizer-runtime-silent-start-failure`](../../.agents/pitfalls/sanitizer-runtime-silent-start-failure.md).

### The same-revision probe

With the host at 28 bits, Core Nightly run `34030066433` was dispatched from
this branch at `a0556523` with `probe_self_hosted_tsan=true`. Both TSan jobs
ran the identical fixture, dependency, `configure tsan` (`CC=clang-22
CXX=clang++-22`), build and `test tsan stress` commands:

| Job | Runner | Result | Stress tier | Wall |
| --- | --- | --- | --- | --- |
| `core-tsan` (Hosted `ubuntu-24.04`, installs 22 per job) | GitHub-hosted | success | 11/11 passed, 157.0 s | 11 min 35 s |
| `core-tsan-self-hosted-probe` (`ci-core`) | `netcup-lmdj-linux-04` on `netcup01` | success | 11/11 passed, 52.0 s | 4 min 12 s |

That is the accepted same-revision `runner_name` plus successful-job evidence
the policy required before scheduled TSan could leave the Hosted image, and
scheduled `core-tsan` moves to `ci-core` in the same Pull Request. The
`core-stress` job of that dispatch failed on `audio.master_fx_stress`, the
open #666 (PR #692); it ran before the probe in the `lmdj-native-heavy` queue
and is unrelated to this Task.

## Finding 2 — `-Werror` on 22

`dev`, `tsan` and `coverage` presets built with clang-22 on x86_64 (netcup)
and on arm64 (a noble container) with zero diagnostics. `asan` stays on GCC
by decision and was not swept under Clang.

## Finding 3 — every floor still holds on 22; 22 counts about 40 fewer covered lines and a different branch topology

Same tree (`bd792f5f`), same host, `ccache` off, fresh build for each
toolchain. Runs 1 and 2 on 22 are back-to-back on an unchanged tree; run 1
was a cold build, run 2 reused the build directory. The two `contract`-tier
tests that depend on release tags (`build.release_transitions`,
`build.release_audit.snapshot_provenance`) failed in this tag-less bundle
clone and were allowed through for export only; neither is a coverage object,
so the counts below are unaffected. The `core-coverage` lane of #710 is the
authoritative gate run on the same revision.

| Scope | Floor (lines / branches) | clang-18 (lines / branches) | clang-22 run 1 | clang-22 run 2 |
| --- | --- | --- | --- | --- |
| Overall | 76 / 64 | 82.77% (34423/41587) / 68.73% (10419/15160) | 82.67% (34381/41587) / 69.04% (10091/14616) | 82.66% (34377/41587) / 68.97% (10081/14616) |
| Foundation | 87 / 92 | 91.30% (231/253) / 93.52% (101/108) | 91.30% / 93.52% | 91.30% / 93.52% |
| Authoring Domain | 88 / 85 | 93.38% (1030/1103) / 88.14% (520/590) | 93.38% / 89.92% (464/516) | 93.38% / 89.92% |
| Project I/O | 65 / 61 | 70.97% (9467/13340) / 62.20% (3564/5730) | 70.88% (9455/13340) / 62.96% (3493/5548) | 70.86% (9453/13340) / 62.78% (3483/5548) |
| Project Cooker | 89 / 71 | 89.46% (789/882) / 80.00% (288/360) | 89.34% (788/882) / 79.89% (286/358) | 89.34% / 79.89% |
| Audio Runtime | 80 / 67 | 89.87% (2732/3040) / 80.18% (1007/1256) | 89.87% / 80.15% (973/1214) | 89.87% / 80.15% |
| Provider SDK | 77 / 61 | 81.33% (1729/2126) / 65.38% (625/956) | 81.04% (1723/2126) / 65.11% (599/920) | 81.04% / 65.11% |
| Application Facade | 85 / 64 | 85.87% (7582/8830) / 70.94% (2253/3176) | 85.72% (7569/8830) / 71.18% (2181/3064) | 85.72% / 71.21% (2182/3064) |

What the numbers say:

- **Line denominators are identical** across toolchains (41587 overall, every
  package equal), so 18 and 22 agree on which lines exist. 22 reports 42
  fewer covered lines overall: 13 in the facade, 12 to 14 in Project I/O, 6
  in the Provider SDK, 1 in the Cooker. That is a change in `llvm-cov` 22's
  region accounting, not in what the tests exercise — the same tests ran to
  the same results on both.
- **Branch denominators differ** (15160 on 18, 14616 on 22, and every package
  shrinks): 22 emits fewer branch regions for the same source. Branch
  percentages move by under a point in either direction and stay above every
  floor.
- **Run-to-run variance on 22** is the ±4 lines and ±10 branches the
  2026-08-18 record measured on 18, all of it in Project I/O and the facade's
  branch count, the same stress-adjacent files as before.
- **Floors are unchanged.** All sixteen pass on 22 with the margins below;
  none is lowered and none needs to be. The Project Cooker line floor is the
  tightest at 3 lines (788 covered against 785 needed) and was 4 lines on 18;
  it was already the tightest floor in the table and this Task does not touch
  it. The facade line floor keeps 64 lines of headroom (7569 against 7506),
  well outside the noise band the 2026-08-18 record required.

| Floor | Margin on 18 | Margin on 22 |
| --- | ---: | ---: |
| Project Cooker lines 89% | 4 lines | 3 lines |
| Application Facade lines 85% | 77 lines | 64 lines |
| Project I/O branches 61% | 1.20 points | 1.78 points |
| Provider SDK branches 61% | 4.38 points | 4.11 points |

## Finding 4 — CI timings on the new toolchain

Recorded from Pull Request #710's full runs on `ci-core` (netcup). The first
run to reach the Core lanes is cold: the persistent `ccache` holds only
clang-18 objects, so every Core lane compiles from scratch. The next is warm.

| Run | Head | Outcome | Core lanes |
| --- | --- | --- | --- |
| `34029534657` | `a0556523` | `PR Gate` failure | not executed |
| `34039919843` | `c55fb33c` | **success** | all four green |
| `34050917752` | `b4f2e9c1` | **success** | all four green |

Two full runs green on the new toolchain, per lane:

| Lane | `34039919843` | `34050917752` | ccache hits |
| --- | ---: | ---: | --- |
| `core (ubuntu-latest)` | 69 s | 65 s | 120/120 both runs |
| `Core package` | 298 s | 299 s | disabled by design |
| `core-coverage` | 504 s | 475 s | 4/117 then 6/117 |
| `core-asan` | 368 s | 362 s | 117/117 then 116/117 |

The Issue expected a wholesale cache miss on the first run after the pin
moved. That did not happen, for a reason worth recording: **only
`core-coverage` pins the compiler.** `core (ubuntu-latest)`, `core-asan` and
the Nightly `core-stress` lane use the platform default, still GCC 13, so
their persistent `ccache` entries were never invalidated and they report full
hits on both runs. There was no cold run to compare against.

`core-coverage` misses almost everything, but it did so before this Task too
and keeps doing so on the second run: 3.4% then 5.1% hits. That lane is not
warmed by the persistent cache at all, so its cost is a standing property of
the lane rather than a cold-start effect of the pin. Its runtime is dominated
by test execution in any case: a dispatched `ci-self-hosted-core-benchmark` of
`core_coverage` at `b4f2e9c1` (run `34050980331`, `netcup-lmdj-linux-02`)
reported `elapsed_seconds=547` beside the two gate runs' 504 s and 475 s. No
`ccache` warm-up window needs planning for.

That benchmark also reproduced the coverage numbers on CI hardware
independently of the gate: overall 82.66% lines (34374/41587) and 69.03%
branches (10089/14616), against 82.66%/68.97% measured by hand on the same
host in Finding 3, and the gate reported PASS.

Run `34029534657` never reached the Core lanes: `creator-web` failed on
`creator_web_lifecycle.spec.mjs:424` ("suspend, restart, and reopen clear an
active loop toggle before reactivation", 125 s predicate timeout waiting for a
state other than `pending`), so `Pre-heavy Gate` refused admission and the
four native Core jobs were skipped. Following
[`flake-closed-on-environment-correlation`](../../.agents/pitfalls/flake-closed-on-environment-correlation.md),
the retained artifact `web-ci-failure-creator` was opened before attributing
anything: the trace holds zero `pageerror` events and no console error other
than a `favicon.ico` 404, and the page snapshot shows the Runtime `ready` with
audio inactive. This Task changes no Web source; the failure is recorded here
as an unrelated Creator lifecycle timeout observed on `netcup-lmdj-linux-08`
while four other Pull Requests' runs and this Task's Nightly dispatch shared
the host, and it is not closed as environmental by this record.

The runs that follow the routing commit are appended to the table above as
they complete; the last run's own timings can only live in the Pull Request
and the Issue closing comment, because recording them here would itself
trigger another run.

## Finding 5 — netcup's elastic controller was still running its 2026-08-31 configuration

Registering `core-tsan` in `core_job_names` (the
[`core-job-name-elastic-registration`](../../.agents/pitfalls/core-job-name-elastic-registration.md)
rule) meant redistributing `scripts/ci/elastic-runner/netcup.json`, and the
live `/etc/lmdj/elastic-runner.json` on netcup turned out to date from
2026-08-31: no service carried the `ci-core` role and `core_job_names` was
empty, so since #694 moved `ci-core` to netcup the controller had classified
every Core job there as non-core and was free to admit elastic scale-out
beneath it. `deploy-controller.sh netcup.json` was run from the repository
copy on 2026-09-06; the installed `elastic_runner.py` already matched the
repository byte for byte, and the first tick after the deploy decided
`no action required`. The repository is the authority for that file; the
host copy is not, and this is the second time the two had drifted apart.
