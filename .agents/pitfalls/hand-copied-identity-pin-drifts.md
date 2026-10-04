---
id: hand-copied-identity-pin-drifts
area: core
status: absorbed
recurrences:
  - date: 2026-09-16
    occurrence: https://github.com/endaye/lmdj/issues/1073
    observed_by: Hermes Agent (deepseek-v4-flash)
  - date: 2026-10-04
    occurrence: https://github.com/endaye/lmdj/pull/1808
    observed_by: Claude Code (Opus 5.5)
exit: gate:tests/build/version_test.py
---

# A hand-copied module-identity pin is owned by no step of the version cascade, so a bump forgets it and it fails a lane that does not own the fact

## Why

`test_module_versions_and_dependencies_are_exact` in
`tests/core/facade/application_test.cpp` restated as a C++ literal what
`packages/application-facade/module.json` already declares -- the same fields
the `expected_modules` table in `tests/build/version_test.py` pins exactly, in
the `contract` tier. No bump procedure named it: #1025 (`3.1.0` -> `3.2.0`) and
the cascade #1348 repaired (`5.3.0` -> `6.0.0`) both updated `module.json`, the
Assembly, the lock, `compiled_assembly.cpp`, the Portal pages and
`version_test.py`, and the C++ copy drifted through both.

The cost was a lane that cannot diagnose it. `facade.application` is registered
`component`, so the C++ copy was the *only* copy of that pin inside
`scripts/core.sh package`, which runs the unit and component tiers and nothing
else. A manifest bump therefore took the Core package lane red for a version
fact that lane does not own, filed a second self-test Issue bucket beside the
`core_ubuntu` one for the same drift, and left `main` red until the next full
batch. The duplicate bought no detection the contract-tier table did not
already have; it only doubled where one drift surfaced.

The second occurrence was a product copy, not a test copy. The Cardputer profile in
`products/lmdj/src/cardputer_assembly.cpp` repeats the Product Build, the
Cardputer Host version and `sha256(products/lmdj/assembly.json)`, and
`apps/cardputer-host/CMakeLists.txt` repeats the Build as `PROJECT_VER`. No
generator writes them, and no check read them. The settle PRs kept the digest
current, but the Build allocations of #1808, #1810 and #1800 left it at a value
matching none of their Assemblies. Products `2.0.78.0` to `2.0.81.0` therefore
shipped a Cardputer profile reporting a stale Assembly digest. The
`2.0.82.0` settle repaired it, and extended the exit gate:
`tests/build/version_test.py` now fails, with `why` and `remedy`, when either
copy disagrees with `products/lmdj/version.json`,
`apps/cardputer-host/module.json` or the Assembly's sha256.

## How to apply

- Never restate a module manifest's identity, version or dependency pins as a
  literal in a test binary. `expected_modules` in `tests/build/version_test.py`
  is the single owner of that fact; a second copy is a defect, not extra
  coverage, and it fails in whichever lane happens to run it.
- Before adding an assertion, ask which lane executes it and whether that lane
  owns the fact. Identity pins belong to the `contract` tier, which
  `scripts/core.sh test dev full` and `core_ubuntu` run -- not to `package`,
  which deliberately runs only unit and component.
- When a bump forgets a copy, prefer deleting the duplicate over re-binding it:
  a literal that must be hand-edited in lockstep with a generated identity is
  forgotten again. See
  [`parity-check-between-agreeing-copies`](parity-check-between-agreeing-copies.md).
