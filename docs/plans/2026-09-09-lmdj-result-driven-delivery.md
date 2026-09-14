# Result-driven testing, Issue reporting and canary delivery

Status: implementation in progress; no deployment activation or release.

## Settled scope and order

This plan supersedes the daily deployment trigger proposed in the September 8
canary design. Keep ordinary PR review, relevant Task verification, conflicts and
conversation protection without strict/full-CI merge gates. CI reports failures;
external people/tools repair them through ordinary PRs. No autonomous repair,
repair-PR merger or OpenClaw orchestration is part of CI.

1. Verify main incremental execution, terminal persistence and next-batch
   coverage. Diagnose pending/failed controllers before adding delivery work.
2. Verify durable Issue reporting, unavailable-versus-failed results and scoped
   revalidation after an external repair. A green unrelated suite cannot erase
   defects/debt; reporting retries never rerun product tests or blindly repeat
   an uncertain Issue POST. CI does not automatically close defect Issues.
3. Reuse the read-only canary planner for independent version-accounted/site/
   formal progress. Add bounded GLM→Kimi→Grok version advice, deterministic
   validation and normal version/changelog PR preparation. Final merged
   candidates need applicable evidence, not a pre-version-commit green result.
4. Successful result persistence wakes conditional delivery; manual requests
   and lightweight recovery share the same coordinator. No date-based tests
   or deployments. Coalesce pending work, pin candidates and verify all required
   scopes/debt before delivery. Missing events are recovered from durable
   state; metadata-only preparation cannot recursively allocate versions.
5. Deploy changed sites to independent canary addresses only. Build complete
   same-candidate Host assets, verify/sign/publish, then accept each fixed site
   before advancing its own progress. docs-only needs no Product allocation.
6. Owner-selected exact canary promotion requires applicable complete 16-suite
   evidence and artifact/compatibility acceptance. Reuse tested bytes and tag;
   promotion never rebuilds main or silently deploys a formal site. Resolve the
   existing stable-policy question before enabling its mutation.

The existing Netcup instance must first prove a deployment isolation boundary
separate from ordinary CI/AI execution. Users, labels or ordinary containers
alone are not acceptance. If suitable isolation is unavailable, keep delivery
disabled; do not buy a host, move keys or expose privileged credentials as an
implicit fallback. Retain the authorized macOS hosted recovery exception and
measure it separately. No zero-total-cost claim.

Cut over docs first, Product canary second, formal promotion last; disable old
overlapping triggers with each replacement. Preserve in-flight operations and
pause/reconcile rollback, never reset journals or restore daily full CI.

## Follow-up — Stacked PR compatibility

Status: planned, not implemented or accepted. This is an optional developer
workflow after the core testing/reporting/delivery chain is connected, not a
prerequisite for completing the six original steps above. Track its acceptance
separately; completion of those steps must not imply stacked PR support.

Goal: let dependent changes develop and receive focused review before their
prerequisites merge. Pilot a same-repository, linear stack of two or three PRs;
independent work continues to branch directly from main. Do not require Graphite
or another vendor, introduce a stack-wide full-CI gate, or promise fewer test
runs merely because PRs belong to one stack.

The current `.github/workflows/pr-review.yml` filters PR targets to `main`, and
`scripts/ci/review_scope.py` requires a main-target PR when authenticating review
evidence. Existing temporary stacked development is not proof that an upper PR
is automatically reviewed. Extend event admission and receipt validation together;
removing the branch filter alone is not sufficient or an accepted security change.

### Implementation work and boundaries

- **S1 — Layer-aware review.** Bind repository, PR/dependency identities, exact
  parent base, head, trusted main control and policy to each review input and
  receipt. Review the layer's own delta with sufficient dependency context, not
  the cumulative stack as if every layer authored it. Treat unmerged dependency
  files as untrusted data, never as credential-bearing executable control code.
  Target files: `.github/workflows/pr-review.yml`,
  `scripts/ci/review_pipeline.py`, `scripts/ci/review_scope.py`,
  `tests/build/ci_pr_review_workflow_test.py` and
  `tests/build/ci_review_scope_test.py`. Declare any necessary codec/consumer
  migrations and their tests in the focused implementation Task before editing.
