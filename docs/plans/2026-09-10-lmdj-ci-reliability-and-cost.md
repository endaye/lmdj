# LMDJ CI reliability, recovery and execution cost

Status: owner approved for implementation on 2026-09-10. Supersedes the pending
choices and task ordering in the 2026-09-09 CI consolidation plan, retains its
historical evidence, and continues umbrella #1089 / Orca Run run_71c2492cd783.
Coordinator: Codex. Baseline reviewed: main 5b1db209; refresh live evidence at
every acceptance boundary. No local/bot success claim substitutes for that.

## Goal

Keep task verification and independent review on PRs, immutable fixed-target
incremental product batches on main. First repair false review/coverage signals,
then controller recovery/reporting, then idle wakeups and host dependencies.
Do not restore universal full PR CI or buy runner capacity before measuring.

## Owner decisions (confirmed in conversation)

| Gate | Outcome |
| --- | --- |
| D1 | Add change-selected PR advisory CI contracts, static docs and documentation-impact checks on trusted self-hosted capacity, not required checks. Measure actual cost; do not promise it runs Creator parity or completes in a few minutes. |
| D2 | Freeze automatic Canary Planning workflow_run; retain manual entry. No init or readiness activation in this program. |
| D3 | Require an independent current-head review; only owner may explicitly waive it with a reason bound to exact SHA. review:skipped is display, never standalone authority. |
| D4 | Explicit common Catalog upstream admission semantics in Worker and proof server; verify Node 22 and 26. Source/test change only, no deployment. |

## Tasks and dependencies

