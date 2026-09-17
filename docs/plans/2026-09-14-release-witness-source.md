# Authenticated witness Task and squash source proof

Delivery base: 871c75019b54ca0cf173373cc3f523c2b7d007c5.

## Task

Replace the missing production source-verification leg of the witness PR
journey with a concrete passive consumer. Read the original confirmed official
witness receipt and private source history through CandidateWitnessRun, then
read the dedicated CandidateWitnessTask's private binding under its own writer.
The lock order remains source then Task. A caller-supplied spec, API merged flag
or matching endpoint blob is not independently sufficient evidence.

Verify the exact one-parent Task, its original base plus only the canonical
regular witness blob, current retained checkout and index, source identity,
receipt and binding digests. For the actual witness squash, require one parent,
the base and original candidate in main history, exact parent plus witness tree,
and no preexisting witness in that parent. Preserve later unrelated main edits.
Verify every retained immutable snapshot path and witness at the observed main;
reject intervening edit/revert history, not only endpoint byte drift. Future
versions may be added to versions.json, but this candidate must remain unique.
Check original authority, both private bindings and current main again before
returning proof. A moving observation retries the same candidate observation,
never selects a new target or repeats a remote write.

This consumer performs no generation, Task command, checkout, ref/staged-entry
update, fetch, GitHub mutation or provider call. Private temporary indexes may
add expected tree objects. Existing source guards use write-tree and may refresh
Git's index cache; unchanged staged entries are not a raw-index-byte guarantee.
Missing objects/state are errors, never repaired here.
It proves source only: trusted original request/protection, actual full Task
command receipts, current-head/historical review and production parent/factories
remain separate prerequisites. No local proof is a release or online acceptance.

The upstream PR #1296 remains OPEN/UNSTABLE at its original head. The inherited
dependent-stack hold keeps this Task local/unpushed; no owner attestation,
signer, host/authentication, protection, dispatch, release or cleanup is allowed.

## Declared files

- tools/release/witness_source.py
- tests/build/release_witness_source_test.py
- tests/build/release_witness_pr_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-14-release-witness-source.md

## Verification

Lowest tier: contract. Produce the real official witness and independent Task
in the existing narrow snapshot fixture. Exercise pre-PR proof, actual squash,
later main preservation and cold source consumers; assert unchanged source/Task
HEAD, real indexes, retained command bytes, refs and artifact bytes. Negative
cases change one identity/binding/parent/blob/mode/history/authority fact and
must fail with why/remedy. The fixture is not a full Portal snapshot or live
GitHub approval. Register binding, merge, history and authority groups with
initial 120-second budgets before execution; no existing test/budget is changed.

Extend the existing real Task -> create-only remote push -> actual squash ->
cold PR reader journey to call this production source verifier. Transfer actual
far-side merge objects explicitly in the fixture, never in the verifier. Keep
the independent far-side blob/parent/tree assertions and the committed-byte
negative; fixture review/protection remain labelled, not production authority.
Run all existing witness PR groups and candidate source regressions unchanged,
locked Node install, full Portal check and actual rendered-page assertions.
Stage only declared files and run ownership/admission before commit. Preserve
raw failures and obtain independent complete-diff and exact-head review.

## Version Management

Version impact: none

Reason: release source verification only; no Product Build, Assembly, Module,
Host, Provider, Contract, tag or immutable snapshot is allocated or modified.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish implemented real witness source proof from the still
unimplemented production authority/review/command-evidence composition.

## Execution evidence

All commands used the explicit Node 22.22.2 PATH. Direct Python was 3.11.15;
the configured CTest interpreter was Python 3.14.7. Evidence files are retained
local logs, not published release receipts.

- Initial source contracts: 17/17 passed, exit 0, 374.816 seconds;
  `/tmp/lmdj-witness-source-contract-v1.log`.
- Two additional causal negatives: consistently rebound Task with an extra
  file, and unchanged snapshot bytes with changed committed mode. Both passed,
  exit 0, 70.021 seconds; `/tmp/lmdj-witness-source-negatives-v1.log`.
- Real witness PR journey: 2/2 passed, exit 0, 112.147 seconds;
  `/tmp/lmdj-witness-source-journey-v1.log`. The success leg checks the actual
  producer/Task before push, actual temporary remote squash bytes/tree and
  production source proof after merge, then cold observation and advance.
  The changed far-side blob is rejected by the same production source reader;
  both legs retain exactly one push, one POST and one PUT, not replayed writes.
- Locked dependency install and configure passed, exit 0;
  `/tmp/lmdj-witness-source-install-v1.log` and
  `/tmp/lmdj-witness-source-configure-v1.log`.
- Full Portal check: 170/170 tests, zero failures/skips, production build and
  all 47 routes/internal links passed, exit 0;
  `/tmp/lmdj-witness-source-docs-v1.log`. Four actual generated HTML assertions
  passed in `/tmp/lmdj-witness-source-rendered-v1.log`.
- Staged ownership/admission: 74/74 passed, exit 0, 6.110 seconds;
  `/tmp/lmdj-witness-source-scope-v1.log`. Only the six declared files are staged.
- Final configured CTest: 10/10 groups, 98/98 cases passed, zero failures/skips,
  exit 0, 556.14 seconds; `/tmp/lmdj-witness-source-ctest-v1.log`. This includes
  all four new source groups (19 cases), all four witness PR groups (73 cases)
  and both existing candidate source groups (6 cases), with original budgets
  unchanged. The real PR journey took 108.62 seconds within its existing
  120-second budget. The five non-plan files match
  `/tmp/lmdj-witness-source-tested-files-v1.sha256`.

The new failures-under-test are source invariants fully represented by the
regressions, not a newly discovered process pitfall; no ledger entry is added.
The prior retained complete Portal/snapshot/witness rehearsal is companion
evidence, not a claim that this narrow fixture repeats its full content proof.
This Task does not establish production request authorization, full Task-command
receipts, independent live review, protected CI, signing, publication, deployment,
doc-site publication or Channel promotion. The overall automation remains open.
