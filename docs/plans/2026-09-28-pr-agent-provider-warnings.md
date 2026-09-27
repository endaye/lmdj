# PR-Agent provider limit warnings

Task: [#1188](https://github.com/endaye/lmdj/issues/1188).
Baseline: `0d376962` on isolated branch `feat/review-provider-warnings`.

## Outcome and scope

Observe failed model requests at the existing LiteLLM admission seam. Retain
only distinct finite warning categories per provider attempt, including failures
followed by a successful retry or fallback. The authenticated result already
binds provider, run and attempt; the capture step renders those identities and
fixed operator guidance in the Actions log and step summary.

Categories: `insufficient_balance`, `quota_exhausted`, `rate_limited`,
`unknown_limit`. A bare 429 or ambiguous limit response is `unknown_limit`,
never proof of missing funds. Structured provider-specific codes take precedence
over generic status. Account data, raw messages, credentials and headers never
enter warnings. Existing failure classification, ledger accounting, retry
policy, provider activation, fallback and review eligibility stay authoritative.
No balance API, paid verification, deployment or new required check.

The optional bounded `provider_warnings` attempt field is accepted by the
consumer before any installed adapter is updated. Older installed engines and
retained results without that field remain readable. Host installation is a
separate operation through the existing installer, not part of this Task.

## Declared files

- `scripts/ci/pr_agent_review.py`
- `scripts/ci/review_pipeline.py`
- `tests/build/ci_pr_agent_review_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/plans/2026-09-28-pr-agent-provider-warnings.md`

## Classification evidence

Provider references checked on 2026-09-28:

- [DeepSeek errors](https://api-docs.deepseek.com/quick_start/error_codes/):
  402 is insufficient balance; bare 429 remains conservative in this adapter.
- [Z.AI errors](https://docs.z.ai/api-reference/api-code): 1113 identifies a
  balance/resource-package refusal; 1302 request rate; 1308/1310 usage quota.
  Compound quota/balance and unknown codes remain ambiguous.
- [Kimi troubleshooting](https://www.kimi.ai/help/kimi-api/api-troubleshooting):
  distinguish rate-limit type from account quota/billing type; a specific
  balance message may refine the latter, but the type alone is not a balance
  measurement.
- [xAI errors](https://docs.x.ai/developers/debugging) and
  [billing limits](https://docs.x.ai/developers/rest-api-reference/management/billing):
  rate and billing limits are distinct; unknown or compound credit/spend
  refusals must not be forced into an insufficient-balance claim.

Synthetic explicit structured codes exercise each category for all four
providers; these fixtures do not claim every code is emitted by every provider.
Provider-specific cases exercise the documented native shapes separately.

## Verification

Lowest tier: adapter classification/seam tests and capture tests. Assert finite
classification, no auth/network/success false positives, secret-free output,
deduplication, unchanged request counts, failed outcome retention, retry/fallback
success retention, timeout retention, and rejection of malformed warning data.
Run the pinned real PR-Agent/LiteLLM offline integration lane with synthetic HTTP
responses to verify SDK exception wrapping; it denies outbound model traffic.

Commands:

- `python3 tests/build/ci_pr_agent_review_test.py`
- `python3 tests/build/ci_review_pipeline_test.py`
- `bash scripts/ci/pr-agent/integration-test.sh`
- `python3 tests/build/ci_pr_review_workflow_test.py`
- `scripts/docs-site.sh check`
- After staging the new plan: `python3 tests/build/ci_change_scope_test.py`

Baseline adapter: 66 tests, 9 explicit pinned-runtime skips. Pipeline: 71 tests,
1 explicit pinned-runtime skip. Integration must be run separately, not counted
as covered by those skips. No live account health or deployment claim follows
from synthetic responses. No pitfall recurrence identified at task start.

Completed local verification:

- Adapter: 71 tests, 9 explicit source/runtime skips in the ordinary interpreter.
- Pipeline: 74 tests, 1 explicit pinned-runtime skip.
- Pinned integration: PASS, including the 50-test real-handler child, four
  native HTTP provider paths, retry/fallback/deadline retention and raw-secret
  rejection. The parent retains one dependency-import skip in its ordinary
  interpreter; the Python 3.12 child and bundled cost-map probe run explicitly.
  The initial four-provider fixture attempted a forbidden non-DeepSeek-first
  configuration; the corrected fixture keeps the production admission rule and
  reaches each secondary via a real synthetic DeepSeek authentication refusal.
- PR workflow: 35 tests; staged ownership: 75 tests.
- Portal: 170 tests, 10 diagram sources / 20 outputs, 48 routes and internal
  links; installed dependencies with the existing lockfile first.

No production adapter installation or paid provider call was performed.

## Version Management

Version impact: none — internal review tooling, no Product, Module or Contract
identity changes. Optional diagnostics extend the internal result only.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Document categories, operator visibility and the separate installed-engine
update boundary without claiming this source change is already deployed.
