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
exit: skill:.agents/skills/issue-done/SKILL.md
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

The exclusion list in `CMakePresets.json` is maintained by hand and a new test's
spin behavior is not mechanically decidable, so this exits to guidance.

## How to apply

When adding a `stress`-tier test, ask whether it saturates a core, not how long
it runs. If it busy-spins, add it to the `coverage` test preset's exclusion list
in `CMakePresets.json` alongside the existing entries in the same commit.
Coverage measurement never needs a concurrency run: the stress tier has its own
lanes, and `core-asan` runs `full` then `stress`. Never run
`ctest --preset coverage` by hand from the repository root — it drops
`default.profraw` there and `build.active_tree` correctly fails on it; use
`scripts/core.sh coverage report|check`, which points `LLVM_PROFILE_FILE` inside
`build/`.
