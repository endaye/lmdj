---
id: local-ci-list-names-batch-lanes
area: ci-release
status: open
recurrences:
  - date: 2026-09-17
    occurrence: https://github.com/endaye/lmdj/pull/1490
    observed_by: Claude Opus 5
  - date: 2026-09-17
    occurrence: https://github.com/endaye/lmdj/pull/1492
    observed_by: Claude Opus 5
exit: gate:tests/build/release_deployment_effect_test.py
---

# `scripts/local-ci.sh --list` names lanes a Pull Request never runs, so a change owned by one of them is unverified at merge.

## Why

`--list` reports every lane the change-scope classifier selects, for example
`ci_contract, deploy_contract, portal, web_runtime_host`. That reads like "these
lanes will verify this Pull Request". They will not.

`pr-contract.yml` has exactly five jobs: `change-scope`, `ci-contract`,
`docs-static`, `documentation-impact`, `portal-provenance`. Every other lane —
`deploy_contract`, `web_runtime_host`, `creator`, `core_*`, `package` — lives in
`ci.yml`, which is `workflow_call` only and runs inside admitted incremental main
batches. This is the documented design rather than a defect: `CLAUDE.md` places
those in "selected incremental main batches and explicit complete self-tests, not
a Pull Request merge gate".

So a change owned only by a non-PR lane reaches `main` green and fails later, in
a batch, attributed to whatever else that batch happens to carry.

## How it bit

#1490 and #1492 flipped the expected deployment evidence contracts in
`tools/release/deployment_effect.py` to their Cloudflare versions.
`tools/release/` is owned by `deploy_contract`, which runs
`python3 -m unittest discover -s tests/build -p 'release_*_test.py'` — including
`release_deployment_effect_test.py`, whose fixtures still built Netlify-shaped
documents. That suite went 38 of 48 red on `main`, and no Pull Request check ever
ran it. Both PRs had run the test files they edited.

## How to apply

When `--list` selects a lane that is not `ci_contract`, `docs_static` or
`portal`, run that lane locally before pushing:

```bash
scripts/local-ci.sh --lanes deploy_contract
```

Running the individual suites you edited is not a substitute. The lane's
`discover` pattern picks up suites that consume what you changed without naming
it, which is precisely the gap that let this through twice.