- **S2 — Restack and merge evidence.** Merge bottom-up into main, retargeting and
  restacking upper PRs after a prerequisite squash merge. Recheck exact current
  head, conflicts and conversations. A changed head, dependency input or review
  base invalidates the previous current-input review; the initial implementation
  obtains fresh review or a documented exact-input takeover. Cross-SHA evidence
  reuse is deferred, not inferred from similar diffs. Duplicate callbacks for the
  same authenticated input must not create duplicate review publications; retain
  original receipts and reject stale publications. Target files:
  `scripts/ci/review_pipeline.py`, `scripts/ci/review_merge_map.py`,
  `scripts/ci/review_merge_map_reader.py` and their existing `ci_*_test.py` suites.
  S1 and S2 share review-pipeline ownership and are sequential, not independent
  agent workstreams. Reject cyclic, missing or closed-unmerged dependencies;
  unsupported stack shapes use the ordinary main-target workflow explicitly.
- **S3 — Main-batch compatibility and pilot.** Preserve the complete first-parent
  main interval, deterministic scope floor, affected-consumer closure, eligible
  debt and authenticated review-scope union. Upper-layer advisory scope must not
  shrink cumulative coverage. Keep the active target fixed; later merges coalesce
  pending, without requiring an entire stack to finish or creating a second stack
  test scheduler. Target tests: `tests/build/ci_test_scope_test.py`,
  `tests/build/ci_review_merge_map_reader_test.py` and the existing incremental
  controller journey suites. Update `docs/governance/git-workflow.md` and
  `/operations/testing-and-proof/` with the accepted procedure at implementation.

### Acceptance, not yet exercised

- [ ] Open A against main and B against A: both receive receipts for their exact
  inputs; B's reviewed delta excludes A's already-owned edits but includes the
  dependency context. An independent main-target PR remains unaffected.
- [ ] Change A and restack B: stale receipts cannot publish as current; duplicate
  callbacks do not duplicate publication. Missing/failed review stays visible,
  with existing fallback/reporting semantics, never an assumed clean review.
- [ ] Squash-merge A, retarget/restack B, resolve a real conflict and merge the
  newly reviewed B: authenticate each actual main commit and its scope. Also
  exercise A closed without merge and verify B cannot claim dependency completion.
- [ ] Merge those PRs while a main batch is active: its target does not change;
  after terminal persistence the next interval covers every intervening change,
  including rename/delete/revert paths and outstanding debt. If the merges span
  batches, coverage is complete across them; exactly one batch per stack is not
  required. Verify retained results and reports without version/deploy activation.

Use real-Git regressions in the named lowest-tier suites, then one bounded GitHub
pilot with observable receipts after each transition. Record review calls,
workflow runs, runner time and queue delay; do not claim capacity savings from
local fixtures. No new required merge check is planned. Each implementation Task
must declare exact files and tests; protocol validators retain `why`/`remedy`.

Declared files for this planning-only addition: this plan. Verification:
`git diff --check`, final-diff review against the scope and acceptance above,
and the `docs_static` lane on the committed range. Version impact: none; no
identity or allocation changes. Documentation impact: none for this addition;
it records future work, not implemented Portal behavior. S3 must declare the
Portal update required when the operator procedure actually changes.

## Approved first version baseline — September 9

The owner explicitly confirmed the proposed first version baseline in the
conversation on September 9: `a81faad3b85d362e3e44541cd28ee21dac6848a4`.
The confirmation fixes this exact commit, not a moving `main` reference.
At that revision, `apps/creator-web/module.json` and
`apps/web-runtime-host/module.json` each declare `4.1.0`; preserve both values.
Do not manufacture historical changelog entries or retroactively allocate
versions for changes at or before this baseline. The first automatic version
assessment covers the complete subsequent first-parent interval to its pinned
target; later assessments use independently persisted version-accounted progress.

This is a version-history starting decision only. It does not prove that the
baseline passed tests, was deployed, was released or was promoted. Do not advance
test, site or formal progress, erase failures/debt, or replace existing scheduler
history with this SHA. Existing historical changelog entries remain unchanged.
An assessment target preceding the baseline cannot be treated as a new version
interval. No new runtime baseline field or live journal entry is created by this
documentation Task: the durable bootstrap and planning-to-assessment handoff still
need implementation and acceptance using this approved identity.

