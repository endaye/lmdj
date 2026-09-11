# PR-Agent complete-input producer

Date: 2026-09-11
Status: lead-approved implementation specification; no host or model admission.
Relates to #1149, #1151, #1153 and #1154. These Issues remain incomplete.

## Outcome and ownership

Implement the missing read-side producer from fixed, authenticated Git objects
to the existing complete `lmdj.pr-agent-input.v1` contract. Lead owns this plan,
scope and independent acceptance. A supervised Luna worker owns implementation
and focused tests in a fresh isolated `feat/pr-agent-complete-input` worktree.
Copy this approved plan verbatim to the declared repository plan path.

The verified main baseline at specification time is
`ed4afbcb5003be9879c52c42fa2f15e1695cc4c5`. Refresh main before worktree creation
and inspect any relevant drift before editing. Do not change another worktree,
global Git configuration, the accepted installed bundle or the frozen T5 oracle.
One Task is one Conventional Commit. Worker authority ends after local verified
commit and report; lead will arrange independent exact-head review and shipping.

Declared files:

- `scripts/ci/pr_agent_input.py` (new producer module)
- `tests/build/ci_pr_agent_input_test.py` (new lowest-tier real-Git tests)
- `scripts/ci/review_pipeline.py` (opt-in collection entry, explicit trusted
  publication-witness consumer, and rename-inventory capture parity below)
- `tests/build/ci_review_pipeline_test.py` (entry and existing-consumer seam)
- `scripts/ci/review_scope.py` (narrow changed-path union validation only)
- `tests/build/ci_review_scope_test.py` (rename union and RIGHT separation proof)
- `docs/plans/2026-09-11-pr-agent-complete-input-producer.md` (this exact plan)

No other repository file is writable. If an ownership or semantic correction
needs another file, ask the lead with a reduced counterexample before editing.
The existing full-rule ownership of `scripts/ci/` and `ci_` test prefix are
read-only inputs, not permission to lower conservative lane selection.

## Evidence and boundaries

Current `review_pipeline.collect` resolves the current PR, fixes the merge base
and head, and writes legacy context/diff/history. It does not emit a T2 input.
The actual adapter already validates blobs, exact diff/file/hunk partition,
RIGHT lines and the canonical complete-input digest. T3 already consumes a
separately retained `t2-input.json`. Reuse those boundaries, not another model
client, another publisher or a second provider fallback loop.

This Task must not change `pr_agent_review.py`, public receipt schemas, engine
limits, dependencies, units, inventory, workflow triggers, production route,
provider configuration, credentials, ledger, admission flags or branch protection.
Do not call a provider, SSH, sudo, systemd, funding endpoint or live shadow run.
No new permanent gate, full-CI requirement, paid execution or product release.

## Producer contract

Provide a callable builder accepting an exact existing repository and the closed
seven-field T2 identity: repository, pull_request, base_sha, head_sha, control_sha,
run_id and run_attempt. The builder has no API or environment-derived identity
authority. Require exact types/SHAs and existing commit objects, verify base is
the selected merge base and control is the trusted checkout identity supplied by
the caller. A caller assertion is not a GitHub provenance attestation.

Use only Git object reads and bounded subprocesses. Never checkout the PR, read
its files through the working tree, follow a PR symlink, hydrate LFS, initialize
submodules, invoke hooks, load repository Python/configuration or execute PR code.
Disable replace objects, external diff/textconv, color/pager and implicit lazy
network fetching. Isolate dangerous ambient Git/config environment. Select fixed
diff options for both full diff and NUL-delimited change inventory so custom
configuration cannot silently change their rename/header/hunk semantics. Reuse
`change_scope.parse_name_status_z`; do not trust a hand-split whitespace inventory.
Use Git object type/size checks before bounded blob reads; missing or wrong-type
objects, unsafe/unsupported paths and resource limits produce explicit refusal.

