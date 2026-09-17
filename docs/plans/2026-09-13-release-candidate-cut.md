# Recoverable complete candidate cut commit

Delivery base: bd02736f9ee99175d3b26665e16163cbfbdd903f.
Original Task: 0fcffb83703fe6d0d0335ddcab9fd407e4e399e0 (base
af04ba5237ee34c9b5a00f786fb2e04dc76f7975). Retain original-stack evidence
below as history, not validation of this delivery base. Incorporate the
canonical cut-path correction from c259fd12f7fbb1edae4f364f361f75e14a4f922a;
the parent already preserves canonical snapshot paths and actual symlinks.

## Task and files

Consume the actual installed source binding and durable verified snapshot state.
Build one deterministic Conventional Commit whose parent is the original input
baseline and whose exact diff is the four generated source files plus the
verified snapshot inventory. Do not push the intermediate source commit or
regenerate a snapshot. Retain the original source object under a request-bound
local ref until the later squash/witness proof is complete.

Declared files:

- tools/release/candidate_cut.py
- tools/release/candidate_snapshot.py
- tests/build/release_candidate_cut_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-cut.md

Share the existing source-worktree writer lock and snapshot state validator.
Require original authorization, successful resume command evidence and exact
snapshot digest; inspect raw files rather than filtered Git diff. Bound paths
to this Build's snapshot, require source revision/channel/time consistency and
preserve unknown edits. Construct the final tree in a private index and persist
the exact cut binding before updating the real index or branch. Verify the
staged Task, retain source with a create-only expected-absent ref, and advance
the candidate branch with an expected-source guard. Reverify the committed Task
and retained source before returning cut-committed. Failed postcommit checks
keep the commit and block success; resume verifies that same commit.
Snapshot state v2 separately records the command count whose post-command
authority, source and output checks completed. A later zero exit followed by
failed postchecks does not admit a cut. Old v1 records without that confirmation
boundary refuse; they are not silently upgraded into successful evidence.

## Verification

Actual temporary Git reservation, source material installation and snapshot
command journal feed the cut installer. Cover exact one-commit diff/parent,
source retention, revalidation without ref replay, staged-verification failure,
actual process death after index/ref writes, snapshot drift, unknown untracked
files, backdated commit, retention collision, missing binding after staging and
failed postcommit verification followed by recovery.

The snapshot subprocess remains a small Bash fixture, and Task verification is
a source/metadata fixture callback, not the full Portal generator or release
proof. The official snapshot/provenance Node suites remain companion evidence;
a full actual generator -> cut -> fresh-clone/squash/witness journey is still
required. Production authorization/toolchain/config intake, real Task verifier
composition, push/PR/current-head review/squash, witness and exact-target CI
remain parent obligations, not facts proved by a local cut receipt.

Run both cut suites at the existing 30-second contract budget, both snapshot
runner suites after validator extraction, staged ownership and full Portal.
No real Build allocation, remote write, signing, publication or deployment.

### Delivery verification and fixture boundaries

- On the delivery base, the original cut allowlist rejected the actual emitted
  canonical snapshot inventory: 1 error, exit 1, 9.245 seconds, retained in
  /tmp/lmdj-candidate-cut-delivery-canonical-red-v1.log. This is a real
  source -> Bash snapshot -> cut failure, not a Docusaurus generator failure.
  The cut now accepts only the official archive paths already emitted by its
  parent snapshot runner; active-site aliases remain unchanged.
- Direct cut verification passed 12/12, exit 0, 36.480 seconds:
  /tmp/lmdj-candidate-cut-delivery-tests-v1.log. The 11 original cases remain;
  one additional case explicitly materializes a canonical legacy v1 state,
  then proves refusal without rewriting it or changing HEAD/index/cut binding.
  That controlled legacy fixture is not a historical production transcript.
- Each serial cut test class creates one seed through the real reservation,
  source installer, Bash snapshot subprocess and verified-state consumer.
  Each case restores the entire emitted temporary container at its original
  paths, preserving Git pointers, identities, modes and symbolic links, and
  creates fresh controller objects. Writer closure is checked after each case.
  Source/snapshot production is therefore once per class, not once per cut
  case. Every staged/ref/crash/recovery cut transition still executes per case.
  The companion snapshot recovery suite retains fresh producer journeys.
