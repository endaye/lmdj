---
name: lmdj-release
description: Use when auditing or operating an LMDJ tag, Draft Release, Release publication, Runtime deployment boundary, or Channel promotion.
---

# LMDJ Release

One overall release authorization covers its scoped transitions; each transition
remains a separate verification boundary. Explicit narrower user restrictions win.

## Authority and execution

Before responding, read `docs/governance/git-workflow.md`,
`docs/governance/version-management.md`,
`docs/release-evidence/release-intents.json`, and
`docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`.
Read current `AGENTS.md` for standing authorization. Resolve the exact tag,
candidate, deployment targets and Channel from the request and established
configuration. Ask only when that scope is missing or ambiguous, not merely
because the next covered transition changes external state.

Begin release operations with `scripts/release.sh audit --remote --tag TAG`.
Before the long local path, read the host: `scripts/release.sh doctor` is a
read-only preflight that names each failed condition with its remedy — the
pinned emsdk, both signing-key roles in their own keyrings, GitHub auth, a free
journal writer lock, no second driver, disk space, host load, `fseventsd` and
Spotlight pressure, and the M1 runner (a running job fails; a loaded runner
fails for `prepare` and for a `resume` whose next step is `prepared`, with the
pause and resume commands; a `run` or an earlier `resume` needs it up for the
candidate batch). `run`, `resume` and `prepare` run it first and refuse while
any check fails; `status`, `audit` and the other read-only commands never wait
on it (#2422 items 5 and 7).
For an audit-only, design or development request, keep release mutations out of
scope. For an authorized release, execute covered transitions sequentially,
verify each result, and continue without renewed approval while its gates pass.
A boundary-specific restriction still stops at that boundary. This permission
does not imply an unattended controller exists or that credentials are usable.

Before cutting a candidate, apply the feature admission rule (#2422 item 12,
Owner decision 2026-10-23): a timing-sensitive feature merged since the last
candidate is in release scope only after two consecutive green automatic
main batches on the candidate hosts (the M1 for the macOS gates and Release
stress, netcup for the Web lanes, ci-core for Linux Core), each with a
successful executor run, the suites owning the feature's lanes `passed` in
its `batch-verdict-<target>-<run>-1` artifact and no new triage Issue for
them; candidate, node and overflow-host batches do not count. A feature that
has not earned that is withdrawn from the cut (reverted or the cut waits);
there is no release-scope flag yet. Timing-sensitive means it touches audio
scheduling, the Control thread or worker, count-in, recording switches, the
Runtime or Creator browser Proof journeys, a lane with a deadline or budget
(`core_macos` gates, `core_release_stress`, `core_tsan_stress`,
`web_runtime_host`, `creator`), or its PR left an unverified claim in a
batch-only lane; when in doubt, treat it as timing-sensitive. The COUNT-IN
merges of 2026-10-18 cost two candidates this way (#2394, #2395).

Only a verified releasable intent admits new preparation/tag/Draft/publication.
For an already published identity, audit and verify it without republishing or
rewriting history; continue only any separately verified, covered deployment or
promotion still due. An allocated identity needs candidate evidence and a
reviewed releasable intent first. While main's tip is the allocation cut or the
squash witness and no candidate batch has a result for that tip, the
incremental controller holds automatic admission so the candidate batch is
not queued behind a main batch; dispatch the candidate (its target is the
witness merge, never the cut SHA) promptly, because any ordinary merge ends
the hold (#2422 item 9). Refuse abandoned or superseded-unreleased
identities. Stop on unknown, conflict, unverifiable or external-error; report
the last verified state, evidence and remedy. Never turn a failed gate into a
new approval prompt that would bypass it.

Report publication, each Deployment, Channel promotion and remaining work
separately. Do not relabel historically completed states as unperformed.
Missing external authentication, required external approval, scope expansion
and unresolved product decisions are real stops. Never forge an owner-only
review waiver or manual acceptance, or alter protection to continue.

## Command mapping

The single sequential entry is `scripts/release.sh run --authority REF [--tag TAG]
[--base-revision SHA]`, with read-only progress `scripts/release.sh status
[REQUEST_ID]` and continuation `scripts/release.sh resume REQUEST_ID`. `run`
freezes one request from the authenticated canonical control and drives it
through the one ordered driver; `resume` continues that same request ID
without replaying an unresolved intent. Both hold the release freeze for the
request they drive: the repository variable `LMDJ_RELEASE_FREEZE` names it
from before the first transition until the request completes (`final`
verified) or is retired, and the PR Contract's `Release freeze` job fails any
Pull Request that changes CI or release-tool control-plane paths
(`.github/workflows/`, `.github/actions/`, `scripts/ci/`, `scripts/release.sh`,
`tools/release/`) while it is set; agents do not merge such PRs either
(issue-done §5). Ordinary product PRs are not frozen. A second release
request refuses to start while another holds the freeze; `doctor` reports who
holds it, names the clearing command for a freeze whose request this journal
retired, and for a holder this journal does not know sends the operator to the
host that drove it first (#2422 item 10). A step the journal already verified is
not re-driven and not re-proven: the driver rechecks only its immutable
identity — the candidate and reviewed PR merge commits and heads, the executor
run, the Release's numeric identity, plan digest and asset inventory, the
deployment runs — through a handful of reads, and any drift (a moved merge, a
re-run, a replaced asset, a missing Release) fails closed as
`evidence-conflict` or `evidence-absent`. A begun but unverified
step is still observed in full. Expect a resume with only publication and
deployment left to take minutes, not the 25–30 minutes a full re-proof cost
(#2422). Both refuse
before creating a request while any step still lacks an enrolled carrier, and
they list those steps instead of starting a partial run. A journal record is a
progress record, not external proof.

Only one unfinished request may exist per repository. When a request's later
steps were completed outside the entry, so that it can never finish, retire it with
`scripts/release.sh retire REQUEST_ID --superseded-by TAG`. The tag must be
the request's own reserved Build (for a tag-mode request, its requested tag),
published and passing its exact-tag remote audit. A candidate that was never published, for example one whose complete
batch went red, is retired with `--superseded-by-build BUILD` once main
carries that later BUILD on the same product line. Its own reserved Build must
have no remote tag and no releasable or published intent. Retirement refuses a
completed request. An outstanding intent is refused for the never-published form
(`--superseded-by-build`); the published form (`--superseded-by TAG`) accepts it,
because the published, audited Build settles every step it could still be
working toward. Either way the full original state is kept in a `.retired`
record, and nothing remote is mutated. Never delete or edit journal
files by hand.

The changelog step stays `pending` until the Owner-approved editorial is
recorded. Draft the `{"changes": [...], "exclusions": [...]}` pair from the
exact baseline-to-target range, get the Owner's approval of that content, then
run `scripts/release.sh editorial REQUEST_ID FILE`. It freezes the pair against
the request's releasable intent, refuses incomplete coverage, and records it
once; a different editorial for the same request is refused. Never invent an
editorial or record one the Owner has not approved.

Use `scripts/release.sh prepare TAG`, `scripts/release.sh push-tag TAG`, and
`scripts/release.sh create-draft TAG` in order when covered and admissible.
`prepare` builds each Web Host reproducibly (two clean builds, byte-compared)
and does not rerun the Hosts' tests or browser journeys locally: it already
refuses an intent without the exact target's complete candidate batch
evidence, and that batch proved them on CI. Pass `--reprove` (also accepted by
`run` and `resume`) only when a complete local proof is wanted; it is the slow,
load-sensitive leg that cost 2.0.122.0 two timeouts (#2422 item 4). Once
passed to `run` or `resume`, the request records it, every later `resume`
keeps it, and `status` reports it.
Use `scripts/release.sh verify-draft TAG RELEASE_ID PLAN_SHA256` only for
read-only Draft verification. Use
`scripts/release.sh verify-published TAG RELEASE_ID PLAN_SHA256` for the
read-only post-publication Release check. Audits before and after
pre-publication mutations use `scripts/release.sh audit --remote --tag TAG`;
publication is followed by `verify-published`.

`prepare` and the Web proofs activate the pinned Emscripten SDK from `EMSDK`,
falling back to `build/toolchains/emsdk`. On the operator host install it
outside the repository (any path, exported as `EMSDK` in the shell that runs
`scripts/release.sh`), so a branch/worktree or `build/` sweep cannot delete it;
the in-tree default stays for CI workspaces. The toolchain tree and the
prepared output tree are release-owned and never a cleanup target (issue-list
Mode 2); `doctor` reports a missing or drifted SDK with its reinstall command.

On a fresh clone or a fresh runner workspace, run `scripts/release.sh hydrate`
before the first audit. It is the only stable subcommand that writes the local
Git object store: it fetches by SHA exactly the release intent target objects
the clone lacks, prints what it hydrated versus what was already present, and is
idempotent, so running it unconditionally is safe. It authorizes nothing — no
tag, Draft, publication, deployment or promotion follows from it. The audit
itself never fetches on miss, so an absent target is a reported finding whose
remedy names this command.

Channel promotion is `scripts/release.sh promote TAG CHANNEL --deployment-run
HOST=RUN_ID ... [--evidence PATH ...]`. It is a local mutation of the ledger and
one evidence document only: it audits first, verifies every Host deployment
run's retained evidence for the exact tag, and never edits the GitHub Release.
The written files ship as a reviewed docs Pull Request under the current Git workflow.
`stable` is refused; the open question it points at is the authority, not this
skill. Promotion requires a published intent and both Host deployments to have
succeeded; it is a separate boundary from deployment and does not follow from it.

## Operator host during a release

The M1 workstation is the release operator's machine, the Release stress
runner, the macOS gates runner and the host `prepare` builds on. During
2.0.122.0 `fseventsd` held a core for 17 days, Spotlight re-indexed after
every `npm ci`, other agent sessions ran proofs beside the release, and the
runner executed a candidate batch while `prepare` built — two prepare proofs
timed out at load 35–41 and passed at load 3–8 (#2422 item 7). Before `run`,
`resume` or `prepare`, and whenever `doctor` fails, walk this list:

1. **Spotlight off for the project and runner trees.** System Settings →
   Siri & Spotlight → Spotlight Privacy, add `~/Projects` and
   `~/actions-runner`. `mdutil -s /` shows the volume state; indexing stays on
   for the rest of the volume. `doctor` fails when `mds_stores`/`mds` exceed
   30% cpu.
2. **Restart `fseventsd` when it is pegged.** Check with
   `ps -o %cpu= -p "$(pgrep -x fseventsd)"`; above 50% run
   `sudo killall fseventsd` (launchd respawns it at once), then rerun
   `doctor`, which fails above the same limit.
3. **No heavy work beside the release.** No local proof lanes, Core builds,
   Playwright runs or other agent sessions on this host while a request is
   driven; check `uptime` (1-minute load must stay below the cpu count,
   `sysctl -n hw.ncpu`) and `pgrep -fl "creator-web.sh|web-runtime-host.sh|core.sh|playwright"`
   before starting. `doctor` fails on load above the cpu count and on a
   second release driver.
4. **Pause the M1 runner while `prepare` builds.** Pause:
   `launchctl bootout gui/$(id -u)/actions.runner.endaye-lmdj.endaye-mbp-m1`;
   resume right after `prepare` reports its plan:
   `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/actions.runner.endaye-lmdj.endaye-mbp-m1.plist`.
   Do not pause it for the rest of the request: the candidate batch a `run`
   or an earlier `resume` waits on executes on this runner. `doctor` refuses
   `prepare`, and a `resume` whose next step is `prepared`, while the runner
   is loaded, and fails any command while it is executing a job.

`scripts/release.sh doctor` checks items 2–4 and the volume's Spotlight cpu
automatically and prints each failure with its remedy; the Spotlight Privacy
exclusion itself (item 1) is not readable from the command line and stays an
operator step.

## Full exact-main CI evidence

Current prospective policy is `complete-test-v2`: the Owner explicitly references
exactly one passed, complete 15-suite source for the exact candidate in a reviewed
intent: old `self-test-v1` via `self_test_evidence`, or full incremental evidence
via `batch_test_evidence`, together with the actual executor run ID. The one
composed form is a candidate that lost lanes to the platform plus its single
lane-scoped retry (`lmdj.ci-batch-release-reference.v2`): every suite is still
proven by exactly one attempt-1 run, and the candidate's `failure` conclusion is
accepted only through its proven environmental lanes. No reference, mixed
references, focused/none batches or legacy fourteen-lane scope qualify.
The tool verifies stable source and main ancestry, distinct control/target
revisions, attempt, current policy and digest; a green summary or AI label
is not evidence. Batch evidence additionally requires original origin/admission
controller artifacts (trusted durable-claim attestation, not latest journal
replay), the complete three-file verdict bundle and authenticated API jobs.
See the version governance for the closed reference fields and cutover.

An existing valid complete verdict may be reused for the same exact target,
including retained historical daily/node evidence. Fresh complete verification
uses `self-test-report.yml` on ref `main`, `batch_operation=reconcile`, and
`batch_request={"id":"<stable-request-id>","kind":"candidate","target":"<exact-main-SHA>"}`.
Leave `journal_config` empty to use the repository's authenticated fixed scheduler.
Use `kind=node` for an explicit diagnostic rather than candidate selection.
Both kinds request all 15 suites and share the durable execution budget;
neither moves automatic processing progress or authorizes a release. A
candidate or retry batch runs on the pinned release hosts (the M1 for the
macOS gates and Release stress, netcup for the Web lanes): the selectors
never hand it to the M4 Pro or en-home overflow, so an admission flip on
those workstations cannot change where release evidence comes from (#2422
item 11).
Redelivering the same ID and target reconciles the original request; a genuinely
new test needs a new ID. Do not use lane selection, a queue ticket, or a SHA as
the dispatch ref. When a candidate did not pass only because the platform
stopped a lane (a `timed_out` or `cancelled` job, a missing artifact, a lost
runner), do not cut again: send the retry short form for the same target,
`{"id":"<new-stable-id>","kind":"retry","target":"<the candidate's exact
SHA>","retry_of":"<the candidate's request id>"}`. The controller derives the
lanes from the candidate's durable result and freezes their environmental proof
from the jobs API; never list suites. A lane that failed on a test is refused,
and a candidate is retried at most once (#2422 item 8). The trusted control revision may be newer than the candidate.
Record only validated artifacts' facts; never invent or backfill a reference.

Verdict artifacts currently retain 30 days. Missing/expired evidence is
`unverifiable`; mismatched, incomplete or non-passing evidence is `conflict`.
Recovery requires a new explicit request ID on main for the same target (a
`retry` when only environmental lanes failed, a new candidate otherwise) and a
separately reviewed intent update, not Re-run jobs: the producer currently
accepts attempt 1 only. Only actually `published` history may use the recorded attempt without
re-adjudicating ephemeral retention; allocated/abandoned/superseded is not this
exception. Immutable tag/signature/Release/assets and exact plan-marker proof
remain required. Batch `lmdj.release-plan-marker.v3` permanently binds the entire
reference including `executor_event`; old self-test v2 and legacy v1 remain
unchanged. An old marker cannot prove a newly added batch reference. Never
rewrite history or infer executor event from the queue request kind.

A full dispatch is evidence, not authorization: completing one authorizes no
tag, Draft, publication, deployment or promotion.

When a verified Draft is ready and publication is covered, dispatch the protected
`publish-release.yml` on main using its verified `tag`, `release_id`, and
`plan_sha256`, wait for the exact run and verify publication. Do not approve
someone else's required approval or bypass the protected `release` Environment.
After verified publication, ship an evidence-only reviewed PR recording the
observed Release and changing its intent to published; verify the live main
ledger and rerun audit. Publication does not update that ledger automatically,
and promote requires a published intent. Do not change the candidate target or
rewrite the published Release during this handoff.
Then dispatch each covered Host deployment using the exact tag, verify its
retained evidence, and continue to covered Channel promotion through its normal
reviewed PR. Report only independently verified status; Release publication
alone never proves Deployment or Channel promotion. If publication is not
covered, report the verified inputs without dispatching.

The driver's dispatches do not need main to stay at the frozen control. Main
moving on during a release is normal, and a dispatch runs on live main when it
descends from the control and the dispatched workflow file is unchanged since.
Newer reviewed tooling is accepted. A commit missing locally triggers one
canonical-main fetch first. A changed workflow, or history still unreadable
after that fetch, is refused before any POST intent is recorded. Resume once
the history is readable; a changed workflow needs a new request.

If `publish-release.yml` fails at `verify-published`, read the live Release by
numeric ID and compare it with the immutable plan before concluding publication
failed. If it fails earlier, treat publication as not done and diagnose the
failure before retrying; see
[`post-publish-audit-releasable-ledger`](../../pitfalls/post-publish-audit-releasable-ledger.md).

## Pitfalls

Open the entries below before the step each one names. They are recorded
recurrences from this repository's own history, not general advice; the
contract is [`docs/governance/pitfall-ledger.md`](../../../docs/governance/pitfall-ledger.md).

- Before treating a Product Build as allocated —
  [`squash-witness-provenance`](../../pitfalls/squash-witness-provenance.md).
  A squash rewrites the introducing commit, so a snapshot frozen from a branch
  SHA loses its provenance. Avoid needing the witness at all: freeze the
  snapshot as the first and only commit on a branch cut from the current `main`
  and merge it before `main` moves, so the squash parent is the recorded source
  revision. Generate the witness for the exact post-squash
  `main` SHA with `scripts/docs-site.sh witness PRODUCT_BUILD
  INTRODUCING_REVISION` and verify it; never hand-edit an immutable snapshot to
  make provenance agree.
- Before running any audit from a fresh clone or workspace —
  [`release-intent-target-reachability`](../../pitfalls/release-intent-target-reachability.md).
  An allocated intent can record a pre-squash target no advertised ref reaches,
  so the clone lacks the object and the audit correctly reports the intent
  unverifiable. Run `scripts/release.sh hydrate` first; never add an inline
  fetch copy of your own and never make the audit self-heal.
- Before creating or binding a release intent —
  [`release-intent-binding`](../../pitfalls/release-intent-binding.md).
  Allocation needs no intent. Bind the intent only after the exact
  protected-main squash SHA exists; a pre-squash or branch SHA is not a
  protected-main ancestor and fails closed.
- When diagnosing a failed `publish-release.yml` job —
  [`post-publish-audit-releasable-ledger`](../../pitfalls/post-publish-audit-releasable-ledger.md).
  For a `verify-published` failure, read the live Release by numeric ID and
  compare it with the immutable plan; for an earlier failure, treat publication
  as not done and diagnose before retrying.
- Before treating a failed Creator deploy as a failed signed-archive verify —
  [`manifest-role-validator-sync`](../../pitfalls/manifest-role-validator-sync.md).
  Prior identity discovery must accept the live Host's inventory. Creator 3.x
  smoke still requires `perform_master_tap_worklet`; Creator 2.x priors have
  five roles. Preflight already verified the candidate Release.

When a release operation exposes a new process invariant, record it through the
Pitfall Ledger step in
[`.agents/skills/issue-done/SKILL.md`](../issue-done/SKILL.md) rather than
leaving it in a report.
