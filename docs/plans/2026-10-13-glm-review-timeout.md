# GLM review timeout: speed-tier correction

## Premises at current main

Integration base: `25b8875478396df39ff0882c223c4c11bdf98806`.

- Outstanding: GLM fallback on PR #2083 (run 38261680621, attempt 4)
  and PR #2109 (run 38323591263) exhausted the whole-response 60-second
  request bound (60241 / 60224 ms), with no response usage. This repeats the
  large-input residual recorded after #1912; neither PR's owner takeover
  repairs provider latency.
- Already delivered: the installed adapter/config match main. The low
  reasoning effort and domestic pay-as-you-go endpoint are correct. A probe
  through the pinned PRReviewer, LiteLLM handler and mocked HTTP transport
  confirmed `reasoning_effort: low` reaches BigModel's request JSON. An
  unauthenticated host probe returned HTTP 401 in 205 ms; this rules out a
  persistent connection failure during that probe, not inference latency.
- Uncertain: historical non-streaming failures contain no first-token or
  provider-side timing, so prefill, queueing and generation cannot be separated.
  The #2083 complete prompt is about 4 MB; its offline token estimate is not
  provider usage. No claim of a context-limit breach is established.

## Task and declared files

Use the same-family speed-optimized `glm-5.3-flashx` service for the GLM
fallback. Keep the complete single prompt, provider order, 60-second request
bound, 600-second engine deadline, 4096 output cap and existing dollar/count
budgets. Preserve the ledger and prior failures. This is a latency mitigation
to be accepted by production observation, not proof of which upstream stage
was slow.

Official evidence read on 2026-10-13:

- https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash:
  FlashX is the speed tier, advertises up to 200 tokens/s, retains 1M context
  and the same text parameters. It is available through the standard API;
  Coding Plan does not include it.
- https://docs.bigmodel.cn/cn/guide/start/pricing.md:
  standard cache-miss input CNY 2 / million tokens; output CNY 7 / million.
  Convert at the existing conservative CNY 7 / USD, rounding input upward.
  Two maximum DeepSeek reservations plus one FlashX reservation remain below
  the unchanged USD 1 per-attempt cap (about USD 0.944). The new price/model
  identity opens a separate pricing envelope without resetting global spend.

Declared files:

- `scripts/ci/pr-agent/runtime.toml`
- `tests/build/ci_pr_agent_review_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- this plan

## Verification and installation

Run the full adapter policy and pinned real-handler integration suite. The
new wire regression must exercise two failed primary requests followed by
FlashX, check the actual URL/model/low-effort/output cap, complete input,
served-model identity, usage settlement and surviving uncertain reservations.
Run change-scope preflight and portal check. Obtain independent current-head
review and guarded merge.

After merge, use the existing supported installer under its slot lock, verify
the witness and unchanged ledger, then exercise a controlled GLM fallback.
Retain raw run evidence; a small-PR success does not discharge large-input
latency acceptance. Closed PRs cannot be dispatched for review by the trusted
target resolver. Use an open, temporary, unmerged canary with #2083's 14 changed
code files and harmless comment-only edits to exercise complete current base
and head bytes of comparable size; retain the actual collected size/usage.
It establishes large-input service acceptance, not an exact historical replay.
If large-input acceptance fails,
retain the failure and roll back the model/config via the supported installer;
do not expand the deadline or claim the incident fixed.

## Version Management

Version impact: none
Reason: review-host routing and its tests/docs change; no product, Core,
Provider implementation or Contract version changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: document the active GLM model, standard pricing and installation boundary.

## Pitfall Impact

Pitfall impact: none — reason: this provider latency/configuration correction
is derivable from request configuration and finite runtime evidence.
