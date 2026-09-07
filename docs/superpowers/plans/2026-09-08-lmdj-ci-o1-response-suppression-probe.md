# O1 controlled response-suppression probe — implementation draft

Status: isolated delivery of the reviewed implementation at
`0e0c79f76ad37dfba5345fce799e4c24fa3261cd`, based on main
`0fedd7268e5f0f9a27390c3d8085387083f46e86`. The original design and evidence
below are retained together; historical pending boundaries do not describe the
current progress of separately owned reservation or configuration Tasks. The
new delivery head requires independent review; implementation and test bytes
are unchanged from that reviewed source.
Remote reservation, initialization and each dispatch remain later separate
boundaries. No workflow wiring or remote mutation is delivered by this Task.

## Original documentation Task

Declared file: this plan only. Work on an isolated `docs/` branch. Lowest-tier
verification is committed-range docs-static/whitespace and staged ownership;
record any attempted Portal check honestly, not as remote probe acceptance.

Precommit verification for this document: staged ownership passed 66 tests and
staged whitespace passed. `scripts/architecture-portal.sh check` was run and
exited 1 in its initial Node test stage: 57 tests, 54 passed, 3 failed, no skips.
No later Portal validation/build or Portal pass is claimed. This design-only
Task does not install dependencies or alter Portal sources to change that result.
This documentation commit is retained as its own Task; later implementation may
update this plan in its own declared commit, not amend this documentation Task.

## Single implementation Task and ownership

- `scripts/ci/o1_recovery_probe.py` — narrow composition and response-suppression
  API adapter; no changes to scheduler/outbox reducers or event schemas.
- `tests/build/ci_o1_recovery_probe_test.py` — real existing modules and strict
  HTTP-boundary fault journeys with complete far-side assertions.
- This plan — implementation outcomes and remaining platform gaps.

Workflow wiring is a later, independently reviewed Task owned by root:
`.github/workflows/self-test-report.yml` and its dedicated workflow contracts.
Do not combine automatic-trigger cutover, claim/executor faults or cancellation.

## Authority and isolation

Both probes use existing Runtime authentication and injected API interfaces,
the existing `Incremental batch controller` job, trusted exact main control,
fresh Actions attempt 1, the same short `self-test-report` lock and existing
contents:read/actions:read/issues:write permissions. No Actions write or PR
permission is added. No command emits GITHUB_OUTPUT execute/request/executor.

Root first reserves and explicitly initializes NEW isolated recovery storage
Issues/epochs: one scheduler-format journal and a separate outbox-format journal.
Read-only snapshots establish fixed Issue/node/bot/workflow identities and exact
empty authenticated checkpoints. No IDs are guessed here. The implementation
must reject #807 and #817 as storage targets, and reject production configuration
or an epoch not explicitly selected for this rehearsal. Never replay outbox
events through the scheduler reducer or alter existing comments/checkpoints.

The B business bucket is also isolated: root selected a probe-only namespace,
not the existing backend-outage bucket #819. `review_failure_report.collect`
must first authenticate an ACTUAL completed all-backend-failed review. Preserve
its original observation, source facts and failure classification; use a visibly
diagnostic O1 title/body and namespaced key `o1-recovery/<outbox-epoch>/<original-key>`.
The diagnostic wrapper explicitly says this is an O1 recovery observation of a
real source failure, not another product defect. Freeze namespace, title, full
body, labels/assignee and original source observation before any business write.

Use a complete paginated all-state Issue inventory to verify that this fresh
epoch has no previous matching diagnostic bucket. An incomplete/error inventory
is not absence. Existing outbox history or a bucket in this namespace stops the
injecting command; ordinary recovery, not a second injection, handles it.
The business Issue number cannot be fixed before its create-issue POST; record
its independently observed actual identity after the injected failure. Root has
approved this design choice, not implementation or a dispatch in this Task.

## Closed command and default-disabled behavior

Proposed CLI: `o1_recovery_probe.py --config CONFIG --request REQUEST --summary SUMMARY`.
No arbitrary endpoint, method, payload, shell command, target path or fault count.
No output file usable as a scheduler execute action.

The final prepared request is a closed discriminated object with:

- `schema`: `lmdj.o1-response-probe.v1`;
- `operation`: `journal-append-response` or `outbox-business-response`;
- `fault`: `disabled` (default/no mutation) or `after-successful-post`;
- `controller`: exact `run_id`, `attempt: 1`, `control_sha`, checked against
  authenticated live context, not trusted because the caller supplied them;
