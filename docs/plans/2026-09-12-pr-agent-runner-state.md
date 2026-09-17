# PR-Agent runner mount permissions

## Defect and scope

PR #1238 run 34628173677 attempt 1 made zero model calls and failed admission.
The ledger held USD 0.015171, not an exhausted USD 20 budget. In runner 04's
actual systemd mount namespace, opening the ledger lock fails with EROFS.
The runner-account smoke check outside that namespace succeeds: ACL permission
is necessary but does not override `ProtectSystem=strict`.

Keep the runner sandbox and all monetary/request limits. Add only the two
PR-Agent state directories to the Netcup template's `ReadWritePaths`; keep the
installation parent, releases and configuration read-only. Optional path
prefixes allow provisioning before the engine directories exist; service
restart after directory creation is still required. No Contabo, product,
provider, workflow routing or release changes belong to this Task.

## Declared files

- `scripts/ci/elastic-runner/unit-netcup.template`
- `scripts/ci/pr-agent/install.sh`
- `tests/build/ci_elastic_runner_test.py`
- `tests/build/ci_pr_agent_install_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- `.agents/pitfalls/runner-account-check-misses-service-mounts.md`
- `docs/plans/2026-09-12-pr-agent-runner-state.md`

## Verification and deployment

Lowest-tier tests: `ci_elastic_runner_test.py` checks the exact narrow template
allowlist and retained hardening. Linux-root `ci_pr_agent_install_test.py`
executes real transient systemd mount namespaces, proves the old configuration
rejects state writes, then proves the source template allows state append and
creation while independently DAC-writable files outside it remain mount-read-only.
These tests call no provider and do not change production runner services.
Run `ci_change_scope_test.py`, `bash -n scripts/ci/pr-agent/install.sh`, and
`scripts/docs-site.sh check` before commit. No new required GitHub check.

For the existing eight exact Netcup units, install a dedicated additive
drop-in containing these same two paths. Read back effective properties;
restart only an idle active runner, one at a time, and leave offline elastic
services stopped. Never interrupt a busy worker or change labels/capacity.
After restart, enter each actual service mount namespace to verify state
access and protected release bytes without reading credentials or calling a
provider. Retain the ledger byte identity through deployment. Then use an
authorized PR Review run as the separate end-to-end admission/publication
check; preserve the original failed attempt rather than reclassifying it.

## Documentation impact

Documentation impact: required — `/operations/testing-and-proof`; installation
account smoke checks and live service write access are separate boundaries.

## Version Management

Version impact: none — CI runner mount policy only; no product/module/provider
manifest, Contract, Product Build, or release allocation changes.