Every changed path participates. Emit exact old/new blob bytes with Git object
ID, SHA-256, byte length, base64 and UTF-8/binary classification; absent sides
are null. Read deletion bytes from the old tree, rename old bytes from old_path,
and new bytes from the fixed head. Preserve line endings and missing final
newline. Derive full canonical Git diff and each exact file/hunk fragment;
derive deterministic unique hunk IDs and RIGHT-side line text/digests. Do not
invent patch text, discard a hunk, normalize away bytes, guess missing blobs,
or slice a diff to make it fit. Hash canonical unsigned JSON exactly as the
existing adapter does, then run actual `authenticate_input` on the final result.

Reuse existing parsing/validation helpers where appropriate. The test oracle
must still independently compare real Git object/diff bytes, not merely show
that a generator and validator using the same helper agree.

Supported existing contract cases include ordinary addition/modification,
deletion, textual and pure rename, and representable binary modifications.
The closed adapter contract currently cannot represent every valid Git change
(for example metadata-only modification, some binary addition/deletion/rename,
gitlink/type change, or Git-quoted path headers). Preserve these as explicit
unsupported required-input failures with the complete inventory and finite
per-path reasons; never relabel readable data as unreadable or mark a subset
complete. Do not change the adapter contract in this Task. These refusals are
not successful reviews and remain visible limitations for T5 selection; they
cannot be used to remove an admitted sample or reduce the frozen denominator.
Any discovered case required by the frozen cohort that cannot be represented
must be escalated as the next concrete contract repair, not silently excluded.

Keep current MAX_FILES/MAX_BLOB_BYTES/MAX_PATCH_BYTES/MAX_INPUT_BYTES and total
represented-byte constraints. Enforce bounds while collecting, not only after
unbounded capture. An oversized/unreadable/empty input returns no admitted T2
input. Retain an explicit finite failed collection result with identity and
inventory/reasons; never synthesize reviewed/clean output or provider coverage.

## Opt-in production-source entry and publication

Add an explicit `collect-t2` command to `review_pipeline.py`; leave existing
`collect` and all current production commands/callers observably unchanged.
Factor only shared target resolution and exact Git/identity collection needed
to prevent drift; do not create another GitHub PR client. The opt-in entry uses
the existing trusted target resolver and read-side Git fetch boundary, requires
the expected current head, and rechecks the target before admitting publication.
Keep GitHub tokens out of diagnostics and every emitted file. No workflow calls
this new command until its separately reviewed T5/T6 wiring Task.

The successful output retains existing context/body/diff/history plus
`t2-input.json` and a bounded collection receipt that binds the exact input and
context identities/bytes. Refuse a reused output directory or existing committed
output; publish verified complete bytes with an atomic no-clobber mechanism in
a caller-owned new workspace directory. No arbitrary absolute host path or
privileged publication interface. Failure at any write/fsync/commit boundary
returns no successful publication witness, admits no input for opt-in
consumption, and never consumes old output. Keep partial failure evidence
rather than retrying or silently overwriting it. A persistent filesystem error
may also prevent cleanup: report exact uncertainty and observed residuals,
never assert that a marker was removed when its unlink failed.

### Publication authority clarification — 2026-09-11

Lead independently reproduced final directory-fsync EIO followed by marker
unlink EIO at source SHA-256
`106a54bfc88b20e8354f65c76c2db179b1dee8938e96915049c4df7fbc46b3e5`;
both final files remained while the publisher raised PublicationError. Evidence:
`/tmp/lmdj-pr-agent-plan/t4-lead-input-publication-double-fault-actual-20260911.json`.
The prior wording promising absence under arbitrary cleanup failure was too
strong; this clarification preserves the actual no-admitted-input invariant.
The previous exact plan is preserved externally as
`t4-lead-complete-input-producer-spec-pre-publication-witness-20260911.md`.

