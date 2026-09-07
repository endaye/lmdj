---
id: coverage-target-list-omits-new-test
area: ci-release
status: open
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/pull/697
    observed_by: Claude Code (Opus 5)
exit: none
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

A gate is admissible here — the invariant is settled, violation is decidable by
comparing the registered CTest target set with the list, and the comparison is
deterministic — but no such gate exists yet, so the entry stays `open`.

## How to apply

- When a Task adds a C++ test target, add it to `lmdj_coverage_targets` in the
  root `CMakeLists.txt` in the same commit as the package registration, and
  keep the two in the same order.
- Read the count's *direction* before editing anything. The message is the only
  symptom, and it fires both ways: one module more than the list means a target
  the list has not learned, which is the case above. Far **fewer** signatures
  than objects -- `7 != 64` -- is not a list problem at all, and editing
  `lmdj_coverage_targets` is then the one repair that cannot help. It means a
  second coverage run cleared `profiles/` mid-flight, because
  `scripts/core-coverage.sh:66` deletes that directory at start and two runs
  sharing one build tree keep destroying each other's profiles. Confirm no
  other run is alive, wipe `build/core/coverage`, and rerun before touching the
  list. Take the same care with a bare `ctest --preset coverage`: only
  `scripts/core.sh coverage` exports `LLVM_PROFILE_FILE`, so running `ctest`
  directly writes `default.profraw` into the repository root, and the next run
  fails `build.active_tree` with `coverage artifact exists outside build/core`
  -- naming neither the stray file's origin nor the command that left it.
- Run `scripts/core.sh coverage check` before pushing any Task that adds a test
  target. The tiers `scripts/core.sh test dev fast` runs cannot see this.
- A new target usually lowers its module's covered fraction as well, because
  the new source lands with only the paths its own tests walk. Raise the tests
  until the module's floors hold; never lower a floor
  ([`coverage-floor-tuning`](coverage-floor-tuning.md)).
