# Durable candidate branch to PR sequence

Delivery base: 7e95ee9f5c5152ded1b97318270a68a2b038e17b.
Original Task: 6641476a13ce912057d6eb7271d3669dd84640a2. Original-stack
observations below are historical, not delivery-base or current remote evidence.
Preserve newer child enrollment, bounded state/document, sanitized exceptions
and final PR parent guards while composing the children.

## Task and files

Add remote-read-only branch observation, explicit private-state initialization
and a require-initialized write entry. Compose the concrete CandidateBranch and
CandidatePullRequest under a separate durable parent with exact child paths and
scope. The trusted release parent initializes before its intent, then advances
this subjourney under that intent. Legacy standalone branch defaults remain
compatible; managed callers always require initialized children.

Declared files:

- tools/release/evidence_branch.py
- tools/release/candidate_pr_sequence.py
- tests/build/release_branch_observation_test.py
- tests/build/release_candidate_pr_sequence_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-branch-pr-sequence.md

Local phases are initializing, branch, pr-initializing, pr. Persist each phase
before the next child leg. Missing state after its initialization boundary is
unknown even if a matching ref/PR exists; neither observe nor advance silently
re-enrolls that child. Observation sends no remote mutation, but persists exact
ref adoption so later deletion cannot authorize recreation. Advance ignores
transport ACKs and re-observes. Unknown branch effects stop PR operations.
All child authority, source, allocation and review gates remain mandatory.
The new parent enrolls through a durable private marker before its first state
write; a missing state cannot be re-enrolled even with initialize=True. Both
parent and branch preflight document bounds before enrollment. Parent writes
fit the same 64KiB read bound. Sequence advance requires a trusted before_write
callback; every push/POST/PUT revalidates parent state/paths/writer and that
outer authorization, then the concrete child rechecks its own writer.

The final result is merged, not verified candidate/release completion. The
source-preserving witness Task, full release-parent adapter, production gate
factories and service CLI remain unimplemented. This step allocates no live
Build and uses no real GitHub, signing, provider or deployment mutations.

## Verification

Six actual bare-Git observation tests and nine branch+PR sequence tests, with
actual Git ref effects and the real PR transport against fake HTTP. Include
unknown/later effects, missing child/parent state, pending review, cold reopen,
real process death between branch and PR, and API merged without accepted source
proof. Preserve unchanged publication/candidate branch suites. Register the
observation, journey and boundary populations separately as contract/TIMEOUT 30;
run ownership and full Portal, inspect HTML,
and independent read-only review. Fixture review/auth/source callbacks are not
production acceptance. Existing lower-level tests retain per-child crash cases.
The parent spec is compared by canonical bytes, not Python numeric equality;
changing an integer identity to an equal floating value must refuse unchanged
raw state without any remote write.

### Delivery verification plan

Retain all nine original sequence and six branch-observation cases. Add parent
enrollment/preflight regressions, real process death immediately after enrollment,
marker-integrity and bounded-save refusal, mandatory outer guard, and independent
authority/writer loss at each push, POST and PUT boundary. After each fault,
reopen actual parent/child journals and assert the same claim/intent remains with
no replay. Add branch observation preflight/missing enrollment refusal, child
writer recheck after the parent guard, and callback exception sanitization.
The three new CTest populations are declared before their first registered run;
existing candidate/publication branch and PR test budgets stay unchanged.
All branch effects use real temporary bare Git remotes; PR HTTP, original
authority/review and merged-source gates remain fixtures, not live acceptance.

### Delivery evidence

- The original thin composition baseline passed 9/9 in 12.816s, exit 0:
  /tmp/lmdj-branch-sequence-delivery-baseline-v1.log. Two focused negatives then
  reproduced missing-parent re-enrollment and late oversized-document rejection:
  2 failures in 1.056s, exit 1,
  /tmp/lmdj-branch-sequence-delivery-enrollment-red-v1.log. Fixed by enrolling
  before the first state write and preflighting before any parent directory.
- After those repairs, the eleven journey tests passed 11/11 in 12.159s,
  exit 0, /tmp/lmdj-branch-sequence-delivery-tests-v1.log. Initial twelve boundary
  tests passed 12/12 in 11.213s and ten observation tests passed 10/10 in 7.480s,
  both exit 0, boundaries-v1.log and observe-v1.log under that delivery prefix.
  The subsequent thirteenth boundary case proves a parent state deleted inside
  the outer guard still prevents the push and cannot be re-enrolled.
- First registered run retained a real failure: 7/8 groups passed, but the new
  boundary group timed out at 30.08 seconds with no child output; overall exit 8,
  89.97s, /tmp/lmdj-branch-sequence-delivery-ctest-v1.log. That process was
  confirmed terminal before the diagnostic run. The initial record is not
  overwritten or recategorized as passing. Its exact cause remains unlocalized;
  concurrent Portal building is not sufficient evidence to attribute it to load.