Only return/emit the exact successful collection-receipt digest after every
required publication durability operation succeeds. The opt-in consumer must
explicitly require that separately supplied successful-producer witness and
authenticate the retained receipt, context and complete T2 input against it.
A directory's marker bytes or the absence of a failure fence never establish
publication authority. A best-effort failure fence may aid diagnosis but its
own write/fsync failure cannot grant admission. A fresh consumer presented
with residue and no trusted success witness must refuse, including after a
crash or failed cleanup; it must not fall back to legacy collection mode.
Keep the existing legacy collector API behavior for existing callers; the new
opt-in caller must explicitly select the strict mode. No hidden global state,
generic crypto framework, retry or workflow routing change is introduced.
This local callable witness is not a GitHub attestation: later T5/T6 wiring
must derive it from the authenticated successful producer job and exact
run/attempt/head/control identity, never from an artifact attesting to itself.

Lead's complete six-artifact callable and descriptor reductions are retained in
`/tmp/lmdj-pr-agent-plan/t4-lead-publication-descriptor-reduction-20260911.py`
and `t4-lead-publication-descriptor-reduction-actual-20260911.json`. At unchanged
producer SHA-256 d2f80d04c23aacdafeb229848a0d48311ff9213fa441518790b74515e831d25f,
all six exact artifacts remain after final-directory-fsync EIO, final-receipt
unlink EIO and failure-fence-open EIO; no successful witness is returned and a
fresh strict consumer refuses. This callable proof passes, but is not CLI proof.
Add the same three low-level faults to the actual collect-t2 CLI dispatch after
a successful six-file positive control. Assert every fault was traversed,
all six residual bytes equal the expected artifacts, failure fence is absent,
the failed caller emits/returns no successful witness, and a fresh strict
consumer rejects. A single fsync failure whose cleanup and fence succeed is
a useful separate case, not this required triple-failure journey.

The same reduction confirms an actual no-writer FIFO blocks O_RDONLY open
before fstat: the child emitted READY, then exceeded the two-second diagnostic
deadline and was killed by its owner (PID 4137, waited rc -9). That is failure,
not a passing negative. Open retained artifacts nonblocking and no-follow,
validate their descriptor-bound regular-file type, then read at most the
trusted bounded length plus one sentinel byte and authenticate exact digest.
Test real FIFO refusal in a child: normal typed failure after READY, no parent
timeout/kill. Include actual symlink replacement at the open boundary and an
oversized retained artifact; tests cannot merely bypass or mock the consumer.

The later host attempt supervisor owns continuous slot locking and service
publication; this workspace producer is not that supervisor or its acceptance.

### Failure-inventory correction — 2026-09-11

Lead independently reduced a real Git tree with an undecodable byte path
`a-\xff.txt` followed by valid `z-later.txt` at source SHA-256
`51bb33d63f6b637899efa11c7275f53ec026d76d3c5049c303e69b1770f4301f`.
The unchanged producer correctly refused admission but stopped at the first
strict UTF-8 decode and emitted empty `inventory`/`reasons`, losing both the
undecodable path identity and the later valid record. The original raw capture
is preserved at
`/tmp/lmdj-pr-agent-plan/t4-lead-capture-producer-nonutf8-red-1400/` and the
unchanged reduction is retained in
`/tmp/lmdj-pr-agent-plan/t4-complete-input-producer-evidence-20260911/122-independent-byte-path-red`.

The corrective producer path keeps strict name-status parsing as the sole
admission authority and uses a bounded failure-only raw parser after strict
decoding fails. It retains every parseable status/path record in order,
represents undecodable path bytes with both raw lowercase hex and base64,
retains valid later paths and per-path refusal reasons, and records raw
inventory SHA-256, byte length, completeness and truncation fields. This
diagnostic evidence cannot create a T2 input, publication receipt or witness;
ordinary unsafe/quoted paths continue to refuse through the strict parser.

### Bounded failure-receipt correction — 2026-09-11

