# Owned candidate source setup

Status: implementation, declared local verification and independent precommit
review complete. Local dependent stack only, based on
`281b9950df0db9ad9eb21e0118288724d7876032`. No remote shipping, provider,
signing, release, deployment or host/authentication mutation.

## Task

Replace the manual candidate source-worktree/install precondition with a
request-bound local child. Freeze original passive inputs, recover the actual
reservation without allocating from observation, positively establish branch and
path absence before an owned create, and retain the real official installation
command's intent/result. Recovery may recognize completed reservation/checkout
effects, but must never recreate missing enrolled history or replay an unknown
or failed installation. The caller must supply original authenticated request,
main/control/toolchain authority and an explicitly provisioned shared catalogue.

This is a prerequisite for composing request -> source -> snapshot -> checked
cut -> managed candidate. It is not that entire factory or the run/status/resume
CLI, a completed candidate, complete CI, or a real release. Subsequent source,
snapshot and cut consumers still verify their own actual bytes and commands.

## Declared files

- `tools/release/candidate.py`
- `tools/release/candidate_source_setup.py`
- `tests/build/release_candidate_source_setup_test.py`
- `tests/build/release_candidate_portal_journey.py`
- `.agents/pitfalls/macos-git-launch-overhead.md`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- this plan

## Verification

Lowest tier: real temporary Git and provisioned reservation catalogue, real
linked worktree and actual command executor with an explicitly narrow install
entrypoint fixture. Exercise passive absence, completed setup -> actual source
consumer, cold recovery, fixed reservation, unknown create/install, nonzero
install, callback history loss, changed request/main/path and missing catalogue.
Use real fork/exit where process-death acceptance is claimed; check actual
Git registration, source bytes and complete command result identity on the far
side of each executed leg. The fixture is not npm installation acceptance.

Run existing reservation/material/source-workspace tests, register all new tests
under unchanged existing budgets, run staged ownership/admission, and run the
current Portal check. Separately exercise the new child against actual repository
inputs and the unchanged official `scripts/docs-site.sh install`, then consume
its owned workspace through the real source generator. No GitHub/provider call.
Retain failed iterations. Use the verified selected macOS Git executable through
a command-local private bin, never a timeout or assertion change.

## Version Management

Version impact: none

Reason: local orchestration development; only disposable fixture reservations
and generated fixture manifests change. No real Product Build is allocated.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Describe the new source-setup boundary and remaining composition/CLI/production
gaps without claiming unattended release availability.

## Acceptance ledger

- Implemented the passive reservation reader and owned source setup child;
  final verification and independent approval are pending.
- First direct reader run: 3/3 passed, exit 0, 3.283 seconds;
  `/tmp/lmdj-candidate-source-setup-reader-v1.log`.
- First lifecycle/boundary subset: 12/12 passed, exit 0, 52.723 seconds;
  `/tmp/lmdj-candidate-source-setup-lifecycle-v1.log`. Later regressions are not
  included in that historical subset.
- Review identified Python numeric equality accepting an integer-to-float scope
  change, and a catalogue removed by a late authority callback being accepted
  from a cached reservation. Both actual single-fact tests failed before the
  fixes with `CandidateSourceSetupError not raised` (1/1 each, exit 1):
  `/tmp/lmdj-candidate-source-setup-numeric-red-v1.log` and
  `/tmp/lmdj-candidate-source-setup-catalogue-red-v1.log`.
  Canonical byte identity and post-callback reservation reads fix the causes;
  their focused rerun passed 2/2, exit 0, 7.440 seconds in
  `/tmp/lmdj-candidate-source-setup-guards-v1.log`.
- The full new selection also covers live orphan installer FD retention for
  both writers after actual controller SIGKILL; it is not inferred from
  `pass_fds` arguments or the already completed-child death case.
- First related CTest run finished 10/11 groups passing, exit 8, 250.66 seconds in
  `/tmp/lmdj-candidate-source-setup-ctest-v1.log`, under original existing
  budgets and the declared new 60/120-second group bounds. The unchanged source
  safety test errored because the temporary symlink Git did not install init
  templates (`.git/info/attributes` parent absent). Raw CTest output is retained
  in `/tmp/lmdj-candidate-source-setup-ctest-v1.raw.log`; no assertion was changed.
- Corrected the same toolchain investigation's pitfall guidance. A four-way
  actual init probe in `/tmp/lmdj-candidate-source-setup-git-prefix-v1.log`
  shows the symlink selected an Xcode exec path and absent templates, while
  `/usr/bin/git`, the absolute Command Line Tools binary, and a thin wrapper
  preserve the Command Line Tools exec path, identical exclude bytes and all
  14 sample hooks. Earlier symlink-environment passes remain historical, not
  equivalent-environment acceptance. The current wrapper is
  `/tmp/lmdj-candidate-direct-git-v2.EjRD5X/git`, executing
  `/Library/Developer/CommandLineTools/usr/bin/git` by its original absolute path.
