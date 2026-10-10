# Business-result reconciliation for uncertain report POST claims

Relates to #1048 (kept open for remote acceptance). Source Task: define the
explicitly authorized business-result reconciliation procedure the Issue names
as the remaining gap; the drain itself is a separately authorized operation.

## Premise dispositions at base 785d36db27dc44fde7cceb4f6cb6da0956a795e1

- Independent report admission: **delivered** by PR #1052 (merge `69b41bb`),
  with real scheduled deliveries audited in Issue comments (generations
  504–511). Not repeated here.
- Journal-level stranded pending drain: **delivered** by PR #1455
  (`reconcile-pending`) and reused for the outbox role via `journal_config`;
  the current outbox pending `f70f050d…` is operational, not code. Not
  repeated here.
- Business-claim reconciliation: **still outstanding**. Outbox delivery
  `302f7663…` (claim generation 879, `create-issue`, unknown POST outcome)
  fail-closes `Outbox.recover()` with `needs-reconciliation` on every tick,
  so no queued observation is delivered (live read-only check 2026-10-10:
  #817 at 1,144 comments, queue events accumulating, none delivered since).
  Only journal-level `reconcile_pending` exists (`batch_runtime.py:421`,
  `incremental_batch_journal.py:256`); no claim-level path exists in
  `report_outbox.py`/`report_runtime.py`. No successor PR delivers one
  (merged-PR search for reconcile-claim work: none).

Recheck before commit: base moved to `9b4d80c9e5ed965f5776c0321cf166d9d1f289ce`
(PR #1936, creator-web encoders). Its diff touches no CI/report/outbox/workflow
file and no page this Task edits; every disposition above stands unchanged.
- The Issue states the requirement: "a canonical positive receipt or an
  explicitly defined business-result reconciliation procedure; an empty
  search does not authorize another POST."

## Declared files

- `scripts/ci/report_outbox.py`
- `scripts/ci/report_runtime.py`
- `.github/workflows/self-test-report.yml`
- `tests/build/ci_report_outbox_test.py`
- `tests/build/ci_report_runtime_test.py`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/plans/2026-10-10-lmdj-report-claim-reconciliation.md`
- `.agents/pitfalls/business-claim-outcome-unknown-blocks-reporting.md`

## Behavior

Add one closed manual report operation `report-reconcile-claim` (workflow
choice) → `reconcile-claim` (report_runtime subcommand with `--request`
closed JSON file) → `Outbox.reconcile_claim(api, command)`. It resolves one
audited uncertain business claim and nothing else: it never emits `execute`,
never plans reports, never initializes storage, and never replays a business
POST inside the operation.

Closed command schema: `{"delivery": "<64-hex>", "claim_digest": "<64-hex>",
"resolution": {"kind": "absent"}}` or `{"resolution": {"kind": "receipt",
"issue_number": N, "comment_id": C|null}}`. Guards, all fail-closed with
`why`/`remedy`:

- the delivery exists and its claim digest matches exactly (exact-digest
  binding, mirroring `reconcile_pending`);
- `absent` requires status `claimed` (an acknowledged write contradicts
  absence) plus a complete authenticated absence proof: the existing
  `_receipt()` full-inventory scan must find no canonical receipt. Effect:
  one new reducer event `claim-cleared` (`{delivery, claim_digest, why}`)
  returns the delivery to `queued`; the next ordinary tick re-derives the
  byte-identical claim and POST from the frozen payload — never a blind
  replay, and reducer validation is unchanged;
- `receipt` requires status `claimed`/`acknowledged` and the operator-named
  exact receipt to equal the live `_receipt()` verification (unique trusted
  bucket, exact frozen body, trusted bot author, managed marker, unedited);
  only then is the normal `delivered` event persisted through the existing
  reducer checks. `refused` stays terminal and untouched.

New controller jobs/paths keep the existing writer trust: same short writer
lock, same authenticated runtime, same Issue storage; no authentication check
is removed. Reporting failure stays visible on its own run; no product batch,
suite selection, budget, debt or Issue closure semantics change.

## Verification

Failing tests first, then implementation:

- `ci_report_outbox_test.py`: reducer admits a well-formed `claim-cleared`
  and rejects wrong digest/status/extra keys/unknown types; `reconcile_claim`
  rejects non-closed commands, wrong digest, `absent` while a receipt is
  visible, `absent` on acknowledged, receipt mismatching the live read, and
  receipt on an edited/wrong-author/wrong-marker bucket; cleared delivery is
  re-claimed byte-identically and delivered once by the ordinary path;
  receipt-bound delivery persists exactly one `delivered` event.
- `ci_report_runtime_test.py`: operation admitted through `execute`, closed
  schema enforced, error/exit-code mapping, and no POST inside the operation.
- `ci_batch_runtime_workflow_test.py`: the new choice is wired to the
  outbox step, `batch_request` is required for it and rejected for every
  other report operation, and scheduler/report input mixing still fails.

Then: the four focused suites, complete `ci_*_test.py` discovery, staged
ownership gate, pinned actionlint plus ShellCheck (workflow changed), Portal
check (`/operations/testing-and-proof` updated), version verification (no
allocation). Ship through normal PR/exact-head review/squash merge; Issue
1048 stays open for its remote acceptance legs.

## Version Management

Version impact: none
Reason: reporting control plane only; no Product, Host, Module, Contract,
Assembly, tag, allocation or snapshot identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: a new closed manual recovery operation and its audit preconditions
must be documented where the report pipeline is described.