- `expected`: the operation-specific closed expectation below.

Configuration uses the existing closed scheduler/outbox pair of six-field
Runtime configs, both NEW recovery storage identities. A writes only scheduler;
B writes only outbox and its diagnostic business bucket. Do not introduce a generic workflow or
bot allowlist under operator input. Those still come from existing trusted code.

A expected fields: exact journal epoch, generation 0, `observe` event ID,
main target SHA, null checkpoint head/pending, and expected complete event/envelope
digest. B expected fields: outbox epoch, exact real review run/attempt, original
observation identity and policy/source binding, namespaced delivery ID, and
frozen Report/POST payload digest. Each digest is a consistency check, never
writer authentication. Validate all identity and full-body equality separately.

### Same-controller read-only prepare; never guess a future run identity

A dispatch caller cannot know its future Actions run ID, and therefore cannot
precompute an envelope digest containing that writer identity. Operator input
is only a closed intent: selected A/B operation, explicit fault opt-in, reserved
storage configuration, and (for B) the exact existing review run/attempt. It
does NOT supply or guess the future controller ID or event/POST digest.

Within the same already-started trusted controller job, a read-only prepare
phase first validates actual GitHub context against exact-attempt API metadata,
current main and the newly initialized empty authenticated journal(s). It then
derives controller run/attempt/control identity and complete A event/envelope
or B diagnostic Report/POST bytes from existing trusted runtime/protocol code.
The phase constructs the closed prepared request above and its exact expected
digests. No arbitrary endpoint/body is accepted as authority from operator input.
It uses strict read-only checkpoint access: Journal.load must not repair a
pending anchor during prepare; any pending/nonempty state refuses injection.

Only after prepare completes and the resulting closed request is independently
validated may the execution phase perform its first write. Preparation and
execution retain the same short writer lock and process/run identity. A fresh
API/main/storage recheck before the first write must still match the prepared
snapshot; drift stops rather than silently preparing another target after writes
have begun. Do not initialize storage, append an event, create a business Issue
or repair an anchor to make preparation succeed. Reserved storage initialization
is an earlier separately authorized operation, never implicit in this probe.

The later workflow may supply github context fields to this prepare interface,
but those fields are claims independently checked against the API, not proof.
Disabled mode takes precedence before either writing phase and performs ZERO
remote writes for the entire invocation, including no checkpoint repair.

Reviewed implementation refinement: the same newly reserved pair can support
A → fresh ordinary settlement → B → fresh ordinary drain. A requires both
journals empty. B still requires its outbox empty, but permits authenticated,
strictly read-only scheduler history consisting ONLY of valid observe events.
It reuses historical-policy replay and requires processed/active both null.
Pending anchors, non-observe events (including request/admit/claim/result/
advance/resume), unknown history and repair attempts refuse B. The full decoded
scheduler checkpoint/event snapshot is part of prepare-to-execute equality;
the shared-pair journey also asserts unchanged complete scheduler Issue/comment
bytes across B and its ordinary drain. This narrow refinement was explicitly
reviewed to avoid reserving extra storage Issues; it does not allow B to settle
or mutate the scheduler.

Unknown/missing/duplicate keys, wrong operation/fault pairing, non-first attempts,
stale expected main or epoch, wrong body, unexpected POST and nonempty injection
history fail closed with why/remedy. In disabled mode return an explicit disabled
summary with ZERO remote writes. No missing flag silently enables a probe.

## A: actual journal append, response suppressed before caller receives it

1. Authenticate the fresh reserved journal and current controller. Confirm empty
   history/checkpoint against the closed expected snapshot.
2. Invoke existing `Runtime.reconcile(execute=False)` only. Its initial observe
   is the sole permitted event; it cannot admit or claim heavy execution.
3. The API adapter checks actual main reads against the expected exact target;
   drift fails before creating an append intent. It permits normal reads and
   the existing journal intent checkpoint write, but only the exact expected
   event-comment POST can arm this one-shot fault.
4. Call the real underlying API exactly once. Only after successful HTTP return
   with a well-formed comment ID, exact returned body and expected bot identity,
   terminate this probe process before returning the response to Journal.
5. The failed run has no execution output. Independent reads must find exactly
   one authenticated comment and a matching pending anchor, not assume creation
   merely because the probe announced an intention.
