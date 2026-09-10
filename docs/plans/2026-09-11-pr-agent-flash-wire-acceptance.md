# PR-Agent Flash Wire and Reasoning Usage Acceptance

## Scope and boundary

This plan is the T4 first-paid-admission acceptance for the pinned PR-Agent
path. It proves the actual pinned `PRReviewer` through the stock
`LiteLLMAIHandler`, the adapter's per-request admission, LiteLLM's real
serialization, an in-process fake HTTP transport, response parsing, and the
durable ledger. It does not prove live model quality, native-funds admission,
four-provider acceptance, the v14 Linux bundle, deployment, or operational
activation.

The exact source prerequisite is `/tmp/lmdj-pr-agent-plan/flash-wire-bound-
review.md`, including its supporting-only scratch probe
`/tmp/lmdj-pr-agent-plan/flash-wire-probe.py`. The inspected pins are
PR-Agent `0.45.0` at commit
`53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c`, LiteLLM `1.100.0`, and the
required Python 3.12 test runtime. The scratch probe is not this acceptance:
the repository tests must retain the real handler, real `acompletion` call,
admission and ledger journey.

No credentials, supplier/model/balance calls, SSH/root operations, GitHub
mutations, dependency or bundle changes, production fake hooks, workflow
changes, or live network calls are allowed. Network denial is installed at
transport/socket/DNS boundaries before third-party runtime import; dotenv and
remote cost fetching are disabled. Both pinned `httpx` and LiteLLM aiohttp
transport paths are covered by the fake transport.

## Locked behavior

Use a synthetic protected runtime configuration selecting provider `deepseek`,
requested model `deepseek/deepseek-flash`, endpoint
`https://api.deepseek.com`, served/priced response model `deepseek-flash`, and
fixed test pricing. This configuration is test-only and does not activate the
default config. Preserve the documented default thinking behavior by omitting
both `thinking` and `reasoning_effort`.

The captured POST must be exactly bound to the intended endpoint and model and
must contain `max_tokens: 4096`, with no `max_completion_tokens`, tools,
search, service tier, thinking, or reasoning-effort field. The request timeout
is bounded by the configured timeout and total engine deadline. There are no
hidden HTTP/client retries; physical DeepSeek requests are at most two, and
the durable reservation count equals the physical request count.

Synthetic complete response usage with `completion_tokens=4096`,
`reasoning_tokens=4000`, `prompt_tokens=100`, and `total_tokens=4196` prices
the full 4096 completion tokens once. It must never price only 96 visible
answer tokens or add reasoning a second time. The complete immutable input and
all response/model/coverage identities remain bound to the result.

The far-side journey covers normal native review, a length stop with
reasoning-only/empty output (never fabricated clean output), missing or
invalid totals, contradictory or unsupported reasoning breakdowns, output
4097, context breaches, a transport timeout with exactly one physical call and
an uncertain reservation, a transient/rate-limit failure followed by the one
supported retry, permanent errors, and no response-body or key leakage. Unknown
cost retains the full reservation. Envelope breaches block further
acceptance/admission. Existing real-handler, ordinary, ledger, coverage, and
negative assertions remain in force.

## Bounded source correction

First add a red test proving the current `_usage_from_response` incorrectly
accepts a contradictory nonnegative integer `reasoning_tokens` greater than
`completion_tokens` as priceable. If confirmed, minimally validate the
optional reasoning breakdown in `_usage_from_response`: it must be a strict,
nonboolean, nonnegative integer no greater than `completion_tokens`; malformed,
negative, or over-total values return invalid usage and leave the existing
uncertain full reservation. Absent reasoning details remain accepted when
aggregate totals are valid. Support mapping-shaped usage and real LiteLLM
typed usage objects. Do not add provider-specific charges or migrate the
ledger/schema; if another nonzero billing category appears at this seam, stop
and request lead policy.

## Implementation tasks and owned files

1. Create this plan with the substantive contract, including the required
   version and documentation declarations, before source/test edits.
2. In `tests/build/ci_pr_agent_review_test.py`, add the red contradictory-usage
   case, then the minimal actual-handler/fake-transport journey and far-side
   assertions. Tests must use the existing enabled integration child/clean
   preparation and the pinned runtime; they must not stub `acompletion` for
   wire serialization or add a skip flag.
3. Only if the red case proves the defect, make the minimal optional reasoning
   validation change in `scripts/ci/pr_agent_review.py`.

No other files are owned. A source change changes adapter bytes and therefore
requires a new verified Linux bundle before operational activation; this
macOS proof must not mutate or relabel v14 or claim to accept it.