The owner also supplied the existing `ssh vienna` access path. Read-only checks
now connect successfully. `systemd-detect-virt` reports `kvm`, but the guest has
no `/dev/kvm`, exposes neither `svm` nor `vmx`, and has no loaded KVM module or
readable nested-virtualization parameter. The command lookup and package query
found no installed QEMU/Firecracker/libvirt/Cloud Hypervisor tools; `sudo -n true`
is unavailable for this session. This does not establish that the provider can
never enable nested virtualization, or that software emulation is impossible.
The accelerated VM/microVM route is not currently ready; no alternative isolation
route has been accepted.
Do not substitute ordinary users/containers or runner labels for the required
isolation. No host package, service, credential, GitHub Environment, readiness
switch or live journal was changed. Provisioning authority and an accepted
isolation route remain prerequisites; deployment and release stay disabled.

Declared files for this decision-record Task: this plan only. Verify the exact
baseline commit and both manifests with Git, run `docs_static` and the Architecture
Portal check, and inspect the final one-file diff and PR declarations. This Task
has no version or Portal-page impact: it records an approved future bootstrap and
read-only prerequisite evidence, without changing live behavior or active identity.

## Task 1 — Bound repeated journal provenance reads

Declared files: this plan, `scripts/ci/batch_github_journal.py`,
`tests/build/ci_batch_github_journal_test.py`, and supersession notices in the
September 8 canary design and implementation plan.

Observed run `34251372817`, attempt 1, failed at `auth-current-run` with HTTP
403 and `remaining=0`; it did not execute product tests. Run `34247801891` had
a cancelled controller after approximately ten minutes. These observations do
not establish one universal cause for all pending runs. The fixed-Issue reader
also repeats workflow/main-ancestry/source verification per distinct historical
writer even when multiple writers share the exact same control identity.

Deduplicate only these already-required control proofs inside one page read,
using bounded concurrent readers and a shared single-flight result. Keep every
writer's exact run and complete job inventory independently verified. Publish
the existing writer trust set only after all page readers succeed. Do not cache
Issue bodies/comments, mutable run/job responses or failures across page reads.
Do not persist proof shortcuts across processes or change journal schemas.

Start with failing request-count regressions, then retain source identity,
malformed ancestry, job mismatch, failed concurrent page, original ordering,
fresh metadata/reopen and unknown-write recovery tests. A 100-writer single-
control page should use 204 REST reads instead of 600 (plus the same GraphQL
page), with all 100 run and 100 job reads preserved. This is fixture request
accounting, not a measured production speedup or proof that rate limiting is
fully resolved.

Verification: journal suite, controller/runtime/entry/report suites, complete
`ci_*_test.py` discovery, staged ownership, Portal check, final range and PR
declarations. Do not lower limits, substitute credentials, cancel external runs
or weaken authentication to make the observation green.

## Task 2 — Read-only Host assessment protocol

The [focused T2a protocol Task](2026-09-09-lmdj-canary-assessment-protocol.md)
adds complete bounded Git input collection, input-bound GLM→Kimi→Grok attempt
records, strict Host/changelog advice validation and stable failure-report
intents. It has no workflow, model invocation, version write or Issue POST.
Live adapters, authenticated PR review collection, chunking, durable outbox
integration and version preparation remain outstanding. This independent
library work does not close the main testing/reporting acceptance gaps below.

The [T2b Host preparation inputs](2026-09-09-lmdj-canary-host-preparation.md)
recollect pinned Git input, compute independent compatible Host bumps and
consume adequate pre-bumps, returning escaped append-only prepared changelog
and manifest edits with complete byte witnesses. No active manifest is changed
by this tooling Task. Canonical Product/Assembly/lock/identity/snapshot generation,
occupancy/fencing, version PR/cut reconciliation and post-squash verification
remain necessary before these Host inputs become a complete allocation.

The [T2c moving-main coverage check](2026-09-09-lmdj-canary-cut-coverage.md)
compares actual reviewed and squash deltas (including paths, modes and Git
objects) and collects every intervening first-parent change under historical
and current scope policy. It distinguishes byte coverage from complete
allocation admission: reviewed GitHub identity, canonical allocation output
proof, fenced occupancy/three-attempt coordinator and snapshot witness are
still required. No live version PR is created by this internal library.

