# PR-Agent Netcup operations — T4 implementation boundary

Date: 2026-09-10 (Asia/Shanghai)

Task: LMDJ #1153 / umbrella #1149 T4
Status: production pilot implementation in progress; see the current record below.

## 2026-09-17 budget raise to USD 100 (owner decision)

The pilot spent its original USD 20 budget (the ledger's lifetime pilot total,
not the calendar-month key, tripped first) and every PR review returned
`budget_exhausted` with `num_ai_calls=0`. At the owner's decision the approved
dollar caps are raised: engine caps `MAX_MONTHLY_USD`/`MAX_PILOT_USD` are now
USD 100, and both `config.toml` and the installed `runtime.toml` set
`monthly_usd`/`pilot_usd` to USD 100. The per-attempt cap stays USD 1 and the
request-count caps are unchanged; the reservation basis (full 1M context at
peak cache-miss rates) is unchanged. The raised caps take effect on the review
host only after the overlay is reinstalled from the main revision carrying
this change; until then reviews keep failing with `budget_exhausted`.

## 2026-09-17 ledger archive at the reinstall

The 09-10 pilot's ledger held 760 records reserving USD 242.81 against
USD 15.88 of actual spend: every attempt reserves the full 1M context at peak
cache-miss rates, so failed admissions dominate the ledger while the real
invoice stays two orders of magnitude lower. The archived total exceeded the
new USD 100 caps, so the raised budget would still have admitted nothing.
At the owner's decision the ledger was archived intact on the review host as
`/var/lib/lmdj/pr-agent/engine-state/ledger.jsonl.archive-2026-09-17-pre-raise`
and the active ledger restarted empty before installing release
`cutover.f8Ktuvu6` (adapter `dab008ceb`, runtime caps USD 100, witness
verified, runner ACLs reapplied). Known deferred defect: the reserve-full-
context policy makes committed reservations diverge from actual cost; a
follow-up Task should align reservations with metered usage so the ledger
stops exhausting budgets that were never really spent. Resolved 2026-09-17
by the reservation-settlement Task (#1469): the engine's committed accounting
now counts reconciled records at their metered actual and uncertain records
at zero, while admission-time reservations and the durable record amounts
are unchanged, so committed totals converge to real spend after each outcome.

## Automatic push and explicit repair recheck (Issues #1322 / #1305)

After the updated adapter is installed, a maintainer can request one source
repair recheck using the existing workflow on main:

```bash
gh workflow run pr-review.yml --ref main \
  -f pr_number=PR_NUMBER -f recheck_comment_id=ORIGINAL_BOT_COMMENT_ID
```

Use the numeric ID in the original inline comment's GitHub API URL, not its
review ID or a reply ID. After the batch-capable adapter is installed, PR push
(`pull_request.synchronize`) automatically includes unresolved bot findings in
the same ordinary model review. Open/reopen/ready events and an empty manual
dispatch remain ordinary reviews. “fixed” replies and comment commands are not
triggers. The existing provider timeout, token and monetary budgets apply.

The complete thread inventory excludes human/resolved threads and paths absent
from the current text input. Original bot roots are considered in comment-ID
order, with at most four authentication attempts and 1 MiB of combined repair
context per run. The Actions collection step log and summary report collected,
not-rechecked and deferred candidates. Unchanged source, unavailable original
evidence and overflow remain open; use the explicit entry above or manual
review. A path-only repair proof cannot establish cross-file/runtime fixes.
The same original artifact is cached within the observation; head and thread
boundary reads remain fresh. An empty candidate list adds no model call.

Continuous pushes share the existing cancel-in-progress PR concurrency group;
superseded results must still pass fresh head checks. This is coalescing, not
a fixed debounce window or guaranteed execution order. Do not dispatch an old
run concurrently as a retry: it can cancel the current PR run. Retry the current
head through the existing explicit entry when needed. GitHub event/concurrency
semantics: [events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
[concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

The collector authenticates the selected LMDJ bot finding against its retained
review artifact, captures the full conversation and original-to-current source
change, and binds them to the current PR input. The model returns `resolved`,
`unresolved` or `insufficient_evidence`. Only source-provable repairs with
concrete original/current quotes and a causal explanation can resolve. The
recheck executes no tests or PR files. Runtime claims requiring execution,
unavailable/expired original artifacts, unsupported path moves and incomplete
source evidence require manual review. New findings also prevent auto-resolution.

GitHub currently requires `contents: write` as well as `pull-requests: write`
for `resolveReviewThread` / `unresolveReviewThread` with installation tokens
([GitHub issue](https://github.com/github/gh-aw/issues/35726)). Only the separate
publisher job holds that permission; target and model jobs remain read-only.
The publisher executes trusted main control code, never PR files or merge calls.
A successfully posted evidence reply does not prove that thread resolution
succeeded: check the final GraphQL thread state and the retained receipt.

The separate publisher validates the current head and conversation again,
replies with the verdict and evidence, and resolves only the selected bot
thread. Human threads are never selected. Retry receipts prevent duplicate
replies for the same captured request; uncertain writes are reconciled by
reading their actual state. A detected head/conversation race after resolve
causes a compensating reopen. GitHub has no conditional-head thread mutation:
cancellation, API failure or a change after the final read can leave a race
requiring manual inspection. Current-head review and merge conversation checks
remain required; this result never grants merge authority.

`pr-review-result-HEAD-RUN-ATTEMPT` retains `t2-input.json` (including
`repair_request` or automatic `repair_requests`) and `t2-result.json` (including
the native `repair_recheck` or `repair_rechecks` verdicts). The publisher's scope artifact also retains `repair-recheck.json`
after each successful thread publication, retaining partial batch receipts
if a later thread refuses publication. Each batch must supply exactly one
verdict per request before any thread can be mutated. A missing/invalid verdict from an older
installed adapter fails closed. Install a reviewed adapter with the existing
`install.sh` procedure below; preserve the previous release and shared ledger.

## 2026-09-12 takeover and current installation

The owner requested direct DeepSeek integration; the current Task is
`docs/plans/2026-09-12-pr-agent-cutover.md`. The former deploy-runner/systemd
entrypoint is retired by this Task. Historical evidence below remains unchanged.
The new entrypoints are `scripts/ci/pr-agent/install.sh` and `run-engine.sh`;
the model and budget are in the separately installed `runtime.toml`.

Read-only host/API inspection during takeover found `netcup01`, four online
matching Netcup runners (01-04), four offline elastic runners, and the GitHub
secret name `PR_AGENT_DEEPSEEK_API_KEY`. No secret values were printed. The
actual `actions.runner.endaye-lmdj.netcup-lmdj-linux.service` runs as
`lmdj-runner-01` with `NoNewPrivileges=yes` under the existing CI slice.
Review execution uses the runner account, not the unactivated dedicated T4
service. Dedicated 1-vCPU/2-GiB isolation and co-running capacity are not proven.

The prior session's final message said one model call had run and a second had
not run. Retained host artifacts and the monetary ledger show two calls:

| UTC start | Input | Result | Usage | Ledger amount USD |
| --- | --- | --- | --- | --- |
| 2026-09-11 16:32:31 | historical PR #1233 | reviewed, complete input | 23313 input / 699 output | 0.0078327 |
| 2026-09-11 16:34:25 | same historical PR | not-reviewed, invalid_output | 23313 input / 287 output | 0.0073383 |

These are conservative peak-price ledger calculations, not a provider invoice.
The second failure is `native review contains unsupported fields`. Both calls
used run_id `1`, attempt `1`, head
`255cde310fccd7f701f90a5cad0a295174a6556f`, base
`8338b7cd0334b441a39be099e9a9d02ae3b0022e`, control
`9a3c34ffe0b19bee794e87f593b9bc726baf2e77`. Neither is an Actions run or
authenticated current-head publication. First-call findings were moved to
summary by the uncommitted adapter; they are not proof of valid inline review
or defect-detection quality. That relaxation is removed in the final Task.

Original host files: `/tmp/live-result-1233.json`, `/tmp/live-result-1233b.json`,
and `/var/lib/lmdj/pr-agent/engine-state/ledger.jsonl`. Local copies and this
session's raw tests are retained in `/tmp/lmdj-pr-agent-cutover.Jx0gpqLL/`.
The real rendered-prompt regression reproduces the upstream example/consumer
contradiction before the fix; it then passes with one configured schema.
The upstream PRReviewer and LiteLLM engine remain pinned and unchanged.

The configured Flash model, peak input/output rates and non-thinking parameter
were refreshed from the official DeepSeek [pricing](https://api-docs.deepseek.com/quick_start/pricing/)
and [thinking-mode](https://api-docs.deepseek.com/guides/thinking_mode/) pages on
2026-09-12. Runtime caps remain USD 1 per PR attempt, USD 20 pilot/month,
60 seconds per request, 600 seconds per engine invocation, 4096 output tokens.
No manual paid call was added by this continuation.

### Verified continuation receipt

The installer completed with exit 0 and selected
`/var/lib/lmdj/pr-agent/releases/cutover.5Jaxm58H`. The original release
`/var/lib/lmdj/pr-agent/releases/c734251f52c21d8a1b2265e3284c1a98fb8ca5d8ff108f2afbc38c2cec387416`
is unchanged and retained as `previous`. Runner 01 verified the candidate
before the switch; runner 02 independently read the installed witness after it.
These are installation checks, not independent source review or model calls.

- Installed adapter SHA-256:
  `6bbe205f95b6957ee62995a39b7aa88f34eddef656ef1e24e84c58153d39c176`.
- Runtime SHA-256:
  `c02b452c9d8c3269bc5025bd9f13a98e0f9c33cbcf9d50c9150575edd230fa74`.
- Monetary ledger SHA-256, identical before and after:
  `132139c2d65951e848a381ec06e335a0657438389293a208096b248f35ddee85`.

Raw logs under the local evidence directory above retain the failed runs as
well as the corrections. Final child processes all exited 0:

| Check | Result | Log |
| --- | --- | --- |
| Pinned engine suite, including its real-handler subprocess | 58 passed, no skips | `engine-tests-v3.log` |
| Direct real PRReviewer/LiteLLM handler suite | 39 passed, no skips; overlaps the parent suite | `engine-child-tests-v2.log` |
| Input, protocol, workflow and consumer regressions | 412 passed, no skips after independent-review corrections | `protocol-tests-v3.log` |
| Change-scope ownership, including retained deletion-path rules | 72 passed | `scope-tests-v3.log` |
| Real Linux root/ACL installer and workflow-lock fixtures, no provider | 6 passed | `install-tests-v3.log` |
| Actual installation and post-switch runner witness | Passed; ledger unchanged | `host-install-v1.log` |
| Portal validation and build | Passed, 46 routes | `docs-check-v5.log` |

Pinned actionlint 1.7.12 with ShellCheck 0.9.0 on Linux and shell syntax checks
also passed. Failed-candidate and busy-lock behavior were exercised in separate
temporary fixture roots, not by disrupting the installed production release.
Independent review found and corrected a stale test that rejected retained
deletion-path ownership, and a witness/installation race. The workflow now
holds one slot lock across both witness and model execution; witness failure
prevents model entry. Three still-active generic pipeline regressions were also
restored. The final heredoc shell spelling is separately exercised by the real
Linux lock fixtures and the affected workflow/pipeline suite; earlier logs are
not rewritten as final-head evidence.

### Update and rollback

Stage the reviewed repository copies of `install.sh`, `run-engine.sh`,
`runtime.toml` and `pr_agent_review.py` in a dedicated host directory. Run
`sudo -n bash STAGING/install.sh STAGING`. The installer requires the existing
root-owned bundle, Python 3.12, ACL tools and a free slot lock. It copies the
bundle into a new protected release, updates only that candidate's member
identities, verifies it with a runner-account `--witness`, and atomically
switches `current`, retaining `previous`. A failed candidate is retained for
inspection; it never replaces current. The original seed archive digest stays
provenance, while adapter/config hashes bind the installed overlay.

The account-level witness does not enter the runner's systemd mount namespace.
PR #1238 run `34628173677` attempt 1 exposed this boundary: it made zero model
calls, reported `budget_exhausted`, and failed to open the ledger lock with
`EROFS` inside runner 04's service despite working ACLs and only USD 0.015171
recorded spend. Preserve that failed run; it is not provider/budget acceptance.

Keep `ProtectSystem=strict`. The Netcup unit template allows only
`-/var/lib/lmdj/pr-agent/engine-state` and `-/var/lib/lmdj/pr-agent/engine` via
an additive `ReadWritePaths=` line. The `-` permits absent directories during
provisioning; it does not update an already running mount namespace. For
existing Netcup services, install that same line in a root-owned dedicated
drop-in, daemon-reload, and restart only idle services one at a time. Offline
elastic units stay stopped. Check GitHub busy state and host worker processes
before each restart; wait for busy workers rather than interrupting them.
Never make the installation root or release/configuration bytes writable.
Read back effective properties and verify state access from the restarted
service's actual mount namespace; retain ledger bytes through the operation.
The real systemd tests in `ci_pr_agent_install_test.py` reproduce the denied
case and exercise both allowed state writes and denied installation writes.
They do not call a provider or substitute for a real PR Review run.

To roll back, first read and record the exact protected previous directory and
current link. Under the same `slot.lock`, atomically replace only `current`
with a symlink to that recorded directory, then run `run-engine.sh --witness`
and compare the complete identity with its retained witness. Keep all release
directories and monetary records. A workflow revert restores old routing,
whose model availability was already unreliable; it does not prove health.

### Remaining acceptance

The proposed workflow still needs independent current-head review and merge,
then a real Actions current-head collect/review/publish/read-back. Its own PR
uses trusted base scripts, so missing new entrypoints before merge must not
be bypassed by executing PR-owned code. New push/rerun, stale/duplicate output,
cancellation/recovery, quality/cohort and real rollback/restoration retain their
own evidence gaps. #1149, #1153, #1154 and #1155 are not completed by these
manual replays. Historical failure Issues need individual disposition.

## Historical T4 source and acceptance record

## What this Task implements

`scripts/ci/pr-agent/deploy-runner.sh` is the repository-owned entrypoint for
the future Netcup slot. It has five explicit modes:

- `dry-run` reads the trusted inventory and bundle identities and writes
  nothing to the target tree.
- `verify` performs the same read-only checks, including archive SHA-256 and
  byte length, detached `DEPLOYMENT_IDENTITY.json`, every named member, safe
  archive paths, and the bytes of the extracted files in a temporary directory.
- `stage` stages an inactive disabled-provider revision with an explicit fixed
  fail-closed service unit; it makes no activation, isolation, capacity, or
  live-host claim.
- `install` stages a deterministic immutable deployment revision, protected operator inventory,
  separately supplied runtime TOML and systemd service/slice units. Release
  directories are mode `0755` for service-user traversal while extracted files
  are mode `0444`; each revision also stores the exact rendered `service.unit`
  and `slice.unit` bytes with closed SHA-256/length identities, so rollback
  never rerenders an earlier revision with today's tool. Service-writable state, attempt and output roots are separate
  mode `0750` paths. It is idempotent, writes a separate append-only
  deployment-receipt stream (never the T2 monetary ledger), and deliberately
  does not invoke `systemctl`. A state-less install is allowed only at a
  demonstrably pristine target boundary: malformed state, or missing state
  alongside any release, unit, receipt, current link, operator config or slot
  lock, stops for explicit manual recovery without clearing uncertain data.
- `rollback` switches only to the exact recorded previous release and carries
  archive byte length, SHA-256, detached identity length/SHA-256, member
  identities and runtime-config identity in both current/previous records.
  Repeating the same authenticated latest rollback is idempotent; release directories and ledger
  records (including `uncertain` records) are retained, and service activation
  remains pending.

The installer fixes its creation mask to `022`, so newly created intermediate
parents are `0755` even when the operator's caller uses a permissive mask.
Explicit private modes remain unchanged. Existing group/world-writable paths
still fail admission without chmod/chown repair. Positive test fixtures use
protected installation modes; separate negative cases retain unsafe paths.

The committed `scripts/ci/pr-agent/netcup-review.json` is intentionally
`active: false`. Its inventory now binds the accepted Flash Linux/amd64 bundle
`lmdj-pr-agent-linux-amd64-53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c.tar`,
SHA-256 `d43d11d489a879e8935b8a70d75665d311db3739f4c1c6907f159c6dcfcc6991`,
`361830400` bytes, and detached identity SHA-256
`0a04de3496b1519ba2b2d3276ce1d3b65c1cdafe9c282a2e1613dd3cbb8c67cd`,
`896` bytes, plus all five detached member identities. No archive is copied
into this repository.

## Accepted Flash bundle and bounded environment evidence

The archive was built from candidate source
`f4f6ebf64eca70b3c5cc17267e61ece7e529c05f`. Separately, PR #1198 source head
`8952cdc98fd67d50341f728b0562c96563737432`, merged as
`374793290e881389bf2513ab23873d8647aca5ad`, is the accepted installer source
and synthetic systemd-test provenance; the installer is not inside this
archive. The present inventory remains inactive, every admission flag is
false, the runtime path has null identity, and the default configuration keeps
all four providers disabled. The accepted archive and detached identity are retained at
`/tmp/lmdj-pr-agent-packaging/artifacts-v15-flash.mjwNyB`; the repository binds
their identities but does not publish or install them.

The lead artifact acceptance has already passed: static independent checks plus
inspection of the author-owned clean-base execution. The supplemental archive
verifier is author-owned evidence, not independently executed reviewer
acceptance. The full corrected builder stdout/stderr logs and exported exact
tool envelopes are in `/tmp/lmdj-pr-agent-packaging/artifacts-v15-flash.mjwNyB/`;
the build report is `/tmp/lmdj-pr-agent-plan/post-funding-bundle-build.md`.
No build or rerun is part of this inventory task.

The superseded v14 compatibility evidence remains explicitly historical:
archive SHA-256 `4359addd2521847509b61c655a346e1a59e49ebec87934024f35c066eb3f26d3`,
`361820160` bytes; detached identity SHA-256
`a1f7f67b6ae9390a3a4117f0bf1bb96a7269306aef5b12433d06b6e62dc3d2c3`,
`896` bytes. It is not the current v15 operator candidate.

The real-host synthetic systemd receipt
`/tmp/lmdj-pr-agent-plan/service-env-systemd-acceptance-receipt.md` records two
accepted bounded legs. The EnvironmentFile-present leg reached the selected
public marker under UID/GID 984/976 and all four blocked names
(`GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`) were
absent. The optional-file-missing leg reached a successful process result with
the selected variable absent and all four blocked names absent; both legs had
empty stderr and the exact terminal properties. The first failure and its
cleanup remain retained; no provider file contents were read, and synthetic
cleanup completed with only named resources removed. The legs used unique
temporary EnvironmentFile/slice/probe paths, a no-adapter probe,
`PrivateNetwork=yes`, and `RemainAfterExit=yes`; they are not production paths.
These legs do not prove production activation, credentials or authentication,
provider health/quality, measured capacity/coexistence, restart/crash/ledger
recovery, route/cutover, or T4 completion.

Proactive supplier balance/funding attestation is withdrawn; manual balances
are outside this gate. USD 1 per attempt, USD 20 pilot and USD 20 monthly
guards remain, as do real authentication/model/route/pricing and all-four
provider health/fallback/quality gates. Kimi's no-call restriction is
unchanged; Issues #1149, #1153, #1154, #1155 and #1188 remain open.

## Isolation and resource contract

The rendered fixed (non-template) unit uses `/usr/bin/python3.12`, user/group
`lmdj-pr-agent`, a single review slot, `CPUQuota=100%`, `MemoryMax=2G`, `CPUWeight=1`, and sibling
`lmdj-pr-review.slice`. It enables `PrivateTmp`, `PrivateDevices`,
`ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges`, an empty capability
set, and explicit `UnsetEnvironment` entries for GitHub write credentials.
The operator source `/etc/lmdj/pr-agent/runtime.toml` is digest-bound and copied
as `runtime.toml` into the service-owned release; the command binds that release
file, not the archive's inactive default `config.toml`. This layout is required
by the T2 guard, which rejects a symlinked source root and requires the engine
root/config to be owned by the runtime UID. The unit exports the T2 vendor path,
tokenizer cache, engine working directory and fixed input/output roots.
`/usr/bin/flock --nonblock
--exclusive /run/lmdj-pr-agent/slot.lock` is the one-slot admission boundary;
the service cannot be multiplied through a template instance. The engine
arguments state no GitHub write token, PR checkout, or PR hooks.
The existing heavy slice remains an inventory assertion of 14 CPUs / 48 GiB;
the entrypoint cannot edit it, the elastic policy, runner labels, workflows,
or a Docker daemon/group.

Operator inventory/runtime config, immutable release identities, the T2
monetary ledger and the separate deployment-receipt stream are
outside a repository workspace. Existing operator-owned config/unit files are
never overwritten when their bytes differ, and the runtime TOML is read-only to
the service user. Only the dedicated state/attempt/output roots and the
pre-provisioned slot lock are writable;
the release and `/etc` parents are not included in `ReadWritePaths`. The
monetary ledger is under service-writable `engine-state`; deployment receipts
and runtime transition state are under separate root-owned `operator-state` and
are not service-writable.
deployment identity is kept
inside each immutable release so rollback cannot silently mix a new identity
with an older bundle. No provider key value is read by this tooling, and no
GitHub API, supplier API, workflow dispatch, checkout, webhook, database or
public endpoint is created.

On a real host (`--target-root /`), installation first requires root EUID and
the provisioned service UID/GID. Before it writes a managed target, it rejects
symlinks, owner/mode drift, group/world-writable parents, and non-canonical
paths at the install root, root-owned operator state/inventory, operator
runtime source and target, and the control-unit parents. The runtime TOML is
root:`lmdj-pr-agent` mode `0440`; operator inventory/state and generated units
are root-controlled with their documented `0600`/`0700`/`0644` modes. It never
silently chowns a pre-existing unowned operator path. Fixture identity checks
are an explicit `PR_AGENT_DEPLOY_FIXTURE_IDENTITIES` emulation, not proof of
Linux service-account behavior; the real-host ownership/read-back acceptance
remains pending.

An interrupted transition can finish only when its target/current link and
stored authenticated unit bytes match the durable target and the receipt stream
contains one byte-canonical record in the closed unpublished v3 shape
equal to that transition's pending record. Current and retained previous
releases, nested detached identities, and every recorded operator path are
verified for exact keys, digest/length, owner, mode and secure parents before
any new intent, receipt append, state clear or file replacement; shared paths
are checked against the intended far-side state. The state witness must equal
the exact final unique-arrival receipt of the base history, and the pending
receipt is permitted only as that history's one final unique arrival in the
documented interrupted append window. A
malformed, legacy, stale, mismatched, or conflicting same-ID receipt fails
closed and leaves the transition and all records intact. Byte-identical repeated
lines are one arrival and are reconciled append-once. Every immutable release
also stores a protected `REVISION_RECORD.json`; receipt history authenticates
that complete record for each endpoint, requires the first arrival to be an
install from null, and requires each later `from_release` to equal the prior
unique `to_release`. Install receipt targets equal the destination inventory
exactly, including the operator-config basename; rollback targets equal the
invoking from-inventory. State and receipt leaves are also required to be
operator-owned `0600` regular files with secure parent chains before reads or
writes; insecure evidence is never repaired. Current must be the direct
literal canonical release symlink, so intermediate aliases are never repaired.
An install arrival whose source and destination are the same immutable release
is rejected even with a distinct transition ID; byte-identical same-ID
duplicates remain one arrival.
The closed receipt also commits each endpoint's canonical complete
`REVISION_RECORD.json` with `from_record_sha256`/`from_record_byte_length` and
`to_record_sha256`/`to_record_byte_length`; the source commitment is null only
for the initial install. A missing or partial commitment is an unpublished v3
schema failure and is refused read-only, never inferred from historical files.
Rollback input must exactly match the authenticated current inventory; only an
exact repeat of the latest authenticated rollback is a no-effect idempotent
read.

## Evidence boundary and pending prerequisites

The readiness refresh and read-only host-access receipt remain authoritative:
T4 is not deployed and is not review acceptance. The successful inventory
receipt is a source/runner observation, not free capacity or co-running
headroom. An earlier runner projection showed runner 04 with an elastic label;
the later classification/readback recorded its normalized baseline role, the
extra label removed and the other ten labels plus online status unchanged. The
`ci-pr-agent` label is an intended dedicated route, not a currently observed
runner label; operator registration and route read-back are pending. The later
strict BatchMode SSH probe recorded in
`/tmp/lmdj-pr-agent-plan/t4-readonly-host-access.md` at 22:41+08 proves
read-only access as `en@netcup01`; it supersedes the earlier readiness note that
had not attempted SSH. The earlier `sudo -n true` failure is historical; a
later sudoers correction receipt records successful noninteractive admin access.
Actual host capacity/admission remains unproved; this Task does not seek or
read a password, alter authentication, or mutate the host.

The source-only operator interface is intentionally limited to a reviewable
sequence. The following retained example is historical v14 compatibility
evidence, not the current v15 handoff:

```bash
deploy-runner.sh stage --config <inactive-operator-json> --bundle <exact-v14-archive> \
  --identity <detached-v14-identity> --runtime-config <disabled-provider-toml> \
  --target-root <isolated-target>
# Only after separate operator, runner, capacity, isolation, activation and
# runtime receipts pass:
deploy-runner.sh install --config <active-operator-json> --bundle <exact-v14-archive> \
  --identity <detached-v14-identity> --runtime-config <enabled-candidate-toml> \
  --target-root <isolated-target>
deploy-runner.sh rollback --config <active-operator-json> --target-root <isolated-target>
```

The current v15 handoff binds the accepted Flash archive and identity from the
trusted inventory (with the same inactive stage first); it must not silently
reuse the superseded v14 identities above.

These are source-tool shapes, not commands executed by this Task; production
paths and service identities must be supplied through the separately reviewed
administrator procedure. The dispatcher must atomically write the fixed
attempt input while holding the same non-blocking slot lock, then start the
fixed service only after all prerequisites are read back; publisher and
recovery read the output/ledger separately. Before a lead-authorized
install/activation, an operator must provide fresh,
read-back evidence for all of the following:

1. approved admin access and execution user;
2. runner-04 label classification and exact target host/service inventory;
3. actual heavy and sibling systemd `CPUQuota`/`MemoryMax` values;
4. available memory, pressure, swap and normal heavy-job co-running/peak
   measurements without stopping unrelated work;
5. runtime filesystem isolation, credential-file ownership and Python 3.12
   availability;
6. an activation receipt for the inactive trusted config and exact bundle;
7. controlled process exit/restart and durable task traceability.

The one-slot arithmetic envelope (1 vCPU / 2 GiB beside 14 vCPU / 48 GiB) is
not measured capacity. A same-host second process is concurrency, not host
redundancy. API authentication, model health, supplier success, fallback
quality, the 20-PR shadow cohort, and production publisher/cutover remain
T5/T6 acceptance, not T4 implementation evidence. Historical balance
observations are retained below but are not a current proactive funding or
balance admission gate.

## Credential preflight and service environment boundary

The following ordered observations are retained as historical evidence, not as
current T4 acceptance. On 2026-09-11 the selected candidate was
DeepSeek-V4.1-Flash (`deepseek-flash`), with no Pro fallback. An earlier
read-only checkpoint recorded `sudo -n true` failing and runner 04 still
carrying an elastic label. A later correction checkpoint recorded successful
`visudo -c` and noninteractive `sudo -n whoami` after correcting the exact
sudoers mode to `0440`; runner 04 was read back as baseline on both host and
main, its extra GitHub `elastic` label was removed, and its other ten labels
plus online status were unchanged. The later access details are retained in
`/tmp/lmdj-pr-agent-plan/t4-sudo-admission-refresh.md` and the runner-04
classification/readback in `/tmp/lmdj-pr-agent-plan/t4-admission-mutations-2026-09-11.md`.
These observations do not prove runtime isolation, resource coexistence,
capacity or T4 completion.

The earlier manual `PR-Agent Credential Preflight` workflow and its sanitized
authentication/balance observations remain historical evidence only. Its
balance workflow instruction and proactive supplier balance/funding admission
were withdrawn from this migration wave; do not rerun that workflow as a
current T4 prerequisite. Provider health, quality, four-provider fallback and
T5/T6 acceptance remain later gates, including the deferred
insufficient-balance/quota warning (#1188). The retained monetary guards are
USD 1 per attempt, USD 20 pilot and USD 20 per calendar month; they are not
funding-approval evidence.

The generated `lmdj-pr-agent.service` uses the existing provider environment
interface through exactly this optional, fixed service-scoped directive:

```ini
EnvironmentFile=-/etc/lmdj/pr-agent/provider.env
```

The operator, outside this source Task, must provision a regular non-symlink
file at that path below protected root-owned parents with `root:root` ownership
and mode `0600`. Each line must be a plain `NAME=value` assignment with no
`export` prefix. It may contain only the approved `PR_AGENT_*_API_KEY`
assignments required by the selected reviewed configuration; never put GitHub
write tokens, Python/tooling overrides or values in the unit. The installer does
not read, create, copy, hash, log, archive or repair this file, and does not
start/restart the service. Environment variables remain visible to the service
and child processes, so this is service scoping, not a claim of secret isolation.

The optional file preserves inactive no-key staging. A later active attempt with
a missing selected key still fails through the existing adapter boundary; an
environment assignment does not enable a disabled provider or establish pricing,
funding or admission. Synthetic service injection and file metadata checks are
separate lead-owned acceptance; no real key or provider request belongs to this
source Task.

## Verification performed by this Task

`tests/build/ci_pr_agent_runner_test.py` uses small meaningful tar fixtures to
exercise read-only dry-run, malformed/mismatched/tampered archive and identity
cases, traversal and isolation rejection, explicit fixture identity emulation,
state-less pristine admission, corrupt/missing-state recovery refusal,
canonical same-transition receipt reconciliation (every receipt line must be a
closed canonical v3 object with a non-null transition ID), authenticated unit
replacement, operator-state separation, idempotent install, repeated exact
rollback, reinstall-after-rollback, retention of uncertain ledger records,
authenticated first-arrival history, exact historical endpoint inventories,
state/receipt leaf and parent trust, actual writer crash recovery, and six
independently reset publication traces. Each trace binds service/slice bytes to
the authenticated A/B record identities, binds the latest receipt target to the
declared inventory, requires the nested `REVISION_RECORD.json` file fsync
before a new release directory is published, and compares final destination
device/inode/mode/UID/GID after the leg. The relocated receipt-tree refusal
also covers bytes outside the target-root snapshot. The durable suite ports all sixteen
independent N1-N3 scenarios. Historical PR1198 evidence retained above reported 95 tests with one v14 skip
in ordinary, child-`-S`, and `umask 0002` variants, and 95/95 when v14 was
enabled; those variants were not rerun by this correction. This correction's
ordinary run reports 96 tests, 94 passed and two explicit v14/current skips;
the run with both exact v14 and current archives reports 96/96 with zero skips.
The six-leg durability trace now
asserts source, destination and parent identities plus the complete far-side
state after every leg, including immediate complete first-A and first-B far
sides with initial monetary-ledger absence. Initial stage/install receipt-before-state crash probes
also recover append-once without changing the base current/previous pair. An opt-in
test validates the extracted bytes, vendor tree and direct canonical release
paths against the actual pinned T2 v14 archive without invoking a paid provider
call. The added EnvironmentFile contract test proves a synthetic provider value
is not copied into generated units or deployment artifacts, inactive staging
works without provider environment, and rollback restores retained historical
unit bytes lacking the new directive. It does not prove non-root Linux T2 CLI startup or real systemd admission;
those remain explicit external gaps. The test never calls `systemctl`, Docker or
a live API. The original implementation report at
`/tmp/lmdj-pr-agent-plan/service-environment-implementation.md` is preserved as
historical evidence. The F1-F6 correction report at
`/tmp/lmdj-pr-agent-plan/service-environment-f1-f6-correction.md` records the
corrected exact source HEAD/base, five-file inventory, test exits/counts/skips,
raw receipt paths, and remaining live acceptance gaps for this Task.

## S1 installed-attempt supervisor source boundary (2026-09-11)

The new `scripts/ci/pr_agent_attempt_supervisor.py` is the bounded source-side
entrypoint for the future installed supervisor. Its public verbs are exactly
`submit REQUEST_UUID`, `observe ATTEMPT_UUID`, `cancel ATTEMPT_UUID` and
read-only `status`; mutation accepts only a strict UUID and reads a
root-published spool generation. It does not accept a path, command, Python
interpreter, provider, environment, unit, hash or timeout from the caller, and
it refuses the old service-owned independent-flock profile and any GitHub
Actions intake until the separately owned S4 boundary exists.

The source binds closed internal schemas
`lmdj.pr-agent-supervisor-installation.v1`,
`lmdj.pr-agent-supervisor-admission.v1` and `lmdj.pr-agent-attempt.v1`.
Admission binds the exact existing seven-field T2 identity, positive job ID,
root-operator intake digest, complete input digest/length and T2 input digest,
successful producer witness and independently approved installation identity.
The fixed installation manifest binds source, adapter, config, bundle and
installation-record member bytes to an immutable deployment revision, fixed
`lmdj-pr-agent`/Python 3.12 runtime identity, and one-slot limits of 1 CPU,
2 GiB, CPUWeight 1, TasksMax 128, 600 seconds maximum engine deadline, 10
seconds launch observation, 5 seconds TERM/KILL grace and 10 seconds final
closure observation.

Each attempt uses one root-generated UUID and one durable append-only journal
whose protected checkpoint authenticates the predecessor tip. The source
journey is validate installation/spool, serialize metadata writers, acquire
the single `/run/lmdj-pr-agent/slot.lock` descriptor, publish immutable input,
persist `launch_pending`, launch one fixed `systemd-run --pipe --wait
--service-type=exec` invocation, observe InvocationID/MainPID/start/boot/
cgroup/slot identity, classify business/cancel/timeout, prove launcher and
descendant closure, authenticate no-follow result/coverage output, copy and
fsync root-owned evidence, read back a terminal receipt and only then close the
slot descriptor. Restart recovery observes the same exact unit and never
relaunches it; missing invocation, changed boot, output mutation, unknown wait
or unproven closure remains `uncertain` and fences new work. Duplicate terminal
requests revalidate the full journal and evidence and return the same result
without a second launch.

The S1 local suite is `tests/build/ci_pr_agent_attempt_supervisor_test.py`.
Its helper is a temporary installed executable, while the test uses real
Popen pipes, `pass_fds`, file publication, no-follow reads and competing OFD
flocks; only root/PID1/host identity and low-level launch observation are
replaced. The verified run on the clean local checkout passed 13 tests with
zero failures and zero skips. This is source/local journey evidence only: the
manifest is not installed, the production unit remains inactive, and no host,
systemd/PID1, provider credential, GitHub intake, runner capacity, paid
provider, T5 shadow or T6 cutover acceptance is claimed here. S2 owns protected
installation and the one-launcher transition; S3 owns the complete producer;
S4 owns authenticated Actions intake.

## Version and documentation impact

Version impact: none. Documentation impact: required for the Portal route
`/operations/testing-and-proof/`; its `source_paths` includes this report,
the deployment entrypoint, trusted inventory and contract test. This page
describes implemented repository tooling only. It is not a deployment
receipt, a systemd activation receipt, a resource acceptance report, or proof
that T4/T5/T6 is complete.
