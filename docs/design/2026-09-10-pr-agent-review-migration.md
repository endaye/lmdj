# PR-Agent review migration

Date: 2026-09-10
Status: design in progress; production remains on the existing review workflow.
Owner: project lead; implementation and independent verification use supervised
Orca workers. Umbrella: #1149. Design Task: #1150.

## Outcome and evidence boundary

Replace the GLM/Kimi Claude Code action and Grok CLI invocation with PR-Agent
running on the existing Netcup server, using the owner's provider API accounts.
Keep complete review input, current-head provenance, test-scope advice,
independent publication and honest failure outcomes. A framework exit code,
valid JSON or an available runner is not proof of a useful completed review.

The baseline is LMDJ `8c6f2ac493f2756b0ba3a71746af550029467a2a`.
PR #1127 run `34388846394/1` and #1132 run `34390281428/1` recorded
`is_error=true` without structured output for GLM/Kimi and
`authentication_required` for Grok. These symptoms do not establish the
underlying provider error. Preserve the runs; do not reclassify them as reviewed.

This design does not change branch protection, product tests, releases,
existing unrelated PR holds, or the incremental controller's authority.

## Execution boundary

GitHub Actions remains the dispatcher and source of run/attempt identity:

1. Collect the trusted policy and fixed base/head inventory without executing
   PR files. Obtain file bytes through Git object reads, not checkout hooks.
2. Execute a pinned PR-Agent engine in an isolated Netcup review worker.
   The engine receives no GitHub write token and no repository-controlled
   configuration. Provider keys enter only through a restricted secret boundary.
3. Validate structured output and actual input coverage, then bind the result
   to repository/PR/base/head/control revision/run/attempt and engine/model.
4. A separate publisher authenticates that identity against GitHub, verifies
   the current head and changed-line locations, and publishes the review/scope.
5. Preserve the existing merged-PR mapping and downstream scope consumers.

Use one production review path, with configured provider fallback inside it.
Shadow evaluation is a separate explicitly triggered read-only path until
acceptance. It must never mint production scope authority.

## Upstream identity and configuration

Source selection for implementation: community PR-Agent commit
`53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c` (package version `0.45.0`).
This is an explicit source pin, not a claim that a latest release is stable.
Its Python requirement is at least 3.12 and its LiteLLM pin is `1.100.0`.
Build from the selected source and a hash-locked dependency set. The existing
Netcup policy excludes a Docker daemon; use a systemd-sandboxed immutable
Python 3.12 environment as the deployment baseline. T2 records the actual
Linux amd64 bundle SHA-256, source and dependency lock; any optional container
build records its image digest but is not a deployment prerequisite. No digest
is invented here. Source/lock/bundle updates require adapter and coverage tests.

Use PR-Agent's real review engine, prompt construction and model integration;
do not replace it with a standalone home-grown LLM client. Register an
immutable-content LMDJ GitProvider through `register_git_provider`, invoke
`PRReviewer` directly with the stock `LiteLLMAIHandler`, and capture native
output through `publish_structured_review`. Do not invoke the stock CLI.
The provider constructs `FilePatchInfo` from authenticated base/head blobs;
repository settings/content discovery returns no configuration. Publication is
a local capture sink with `publish_output=false`. No GitHub write interface
is available inside the model process.

Typed mapping rejects invalid native findings, duplicate keys, wrong-side or
out-of-diff anchors, and oversized output. A coverage receipt is bound by digest
to the attempt history and revalidated by the consumer; a loose artifact is
insufficient. Integration tests replace the real handler's `acompletion` seam,
so they exercise PR-Agent prompt construction and mapping without API costs.

The CLI plain-diff mode writes JSON, but its normal enrichment assumes a
head-version working tree and reconstructs the base by reverse application.
Running it in LMDJ's base checkout is therefore not an acceptable shortcut.
Configuration discovery also reads repository pyproject settings at import time.
Run from a dedicated engine directory with allowlisted settings and controlled
file inputs; untrusted `.pr_agent.toml`, `pyproject.toml`, AGENTS/skills/hooks,
symlinks and subprocess instructions cannot become executable configuration.

## Complete-input and output contract

For every changed file, record old/new object identities and lengths, change
kind, path and all input hunks. Treat binary, non-UTF8, oversized and otherwise
unsupported content explicitly. Unsupported required input means incomplete
review, not a clean result. Include deleted contents, not just deleted names.

