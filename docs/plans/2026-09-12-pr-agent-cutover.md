# PR-Agent production pilot cutover

Date: 2026-09-12 (Asia/Shanghai)
Related: #1149, #1153, #1154, #1155, #939.

## Scope and authority

The owner asked Claude on 2026-09-12 to connect the existing PR-Agent engine
directly, using DeepSeek, and retire unused code/issues after stopping the prior
workers. The next session was asked to continue that work. This Task carries
the production pilot routing change through ordinary Task verification and
current-head review. It does not certify the former T4/T5 cohort or waive
independent review, budget, complete input, finding anchors or branch protection.
No further manual paid probe is part of this continuation.

The earlier plan's shadow-first sequence is superseded for this owner-requested
pilot. Its quality, capacity and recovery criteria remain uncompleted evidence,
not retrospectively passed or reduced. Related acceptance Issues stay open
until their actual remaining scope is resolved. Old failed runs remain intact.

## One implementation Task

Connect collect-t2 -> installed PRReviewer/LiteLLM -> v2 capture/finalize ->
trusted publisher, retain producer/artifact identities and conservative scope,
and remove retired CLI, credential-preflight and deployment entrypoints.
The publisher's GitHub HTTP helper moves out of the removed Grok module.

Repair a reproduced prompt contradiction: the pinned PRReviewer example emits
fields rejected by the strict consumer and omits its required summary. Keep
the upstream reviewer and native YAML parser; configure one consistent output
schema at the actual system-prompt boundary. Normalize YAML terminal newlines
only against the exact changed-path inventory. Invalid anchors remain failures.

Install adapter/config overlays into a new root-owned release. Verify the
candidate with a runner account before switching current; preserve the previous
release and shared budget ledger. The archive identity describes the seed
bundle; member hashes describe the installed overlay. The request timeout stays
60 seconds and the engine deadline stays 600 seconds.

Declared files:

- `.github/scripts/pr_review_target.py`
- `.github/workflows/pr-review.yml`
- `scripts/ci/pr_agent_review.py`
- `scripts/ci/review_pipeline.py`
- `scripts/ci/pr-agent/install.sh`
- `scripts/ci/pr-agent/run-engine.sh`
- `scripts/ci/pr-agent/runtime.toml`
- `scripts/ci/scope_policy.json`
- `tests/build/ci_pr_agent_review_test.py`
- `tests/build/ci_pr_agent_install_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `tests/build/ci_change_scope_test.py`
- `docs/plans/2026-09-12-pr-agent-cutover.md`
- `docs/plans/2026-09-10-pr-agent-review-migration.md`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`

Retired files (recoverable in Git):

- `.github/scripts/advisory_review_liveness.py`
- `.github/scripts/grok_review.py`
- `.github/workflows/advisory-review-liveness.yml`
- `.github/workflows/pr-agent-credential-preflight.yml`
- `scripts/ci/pr-agent/deploy-runner.sh`
- `scripts/ci/pr-agent/netcup-review.json`
- `scripts/ci/pr_agent_credential_preflight.py`
- `tests/build/ci_advisory_review_liveness_test.py`
- `tests/build/ci_claude_review_workflow_test.py`
- `tests/build/ci_grok_review_workflow_test.py`
- `tests/build/ci_pr_agent_credential_preflight_test.py`
- `tests/build/ci_pr_agent_runner_test.py`

## Verification

Run the pinned Python 3.12/LiteLLM 1.100.0 real-handler suite, including actual
rendered-prompt/schema compatibility, complete input, native findings, provider
fallback, wire usage, timeout and ledger tests. Network is denied by that suite.
Run input/pipeline/workflow, v1/v2 scope, wait, discovery, failure and merge-map
regressions. Keep retained v1 receipt tests despite retiring CLI invocations.
Run actionlint, shell syntax checks, staged path ownership and the Portal check.

The no-provider host check covers installation -> runner witness -> current
read-back; the ledger must remain byte-identical. A failed candidate must leave
current unchanged. Real Actions collect -> review -> publication -> read-back,
new head, rerun, cancellation, stale/duplicate handling and rollback/restoration
remain separate acceptance legs. A manual historical PR replay with run_id=1
is not evidence of any authenticated Actions publication.

The cutover PR itself still checks out its trusted base. It cannot execute new
PR-owned scripts before merge; missing base entrypoints require independent
review, never checkout of untrusted PR code or fabricated owner attestation.

## Version Management

Version impact: none — CI routing and the adapter change; no Product Build,
Module, Host, Provider or Contract version is allocated or changed.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Current routing and install instructions change. Historical operations evidence
is retained under an explicit history heading.

## Pitfall disposition

Pitfall impact: none — the prompt contradiction and path normalization are
expressed by executable regression tests. The receipt-first takeover follows
existing issue-done guidance; it adds no global governance gate.