The [T2d assessment runtime](2026-09-09-lmdj-canary-assessment-runtime.md)
executes explicitly configured GLM→Kimi→Grok CLI attempts with complete input,
process-group deadlines, bounded output, private temporary config and a
constructed credential environment. Successful advice and compatibility stops
reuse the protocol; all unavailable backends return a stable report intent.
This unactivated adapter does not authenticate remote input, prove OS isolation
or persist the Issue intent. Real provider acceptance, durable outbox/wake-up
integration and the complete version PR coordinator remain outstanding.

The [T2e assessment journal](2026-09-09-lmdj-canary-assessment-journal.md)
persists complete chunked input and terminal results through the existing
authenticated Journal protocol. Separate claim/execute/complete phases prevent
an observer from repeating a previously claimed model execution. Blocked
results reconstruct deterministic failure reports for the existing outbox,
including restart after an uncertain Issue write. This adds actual storage and
report-adapter composition, not a new database or live storage configuration.
The independent assessment Issue, authenticated workflow phases and retained-
result discovery/reconciliation still need configuration and remote acceptance.

The [T2f canonical metadata proposal](2026-09-09-lmdj-canary-canonical-metadata.md)
composes the existing Host preparer with actual Product/Assembly/lock/compiled
Assembly, Runtime identity and static changelog generators against pinned Git
data in scratch storage. It returns complete file witnesses, preserves caller
edits and rejects stale canonical inputs. The explicit proposed BUILD is not
allocated or proven free. Snapshot creation, authenticated coordinator phases,
fenced occupancy, version PR and post-squash acceptance remain outstanding.

The [T2g authenticated assessment handoff](2026-09-09-lmdj-canary-assessment-handoff.md)
connects the real Actions Runtime and independent assessment Journal to exact
producer/job/artifact verification, durable terminal persistence, canonical
metadata preparation and existing Issue outbox delivery. Recovery retains the
original claim; active/invisible output is pending, and terminal missing or
invalid output reports a reconciliation obligation without fabricating advice.
An already persisted terminal result survives artifact expiry. Independent live
storage and automatic coordinator wiring still require implementation and
remote acceptance.

The [T2h manual assessment entry](2026-09-09-lmdj-canary-assessment-entry.md)
connects explicit init/claim/settle/report commands in a separate manual-only
workflow. A short authenticated controller persists the claim and input before
the credential-isolated bounded producer runs; a fresh observer settles the
original terminal artifact and reports through a separate authenticated outbox.
New claims remain disabled pending accepted disposable VM/microVM isolation,
protected Environment, pinned root-owned binaries and dedicated live storage.
Recovery does not depend on that execution switch. This source entry does not
prove live provider execution, provisioning, storage initialization or automatic
coordinator activation, and does not admit Product allocation or delivery.

The [Host changelog Portal Task](2026-09-09-lmdj-host-changelog-portal.md), merged
in PR #1024 at `262985b6d340b10abe7a978ba3c0ce0174c0619d`, adds independent
Creator and Runtime current pages generated from their own manifests/history.
Prepared entries are not publication/deployment/promotion evidence. Authenticated
state addenda and older-canary promotion presentation remain later T4 work.

## Acceptance ledger