Each task is one reviewable Conventional Commit/PR in an isolated short-lived
fix/* or docs/* worktree. Coordinator accepts by rerunning declared lowest-tier
checks and reading exact-head diff/PR/review. Reviewer must not be the author.
Coordinator alone authorizes merge after acceptance, using match-head-commit.

| Task | Declared boundaries | Lowest-tier verification / acceptance |
| --- | --- | --- |
| T0 plan and handoff | this plan, 2026-09-09-lmdj-ci-consolidation.md, 2026-09-09-ci-consolidation-lead-handoff.md | ownership, whitespace, PR body validation; record all D decisions, correct stale state/P5.1 path/D1 claims; coordinator updates #1089 |
| T1a old admission | resume PR #1100 exact declared files | pinned actionlint, topology, runner fallback, hosted policy and full ci_*; independent current-head review; merge first |
| T1b old queue | resume #1103 exact declared files incl dead github_queue_api.py and retained pitfall exits | integrate T1a, restore valid negative guards, retain historical narratives; full ci_*, scope plan and pinned actionlint; merge second |
| T2 placeholder | scripts/ci/review_scope.py; tests/build/ci_review_scope_test.py | exact #1062 payload red before fix, invalid_output after; real clean review still accepted |
| T3 review admission | .agents/skills/issue-done/SKILL.md; new scripts/ci/review_wait.py and tests/build/ci_review_wait_test.py | read-only helper checks exact head, authentic independent record/findings and owner exception; fail on missing/stale/unknown; workflow not a new required check |
| T4 executed coverage | scope_policy.json; ci_change_scope_test.py; ci_test_scope_test.py; unregistered-test-file-reads-as-coverage pitfall | #914 bundle e2e paths reach actual ASan/coverage executor; retained conservative lanes; literal runner paths/globs and explicit dynamic mappings validated |
| T5a profile inventory | tools/canary/metadata_proposal.py; tests/build/ci_canary_metadata_proposal_test.py | restrict contracts/<family>/lmdj.<name>.v<digits>.md; README/unrelated Markdown refused; metadata and handoff suites |
| T5b Catalog parity | apps/web-runtime-host/deploy/cloudflare_worker.mjs; tools/web-runtime/serve_distribution.py; apps/creator-web/test/server_test.py; Worker matching tests | existing proof-server closed grammar and corpus define shared semantics; Node 22/26 and Worker tests; preserve explicit loopback HTTP-only proof exception |
| T6 HTTP recovery | self_test_report.py; batch_runtime.py; incremental_completion.py; batch_github_journal.py and matching HTTP/runtime tests | primary quota/reset, 429, real authorization mismatch, operation budget, later health recovery, unknown writes never replayed |
| T7a request proof reuse | batch_github_journal.py / batch_runtime.py and matching tests | same-transaction reuse of immutable proofs; retain full history/metadata checks, output equivalence and before/after HTTP counts |
| T7b checkpoint design | new docs/design/2026-09-10-ci-journal-checkpoint.md | decision-complete design with replay equivalence, history edit/deletion protection, pending-write recovery, compatibility/migration/rollback. No implementation/migration of new protocol this round |
| T8a event aggregation | report_runtime.py; self_test_report.py; report_outbox.py and matching tests; batch_verdict.py only if separately declared | one proven common infra event -> one report listing all suite debt; simultaneous failures alone are not common cause |
| T8b bucket recovery | same report/outbox files and matching tests, sequential after T8a | only new explicitly managed buckets close on authenticated later actual successful suite with no debt; old results cannot override new failure; reopen on recurrence; independent/human-investigated defects never auto-close; durable comment/PATCH receipts |
| T9 PR advisory | new .github/workflows/pr-contract.yml; existing PR declaration tool; topology/hosted policy tests | after T1/T4; change-selected checks, exact tested SHA, same-repo trusted boundary, no untrusted fork execution on self-hosted, no new required check or full product DAG |
| T10 canary freeze | canary-planning.yml; matching topology test; result-driven-delivery plan | remove workflow_run trigger; keep manual entry, no readiness or storage changes |
| T11a control host | ci.yml; self-test-report.yml; hosted_runner_policy.json; topology/policy tests | general control jobs eligible on both trusted hosts, retain scopes/concurrency/trust; no new hosted fallback |
| T11b inventory | ci-host-inventory.yml; scripts/ci/host/ relevant probe and inventory tests | explicit target hosts, probe sanitizer/config parity read-only without config mutation; neither random host dispatch nor tool presence proves both hosts ready |
| T11c stress investigation | new docs/quality/2026-09-10-ci-stress-measurement.md | #666 latest evidence, CPU accounting/steal limits and next causal experiment; no tolerance change or host reconfiguration |
| T12 acceptance/hygiene | final quality report; issue-list skill; affected current governance/portal pages | exact merged SHAs, validation, cost comparisons, live report-only observations, open defects and deferred live acceptance. ci:storage excludes storage from work queries; historic missing buckets close only after individual proving evidence |

T0 first. T1-T5 first wave; T6 -> T7 -> T8 sequential for overlapping runtime
ownership. T9 after T1/T4; T10 independent; T11 after T1. T12 closes this bounded
program only after its implementation and acceptance, not every related defect.
Every added file must pass staged path-ownership checks. File expansion requires
coordinator ruling; do not silently edit another worker's files.

## Behavioral contracts

### Review

Reject known placeholder after trim/case normalization in summary and scope
reason. Do not require nonempty findings or pretend structure proves quality.
review_wait is read-only, machine-readable, nonzero for missing/stale/unknown
records. Verify exact SHA and reviewer identity; owner exception requires SHA,
reason and verified owner provenance. A label alone never satisfies it. Failed
bot runs remain visible alongside independent takeover. A push invalidates prior
head evidence. #939 diagnosis records backend runtime categories/timing; do not
raise timeout first. Retain #714 unsigned clean-thread retirement as a separate
bounded follow-up with regression tests, not a blanket thread resolver.

### Coverage and Catalog

The #914 gate connects actual runner invocations to scope ownership. Literal
paths/globs are supported; runtime-generated invocations require explicit
mapping. Preserve existing selection and add actual executing suites for bundle
e2e. AI scope only adds to deterministic floor. T9 runs complete selected
ci_contract; do not prune tests to claim lightweight behavior. Creator parity
remains T5b/Creator-owned.

Use existing Python proof server grammar/corpus as the Catalog semantic baseline,
implement explicit same character admission in Worker before retained canonical
URL checks. Keep host/port/userinfo/dot-segment defenses. Only proof server may
accept loopback HTTP; Worker stays HTTPS. Share semantics/corpus without a new
cross-language runtime dependency.

### Recovery and reporting

403 remaining=0 is transient unknown with reset metadata, not dead-controller or
product failure. Retry idempotent reads within the existing operation budget;
when reset exceeds remaining budget retain retry time/debt for a later health
tick rather than holding the writer lock for the whole reset interval. Keep true
authorization/provenance failures fail-closed and unknown POST reconciliation.
T7a proof reuse is only transaction-local; mutable run states are not cached across
runs. Keep complete comment edit/deletion/provenance verification. New checkpoint
protocol is design-only and requires its own future implementation approval.

Aggregate only a proven shared infrastructure event keyed by exact request,
run/attempt and cause; every suite's unexecuted debt stays visible. Automatic
recovery closes only explicitly new managed failure buckets on later authenticated
same-suite actual success and no debt, with causal ordering and policy coverage.
Never close independent product bugs or historical human-investigated buckets
such as #782 from one later green stress result. Durable recovery comment and
close intents have separate receipts; duplicates/crashes must not repeat comments.
Old buckets migrate only through individually reviewed evidence, never bulk
closure by a number range.

## Verification and measured exit

Red-first minimal regressions per task. T1a/T1b full ci_* + pinned actionlint;
final integrated full ci_* again. No reducing thresholds/timeouts/selection or
journey legs. Tests reading git index must run in a real Git worktree after staging
new files. Document platform-only skips separately.

Validate placeholder/real clean review, stale-head/owner exception, route omissions,
Node22/26 refused/accepted corpus, primary/secondary limits and real auth failures,
unknown POST, event duplicates, crash recovery, stale report ordering and recurrence.
Measure identical fixed histories before/after and real runs separately: request
counts, elapsed/queue time, backlog size and oldest age, actual selected suites,
review publication state. A burst is not the average. Read three real consecutive
report-only ticks; a green skipped DAG is not proof of report/discovery recovery.

T11c does not close #666 from three quiet passes: it delivers diagnostic evidence
and a causal next experiment. P1.4 remains awaiting the next independently
authorized genuine publication. No release is initiated for this acceptance.

## Version Management

Version impact: none. No Product Build/Module/Provider/Contract identity allocation.
Catalog admission is the approved existing-rule consistency fix; source merge is
not publication or deployment.

## Documentation Impact

Documentation impact: none for this plan and handoff records (not current Portal
pages). Individual workflow/review/recovery behavior tasks update current
/operations/testing-and-proof/ when affected, declare required and run
scripts/docs-site.sh check. Governance updates stay aligned; if AGENTS.md changes,
CLAUDE.md changes byte-identically. Frozen snapshots are not regenerated.

## Authority and retained work

Owner authorized implementation, commit, push, PR, independent review and squash
merge. Coordinator owns acceptance and authorized issue hygiene. No release,
deploy, Channel promotion, new hosted spend, protection edits, journal reset,
canary init/readiness activation or worktree deletion. Retain all unresolved
product defects, incomplete live acceptance and unknown write outcomes explicitly.