Lead's unchanged real-Git bounded reduction is retained in evidence directory
`130-bounded-failure-red`; its source SHA-256 is
`b9b9c5c6894b7463bddfad65a3b2853274aaabb10c30fa0181693b9496a6114b`. With
256 undecodable 171-byte names plus later `z-later.txt`, strict collection
still refuses and retains 257 records, but the complete diagnostic exceeds
the fixed `MAX_FAILURE_BYTES` budget. The prior receipt publisher incorrectly
raised and left no failure receipt; this reduction and its raw output are
preserved as the original red evidence.

The correction keeps that bound unchanged and emits a finite
`lmdj.pr-agent-input-collection-failure-summary.v1` receipt when the complete
failure result is too large. The summary retains the original canonical
failure byte length and SHA-256, raw-inventory byte length/digest/completeness,
total and retained inventory/reason counts, bounded edge samples (including
the later valid path where it fits), and explicit `complete: false` and
`truncated: true` flags. It remains `status: failed`, never emits a T2 input or
success witness, and the actual `collect-t2` CLI journey is covered by
evidence `135-pipeline-full-correction-final`, including no `GITHUB_OUTPUT`
and fresh strict-consumer refusal.

### Rename inventory parity clarification — 2026-09-11

Lead independently reduced a real Git R100 rename from old.txt to new.txt:
`/tmp/lmdj-pr-agent-plan/t4-lead-rename-inventory-reduction-20260911.py` and
`/tmp/lmdj-pr-agent-plan/t4-lead-rename-inventory-reduction-actual-20260911.json`.
At pipeline SHA-256
`d1973c717cd1fc090e9165742e812fe26392ba80990431806b925a3619f92d3e`, the real
collect-t2 output context contains only new.txt; the existing publisher's real
Git inventory contains both old.txt and new.txt. The existing coverage consumer
accepts the incomplete new-only list but rejects the actual complete list.
This is not a GitHub publication attempt or model result. Both adapter hunk
records and Git objects already retain the old path; no schema change is needed.

Lead explicitly expands this SAME producer Task's declared ownership from five
to the seven files listed above, adding review_scope.py and its existing test.
No other worker owns those files in this worktree. The original five-file plan
is preserved externally as
`t4-lead-complete-input-producer-spec-pre-rename-inventory-20260911.md`.
This is one reviewable complete-input/consumer parity correction, not authority
for general protocol, publisher transport or workflow changes.

The deterministic changed-path inventory is the exact sorted union of current
file/hunk path and every non-null renamed old_path. Apply that same definition
to collect-t2 context, the existing T2 capture context equality check and the
coverage-versus-authenticated-changed-inventory check. Reuse one narrow helper
in review_scope after structural validation if that avoids divergent rules.
RIGHT-side finding anchors remain only each hunk's new/current path and its
actual changed RIGHT lines; do not manufacture old-path anchors or coverage
hunks. Preserve full blob/patch/input/receipt digests, exact expected/observed
coverage equality, independent collector trust, legacy v1 behavior and all
finite failure branches. Missing old path, extra path, wrong old path, forged
rename and an old-side inline anchor must fail for their respective reasons.
Never relabel rename as unsupported or keep a reduced context to pass capture.

Add real committed pure and edited rename journeys through collect-t2 persisted
output, successful publication witness, actual T3 capture/coverage/finalize and
the publisher's independent Git inventory boundary using only API/transport
doubles. Assert the complete old+new path set at each transition and exact
RIGHT-only anchors separately. Include a rename across policy directories so
the old path cannot disappear from the deterministic scope floor. Keep a valid
positive control before each one-fact malformed inventory/anchor mutation.
No live GitHub write or provider call is permitted. Run the complete existing
review-scope suite plus all original required verification, and record any
additional reader regression required by changed source facts. If a correction
needs any eighth file, ask with an exact failing case before editing it.

Keep complete collection failure classification separate from the engine's
model failure and T3 formal-review result. No model call may be needed to discover
missing input, and collection failure cannot create formal scope authority.

## Lowest-tier tests and far-side acceptance

