# Cloudflare Preview pipeline

Relates to #922 and #873. Depends on the artifact/download helpers in PR #931.
This branch prepares the pipeline; no pilot variable or credential is provisioned
by this Task. The owner has not yet selected the runner budget. Do not activate
or describe a local workflow test as a live Preview.

## Credential-free producer Task

Declared files: `.github/workflows/cloudflare-preview-build.yml`,
`scripts/ci/hosted_runner_policy.json`, `scripts/ci/scope_policy.json`,
`tests/build/ci_cloudflare_preview_workflow_test.py` and this plan.

The exact selected same-repository PR head builds on a fresh standard hosted
Linux runner. No deployment secret, privileged Environment, persistent checkout
credential or mutable shared cache is provided. Normal jobs are skipped while
`CLOUDFLARE_PREVIEW_PILOT_BRANCH` is empty. Setting an exact pilot branch requires
the outstanding budget decision; broad activation is not included. Hosted policy
records the isolation need, not permission to incur unbounded charges.

The base-sourced packer produces `static.zip`; the artifact name binds head and
run attempt. PR code can modify any file on its build machine, including that
packer, so the trusted publisher MUST independently download, validate and
recompute its contents. Base checkout is provenance, not a sandbox boundary.
The producer is discarded before any separate token-bearing publisher runs.

Validation: four workflow boundary tests, hosted-runner-policy tests, staged
scope tests and the existing 23 helper tests. These tests cover declared settings
only. Actual ephemeral runner behavior, artifacts and head identity require a
live opt-in pilot after the consumer is ready.

## Remaining trusted publisher

A separate default-branch workflow must resolve the successful authenticated
build and current PR, download bounded outer/inner archives, generate fixed
preview-only configuration and known headers, upload only to a designated
preview Worker, run trusted smoke and publish status on the same still-current
head. Unsuccessful and superseded runs must not produce a current-head success.
Neither PR scripts nor uploaded JavaScript may execute in the credential-bearing
publisher. Install trusted dependencies before introducing the deployment token.

## Version Management

Version impact: none. No Product/Assembly or serialized production evidence
Contract changes.

## Documentation Impact

Documentation impact: none for this inactive producer preparation. Current
Portal behavior is unchanged; activation must update its runbook and operations
page with actual source/version/status evidence.


## Trusted publisher implementation Task

Additional declared files: `.github/workflows/cloudflare-preview-publish.yml`,
`scripts/ci/cloudflare_preview_publish.py`, its ci-prefixed test,
`apps/architecture-portal/scripts/cloudflare-preview-smoke.mjs`, its Portal test,
the workflow boundary test, scope policy, the current documentation-governance
Portal page and this plan.

The default-branch workflow uses its own workflow SHA, installs trusted tools
before injecting credentials, validates the successful build/PR/artifact and
creates fixed configuration for `portal-preview`. No uploaded Worker/config
executes; stable routing must remain off. First target creation may use deploy
with workers_dev false; later candidates use versions upload. No production
promotion API is called. A foreign or newly live stable target stops publication.

Trusted smoke uses the API-sourced Product manifest and SHA, checks current and
snapshot pages plus headers and every artifact file's digest/length. It never
receives GitHub or Cloudflare credentials. The publisher rereads head immediately
before upload and status; superseded runs produce retained superseded evidence.
A status POST with an unknown receipt is not blindly retried or overwritten.
Failed build/smoke can only report failure on its still-current source head.

Validation: publisher transaction tests (same version URL, first target,
failed build/smoke, stale completion, live stable route and unknown status
receipt), workflow credential-boundary tests, artifact HTTP tests, hosted runner
policy, staged scope ownership and full Portal check. No live upload is claimed.
The runner budget, pilot variable, protected Environment setup and real artifact
pilot remain outstanding before activation. Both workflows default to no job
while the variable is absent.

Documentation impact: required for this publisher Task.
Affected portal pages: /operations/documentation-governance
Version impact: none; internal pilot receipts are not production Contracts.
