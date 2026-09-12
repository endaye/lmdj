# Preserve complete-input review refusals

## Defect and scope

PR 1266 at `c8fab3b67b6abe3bff708b5563acfc84b0e9e671` changes 2,096
files. The input collector's unchanged `MAX_FILES=50` correctly refuses that
inventory before provider execution. Read-only local reproduction on control
`1863817283e2c50f667b5439720128184ba06561` produced an
`InputCollectionError` with a structured failure result. This is a diagnostic
reproduction, not the original runner receipt.

Run `34709720280/1` failed collection, printed a generic pipeline message and
reported no uploadable artifacts. The producer writes `collection-failure.json`,
but the workflow upload list omits it. Preserve that bounded refusal artifact
and distinguish structured collection refusals in the CLI without printing raw
exception, API, provider or PR text. Keep exit 1, no success witness, no model
execution and all input limits intact. This repairs observability, not the
oversized PR's eligibility; independent current-head takeover remains required.

Declared files:

- `.github/workflows/pr-review.yml`
- `scripts/ci/review_pipeline.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/plans/2026-09-13-review-collection-failure-evidence.md`

## Verification

Red/green focused CLI diagnostic and actual workflow upload-contract tests;
existing real-Git collection refusal test proves the bounded file exists, no
success artifacts/witness exist and the CLI exits 1. Run complete pipeline and
workflow suites, ownership and Portal check, then independent read-only review.
No provider, GitHub write, runner change, retry or full release is authorized by
this Task. Local artifact selection is not an actual Actions upload receipt.

### Results

- Workflow causal red: `/tmp/lmdj-collection-refusal-red-workflow.log`, exit 1,
  missing producer failure filename in the actual upload step.
- Corrected diagnostic causal red against the original `c8fab3b6` pipeline:
  `/tmp/lmdj-collection-refusal-red-cli-v2.log`, exit 1, generic message instead
  of the fixed receipt/takeover diagnostic.
- The initial diagnostic test incorrectly mocked across a subprocess boundary;
  independent review identified the same defect. The original red and failed
  full run are retained in `/tmp/lmdj-collection-refusal-red-cli.log` and
  `/tmp/lmdj-collection-refusal-pipeline.log`, not treated as causal proof.
  Both new diagnostic tests now invoke actual `pipeline.main()` under the
  patched collector; the existing real-Git CLI refusal journey still runs.
- Final pipeline: 42 discovered, 41 passed, 1 skipped, exit 0;
  `/tmp/lmdj-collection-refusal-pipeline-v2.log`. The skipped test requires the
  explicitly enabled pinned PR-Agent actual-handler integration runtime.
- Workflow: 27 discovered, 26 passed, 1 skipped, exit 0;
  `/tmp/lmdj-collection-refusal-workflow.log`. Pinned actionlint is not installed.
- Staged ownership 74/74, exit 0: `/tmp/lmdj-collection-refusal-scope.log`.
- Portal 116/116, production build and 46 routes/internal links passed, exit 0:
  `/tmp/lmdj-collection-refusal-docs.log`.
- Independent re-review found the test finding fixed and no new actionable
  finding; independently reran the final pipeline and workflow suites with the
  same passed/skipped populations. No actual Actions upload was exercised.

Pitfall disposition: producer filename versus workflow consumer mismatch and
fixed CLI routing are directly captured by regressions; no new process-only
invariant or exception is introduced.

## Version Management

Version impact: none

Reason: CI failure evidence only; no Product, Assembly or review-limit change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/testing-and-proof/

Reason: document retained input-collection failure evidence and takeover path.