First reduce the baseline gap with a real temporary Git repository and show
that current collection creates no authentic T2 input. Preserve that observation.
Tests use temporary Git objects and exact API/transport doubles only; no live
GitHub mutation, provider, host or workflow calls. Child interpreter prerequisites
must be verified with the exact sanitized environment, not bypassed by passing
the ambient environment back.

1. Real fixed commits -> full inventory: assert the actual NUL inventory,
   merge-base/head/control identities and no checkout/file execution. Include a
   base tip advanced independently after branching, and hostile working-tree
   files/config/hooks whose effects must remain absent.
2. Inventory -> final input: independently compare Git base/head blob IDs,
   lengths and bytes, whole diff and every hunk. Include add, multi-hunk modify,
   deletion-only, rename with edits, pure rename, binary modification, CRLF,
   no-final-newline, and a path containing spaces. Authenticate through the real
   T2 function and compare expected coverage/RIGHT inventory explicitly.
3. Unsupported input -> explicit failure: each unsupported zero-hunk/type,
   binary-side, quoted/path, missing/oversized/blob-limit/file-limit/diff-limit
   case retains the entire changed-path inventory and names the reason; no
   admitted `t2-input.json`, success receipt, engine or publisher call occurs.
4. Opt-in caller -> persisted output -> actual T3 `collector_witness` and
   `trusted_collector`: assert digest and identity agreement across the real
   files. A target change before commit, malformed API reply, wrong context,
   duplicate input, partial write, fsync failure or preexisting output fails
   closed and preserves old content/no successful caller witness. Include
   final-fsync plus marker-unlink failure and inability to persist a failure
   fence; prove a fresh strict consumer refuses leftover bytes without a
   trusted successful-producer witness. Test the actual CLI
   command dispatch, not just a pure helper disconnected from the entry.
5. Tampered blob/hash/hunk/RIGHT/header/identity fixtures must fail the real
   adapter/consumer. Do not count agreement between two fakes as proof. Keep
   existing legacy collect and pipeline behavior unchanged in regression tests.

Required commands: ordinary Python 3.11 producer and complete pipeline suites;
ordinary adapter, review-scope and review-wait suites; new-file staged ownership
`python3 tests/build/ci_change_scope_test.py`; scope consumer parity and
differential suites; `scripts/docs-site.sh check` for this new plan/source facts.
Record exact interpreter identities, actual run/pass/fail/skip counts separately,
and every original failing invocation. A skipped pinned handler test is not an
integration pass. No new engine/import semantics are introduced, so another
Linux bundle or paid handler run is not a substitute for producer verification.

Before commit follow `issue-done`: verify non-main branch, exact declared
staging, full staged diff, `git diff --cached --check`, tests on the staged new
file population, then one Conventional Commit and final file/status read-back.
Inspect the complete committed range with local-ci --list (classification only).
Do not push, create PR, merge or close an Issue in this worker dispatch.

Capture actual tool return objects or subprocess stdout/stderr directly to NEW
evidence files outside the repository. Never reconstruct raw output, invent
missing fields or rewrite an older failure. Deliver exact commit/tree/diff,
file identities, test commands/results, unsupported-case inventory and remaining
T4/T5/T6 gates. The lead will independently review the whole Task before shipping.

## Remaining migration sequence

After this producer lands, separately implement the one-descriptor host attempt
supervisor (publication -> isolated child -> closure -> collection -> durable
terminalization), then authenticate real host invocation/recovery and capacity.
T5 manual shadow wiring consumes those interfaces and the existing frozen
oracle. T6 cutover/rollback/handoff waits for every original T5 gate. Nothing in
this Task enables production or substitutes source proof for that full sequence.

## Version Management

Version impact: none — internal CI producer only; no Product/Module/Contract
manifest, engine adapter, dependency or installed bundle identity changes.

## Documentation Impact

Documentation impact: none — the new internal opt-in source and this plan do
not change a current Portal route or deployed operation. The declared docs-site
check still runs. Actual host/shadow/production documentation belongs to the
later owning Task and must not be claimed by this source-only delivery.
