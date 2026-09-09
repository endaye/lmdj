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

## Version Management

Version impact: none

Reason: internal control-plane request deduplication and tests; no Product,
Host, Module, Contract, Assembly, version or snapshot allocation changes.

## Documentation Impact

Documentation impact: none

Reason: Task 1 changes an internal transport optimization, not operator commands,
selection policy or current Portal facts. Later behavior cutovers must update
`/operations/testing-and-proof/` and `/operations/version-and-release/`, their
source diagrams, and the older daily-deployment proposal before activation.