The coverage witness must describe the prompt actually handed to the model,
not just a collector's inventory. PR-Agent's default compression can omit
patches and deletion-only hunks. Reject that path or replace it through a
narrow audited adapter that retains all required bytes within the admitted monetary and request limits.
Split oversized input only with explicit per-chunk identities, complete union
coverage and cross-file context limits. A lost chunk invalidates completion.

The normalized review retains `summary`, changed-line `findings` and explicit
`test_scope`. Findings must address correctness, security or concurrency, not
style. Invalid locations cannot be silently accepted as a clean finding list.
A clean review publishes a summary without artificial inline issue threads.

Test scope continues to obey the deterministic floor and existing incomplete
input policy. Missing model advice is not fabricated. Any supported conservative
fallback must say that advice was unavailable and must not shrink the floor or
turn incomplete review into reviewed status. Retain historical receipt decoding
for GLM/Kimi/Grok while recording the actual provider/model and new engine pin.

## Receipt and compatibility interface

T2 emits `coverage.json` using closed schema `lmdj.pr-agent-coverage.v1`.
Required keys are `schema`, `identity`, `engine`, `provider`, `model`,
`input_sha256`, `expected_hunks`, `observed_hunks`, `remaining_files`,
`failed_chunks`, `complete`, and `usage`. Identity contains repository, PR,
base/head/control SHA, run ID and run attempt. Hunk entries bind path, change
kind, old/new blob IDs and SHA-256 of required patch/content segments. Deleted
content participates even when it has no RIGHT-side finding anchor.
`complete=true` requires exact expected/observed segment equality, no remaining
files and zero failed chunks at the actual handler boundary.

T3 introduces `lmdj.ci-review-history.v2`: a closed object with `schema` and
`attempts`. Each attempt has `backend`, `status`, `error_class`, `review`,
`engine`, `provider`, `model`, and `coverage_sha256`. The digest is SHA-256 of
the complete canonical UTF-8 receipt JSON (sorted keys, compact separators,
no self-digest field). Failed attempts retain available receipts and explicitly
use null when no receipt exists; reviewed attempts require a valid digest and
complete receipt. The existing normalized review payload remains v1.

`review_pipeline.capture` validates identity and observed coverage, computes
the digest and writes history. Shadow and production result bundles contain
context, history, review/result/failure and the referenced coverage receipts.
Finalize, publisher, wait/failure/discovery and merge-map validation recompute
the digest and reject absent or mismatched evidence. T3 adds v2 marker/codec
support binding history digest; T6 activates emission. Old v1 history and
markers remain readable under their recorded producer policy, but cannot be
used to satisfy new-engine coverage. Historical evidence is not rewritten.

The backend registry retains IDs `glm`, `kimi`, `grok` and adds `deepseek`.
The actual providers are respectively `zai`, `moonshot`, `xai`, `deepseek`;
engine identity is separately `pr-agent` plus its source/bundle hashes.
Provider support remains four-way, but availability is explicit policy, not an
assumed four-way live chain. Initial activation candidate is DeepSeek first;
other providers remain disabled until their account route, model and quota are
verified. Kimi is disabled for the exhausted weekly window reported by the
owner; do not retry it or purchase extra usage to bypass that hold. Record
skipped/disabled suppliers separately from attempted failures. Preserve the
four-supplier health and fallback acceptance gap until all are verified.

The owner entered the DeepSeek key on 2026-09-10. GitHub secret metadata
confirms `PR_AGENT_DEEPSEEK_API_KEY` updated at 2026-09-10T03:45:18Z; its
value, authentication and balance were not read or verified. Allocate these
GitHub Actions Secret names for operator entry: `PR_AGENT_DEEPSEEK_API_KEY`,
`PR_AGENT_ZAI_API_KEY`, `PR_AGENT_KIMI_API_KEY`, `PR_AGENT_XAI_API_KEY`.
The first candidate endpoint/model is `https://api.deepseek.com` /
`deepseek-v4-pro`; the documented effective version is DeepSeek-V4-Pro-0813.
This model alias can change upstream, so retain the actual response model and
source/pricing observation in every cohort. Do not claim live health before a
budget-admitted request succeeds. The initial enabled candidate order is
`[deepseek]`; the registry order for subsequent verified activation is
`[deepseek, glm, grok, kimi]`. Inactive suppliers have `enabled=false` and
null endpoint/model bindings, not guessed defaults. T2 must support all four
provider adapters and reject activation without an explicit trusted endpoint,
model, pricing revision, credential reference and funding/eligibility receipt.
T4 records reviewed activation configuration when those inputs are available.
This inactive state is a complete initial configuration, not four-supplier
acceptance; T5/T6 remain blocked until their live supplier criteria pass.
Do not reuse Coding-plan/login secrets as general API credentials without
verifying the account route. Workflow references to `XAI_API_KEY` do not prove
that secret exists.

