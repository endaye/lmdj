# Managed candidate preparation after the checked cut

Status: implementation and declared local verification complete; local commit
and exact-head review pending. Local dependent stack only. No push, PR,
provider call, signing, release, deployment or host/authentication mutation.
Base: `66c00a6649b9926b282eb70982b78b4c3b34ece6`.

## Task

Connect the actual checked cut to the managed release driver: independently
reviewed candidate PR and actual protected-main squash; retained-source official
witness generation/verification; owned linked witness worktree and durable
dependency installation; staged and committed witness Task checks; independently
reviewed witness PR and actual merged witness/source proof. Only the entire
journey can produce the driver's candidate receipt. Initial request freezing,
source materialization and snapshot/cut production remain upstream producers,
not a new live service or unattended release claim.

The consumer needs two producer interfaces: a GET-only verified PR merge identity
(numeric PR ID/number and actual squash SHA, not parsing an opaque reference), and
passive recovery of the actual confirmed witness receipt without spending another
verification attempt. Missing enrolled state is never fresh work. Unknown POST,
PUT, installation or worktree creation is never blindly retried. Each command or
mutation holds its original writer and rechecks parent authority at the boundary.

## Declared files

- `tools/release/evidence_pr.py`
- `tools/release/candidate_witness.py`
- `tools/release/candidate_transition.py`
- `tools/release/candidate_task_workspace.py`
- `tools/release/orchestration_driver.py`
- `tests/build/release_candidate_transition_test.py`
- `tests/build/release_candidate_receipt_recovery_test.py`
- `tests/build/release_candidate_task_workspace_test.py`
- `tests/build/release_candidate_portal_journey.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `.agents/pitfalls/macos-git-launch-overhead.md`
- this plan

## Verification

Lowest tier: real temporary Git and official witness generator/verifier with
narrow snapshot/command fixtures; authenticated fake GitHub API and local bare
remote for external effects. Exercise the real parent and children, preserving
POST/PUT and local command counts across cold reopen and process-death boundaries.
Independently assert every leg after it occurs; success must include a witness
squash verified against actual artifacts and immutable history. Review pending,
unknown writes, missing state, source/artifact drift, authority/writer loss and
nonzero/unknown install must block later legs. Passive observation performs no
business write or dependency/producer command. Ordinary later main progression
must neither change the frozen candidate nor change its canonical receipt.

Run existing evidence PR, managed PR, candidate PR sequence, witness lifecycle,
source and Task/check suites after the changes. Register new suites without
changing existing budgets, lane scope or thresholds. Run staged ownership and
admission checks. Run `scripts/docs-site.sh check` for the current Portal update,
and extend the retained full actual Portal journey through the composed candidate
parent. Keep fixture-only effects distinct from real GitHub/protection/review
and complete-CI/release/deployment acceptance. Retain all failed runs.

## Version Management

Version impact: none

Reason: controller development only; no real Build allocation, manifests,
Assembly, Product, Module, Provider or Contract identities change. Test Build
identities are derived from temporary fixture manifests.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Document the managed post-cut boundary and remaining upstream/live-service gaps;
do not imply the release goal is complete or operationally accepted.

## Acceptance ledger

- Implemented the concrete checked-cut parent, GET-only numeric merge receipt,
  passive confirmed witness recovery and owned worktree/install child. The
  driver consumes the final candidate receipt and stops at the separate
  complete-test boundary. Both PR gates still require trusted independent
  current/historical review callbacks plus actual local source verification.
- The local API fixture uses real create-only branch pushes and distinct real
  single-parent squash commits. It does not exercise authenticated GitHub,
  branch protection, conversations, independent platform review or any provider.
- New contract cases cover receipt/artifact identity, unknown writes, missing
  enrollment, authority loss, nonzero/unknown install and child checkpoint
  recovery. The workspace tests include actual fork/exit boundaries after
  checkout and installation; the parent checkpoint test instead uses a named
  `SystemExit` injection and makes no OS process-death claim.
- The composed journey checks every candidate/witness leg, cold recovery,
  fixed receipt after a later main descendant and refusal after real artifact
  drift. The retained actual Portal harness additionally uses official snapshot,
  witness, installation and six-command Task checks, then a source-absent fresh
  main clone. Its GitHub API/review remain explicit fixtures.
- Independent review found three defects: callback exception chains could expose
  private diagnostics; a late main observer could delete the parent checkpoint
  before a save; a late source observer could delete workspace history after its
  last check. Fixed explicit exception suppression, original parent checkpoint
  comparison at every save, and final workspace history checks after callbacks.
  Actual regression evidence is retained below; final full-byte local
  verification is complete across the retained runs and explicit environments.
- Independent exact-head review and local Conventional Commit pending.
- Upstream owner adoption hold remains; no remote shipping in this Task.
- Full single-command release and real-candidate acceptance remain outstanding.

### Retained verification and failed iterations

All paths below are private local evidence, not portable release evidence or
claims about a published Build. The fixture Build is derived from its manifests.
Python is 3.14.7; Node is the pinned local 22.22.2 toolchain. No timeout, suite
selection invariant, coverage floor or protection was weakened.

- `/tmp/lmdj-candidate-transition-docs-v1.log`: exit 0, 170 tests, no failures or
  skips, 47 routes. Current Portal page bytes were checked; not a public deploy.
  The fresh v2 check also passed 170/170 and 47 routes, exit 0.
- `/tmp/lmdj-candidate-transition-scope-v2.log`: all 12 declared files staged;
  ownership and admission 74/74 passed, exit 0 (8.297 seconds).
- `/tmp/lmdj-candidate-transition-verification-inputs-v2.sha256`: frozen
  digests of all 11 implementation/test/Portal inputs (the changing acceptance
  plan is excluded). Rechecked unchanged after the new full runs began.
- `/tmp/lmdj-candidate-transition-install-v1.log`: official npm install exit 0;
  npm reported 27 existing dependency vulnerabilities (9 moderate, 18 high).
  This Task does not change dependencies or claim these resolved.
- `/tmp/lmdj-candidate-transition-existing-pr-v1.log`,
  `...-existing-managed-v1.log`, `...-existing-driver-v1.log`: respectively
  36/36, 26/26 and 32/32 passed, exit 0 before final review refinements.
- `/tmp/lmdj-candidate-transition-components-ctest-v1.log`: 19/19 groups,
  23 actual cases, exit 0 (662.71 seconds).
  `/tmp/lmdj-candidate-transition-journey-ctest-v1.log`: 1/1 group and actual
  journey case, exit 0 (676.31 seconds). These predate the final workspace fix
  and added recovery legs. They ran concurrently in the same build directory:
  retain the separate outer logs and collected exits, not the shared CTest
  `LastTest.log`, as each run's transcript. The final registered run is serial.
- `/tmp/lmdj-candidate-workspace-late-guard-v1.log`: the two real late-callback
  deletion regressions pass, exit 0, 76.373 seconds.
- `/tmp/lmdj-candidate-workspace-old-guard-probe-v1.log`: external causal
  negative loaded the unchanged staged pre-fix module in memory without editing
  source files. Both new regression assertions fail for the missing refusal
  (85.671 seconds); no fixture/setup errors. The probe wrapper exits 0 because
  it expected precisely those two failures, not because the old code passed.
- `/tmp/lmdj-candidate-transition-boundaries-v1.log`: parent history deletion,
  traceback secrecy and pending-review boundary, 3/3 passed, exit 0.
- `/tmp/lmdj-candidate-receipt-recovery-v1.log`: exit 1, 10/11 passed; the test
  expected a return where missing enrolled history correctly raises. Corrected
  the assertion, not the product refusal. v2 passed 11/11 before the twelfth
  traceback case was added and passed in the registered component run.
- `/tmp/lmdj-candidate-task-workspace-v1.log`: exit 1, zero executed tests and
  two setup errors because a fixture helper shadowed the inherited producer.
  Renamed the helper; v2 passed 8/8, exit 0 before the final two regressions.
- `/tmp/lmdj-candidate-transition-v1.log`: exit 1, two fixture errors: the
  request was not the canonical repository. Corrected the fixture before real
  material/source production, without rewriting receipts. v2: exit 1, two
  failures because the transport fixture wrongly required a remote argument
  for scratch Git init; narrowed that assertion to remote commands. The
  diagnostic log's exit 0 only records the captured failure, not a passing
  journey. v3 passed 2/2, exit 0 before later parent/review refinements.
- `/tmp/lmdj-candidate-transition-recovery-v1.log`: exit 1, three of four new
  cases passed; the fourth reached recovery but used a nonexistent fixture
  `hashlib` attribute. Added an explicit standard-library import. Final
  registered verification covers the corrected assertion.
- `/private/tmp/lmdj-candidate-transition-portal-v1.mBWWYT/run-v1` and
  `/tmp/lmdj-candidate-transition-portal-v1.log`: retained actual Portal
  integration diagnostic completed with exit 0. It imported the pre-final workspace
  guard, so it is not final-byte acceptance. Controller
  and harness digests are recorded separately from fixture base HEAD.
  Its 17 actual command spools, two real branch pushes, POST/PUT/POST/PUT local
  API effects, cold state/output stability and source-absent fresh-clone Portal
  check all passed. The fresh-clone check returned exit 0; source `cat-file -e`
  returned the expected exit 1 both before and after that check. The outer log
  SHA-256 is `26fb60967ed2deea347599aca1a75ea15be81a49ab1ef7cf55c97da63c442847`;
  events are `0699c86ab826b59d8210c537b7c0a450e8a8978ecbc5a08e2951dfbaaf524411`.
- The final six timeout groups' isolated follow-up is recorded below, including
  its retained failure and subsequent measured environment correction.
  Exact-head independent review remains pending until the local commit exists.
- `/tmp/lmdj-candidate-transition-final-ctest-v2.log`: serial 64-group related
  regression run completed with exit 8, 58 passing groups and 6 timeout groups
  in 4048.02 seconds. The 58 completed unittest groups report 322 executed cases,
  no skips. This is not an all-green run. Full raw output is preserved separately
  in `/tmp/lmdj-candidate-transition-final-ctest-v2.raw.log` (SHA-256
  `06cf91ab56e7f5be8e63f58f1490b63a2a5688b69d0b88b73c91251aadf51767`),
  so later CTest runs cannot overwrite the failure evidence. The outer log is
  SHA-256 `1dcee7b035c052dfad1275543d299cd468f69f8629a75ab1667ab6762c2eb510`.
  The installed-child process-death case hit its
  unchanged 90-second timeout (90.14 seconds), with no unittest case-start output
  in the raw transcript. Two actual Portal builds ran
  concurrently; read-only resource observations recorded approximately 9.6 GiB
  swap use in `/tmp/lmdj-candidate-transition-resource-swap-v1.log` and VM stats
  in `...-resource-vm-v1.log`. These observations do not prove the timeout cause.
  Preserve this failure and check the identical case without concurrent Portal
  builds under the original bound; do not increase the timeout or report the
  interrupted case as executed successfully.
  A later full-log audit found a second, earlier timeout omitted by tail-only
  progress reporting: confirmed witness recovery at the attempt limit reached
  its original 60-second bound (60.20 seconds). Both failures remain in the raw
  run; the earlier one-timeout progress count was incomplete, not a reclassified
  passing test. Monitor the entire result population thereafter. The complete
  composed journey subsequently passed in 804.38 seconds under its unchanged
  900-second bound, including later-main stability and real artifact drift.
  The existing `release_witness_pr_journey` group later timed out at 120.02
  seconds: its first actual case prints `ok`, but the two-case group has no
  completed summary. This is the third failed group, not a passing journey;
  include the entire unchanged group in the same isolated follow-up.
  `release_witness_source_binding` then hit 120.04 seconds with four named
  passing cases but no group completion. It is the fourth failed group; those
  passing prefixes do not complete the group. A subsequent read-only process
  sample (`...-resource-processes-v1.log`) also shows active macOS metadata
  indexing. No system indexing, host settings or test bounds were changed,
  and the observation alone is not a causal performance diagnosis.
  `release_witness_source_merge` and `release_witness_source_history` also
  timed out at 120.04 seconds each. The final six-group failure inventory is:
  witness receipt at budget limit, workspace installation process death,
  witness PR journey, and witness source binding/merge/history. Recheck these
  exact entire groups under their unchanged 60/90/120-second bounds only after
  both heavy Portal rehearsals end. That follow-up is now running serially as
  `/tmp/lmdj-candidate-transition-isolated-ctest-v1.log`; no result is assumed.
- The isolated six-group follow-up subsequently completed with exit 8 in
  573.19 seconds: the receipt and workspace process-death groups passed under
  their unchanged bounds (30.88 and 62.13 seconds), while witness PR journey
  and source binding/merge/history again timed out at 120.04 seconds each.
  Each source group has four named passing prefixes, not completed coverage.
  The original raw transcript is retained separately in
  `/tmp/lmdj-candidate-transition-isolated-ctest-v1.raw.log` (SHA-256
  `dda31e02f700ba0a3be2d7ba1cf49b1410a5c425e63ad1b7dca46423f044c149`);
  outer log SHA-256 is
  `565de56feb24ce75253bf4d094f992e0647e4ce48dde71947a9389c3bd08fe46`.
  No concurrent
  Portal rehearsal remained, so the earlier resource correlation does not
  establish or discharge the cause. Do not rerun blindly or widen budgets.
  A bounded single-case cProfile diagnostic is next; it is not a replacement
  for any of the full failed groups. No production input was edited for it.
- `/tmp/lmdj-candidate-transition-profile-v1.log` and `.prof`: the bounded
  single positive source-consumer diagnostic passed 1/1 in 55.625 seconds.
  Its 1281 workspace Git calls consumed 52.658 seconds and 2569 subprocess
  invocations consumed 52.485 seconds. Class setup took 23.823 seconds,
  Task preparation 14.412 seconds and two actual consumer checks 16.192 seconds.
  This identifies repeated child-launch cost, not a failed witness assertion.
  `/usr/bin/git` and `xcrun --find git`'s selected executable
  `/Library/Developer/CommandLineTools/usr/bin/git` both report
  `2.54.0 (Apple Git-157)`. Alternating 30-invocation comparisons in
  `/tmp/lmdj-candidate-transition-git-launch-benchmark-v1.log` measured about
  18 ms versus 8 ms per launch with identical version and HEAD output.
  An initial interpretation of the JSON-rendered log incorrectly called the
  third filter regex overescaped. A subsequent AST/literal comparison confirmed
  both the v1 recorded query and the separately retained
  `...-git-config-benchmark-v2.py` query are byte-identical to production:
  45 bytes, two backslashes, and a positive match for `filter.example.clean`.
  No query correction was actually needed; the v2 run is an independent
  repeated measurement (about 20 ms versus 10 ms), not a fixed-code acceptance.
  A dedicated temporary bin directory contains only a symlink to the existing
  selected Git; placing it before `/usr/bin` changes only command-local Git
  resolution. Node 22.22.2, Python 3.14.7, all code, six full test groups and
  60/90/120-second bounds are unchanged. No global PATH, xcode-select, tool
  installation, host setting, fixture or production guard is modified.
  The causal six-group follow-up is running as
  `/tmp/lmdj-candidate-transition-direct-git-ctest-v1.log`; the benchmark alone
  does not establish its acceptance and no result is assumed.
- That direct-Git follow-up subsequently completed with exit 0: all six full
  groups passed, 19 unittest cases, no skips, in 321.78 seconds. Group times
  were 15.65, 29.31, 71.48, 66.50, 69.46 and 69.37 seconds respectively,
  under the original 60/90/120-second budgets. The exact command-local PATH was
  `/Users/endaye/.nvm/versions/node/v22.22.2/bin:/opt/homebrew/bin:/tmp/lmdj-candidate-direct-git-v1.LUqG6j:/usr/bin:/bin:/usr/sbin:/sbin`;
  the private bin contains only `git` linked to
  `/Library/Developer/CommandLineTools/usr/bin/git` (SHA-256
  `a73bf622a2e470d5d57a4b1d5aef1e8680e67278018d4858a2f93825b7d595c7`).
  The raw group transcript is retained in
  `/tmp/lmdj-candidate-transition-direct-git-ctest-v1.raw.log` (SHA-256
  `d23875fbd62915ff0a6a9bb97fd897109a468f60543be3af149942c132f0b0da`);
  outer log SHA-256 is
  `a378f349a5c5233131f7c4ab9f7de29284e44f4ef1037910fca92b6b380f8ca2`.
  Together with the original 58 completed groups / 322 cases, all 64 selected
  groups now have completed passing evidence for the unchanged implementation
  inputs. This is 341 cases across explicit environments, not a rewritten
  single green 64-group run or a claim that the original launch environment
  passed. The original exit-8 runs remain failures. No fixture optimization,
  test omission, timeout change or production guard reduction was applied.
- `/private/tmp/lmdj-candidate-transition-portal-v2.zGHwDs/run-v2` and
  `/tmp/lmdj-candidate-transition-portal-v2.log`: fresh latest-controller actual
  Portal journey completed with exit 0. Snapshot, all six actual cut checks, official
  witness, owned installation and all six actual witness Task checks passed.
  Both local PR squashes exist, and the parent has verified the witness merge.
  Driver candidate confirmation passed and stopped at `verification`; cold
  recovery left the complete state and actual output inventory unchanged (17
  spools, two create-only Git pushes and POST/PUT/POST/PUT). The no-local fresh
  main clone lacks the private source both before and after its official Portal
  check (expected `cat-file -e` exit 1). That check passed 170/170, no skips,
  47 routes, exit 0; the final working tree is clean. The outer log is SHA-256
  `c0bb05ea6df97c4c69a73276fdf09327ab873fd92267f70aefdad19a619ba657`, and the
  events SHA-256 is `546ebbb43f9af573948f7c29ff7de68243a9f1c9e4d11564437dbaf01f744a8b`.
  The frozen fixture candidate is `f18f1b025e0bf8b929e14342fe1da32c2f73f54e`;
  witness squash is distinct `1262c70c2bcb243a5d0b6ce9eab54fdff4ccfd39`.
  The witness has 10995 bytes and SHA-256
  `d9300ace4e49c786ee920ea7c999345b1bc84c09554cfce98f04c14720282d86`.
  The older v1 diagnostic does not replace this latest-byte run. The 11 frozen
  implementation/test/Portal input digests remain unchanged.

Pitfall disposition: the new callback/history defects are product invariants
directly expressed by regression tests, not new process-ledger entries. The
measured macOS Git launch overhead is environment knowledge not derivable from
the product code; record its diagnostic procedure in
`.agents/pitfalls/macos-git-launch-overhead.md` without a universal new gate.
Earlier failure evidence is retained; no historical result is rewritten as
success.
