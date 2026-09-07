---
id: generated-identity-check-skips-real-tree
area: ci-release
status: open
recurrences:
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/issues/749
    observed_by: claude-opus-5
exit: none
---

# A freshness check driven only against a test fixture proves the generator works and proves nothing about the artifact the repository actually committed.

## Why

`tools/web-runtime/generate_runtime_identity.py --check` exists to prove that
`products/lmdj/generated/web-runtime-identity.json` and its `.mjs` twin still
describe repository truth; both embed `product_build`, `assembly_sha256`,
`platform.version` and each Web Host's `version`. Nothing runs it against the
repository. `grep -rn "generate_runtime_identity\|runtime-identity" scripts/
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
  Do not infer freshness from a green `version_test.py`; run `--check` yourself.
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

`exit: none` because the mechanism is not this entry's to land:
[#749](https://github.com/endaye/lmdj/issues/749) owns it and names the
placement that cannot silently stop running — one added assertion in
`tests/build/version_test.py` calling
`runtime_identity_generator.write_or_check(repo_root, check=True)` beside the
existing fixture-root coverage, which needs no lane wiring at all. When that
lands, record it here as `gate:tests/build/version_test.py` and set
`status: absorbed`.
