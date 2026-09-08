# Move independent labs to demos

## Scope and dependency

Depends on the root demos migration in PR #911 (carried locally as a prerequisite
commit while that PR remains open). Move `apps/chameleon-lab` and
`apps/web-runtime-lab` to `demos/`; preserve source, assets, tests and stable
`scripts/*-lab.sh` commands. Do not move the Cloudflare Web Runtime Host or alter
deployment configuration. Historical plans, decisions and snapshots stay unchanged.

Declared files: both lab trees, `apps/README.md`, `demos/README.md`, the two lab
wrapper scripts, `scripts/ci/scope_policy.json`, the two CI scope/preflight test
files, current Web Runtime portal page, deployment and Audio Lab acceptance docs,
and this plan. Keep original lab lanes and portal coverage in addition to demos'
docs_static routing; do not reduce tests or physical acceptance obligations.

## Verification

- `scripts/chameleon-lab.sh test`
- `scripts/web-runtime-lab.sh test`
- `bash tests/build/test_active_tree.sh`
- `python3 tests/build/ci_change_scope_test.py` after staging
- `python3 tests/build/ci_local_preflight_test.py`
- `scripts/architecture-portal.sh check`
- Compare moved-file inventory and modes; inspect remaining executable old-path
  references and staged whitespace. No physical audio or browser acceptance claim.

## Version Management

Version impact: none. Independent experiment paths only, no product or module
behavior or identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /platform/web-runtime
Reason: update current Audio Lab source location and distinguish it from the
Core-dependent diagnostic Host; leave immutable historical snapshots untouched.
