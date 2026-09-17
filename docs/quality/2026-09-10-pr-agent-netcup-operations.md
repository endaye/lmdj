# PR-Agent Netcup operations — T4 implementation boundary

Date: 2026-09-10 (Asia/Shanghai)

Task: LMDJ #1153 / umbrella #1149 T4
Status: service-environment tooling and Flash inventory binding documented; host installation and review acceptance pending

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