6. A NEW ordinary first-attempt settlement-only dispatch, WITHOUT the injecting
   adapter, calls existing Journal.load. It must authenticate that exact comment,
   repair the checkpoint to its digest and clear pending, with no second POST
   for the suppressed event. A further ordinary replay remains idempotent.

Expected far side: original event exists once; source run/attempt/body/digest
match; checkpoint pending clears only after positive receipt; no admit/claim,
processed stays null and no tested baseline or heavy run is invented. Main may
advance before recovery and ordinary reconcile may add a separate valid observe;
compare original event uniqueness and legitimate later observations, not a false
claim that the entire journal must remain byte-identical despite changed main.

## B: actual diagnostic Issue POST, response suppressed before Outbox ack

1. Authenticate current controller and the new outbox storage. Collect the real
   review failure and freeze the diagnostic Report described above. Verify full
   namespaced-bucket inventory and initial outbox emptiness before sending.
2. Use existing `Outbox.deliver` and `apply_report`. Queue and claim events must
   be durable with the exact frozen business POST before it can be issued.
   The wrapper must not inject on these journal/anchor writes.
3. Only the expected repository create-issue endpoint, matching complete frozen
   title/body/labels/assignee, may trigger. Call the real API once; after a
   successful well-formed Issue response with exact body, positive IDs and bot
   identity, terminate before the response reaches Outbox's ack logic.
4. Independently reread: one namespaced diagnostic Issue with exact body and
   original real source observation; outbox contains queue and claim but no ack
   or delivered. Save complete before-recovery identities and bytes.
5. NEW ordinary `report-drain`, without injection, must positively find that
   unique receipt, validate full body/identity and durably append delivered.
   An ack event need not be fabricated retroactively: existing recovery may
   transition directly from claimed to delivered after receipt authentication.
6. Another ordinary drain/replay produces no second Issue/comment/business POST.
   Compare all-state matching bucket inventory, Issue body/comments, and durable
   outbox delivery ID/receipt. Do not rely on a successful workflow alone.

Expected far side: exactly one diagnostic business receipt and a recoverable
durable claim, then independently authenticated delivered receipt, with no
second business POST and no modification of #819/#807/#817 or product history.

## Error semantics and one-shot fencing

This is **controlled response suppression after a real remote write**, NOT a
claim that GitHub spontaneously lost a response. No API response is fabricated.
An original HTTP refusal, transport timeout, malformed response or authentication
failure must retain its normal error semantics and must NOT be replaced by the
injected-success exit or reported as a completed injected leg. Do not catch the
original exception merely to claim that the expected remote write happened.

After successful-response suppression the wrapper terminates the process; it
must not return an invented status to encourage the existing caller to retry.
Before executing a matching POST, verify the exact durable phase/identity and
refuse reused injector invocations whose storage is no longer empty. The adapter
has a local single-shot fence too, but that is not the cross-process proof: fresh
storage admission plus authenticated durable intent and ordinary recovery are.

A real unknown write can occur BEFORE the synthetic boundary is reached. Its
pending/claimed state remains unresolved until positive receipt verification.
Absent lists, 404, temporary invisibility or claim-before-send death never grant
another POST. If the receipt cannot be found, report needs-reconciliation with
exact identity and remedy and STOP; permanent waiting is not successful recovery.
No history edits, forced resets, fabricated ack, claim expiry or deletion cleanup.

## Implementation verification journeys

Lowest tier reaches the actual API boundary with strict endpoint/method/body
fixtures, existing Runtime/Journal/Outbox/consumer modules and real Git fixtures:

- Disabled/default/invalid commands: no write; wrong source/epoch/target rejects.
- Actual current run unavailable before dispatch: read-only prepare derives it
  from authenticated context/API and computes the exact expected payload; no
  operator-guessed identity is needed. Pending anchor, main drift and a changed
  prepare-to-execute snapshot reject before the first write. Assert zero writes
  across prepare and disabled mode, not just absence of the targeted POST.
- Real-shaped successful POST: persist server object, suppress caller response,
  fresh unwrapped driver finds exact receipt and commits recovery; duplicate
  ordinary delivery does not POST again.
- Original 4xx/5xx/transport failure/invalid success document is not counted as
  injected success and is never hidden by the probe exit.