The [approved baseline adoption Task](2026-09-09-lmdj-canary-baseline-adoption.md)
adds the manual `adopt-version-baseline` operation to the existing authenticated
planning entry. It records the reviewed exact baseline and complete approval/Host
manifest bytes in the planning Journal, changing version-accounted progress only.
Same-receipt recovery is idempotent; test/site/formal progress and scheduler
failures/debt are untouched. Live reserved storage and actual adoption remain
unaccepted. The [historical-wakeup reconciliation Task](2026-09-09-lmdj-canary-historical-wakeups.md)
adds durable non-planning observations for authenticated successful targets
strictly before that adopted initial baseline. Complete source and adoption
receipts survive replay without occupying active/pending or changing progress;
subsequent planning retains the full initial site floor. The target equal to
the baseline still plans normally. Source implementation is not live backlog
reconciliation or automatic activation; no scheduler reset or synthetic site
receipt is introduced.
Local planning coverage passes 107 tests; complete CI-contract discovery executes
2,213 tests with one unrelated inherited ledger failure tracked in
[Issue #1078](https://github.com/endaye/lmdj/issues/1078). This is not full-CI green.

The [result discovery integration Task](2026-09-09-lmdj-canary-result-discovery.md)
connects bounded automatic/manual discovery to the existing planning entry,
prioritizing unfinished recovery and retaining complete observations as receipts.
It adds no model, version or deployment execution; readiness/storage activation,
durable adoption of the approved first version baseline and downstream
claim/progress remain separate work.

The [failed review receipt Task](2026-09-09-lmdj-failed-review-receipts.md)
repairs the mismatch between the honestly failed all-backend finalizer and its
success-only report consumer. Complete authenticated failure receipts can enter
the existing outbox without treating arbitrary job failures as backend verdicts.
PR #1068 merged the fix. Controlled run `34311394103/1` delivered the exact
#1061 source `34307707493/1` to Issue #819 comment `5595863850`, with outbox
queue/claim/ack/delivered generations 524–527 verified against the complete
source and exact 558-byte body. Follow-up `34311898608/1` persisted its
`failure-queued` discovery disposition without another target report. Evidence:
[delivery and recovery](https://github.com/endaye/lmdj/pull/1068#issuecomment-5595983824).
This verifies one real failure path, not cleared global backlog or backend repair.

The [page-local common proof Task](2026-09-09-lmdj-journal-page-common-proof.md)
shares validated workflow identity and an exact main SHA within one comment page,
while preserving each distinct control's ancestry/source and every writer's
run/jobs checks. Its different-control request-count fixture is not measured
production savings; report capacity and post-merge delivery need live acceptance.

The [durable planning coordinator](2026-09-09-lmdj-canary-plan-coordinator.md)
connects the authenticated scheduler reader and a dedicated planning Journal to
a manual Actions entry. Explicit bootstrap precedes observation; a small durable
intent freezes complete input identities before chunk storage, and recovery
preserves original decision bytes. One active plan stays pinned while newer
results coalesce pending. This does not execute assessments, retire active work,
advance version/site progress or enable automatic delivery. Live reserved storage
setup, automatic result wiring and downstream completion still require acceptance.

The [shared-client API observation Task](2026-09-09-lmdj-ci-api-observation.md)
adds bounded actual HTTP-attempt counters to controller, reporting, discovery
and relay CLI processes. It enables remote cost measurement without equating
run duration or fixture call counts to live quota usage; no measured production
saving or whole-chain zero-cost conclusion is claimed by the source change.

The [independent report-progress Task](2026-09-09-lmdj-report-progress.md)
addresses #1048: continuous execution can skip every opportunistic report step.
A separate report-only health admission retains scheduler recovery, current writer
trust and existing outbox semantics. Its scheduled delivery/cost acceptance remains
outstanding. Manual report-batches(limit=1) `34302347438/1` delivered the historical
batch139 Creator failure as Issue865/comment5594769827; generations500–503 and the
complete1286-byte queued/POST/receipt bodies match. This is not a full backlog drain.

The [result-driven planner entry](2026-09-09-lmdj-canary-result-wakeups.md)
replaces the internal daily default with manual previews and a separate
persisted-result/recovery consumer. It revalidates the retained complete verdict
and binds the source into a fixed-target plan; recovery reuses the same identity.
The waking verdict cannot reduce the cumulative planning floor or replace
independent version/site progress. This consumer still requires authenticated
scheduler/progress readers and workflow integration before live activation.

- Local reduction/failure behavior: 55 journal tests pass, including six new
  regressions and preserved per-run/jobs, four-reader, atomic page-trust and
  fresh metadata checks. Three initial regressions failed before the fix.
- Complete CI contract discovery: 1,863 tests, OK with one optional actionlint
  semantic check skipped (`LMDJ_ACTIONLINT` unavailable). Staged ownership:
  66 tests pass. Portal verification is recorded in the shipping evidence.
- Read-only live inventory on September 9 (Shanghai): scheduler Issue 807 had
  127 events, 61 distinct writers and 49 control identities; report Issue 817
  had 440 events, 76 writers and 40 controls. These are payload inventory counts,
  not authenticated replay, timing or workflow-token request measurements. They
  confirm repeated controls exist; do not extrapolate the fixture's 66% saving.
- Real main admission → execution → terminal persistence → next interval:
  run `34256523536/1`, target `e12a810108dc30e2115cffefb2e89ba5593b21e9`,
  completed with 15 suites passed and Creator failed. Verdict artifact
  `10071823906` retains the complete result. Main controller `34266309491/1`
  persisted result generation 137 and advance generation 138 in scheduler
  Issue 807. These are live event/producer observations, not independent full
  journal replay. Controller artifact `10072142780` then records action
  `execute`, processed `e12a8101`, and request generation 139 (claim 140) for
  `e12a810108dc30e2115cffefb2e89ba5593b21e9` →
  `b208e9afb837ea6f3cec2fde65cd22207e5adc2a`. The exact Git first-parent
  interval contains seven commits; its full 16-suite scope includes changed
  Facade/Audio Runtime and control-plane inputs. Actual new product jobs began.
  The prior Creator failure is retained and debts are empty, not overall health.
- Product failure → durable Issue → external repair PR → relevant revalidation:
  Creator log identifies URL upstream parity for `https://catalog.example.test/a^b/`.
  The batch 131 Creator receipt is now verified: outbox-only run
  `34283375314/1` on control `c5cbf6161320d2ddec1d8e3f76d051e591590726`
  persisted queue/claim/ack/delivered generations 496–499 in Issue 817.
  Its exact bot comment `5592457267` in open Issue 865 matches both queued and
  POST bodies: 1,286 UTF-8 bytes, SHA256
  `f484fe81e289f767de27dfcdcaec20fb0d6ccfcc84b41bff66ce1c790b643ab3`.
  The matched observation is
  `batch/1667437b6496d1dbf93343bf2a53b0c819f7c1133fa64d04d3549e10d2d43938`;
  retained evidence is PR #1022 comment `5592566626`. This is one historical
  delivery, not a complete backlog drain or a receipt for later batch 164.
  External repair and relevant revalidation remain unverified. No synthetic
  defect or CI repair.
  An older missing-evidence report has an observed outbox ack/delivered and
  matching bot comment `5590141663` in Issue 889; it is not this Creator failure.
  Manual outbox-only run `34263950671/1` succeeded with no product execution,
  but has no new delivery receipt and cannot prove the global backlog empty.
  The single default-budget `report-batches` exercise, run `34267534129/1`,
  terminated cancelled after approximately ten minutes, with product execution
  skipped. Three deliveries reached durable ack/delivered (Issues 890, 820 and
  865); Creator comment `5590556319` is an older batch 105 observation, not the
  latest batch 131 failure. Check-run `102200575280` annotations explicitly
  report exceeding the 10-minute execution limit; this is not an inferred cause
  from timing. Do not call it a successful complete drain or widen the timeout.
  Preserve the delivered receipts and reconcile outstanding work before another
  bounded report attempt. No blind business POST retry or product rerun.
  The subsequent single-report recovery `34269085233/1`, control
  `f1c3f8e4682d55b0c2ce7667ebb91b1302383844`, succeeded with product execution
  skipped. Outbox ack `5590694834` and delivered `5590702337` identify Issue 944
  comment `5590692171`, which was read and matched to the older batch 105
  `web_runtime_host` failure. This is one durable historical delivery, not a
  complete drain or the latest Creator failure receipt.
- Remote request rate, queued-job recovery and end-to-end latency: unverified;
  inspect actual control results after merge, not only workflow conclusions.
- Version assessment, candidate delivery, Netcup isolation and formal promotion:
  later Tasks, disabled/unimplemented as applicable.

## T10 — Freeze unused automatic Canary Planning trigger

The automatic `workflow_run` trigger in `canary-planning.yml` is intentionally
frozen because it generated skipped planning runs before independent storage,
readiness and live acceptance existed. The workflow remains manual-only through
`workflow_dispatch`; its operation inventory, input defaults, controller
provenance/readiness validation and writer-lock protections remain unchanged in
`tools/canary`. This change preserves the historical skipped-run evidence and
does not initialize storage, set readiness variables, execute a live canary, or
enable scheduling.

Future live acceptance of automatic planning is separately authorized work. It
must prove independent storage/readiness, exact provenance and the complete
recovery path before any automatic trigger is restored; this Task does not make
that decision or claim that acceptance.

## Version Management

Version impact: none

Reason: internal control-plane request deduplication and tests; no Product,
Host, Module, Contract, Assembly, version or snapshot allocation changes.

## Documentation Impact

Documentation impact: required

Affected portal route: `/operations/testing-and-proof/` — its Canary Planning
wakeup description is updated in this Task to record the intentional
manual-only freeze. No Product, Host, Module, Contract, Assembly, version or
snapshot allocation changes.
