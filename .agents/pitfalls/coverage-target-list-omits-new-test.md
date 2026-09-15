---
id: coverage-target-list-omits-new-test
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/pull/697
    observed_by: Claude Code (Opus 5)
  - date: 2026-09-15
    occurrence: https://github.com/endaye/lmdj/pull/1351
    observed_by: Hermes Agent (deepseek-flash)
exit: gate:CMakeLists.txt
---

# A new instrumented test target must join the root `lmdj_coverage_targets` list, or the coverage lane fails on a count nobody can read

## Why

`CMakeLists.txt` builds `coverage-objects.txt` from a hand-written
`lmdj_coverage_targets` list, while the coverage run discovers modules from the
`.profraw` files the tests actually produce. A new test target registered only
in its package's `CMakeLists.txt` therefore emits a profile that the object
list does not know, and `scripts/core-coverage.sh:178` refuses:

```
coverage module signature count does not match object count:  60 != 59
```

Nothing in the product code says that adding a test target obliges a second
edit in the repository root, and the two numbers name neither the extra module
nor the list that has to learn it. The `coverage` preset is not part of
`scripts/core.sh test dev fast`, so a Task can be locally green through every
tier it runs and still fail this lane on the first full Pull Request — which is
where it cost a cycle: #697 added `lmdj_foundation_soundset_manifest_tests`,
and Stage 11's plan named `packages/foundation/CMakeLists.txt` in its file list
but not the root one.

The second recurrence is why this entry is now absorbed: eight weeks later the
list was 26 targets behind — the four pattern admission/transport tests, three
candidate-adoption tests, the Facade provider-owner test and 18 cardputer
platform tests — and nothing had reported it, because the count check runs only
after every test passes and `core-coverage` is skipped on most runs. Two
properties kept that drift invisible rather than merely unlucky:

- The object list was resolved where it was declared, before
  `add_subdirectory(tests/platform/cardputer)` registered its tests, so
  appending those names in place is not a repair: the target does not exist yet
  at that point and the loop's own `TARGET` check rejects the entry. The list
  is now built at the end of the root file, after every test subdirectory.
- Every tier a Task normally runs stays green. Only a completed coverage run,
  which belongs to a full batch, can observe the difference.

## How to apply

- Adding a C++ test target needs no second edit any more. The coverage
  configure records every native test target `lmdj_add_test` registers, reads
  the coverage test preset's own `filter.exclude.name`, and fails closed naming
  each selected target the root `lmdj_coverage_targets` list has not learned.
  Read its `why:` message: it lists the exact targets to add, in the remedy.
- A test the coverage preset excludes is not demanded, and no second exclusion
  list exists to maintain: when a new stress test joins the preset's exclusion
  ([`stress-tier-in-coverage-preset`](stress-tier-in-coverage-preset.md)), the
  gate follows the preset.
- Read the count's *direction* before editing anything. The lane's message now
  names the direction and its remedy, and it fires both ways: one module
  more than the list means a target the list has not learned, which is the case
  above. Far **fewer** signatures than objects -- `7 != 64` -- is not a list
  problem at all, and editing `lmdj_coverage_targets` is then the one repair
  that cannot help. It means a second coverage run cleared `profiles/`
  mid-flight, because `scripts/core-coverage.sh:66` deletes that directory at
  start and two runs sharing one build tree keep destroying each other's
  profiles. Confirm no other run is alive, wipe `build/core/coverage`, and
  rerun before touching the list. Take the same care with a bare
  `ctest --preset coverage`: only `scripts/core.sh coverage` exports
  `LLVM_PROFILE_FILE`, so running `ctest` directly writes `default.profraw`
  into the repository root, and the next run fails `build.active_tree` with
  `coverage artifact exists outside build/core` -- naming neither the stray
  file's origin nor the command that left it.
- Run `scripts/core.sh coverage check` before pushing any Task that adds a test
  target. The tiers `scripts/core.sh test dev fast` runs cannot see this, and
  the configure gate only proves the list is complete, not that the lane's
  coverage floors still hold.
- A new target usually lowers its module's covered fraction as well, because
  the new source lands with only the paths its own tests walk. Raise the tests
  until the module's floors hold; never lower a floor
  ([`coverage-floor-tuning`](coverage-floor-tuning.md)).