- Keep the original two cut registrations and two snapshot registrations at
  30 seconds each. Fixture setup reuse adds no test groups, omits no case,
  alters no production path and increases no timeout or execution allowance.
- Independent review inspected all six files, canonical paths, v2 confirmation,
  legacy refusal and actual seed-copy isolation; no actionable findings. Its
  initial delivery review was static, not an independent test execution.
- Configured development CTest passed 4/4 registrations, exit 0, 79.61 seconds:
  /tmp/lmdj-candidate-cut-delivery-ctest-v1.log. Actual child populations were
  cut recovery 5/5 (20.174s), cut safety 7/7 (15.557s), snapshot recovery 4/4
  (26.972s), snapshot safety 10/10 (16.247s). All 26 cases ran; none skipped.
- Staged ownership passed 74/74, exit 0, 5.874 seconds:
  /tmp/lmdj-candidate-cut-delivery-scope-v1.log. Locked dependency installation
  and development configuration both exited 0; logs use the same delivery
  prefix with deps-v1 and configure-v1 suffixes.
- Both cut classes also passed all 12 cases in reverse method order under the
  configured Python 3.14 interpreter, exit 0, 36.587 seconds:
  /tmp/lmdj-candidate-cut-delivery-reverse-v1.log. The real crash/ref operations
  ran again; no state from an earlier case made a later case pass.
- Node 22 scripts/docs-site.sh check exited 0: 159/159 tests, zero skipped,
  production build and 47 routes/internal links passed. Evidence:
  /tmp/lmdj-candidate-cut-delivery-docs-v1.log. The generated operations HTML
  contains the cut/recovery and v2/legacy boundaries; four rendered assertions
  passed in /tmp/lmdj-candidate-cut-delivery-rendered-v1.log. This is a current
  Portal build, not a new immutable Product Build snapshot.
- No new process-only pitfall: the canonical path mismatch and confirmation
  boundary are directly expressed by controller code and causal regressions.
  Preserve the inherited witness, real-generator and service acceptance gaps.

### Historical original-stack evidence and retained limits

- Initial cut fixtures: 10/10 passed, exit 0, 42.668 seconds;
  /tmp/lmdj-candidate-cut-tests-v1.log. Independent review inspected the six-file
  diff and independently ran these 10 cases successfully (44.082 seconds).
- Added an actual exit-0/post-authorization-failure regression when introducing
  the shared consumer: /tmp/lmdj-candidate-cut-postcommand.log, 1/1 passed.
  The retained state has an actual zero exit but an older confirmation count;
  the cut refuses before creating its binding. This is not a reconstructed
  transcript of an earlier failure.
- Final registered CTest selection passed all four suites, exit 0, 87.89 seconds:
  11 cut cases and 14 original snapshot-runner cases. Log:
  /tmp/lmdj-candidate-cut-ctest-v1.log. No tests were skipped or timeouts widened.
- Final staged ownership passed 74/74, exit 0;
  /tmp/lmdj-candidate-cut-scope-final.log.
- Node 22 scripts/docs-site.sh check passed, exit 0: 151 tests, production
  build and 47 routes/internal links. Log: /tmp/lmdj-candidate-cut-portal.log.
  Inspected the actual generated operations page for the complete local cut
  paragraph; this current Portal build is not a new immutable snapshot.
- Final independent review is clean, including the separate v2 confirmation
  boundary review. That last addition was inspected, not independently rerun.
- Pitfall disposition: source retention preserves the existing squash-witness
  obligation; no witness was generated or hand-authored. Snapshot confirmation
  is now a directly tested state invariant, not a new process-only ledger entry.
  Callback source/metadata checks and the Bash generator remain fixtures; they
  do not prove actual Portal freeze, remote review/merge, fresh-clone witness,
  full 16-suite candidate evidence, signed release or service readiness.

## Version Management

Version impact: none

Reason: local cut controller development; all generated candidates exist only
in temporary fixtures, not as team-testing or release Product Builds.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