## Verification and receipt

Run the red contradictory-usage test first and record the expected failure,
then run focused ordinary tests under `python3 -S`. Run
`ci_change_scope_test.py`, and run the clean shared
`scripts/ci/pr-agent/integration-test.sh` using installed pinned Python 3.12
under both `0022` and `0002`. All 27 existing actual-handler methods plus new
methods must execute with zero integration skips. Run the docs-site check for
the new plan. Use unique scratch logs; do not overwrite prior reports.

The implementation report must identify exact source/adapter/config/lock/
runtime identities, wire endpoint/model/cap/forbidden fields and request
count, response usage and charge, reservation/ledger identities and statuses,
retry/error/breach counts, network-block receipt, test method list, and all
remaining limits. A green test is not live supplier, model quality, funding,
four-provider, bundle, release, deployment, or channel evidence.

## Version Management

Version impact: none — internal CI adapter validation/tests; no Product,
Module, Provider, or Contract version changes.

## Documentation Impact

Documentation impact: none

Reason: this is a source prerequisite and test plan; it does not change
installed Portal behavior or documented source facts.

## Lead correction: raw billable usage guard

The bounded correction above is superseded for this Task by the raw-wire
usage guard in `/tmp/lmdj-pr-agent-plan/flash-raw-usage-guard-addendum.md`.
Before normalized LiteLLM response accounting, the adapter observes exactly
one successful raw response for the current admitted physical request through
the pinned `DeepSeekChatConfig` transformation seam and delegates to the stock
transform. The observation is request-scoped, reset for every physical
request, isolated through the existing request context, and restored on every
exit; installation or cleanup failure is fail-closed. It persists only
validated finite accounting evidence and never the raw body, headers, key,
reasoning text, or exception text.

Raw `prompt_tokens` and `completion_tokens` must both be explicitly present
strict nonnegative integers (never bool, string, or null). A supplied
`total_tokens` must equal their sum; an omitted total may be derived under the
existing policy. Optional `reasoning_tokens` must be strict and no greater than
`completion_tokens`; normalized priced counts must agree with raw counts. A
missing, invalid, contradictory, stale, duplicate, or otherwise unusable raw
observation makes the result `not-reviewed` with `invalid_output`, retains the
full reservation as `uncertain`, performs no refund, and cannot consume a
same-provider retry. Non-2xx transient behavior, timeout/cancellation, the
single bounded retry, valid reasoning-inclusive responses, empty length stops,
envelope breaches, permanent errors, and the stock PR-Agent/LiteLLM path remain
unchanged.

The restored real HTTP matrix covers absent `usage`, absent each billable
count, null/bool/string counts, contradictory totals, and cross-request stale
observation/cleanup. Every red case asserts one physical request, no retry,
`not-reviewed`, reserved then uncertain ledger records, unchanged held amount,
and no refund; valid and existing error journeys retain far-side ledger
assertions. Actual HTTP tests mock only transport; no production test-mode or
fixture acceptance branch is permitted.

## Lead correction: known breach survives invalid accounting

Independent review rejected candidate `4bcc04351be47ad60d7a8bb80234a5e7172eda9e`:
invalid optional reasoning, normalized usage disagreement, or stock parser
failure can discard an independently known raw output-envelope breach. A valid
strict raw count that proves an output or context breach remains evidence of
that breach even when other fields make the charge unknowable. Never accept
invalid counts as money, invent a price, or release the uncertain reservation.
Persist the known breach through every reconciliation and exception exit, stop
same-provider retries and fallback, and preserve the existing durable block on
future admissions. This uses the existing breach hold and monetary schema.

The correction must reproduce actual fake-HTTP combined cases before changing
source: 4097 completion tokens with contradictory reasoning; valid over-cap
raw counts with omitted total and normalized disagreement; and valid over-cap
raw counts followed by stock parser failure. Each fixed journey must make one
physical request, retain uncertain full liability, persist the breach, and
reject a later real reservation without appending it. Include context breaches
and retain all valid, invalid-usage-only, timeout, transient, cancellation,
coverage, and cleanup journeys. Correct the non-DeepSeek regression so its
successful request has no artificial DeepSeek raw observation. The independent
real-HTTP GLM fallback probe is supporting evidence, not live acceptance.

Verification remains both full shared umask integration runs, all old and new
actual-handler methods without skips, ordinary `-S`, ownership and Portal
checks. Amend only the unpublished three-file Task after verification; require
a fresh exact-head independent review and newly verified Linux bundle before
operational admission. No tariff, funding, credential, host or quality boundary
is discharged by this source correction.
