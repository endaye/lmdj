---
id: generated-identity-check-skips-real-tree
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/issues/749
    observed_by: claude-opus-5
  - date: 2026-09-09
    occurrence: https://github.com/endaye/lmdj/issues/1029
    observed_by: Codex
  - date: 2026-09-18
    occurrence: https://github.com/endaye/lmdj/issues/1531
    observed_by: Hermes Agent (glm-5.3-flash)
exit: gate:tests/build/version_test.py
---

# A freshness check driven only against a test fixture proves the generator works and proves nothing about the artifact the repository actually committed.

## Why

`tools/web-runtime/generate_runtime_identity.py --check` exists to prove that
`products/lmdj/generated/web-runtime-identity.json` and its `.mjs` twin still
describe repository truth; both embed `product_build`, `assembly_sha256`,
`platform.version` and each Web Host's `version`. At the first occurrence,
nothing ran it against the repository. `grep -rn "generate_runtime_identity\|runtime-identity" scripts/
.github/` returns no matches, and the only consumer,
`tests/build/version_test.py:480-628`, imports the generator and drives it
against a synthetic `fixture_root` — never `repo_root`.

So the check and the artifact never meet. Editing one line of
`products/lmdj/assembly.json` changes the Assembly digest and leaves both
committed identity files describing a different Assembly, while
`python3 tests/build/version_test.py` reports `product version tests: PASS`,
`scripts/core.sh proof` passes, `scripts/architecture-portal.sh check` passes,
and `python3 scripts/version.py verify --version-file … --assembly … --lock …`
passes. Only the unwired `--check` says
`generated Runtime identity is stale`. Observed on the Stage 11
`lmdj.project.v4` Contract cut, where the committed files still carried
`assembly_sha256: c24cabdd…` from the pre-change Assembly.

This is not derivable from the product code: reading the generator, the check
and the test all look correct, because each is. The defect is the wiring
between them, and a passing gate that measures a fixture is
indistinguishable — from inside a green run — from a gate that measures the
truth.

`web-runtime-identity.mjs` is deep-frozen and imported by the Web build, so a
stale `product_build` or `assembly_sha256` propagates into the canonical
distribution manifest of a Product Build — the same manifest the deployment
validator and the release evidence chain bind.

## How to apply

- Regenerate the pair in the same commit as any `products/lmdj/assembly.json`
  change or any Host/platform `module.json` bump, and verify it:
  ```bash
  python3 tools/web-runtime/generate_runtime_identity.py --repo-root .
  python3 tools/web-runtime/generate_runtime_identity.py --repo-root . --check
  ```
  `version_test.py` now runs this exact check against `repo_root`, separately
  from its generator fixtures. Do not infer freshness from fixture-only tests.
- More generally, when a repository ships both a generator and a `--check`
  mode, confirm which tree the check is pointed at before trusting it. Grep for
  the invocation, not for the definition: a check nothing calls is a check
  nothing enforces.
- Do not conclude a lane will host the check because a change currently selects
  every lane. `scripts/ci/scope_policy.json` lists `products/lmdj/` twice — as
  a full rule (`reason: product assembly`) and, for the focused path, mapped to
  `["portal"]` only. Every lane runs today because the full rule wins, not
  because anyone declared a mapping for these files, so a check parked in an
  incidentally selected lane stops running the moment that full rule narrows.

The recurrence at [#1531](https://github.com/endaye/lmdj/issues/1531) is the
first where the torn state was *manufactured* rather than merely missed. The
Build allocation [#1516](https://github.com/endaye/lmdj/pull/1516) moved
`products/lmdj/version.json` to `1.0.61.0` while the candidate cut rendered
only the four Assembly files, so `main` carried an identity describing
`1.0.60.0`. The exit held and failed with the generator's own mismatch reason
— but after the merge, because the lanes that run ctest are batch-only and no
Pull Request check runs them (see
[`local-ci-list-names-batch-lanes`](local-ci-list-names-batch-lanes.md)). A
mechanism that binds the check to the real tree still cannot bind it before
`main` moves, and allocating a Build is exactly the change the first **How to
apply** bullet names — and the one most likely to be prepared by tooling
rather than by someone reading this entry.

The repair, [#1535](https://github.com/endaye/lmdj/pull/1535), moves the
obligation into the producer: `tools/release/candidate_material.py` loads
`tools/web-runtime/generate_runtime_identity.py` from the frozen export and
regenerates the pair for the reserved build, so the cut's declared inventory is
six files rather than four, and
`tests/build/release_candidate_material_test.py` asserts that literal inventory
and runs the generator's own check against the exported pair. That gate holds
the release path; `tests/build/version_test.py` remains the exit for this entry
because it is what binds the check to the repository tree for every ordinary
`assembly.json` or `module.json` change, which no candidate cut sees.

The recurrence at [#1029](https://github.com/endaye/lmdj/issues/1029) exposed
stale Product, Assembly, Platform and Host projections during canonical canary
preparation. The existing version test now calls
`runtime_identity_generator.write_or_check(repo_root, check=True)` beside the
unchanged fixture-root coverage, implementing the mechanism requested by
[#749](https://github.com/endaye/lmdj/issues/749). The check fails with the
generator's concrete mismatch/staleness reason and regeneration remedy; it
does not add a new workflow or PR required check.
