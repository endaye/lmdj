---
id: stress-tier-in-coverage-preset
area: core
status: absorbed
recurrences:
  - date: 2026-08-02
    occurrence: https://github.com/endaye/lmdj/pull/74
    observed_by: unknown
  - date: 2026-08-20
    occurrence: https://github.com/endaye/lmdj/pull/196
    observed_by: unknown
  - date: 2026-08-30
    occurrence: https://github.com/endaye/lmdj/pull/445
    observed_by: codex
exit: gate:tests/build/core_script_test.py
---

# A busy-spinning `stress` test left in the `coverage` preset starves unrelated tests near their tier budget, and the failure surfaces on a test you did not touch.

## Why

The coverage run is parallel and, unlike the sanitizer lanes, carries no
timeout multiplier, so a 30s `component` budget has nothing to absorb CPU
contention. A yield-free loop saturates a core regardless of how briefly it
runs: on 2026-08-19 the new stress test in #196 ran in 0.8s locally and still
took `core-coverage` red by timing out `facade.application` — a test it has no
relationship to. A first-hand note from the session that hit it survives and is
the source of this entry, but it does not record which model, so `observed_by`
stays `unknown` rather than a plausible guess. The same decision had already been made once, silently, when
`audio.realtime_spsc_stress` was added to the exclusion in #74; nothing recorded
it, so it had to be rediscovered from a red lane.

The exclusion was a hand-maintained list of test names in `CMakePresets.json`,
chosen by each test's spin behavior, and it drifted: by 2026-10-14 it named 7
of the 15 stress-tier tests. The owner then settled the rule as the whole tier,
which is mechanically decidable, so the preset now excludes it by label.

## How to apply

Register a new stress test with `TIER stress`; the `coverage` test preset's
`filter.exclude.label: ^stress$` keeps it out of every coverage run, and
`tests/build/core_script_test.py` fails if that label exclusion is removed or a
stress name reappears in the name list. Do not add stress names to
`filter.exclude.name`; it holds only the `build.release_*` tooling entries.
A target that only stress tests run is not a coverage object: the coverage
configure gate reads both exclusions and names such a target in
`lmdj_coverage_targets` as stale. Never run
`ctest --preset coverage` by hand from the repository root — it drops
`default.profraw` there and `build.active_tree` correctly fails on it; use
`scripts/core.sh coverage report|check`, which points `LLVM_PROFILE_FILE` inside
`build/`.