- Unrelated endpoint/body/delivery/generation cannot arm the fault; no heavy
  action outputs exist even if an injecting process fails unexpectedly.
- Positive-response body or author mismatch is unresolved, not fabricated
  successful recovery; missing/404 then later exact visibility exercises both
  the honest waiting boundary and the positive receipt transition.
- Namespaced diagnostic Report retains actual review observation and does not
  match the production outage bucket. Complete pagination/error cases cannot
  be treated as a clean initial namespace.

Local tests do not satisfy the remote journey. The later wiring Task must verify
the existing job/permissions/short lock, explicit closed inputs and no executor
bridge. Record actual remote run/attempt/control, complete jobs, reserved storage
snapshots, exact receipt IDs and full-body comparisons at each transition.

## Explicit non-goals and stop conditions

C (durable execution claim before output), cancellation, timeouts of real heavy
tests and claim-before-business-POST death remain separate future Tasks. This
plan grants no cancel authority and neither pauses nor cancels the current batch.
No automation that dispatches or writes Actions state is added. No host repair,
release, permission expansion, automatic-trigger cutover or production Issue
mutation belongs here. Ambiguous scope/identity or unexpected pre-existing state
stops the rehearsal; root decides whether to reserve a fresh isolated epoch.

## Version Management

Version impact: none — internal diagnostic probes, not product identity.

## Documentation Impact

Documentation impact: none — internal CI adapter and plan, no Portal pages or
projected product facts changed.

Pitfall impact: none — preserves existing unknown-write and fixture-strictness
guidance; no new platform incident or completed remote fault injection is claimed.

## Local implementation evidence and remaining boundaries

The implementation retains the separate design commit and changes only the
three declared files. `Probe.prepare` derives current authenticated run identity
and exact expected wire sequence inside the running controller; `Probe.execute`
re-prepares read-only and requires whole-document equality before any write.
The default absent fault flag produces a disabled summary and zero API calls.
CLI accepts `--config`, `--request` (closed operator intent), `--root`, and
`--summary`; it has no execute/output bridge. Successful controlled suppression
exits 86 with an explicit diagnostic; ordinary errors exit 1 without credential
text and without claiming injection. This is not a GitHub-generated outage.

`SuppressingApi` permits the exact existing checkpoint/event sequence and one
expected final POST. For a definite business 4xx refusal it also permits only
the existing exact Outbox refused-event sequence, retaining original error
semantics rather than fabricating controlled success. An uncertain failure
does not authorize a second business POST. Successful B receipts must match
complete body/title/labels/assignees and positive IDs plus the configured bot.
The full unfiltered all-state inventory handles valid null bodies as empty,
but rejects missing/nonstring bodies and incomplete or duplicate pagination.

Lowest-tier verification: `python3 tests/build/ci_o1_recovery_probe_test.py`
passed all 31 tests. Full CI discovery with the pinned actionlint environment
passed all 1455 tests with no skips. Staged new-file ownership passed all 66
tests; staged whitespace passed. No workflow was edited by this Task.
The local journeys reach real Runtime, journal, historical-policy replay,
review-failure artifact consumer, Report, Outbox and existing HTTP methods.
They include A pending → invisible/blocked → positive recovery, B claim →
absent/404/unknown → positive delivered, repeat zero writes, original refusal/
transport failure, malformed success and changed metadata, closed inputs,
read-only preparation, source/main drift and the shared-pair full journey.
External API receipts and remote state in these tests remain strict fixtures;
hosted token scopes, actual shared lock, run finalization timing, eventual
visibility and new-process remote fault/recovery still require actual O1 runs.
C claim-before-executor-output and cancellation remain explicitly unimplemented.

Precommit Portal command was run: `scripts/architecture-portal.sh check` exited
1 at its initial Node tests, 57 total / 54 passed / 3 failed, missing `glob`,
`gray-matter` and `cheerio`. Later Portal stages were not reached; no Portal
pass or dependency repair is claimed. Logs are local verification only.

The isolated delivery reran 31 targeted tests, all 1455 CI contracts with
pinned actionlint and no skips, plus 66 staged ownership tests: all passed.
Staged implementation/test blobs match the reviewed source exactly. Its Portal
check again reached 57 tests, 54 passed and three failed for the same missing
dependencies; no downstream build ran. This delivery adds no wiring or storage
manifest and performs no remote fault, initialization or dispatch operation.
