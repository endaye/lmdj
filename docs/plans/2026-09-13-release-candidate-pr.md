# Durable candidate PR child

Delivery base: e81b7f388635d327ef8f4107d7eeda53f160bc9a.
Original Task: f091170b9dc2dda9bb6b96a0aa6a3876dd461cf2. Original-stack results
below are historical, not validation of this delivery base. Preserve newer
enrollment, bounded state/document, sanitized exceptions and final parent guard
protections in the shared PR controller and transport.

## Task and files

Reuse the publication PR state machine with a closed candidate spec/document
policy and a separately scoped GitHub transport. Preserve publication behavior
and its branch allowlist. Candidate head is the existing feat/release-candidate
operation branch, not an evidence branch; it is not called a target before the
actual protected-main squash is verified.

Declared files:

- tools/release/evidence_pr.py
- tools/release/candidate_pr.py
- tools/release/github_api.py
- tests/build/release_candidate_pr_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-pr.md

The shared implementation retains durable create/merge intents, one POST/PUT,
unknown outcome reconciliation, exact-head squash and mandatory trusted gates.
Its private state schema remains byte-compatible for publication; candidate and
publication scopes have disjoint closed fields and branch transports. No generic
user-supplied document policy or new public release command is introduced.

Trusted parent gates must authenticate original authority, completed Task proof,
cut/source/snapshot bindings, live main/protection and reservation competition;
review includes findings, conversations and closing relations. A verified merge
must pass CandidateSourceVerifier and historical review. Witness is a subsequent
Task, so this child alone must not complete the overall candidate step. Branch
push, production gate factories and parent/witness composition remain separate.

## Verification

Run the original publication suite unchanged and the full inherited lifecycle
suite with candidate spec/document and actual candidate GitHub HTTP adapter.
Add cross-scope refusal, operation/Build refusal and read-only/missing-child
recovery checks. No real GitHub writes, providers, signing or deployment.
Register the candidate suite at the existing 30-second contract budget. Run
staged ownership and full Portal check, inspect built HTML, independent review.

### Delivery verification and compatibility repair

- Reproduced the current-base transport mismatch before repair: the candidate
  lifecycle returned unknown-create instead of verified, 1 failure, exit 1,
  0.004 seconds (/tmp/lmdj-candidate-pr-delivery-transport-red-v1.log). The
  retained publication-only POST validator correctly rejected a candidate
  branch; copying the old extraction alone could not implement the new route.
- Keep the publication and candidate branch patterns disjoint. Extract the
  existing closed document check into one private helper, used by both fixed
  public validators and the actual POST transport. The candidate producer also
  checks it before enrollment. Retain exact fields, main-only base, non-draft,
  maintainer write refusal and the 20000-character title/body bounds.
- The two inherited tag-specific document tests are overridden with equivalent
  candidate Build tests, not skipped: maximum admissible generated content is
  actually posted; oversized content refuses before both observe/advance can
  enroll or call HTTP. All other current publication lifecycle tests remain
  inherited. The original publication test file is unchanged.
- Direct candidate 39/39 passed (0.115s) and publication 36/36 passed (0.098s),
  both exit 0. Logs: /tmp/lmdj-candidate-pr-delivery-tests-v1.log and
  /tmp/lmdj-candidate-pr-delivery-publication-v1.log.
- Registered CTest passed 3/3, exit 0, 1.22 seconds. Actual child populations:
  managed parent 26/26 (0.547s), candidate 39/39 (0.113s), publication 36/36
  (0.116s), no skips or timeout changes. Evidence:
  /tmp/lmdj-candidate-pr-delivery-ctest-v1.log.
- An AST comparison confirmed all 11 existing shared PR methods are unchanged
  after normalizing only the deterministic document/spec policy hooks. Original
  publication tests remain byte-unmodified. This source-preservation check is
  complementary to the executed regressions, not runtime acceptance:
  /tmp/lmdj-candidate-pr-delivery-preservation-v1.log (exit 0).
- Staged ownership passed 74/74, exit 0, 5.964 seconds:
  /tmp/lmdj-candidate-pr-delivery-scope-v1.log. Locked dependency installation
  and development configuration both exited 0, separately captured under the
  same delivery prefix with deps-v1 and configure-v1 suffixes.
- Independent seven-file review found no actionable finding and independently
  ran candidate 39/39 (0.109s) and publication 36/36 (0.099s), both exit 0.
  Numeric PR GET/PUT operation authorization still belongs to the trusted
  controller and gates; transport route filtering alone is not that authority.
- Node 22 scripts/docs-site.sh check passed, exit 0: 159/159 tests, zero skipped,
  production build and 47 routes/internal links:
  /tmp/lmdj-candidate-pr-delivery-docs-v1.log. Four assertions against generated
  operations HTML confirm the child/recovery/preflight/remaining-composition
  statements are rendered: /tmp/lmdj-candidate-pr-delivery-rendered-v1.log
  (exit 0). No Product Build or immutable snapshot was allocated.
- The scope/transport mismatch is a direct code invariant covered by the
  lifecycle and cross-scope regressions; no new process-only pitfall entry.
  Real intake, completed Task/source/reservation/protection gates, review,
  branch push, witness and complete candidate orchestration remain separate.

### Historical original-stack verification

Observed: candidate 26/26 and unchanged publication 23/23 pass through the
registered CTest groups (0.24 and 0.17 seconds, original 30-second limits).
Existing managed publication-parent regression 16/16 also passed (0.330 seconds).
Staged ownership 74/74 passed (5.401 seconds). Independent seven-file read-only
review clean. Logs: /tmp/lmdj-candidate-pr-ctest.log,
/tmp/lmdj-candidate-pr-managed-tests.log and /tmp/lmdj-candidate-pr-ownership.log.
Full Portal passed 152/152 tests (zero skipped) and 47 routes, retained in
/tmp/lmdj-candidate-pr-portal.log. The candidate child paragraph was inspected
in the actual built operations/version-and-release HTML.

Fresh upstream #1266 remains open/UNSTABLE at
c8fab3b67b6abe3bff708b5563acfc84b0e9e671; paginated comments contain no owner
review attestation. This Task remains local/unpushed with that stack.

The API observations, original-authority gate, review and merged-source gate in
these tests are fixtures. They prove controller/transport refusal and recovery,
not real protected-main, review, allocation, provider or release acceptance.
Pitfall disposition: code regressions fully express this adapter's invariants;
no new process-ledger entry.

## Version Management

Version impact: none. Internal orchestration adapter only; fixture Builds do not
allocate a real Product Build or initiate a release.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