## Retry and cost admission

The owner authorized **USD 20 per month** in the 2026-09-10 conversation.
Use calendar months in `Asia/Shanghai` for the review ledger; unused allowance
does not roll over. This is the project's incremental metered API usage cap,
including consumption of prepaid balances, failed requests, retries, probes,
historical replay, shadow trials and cutover acceptance. Existing subscription
fees are separate. The first pilot additionally stops at USD 20 cumulative
spend if it spans months. No automatic recharge, subscription upgrade or new
purchase is configured by this authorization.

The lead sets a USD 1 per-PR attempt cap (including all provider retries),
further bounded by remaining pilot/monthly allowance and verified supplier
funds. The reported DeepSeek balance of approximately USD 10 is unverified;
never treat the reported amount as confirmed available funds. Requests still
require configured credentials, verified pricing and ledger admission.

The available GitHub repository secret names observed on 2026-09-10 are
`ZAI_CODING_KEY`, `KIMI_CODING_KEY`, `GROK_AUTH_JSON`, the runner read token,
and the newly confirmed `PR_AGENT_DEEPSEEK_API_KEY`. No secret values have
been read. Only DeepSeek has a configured dedicated credential reference;
its paid probes still require request-level admission. Coding-plan and general
API keys are not interchangeable without verified account-route eligibility.

LMDJ owns provider fallback. Set PR-Agent `fallback_models=[]` and client
`num_retries=0`; disable timeout retries. The pinned handler also has a bounded
two-attempt decorator that must be included in the call allowance and tested
at the actual dispatch boundary. Every HTTP request, including that retry,
requires its own ledger admission; wrapping only the outer engine invocation
is insufficient. Use a narrow handler admission seam without replacing the
stock provider/model integration. Disable client retries that multiply retries.
Authentication/invalid-parameter/unsupported-model errors advance or stop
without retrying the same request. Bound transient retries, backoff, provider
attempt count and total wall time. Deadline expiration terminates the process
and produces an explicit outcome, never an empty success.

Pilot execution limits are eight HTTP requests total per PR attempt, at most
two per provider, 60 seconds per HTTP request, at most five seconds backoff
between requests, and 600 seconds total engine wall time. Authentication,
invalid-parameter and unsupported-model failures receive no same-provider
retry. The pilot uses one complete prompt per provider; oversized input fails
closed. Chunked paid evaluation is deferred until its complete union and
cross-file quality oracle is explicitly added, without relaxing acceptance.
The owner excluded supplier-specific token counting from this development scope
on 2026-09-10. Remove the custom counter registry, tokenizer activation fields,
local rendered-message counting gate and former 100,000-input-token cap.
Do not introduce a replacement counter framework. Preserve complete rendered
messages and existing byte/file/hunk limits; never trim or split a prompt to
force success. A provider context rejection is an explicit failed attempt.
Requested output remains at most 4,096 tokens, enforced at each actual request.
The pinned stock startup tokenizer asset remains an upstream dependency only,
not evidence of supplier-specific counts or admission eligibility.

The durable ledger is operator-owned outside runner workspaces. Each append-only
record carries schema, approval ID, currency, attempt/request ID, effective
model, price revision, reserved amount, actual amount if known, and status
(reserved, reconciled, uncertain). Serialize admission with an exclusive lock;
lock failure or duplicate request admission denies the request. Before EVERY
physical HTTP request, including the one stock transient retry, reserve with
upward conservative monetary rounding:

`context_token_limit * peak_input_rate + output_token_cap * peak_output_rate + fixed_request_charge`

Rates are per token. The trusted context limit is a monetary upper bound on all
billable input units, including provider-added request overhead and any billed
context-rejected request; it is not a locally measured prompt size. Require
`0 < output_token_cap < context_token_limit`. Peak rates cover every enabled
billable input/output class. Reasoning, tools, search, priority and other charged
features must be disabled unless their charges fall within these same enforced
bounds. A zero fixed charge requires reviewed pricing evidence. Unknown or
unbounded charges, unverified funding, non-finite bounds, or a reservation above
remaining USD 1 attempt / USD 20 cumulative pilot / USD 20 Asia/Shanghai monthly
allowance deny admission. A context above 100,000 is eligible under this formula
without a supplier counter. Available balance subtracts reconciled spend plus
outstanding reservations. Never reset or clear the ledger when replacing a worker.