- With the same configured Python 3.14, the complete boundary population ran
  verbosely: 13/13, 12.723s, exit 0,
  /tmp/lmdj-branch-sequence-delivery-boundaries-v2.log. The registered boundary
  command now adds only -v for per-case evidence; no budget, case or assertion
  was removed or changed to pass. All three new groups retain TIMEOUT 30.
- Staged ownership passed 74/74 in 6.226s, exit 0:
  /tmp/lmdj-branch-sequence-delivery-scope-v1.log.
- Final registered run passed 8/8 groups, exit 0, 62.85 seconds:
  /tmp/lmdj-branch-sequence-delivery-ctest-v2.log. Actual child populations were
  managed PR 26/26 (0.453s), observation 10/10 (7.406s), sequence 11/11 (12.050s),
  boundaries 13/13 (12.495s), candidate branch 23/23 (15.071s), publication branch
  21/21 (14.218s), candidate PR 39/39 (0.100s), publication PR 36/36 (0.091s):
  179 cases, zero skipped. All newly registered budgets remain 30 seconds;
  publication branch's existing 60-second budget was not modified. This later
  pass does not establish the cause of the retained initial timeout.
- Locked Node 22 install and both development configurations exited 0,
  separately captured as deps-v1.log, configure-v1.log and configure-v2.log under
  /tmp/lmdj-branch-sequence-delivery-.
- Six existing non-advance branch methods are AST-identical to the delivery
  base. Candidate/publication branch test files and both PR controllers remain
  byte unchanged: /tmp/lmdj-branch-sequence-delivery-preservation-v1.log, exit 0.
  This complements execution and is not production acceptance.
- Independent seven-file review found no actionable finding and independently
  ran parent deletion during the guard plus all three authority-loss boundaries:
  4/4, 6.270s, exit 0. The initial CTest timeout was reported to the reviewer;
  static review does not supersede that failure record.
- Node 22 scripts/docs-site.sh check passed, exit 0: 159/159 tests, zero skipped,
  production build and 47 routes/internal links:
  /tmp/lmdj-branch-sequence-delivery-docs-v1.log. Four rendered-HTML assertions
  confirm the sequence, remote-read-only observation, missing-state refusal and
  merged-not-candidate-complete boundary, exit 0:
  /tmp/lmdj-branch-sequence-delivery-rendered-v1.log. All tracked symlink entries
  were actual symlinks; no checkout/config repair or Product Build allocation.
- Pitfall disposition: the reproduced enrollment/preflight and composition
  invariants are directly expressed by code regressions. The one unlocalized
  timeout establishes no new process cause; retain it without inventing a ledger
  recurrence. Full production parent/witness/gate/service wiring and real release
  acceptance remain unperformed. This dependent stack remains local/unpushed.

### Historical original-stack executed evidence

- Direct observation: 6/6, exit 0; initial sequence: 8/8, exit 0.
  Canonical binding regression: sequence 9/9 in 9.362s, exit 0.
- Initial CTest: all four registered suites passed in 29.91s total, including
  unchanged candidate/publication branch suites. Logs:
  `/tmp/lmdj-branch-sequence-ctest.log` and
  `/tmp/lmdj-candidate-pr-sequence-tests-v2.log`.
- Final sequence CTest after strict canonical binding: passed in 8.79s,
  exit 0; `/tmp/lmdj-branch-sequence-ctest-v2.log`.
- Staged ownership: 74/74 in 6.399s, exit 0;
  `/tmp/lmdj-branch-sequence-ownership.log`.
- Full Portal check on Node 22: 152/152 tests, production build and all 47
  routes/internal links passed, exit 0; `/tmp/lmdj-branch-sequence-portal.log`.
  Inspected the actual built operations/version-and-release HTML: the new
  durable subjourney and still-unimplemented parent/witness boundary appear.
- Independent read-only review of all seven files and final canonical-binding
  increment: no actionable findings; reviewer independently ran sequence 9/9,
  exit 0. No real provider, GitHub write, signing or deployment was exercised.
- Pitfall disposition: the strict state-binding invariant is expressed by its
  deterministic regression; no new non-code process recurrence was observed.
- Locked Node 22 dependency installation passed; npm reported 27 dependency
  vulnerabilities (9 moderate, 18 high). No dependency update or vulnerability
  remediation is part of this Task.

Shipping remains behind the preceding local stack: live PR #1266 is OPEN,
head `c8fab3b67b6abe3bff708b5563acfc84b0e9e671`, no mergedAt and no owner-review
attestation in the paginated issue comments at this check. Local independent
review does not manufacture owner adoption or authorize a protection bypass.

Subsequent live correction after the user's merge notice: PR #1266 is MERGED,
mergedAt `2026-09-13T04:22:40Z`, actual squash
`52856e25f16f9dd9487a776ea1b43838ae8e34cc`; fetched origin/main confirms it.
The prerequisite is no longer a shipping blocker. This Task and its earlier
local dependencies still need ordered, current-head reviewed PR delivery;
the former open observation above remains historical evidence, not current state.

## Version Management

Version impact: none. Internal durable orchestration only.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