- Independent review found that a late callback could advance actual main
  through a BUILD increase and revert, leaving original endpoint bytes but a
  higher history floor. The focused test reproduced acceptance before the fix:
  1/1 failed, exit 1, 19.904 seconds in
  `/tmp/lmdj-candidate-source-setup-highwater-red-v1.log`. Live-write guards now
  reread reservation history against fresh main, while completed historical
  setup observation keeps its original base. The same test passes 1/1,
  exit 0, 10.316 seconds in
  `/tmp/lmdj-candidate-source-setup-highwater-green-v1.log`, asserting no checkout,
  no installation and no new reservation. The entire related selection is being
  rerun under the corrected wrapper; no new final result is assumed.
- Wrapper run v2 completed 7/11 groups passing and four timeouts, exit 8,
  405.94 seconds: workspace recovery, setup lifecycle, setup boundary and
  reservation groups. Both `/tmp/lmdj-candidate-source-setup-ctest-v2.log` and
  its `.raw.log` companion are retained. The init-template regression passed.
  A current 20-launch median probe measured 22.3 ms for `/usr/bin/git`, 14.0 ms
  for the wrapper, and 8.3 ms for the original absolute Command Line Tools Git.
  These are diagnostic measurements, not passing test evidence.
- The final rerun selects the existing original Git directory command-locally:
  `/Users/endaye/.nvm/versions/node/v22.22.2/bin:/opt/homebrew/bin:/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin`.
  Resolution of Python, Node, npm, bash, cmake, ctest, sh and tar was compared
  against the wrapper PATH and is unchanged. No global setting, test assertion
  or timeout changed. Run v3 is pending.
- The first official-install rehearsal used the pre-review harness capture
  scope. Its actual install passed, but that run cannot independently prove
  cold no-reexecution from spool count because cold entries were outside the
  capture patch. The harness now captures all cold entries and checks the same
  output inventory and bytes; a fresh final rehearsal remains required.
- Final CTest v3 passed all 11/11 groups and 84/84 unittest cases, exit 0,
  284.01 seconds. The group case counts are 4/2/9/11/3/6/11/1/1/20/16;
  all 22 new setup cases ran. Retained outer/raw logs:
  `/tmp/lmdj-candidate-source-setup-ctest-v3.log` and
  `/tmp/lmdj-candidate-source-setup-ctest-v3.raw.log` (raw SHA-256
  `4a71082a7bc5ea8c95c965fcc4960027fba8da4f74c221aed73f087065f83938`).
  This is a complete related selection, not a complete release CI run or a
  retrospective equivalent-environment rerun of every predecessor Task group.
- Staged eight-file ownership/admission passed 74/74, exit 0, 6.434 seconds:
  `/tmp/lmdj-candidate-source-setup-ownership-v1.log`. Independent complete
  staged static review found no remaining findings; final dynamic evidence and
  exact committed-head review remain pending.
- Official control-worktree installation passed, exit 0, with the locked
  dependencies unchanged. npm reported 27 existing dependency vulnerabilities
  (9 moderate, 18 high); no audit fix, lock update or package upgrade was run.
  `/tmp/lmdj-candidate-source-setup-control-install-v1.log` is retained.
- Current Portal `scripts/docs-site.sh check` passed, exit 0: 170/170 tests,
  47 pages, 10 diagram sources/20 outputs, Host and release changelog validation,
  full static build and 47 routes/internal links. Raw log:
  `/tmp/lmdj-candidate-source-setup-portal-v1.log`. This is local current Portal
  proof, not a new immutable snapshot or production publication.
- Verification inputs for the two product modules, new tests, actual harness,
  CMake registration and Portal page are frozen in
  `/tmp/lmdj-candidate-source-setup-verification-inputs-v1.sha256`; all six
  entries rechecked unchanged after the runs. Plan/ledger evidence additions
  do not replace or overwrite any earlier raw failure.
- Fresh official rehearsal v2 passed, exit 0, under the final direct Git PATH:
  `/private/tmp/lmdj-candidate-source-setup-official-v1.5iTrJ8/run-v2`.
  Actual child creation and official npm installation fed actual source
  generation and canonical Assembly/lock verification. All cold entries stayed
  under output capture; the one command spool and all three original histories
  remained byte-identical before and after source consumption. The command
  output was 887 bytes, SHA-256
  `35a70dabb1a7201b74edea6d5f40470bca09cbb18f400241a2b383d452fca6b0`.
  Source fixture commit `e6d3d2cf0413662e5a42a7aa4ee45672fdea371e` has tree
  `815a3d3bc3c68d879c56cf21af10de97647b4803`; no real Product allocation.
  Outer log `/tmp/lmdj-candidate-source-setup-official-v2.log` SHA-256
  `b6fe82e4af125dc331ea591554451a473b1232b0cb35ba77979fce6b7bb5ff7c`;
  `run-v2/events.jsonl` SHA-256
  `85fefb8e5dfd32a5df16122ea424c67a24c364b502692259af3c03708c230246`.
  Controller/harness hashes are recorded separately from the cloned parent
  fixture revision. This source-only leg executes no snapshot, review, PR,
  GitHub operation, signing, release, deployment or promotion.
- Independent reviewer `release_journal_review` inspected the complete staged
  eight-file Task and actual final artifacts, confirmed the six verification
  input hashes, 11/11 groups/84 cases, unique official command output and original
  histories, and reported no remaining finding. This supports the local Task
  commit only; it is not repository-owner adoption or remote merge eligibility.
- Upstream owner-adoption hold and all real-release acceptance gaps remain.