The trusted price revision binds context limit, output cap, rates, fixed charge
and enabled billable categories; any change requires a new reviewed revision.
Reconcile a successful response only from complete authoritative supplier usage
with the priced response-model identity, or an authoritative actual monetary
charge. Otherwise finalize exactly once as uncertain and retain the reservation.
A timeout is not refunded merely because no response was observed. Preserve a
known actual charge above the reservation rather than clamping its liability.
Output-usage, total-context-usage or known-charge envelope breaches fail the
review, suppress all remaining provider fallback in that attempt, and deny
future admission for the same `(provider, effective_model, price_revision)`
until operator review replaces/disposes that envelope. Reuse the append-only
ledger's finalized records for this durable hold; add only necessary internal
reservation-basis data, not a second ledger or public coverage schema. Record
estimates separately from supplier billing. Supplier counter certification is
not a T2 completion prerequisite; funding, live qualification and model selection
remain in their existing later Tasks without increased dollar caps.

Only finite error categories, HTTP status, safe request IDs and aggregate usage
leave the engine boundary; raw provider errors and keys do not enter artifacts.

## Subscription and API funding boundaries

Official documentation checked 2026-09-10 distinguishes these routes:

- Z.AI Coding Plan uses a dedicated endpoint within supported tools. Its
  allowance is not general API credit, and PR-Agent eligibility is not established.
  Keep that subscription route disabled for this integration; do not impersonate
  another tool. General Z.AI API funding must be checked independently.
- Kimi Code has subscription-backed coding endpoints and a console/`/usage`
  quota view, while Kimi Platform uses a separately funded route. The owner
  reported the weekly coding quota exhausted, so no Kimi request is admitted
  until reset and eligibility are verified. No Extra Usage auto-fallback.
- xAI API requests deduct API credits or accrue configured API invoice usage.
  Grok app subscription availability is not evidence of funded API access.
- ChatGPT/Codex subscription usage remains available for supervised development
  and review workers. It is not an OpenAI API key for PR-Agent; OpenAI is not
  silently added as a fifth live provider.
- DeepSeek API uses prepaid/granted balance. Configure and verify its dedicated
  key first; API fees count against this project's monthly cap even when they
  consume money previously topped up.

