# Standalone Python for Linux Core and release checks

Relates to #1551.

## Defect and choice

On netcup, executing the runner's Python 3.11.16 as `lmdj-runner-01`
with `env -i PATH=/usr/bin:/bin` exits 127: `libpython3.11.so.1.0`
cannot be found. The same command with `/usr/bin/python3` runs Python
3.12.3 and successfully starts a PATH-only child through `sys.executable`.
Use the Issue's second option: select system Python for Linux Core,
Deploy contract and release-audit. Include the Core package, sanitizer,
coverage, TSan and benchmark consumers of the same prerequisite.

## Task and declared files

One control-plane Task, one Conventional Commit:

- `scripts/ci/host/select-system-python.sh`
- `.github/workflows/ci.yml`
- `.github/workflows/core-nightly.yml`
- `.github/workflows/ci-self-hosted-core-benchmark.yml`
- `.github/workflows/release-audit.yml`
- `tests/build/ci_system_python_test.py`
- `tests/build/release_audit_workflow_test.py`
- `.agents/pitfalls/sanitized-child-interpreter-dependency.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- this plan

The selector defaults to `/usr/bin/python3`, requires Python 3.11+, and
probes startup and a nested `sys.executable` child with no inherited loader
environment. A job-local directory exposes only `python` and `python3`,
preserving the rest of PATH and later pinned Node setup. An explicit absolute
interpreter argument supports isolated prerequisite tests. It installs nothing
and restarts no runner. Checkout's existing clean behavior discards old CMake
build caches before the interpreter is selected.

The prerequisite catches an interpreter which cannot start under the production
sanitized environment; failure names the invariant and host repair. No new
required PR check, test selection change or production allowlist change.

## Verification and acceptance

- Lowest tier: execute the selector with a real independent interpreter and a
  deliberately loader-dependent fixture; assert PATH publication only follows
  a successful sanitized parent/child probe. Workflow contracts pin all named
  consumers to this prerequisite before their Python work.
- Run the affected CI/workflow contracts, ownership checks, actionlint and
  `scripts/docs-site.sh check` before committing.
- Obtain independent current-head review and guarded squash merge.
- Retain actual post-change Core Ubuntu, Deploy contract and release-audit run
  identities and interpreter evidence. A local probe alone is not acceptance;
  any unrelated lane failures stay explicit. Keep #1551 open until its live
  acceptance is established, then record the evidence and close it.

## Version Management

Version impact: none — CI interpreter selection only; no product identity,
Module, Host, Provider or Contract changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: Linux Core and release-check interpreter prerequisites change.