Sources: [Z.AI supported tools](https://docs.z.ai/devpack/tool/others),
[Kimi Code membership](https://www.kimi.com/code/docs/en/kimi-code/membership.html),
[xAI API billing](https://docs.x.ai/developers/faq/billing),
[OpenAI pricing modes](https://learn.chatgpt.com/docs/pricing), and
[DeepSeek API pricing](https://api-docs.deepseek.com/quick_start/pricing/).
For initial DeepSeek reservation, use observed peak cache-miss USD 1.32/M input
and USD 3.96/M output, without assuming off-peak or cache discounts. Refresh
pricing before admission and fail closed on unknown/changed pricing.

## Netcup capacity and availability

Start on one existing Netcup host with one review slot. A recent inventory says
16 cores and about 62 GiB RAM; an online/idle runner snapshot is not capacity
acceptance. The resource plan must account for every existing baseline and
elastic service before reserving review capacity. Initial review hard limits are
1 vCPU and 2 GiB in a sibling `lmdj-pr-review.slice`, with low CPU weight.
The documented heavy slice retains 14 vCPU/48 GiB; totals leave 1 core and
about 12 GiB for OS/cache/co-tenants, subject to fresh measurement. Preserve
existing elastic ceiling and heavy allocation; reject admission if the reserve
cannot be demonstrated. Do not widen product timeouts to accommodate review.

A dedicated slot should avoid queueing behind builds while preserving heavy
CI's existing allocation. T4 must prove the resulting controller configuration,
cgroup limits, launch identity, immutable environment and rollback. The
read-only audit found runner 04 carrying an elastic label despite its baseline
policy role; reconcile that observation before deployment. The documented SSH
alias is unavailable locally and Tailscale requests additional authentication;
operator access remains pending. Do not add a Docker daemon or Docker-group
privilege to bypass the existing host boundary.
No new server, GPU, public webhook, database or Kubernetes is in this scope.

Two workers on one host improve throughput but do not survive host failure.
An in-flight failed job requires explicit retry/reconciliation and idempotent
publication. A second independent host is deferred until observed availability
or queue requirements justify it. A second provider API is not host redundancy,
and a second host does not repair a bad API credential.

Pilot recovery target: restore the isolated review process within 30 minutes
of an observed process failure, while retaining its interrupted attempt. This
is a measured acceptance target, not a host-repair SLA. A host outage remains
an explicit availability limitation; do not claim redundancy from process
restart. Record detection, reconciliation and recovery timestamps separately.
After two completed cohorts with p95 queue above five minutes, investigate
queue attribution before proposing higher concurrency; any expansion requires
new measured capacity and budget. A second host is a separately authorized
follow-up if host downtime prevents the agreed availability objective.

GitHub-hosted minutes are not consumed by self-hosted execution. API wait time
still occupies a local runner slot. Artifacts/cache storage and model charges
remain separate costs. There is no automatic paid hosted fallback.

## Acceptance protocol (freeze before first evaluation)

Evaluate against one fixed engine/config revision. After a material change,
start a new cohort and retain the failed cohort rather than replacing it.

- Offline safety cases must all pass: untrusted configuration, path escape,
  base/head mismatch, deleted and oversized input, missing coverage, invalid
  output, swallowed exception, bounded retry, budget exhaustion, credential
  redaction, stale head, forged provenance and duplicate publication.
- Model quality set: at least six independently annotated known-defect changes
  covering correctness, security, concurrency, deletion, cross-file and policy
  failures, plus six independently checked clean controls. Freeze exact input
  hashes and an oracle before running. Require every designated blocking defect
  to be identified and no invented blocking finding on a clean control.
- Historical replay includes #1127 head
  `91f28ee2039a95d7c6c91e5943668e91c0e6cc14` and #1132 head
  `85c129208f858bb1a8c3efc6100e8bd5f9cd8403`; it is labeled historical and never
  passed off as current-head publication evidence.
- Shadow reliability cohort: 20 admitted real current-head PR attempts across
  at least five distinct heads, retaining repeated-head correlation and actual
  load conditions. At least 19/20 must produce complete valid reviews within
  10 minutes of execution start. Report queue separately; p95 queue must be at
  most 5 minutes. These are pilot acceptance thresholds, not a service SLA.
- Retain every admitted attempt in the ledger. Report cancellations and stale
  heads separately; they do not count as successful reviews. Use replacement
  samples only for a separately disclosed eligibility cohort, never erase the
  initial denominator. Insufficient eligible heads/budget is an acceptance gap.
- Prove successful API operation for each of the four configured suppliers;
  live fallback recovery and deterministic failure injection are separate
  evidence. Do not claim one supplier is healthy because another succeeds.
- Resource peak must remain inside the reserved limits; document co-running
  heavy work and any contention, without manufacturing unrelated production
  load or stopping another user's job.
- Cutover acceptance must read back current-head review, scope and merged-map
  identity, a real fallback, no duplicate write after replay, explicit all-failed
  state, stale-head refusal, and controlled rollback followed by restoration.
  Keep synthetic negative-path evidence distinct from real API/publication runs.

The lead independently examines finding disposition and full journey evidence.
Subagent completion messages are handoffs for verification, not acceptance.

## Rollback and operations

T6 prepares a specific routing/revert change before enabling the new engine.
The old invocation is already unreliable: restoring that configuration proves
rollback mechanics, not recovered model health. Keep a visible current-head
human/agent takeover path when no backend works. Reconcile an uncertain write
against its exact receipt before retrying publication.

Operations ownership includes secret rotation, approved spend ledger, quota
alerts, version/image updates, failed-attempt recovery, coverage limits and
capacity review. Do not auto-close #939 or other historical tracking issues
without independently satisfying their acceptance scope.

## Version Management

Version impact: none — CI tooling and operation only; no Product, Module,
Host, Provider or Contract manifest changes. No Product Build/snapshot/release.
The engine source, dependency lock and image are separately recorded tool IDs.

## Documentation Impact

Documentation impact: none
Reason: this design describes a proposed migration and does not change current
Portal behavior or deployed review operation. Run the declared docs-site check.
T4/T6 must update `/operations/testing-and-proof/` in
`apps/docs-site/docs/operations/testing-and-proof.mdx` when their documented
operation becomes current; update its source paths in the same Task.

## Sources

- [Pinned PR-Agent source](https://github.com/The-PR-Agent/pr-agent/tree/53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c)
- [Plain-diff provider](https://github.com/The-PR-Agent/pr-agent/blob/53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c/pr_agent/git_providers/plain_diff_provider.py)
- [Configuration loader](https://github.com/The-PR-Agent/pr-agent/blob/53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c/pr_agent/config_loader.py)
- [Diff processing](https://github.com/The-PR-Agent/pr-agent/blob/53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c/pr_agent/algo/pr_processing.py)
- [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
  retrieved 2026-09-10: “GitHub Actions usage is free for self-hosted runners”.
