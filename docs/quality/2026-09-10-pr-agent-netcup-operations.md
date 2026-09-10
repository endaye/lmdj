# PR-Agent Netcup operations — T4 implementation boundary

Date: 2026-09-10 (Asia/Shanghai)

Task: LMDJ #1153 / umbrella #1149 T4
Status: repository tooling implemented; host installation and review acceptance pending

## What this Task implements

`scripts/ci/pr-agent/deploy-runner.sh` is the repository-owned entrypoint for
the future Netcup slot. It has four explicit modes:

- `dry-run` reads the trusted inventory and bundle identities and writes
  nothing to the target tree.
- `verify` performs the same read-only checks, including archive SHA-256 and
  byte length, detached `DEPLOYMENT_IDENTITY.json`, every named member, safe
  archive paths, and the bytes of the extracted files in a temporary directory.
- `install` stages a content-addressed release, protected operator inventory,
  separately supplied runtime TOML and systemd service/slice units. Release
  directories are mode `0755` for service-user traversal while extracted files
  are mode `0444`; service-writable state, attempt and output roots are separate
  mode `0750` paths. It is idempotent, writes a separate append-only
  deployment-receipt stream (never the T2 monetary ledger), and deliberately
  does not invoke `systemctl`. A state-less install is allowed only at a
  demonstrably pristine target boundary: malformed state, or missing state
  alongside any release, unit, receipt, current link, operator config or slot
  lock, stops for explicit manual recovery without clearing uncertain data.
- `rollback` switches only to the exact recorded previous release and carries
  archive byte length, SHA-256, detached identity length/SHA-256, member
  identities and runtime-config identity in both current/previous records.
  Repeating the same rollback is idempotent; release directories and ledger
  records (including `uncertain` records) are retained, and service activation
  remains pending.

The committed `scripts/ci/pr-agent/netcup-review.json` is intentionally
`active: false`. Its inventory binds the T2 Linux/amd64 bundle
`4359addd2521847509b61c655a346e1a59e49ebec87934024f35c066eb3f26d3` /
`361820160` bytes and detached identity
`a1f7f67b6ae9390a3a4117f0bf1bb96a7269306aef5b12433d06b6e62dc3d2c3` /
`896` bytes, plus all five detached member identities. No archive is copied
into this repository.

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
generated units match the durable target and the receipt stream contains
exactly one byte-canonical, closed receipt equal to that transition's pending
record. A malformed, mismatched, or duplicate same-ID receipt fails closed and
leaves the transition and all other records intact; a distinct occurrence gets
a new transition ID.

## Evidence boundary and pending prerequisites

The readiness refresh and read-only host-access receipt remain authoritative:
T4 is not deployed and is not review acceptance. The successful inventory
receipt is a source/runner observation, not free capacity or co-running
headroom. Runner 04 still carries an elastic label while its normalized policy
role is baseline and needs operator classification. The `ci-pr-agent` label is
an intended dedicated route, not a currently observed runner label; operator
registration and route read-back are pending. The later strict BatchMode SSH
probe recorded in `/tmp/lmdj-pr-agent-plan/t4-readonly-host-access.md` at
22:41+08 proves read-only access as `en@netcup01`; it supersedes the earlier
readiness note that had not attempted SSH. `sudo -n true` failed, so admin
access is unavailable, and actual host capacity/admission remains unproved;
this Task does not seek or read a password, alter authentication, or mutate the
host.

The future lead-authorized operator invocation is, in outline:

```bash
sudo install -d -o lmdj-pr-agent -g lmdj-pr-agent -m 0750 /var/lib/lmdj/pr-agent/engine-state /run/lmdj-pr-agent/attempt /run/lmdj-pr-agent/output
sudo install -d -o root -g root -m 0700 /var/lib/lmdj/pr-agent/operator-state
sudo install -o lmdj-pr-agent -g lmdj-pr-agent -m 0660 /dev/null /run/lmdj-pr-agent/slot.lock
sudo install -o root -g lmdj-pr-agent -m 0440 runtime.toml /etc/lmdj/pr-agent/runtime.toml
sudo install -o root -g root -m 0600 scripts/ci/pr-agent/netcup-review.json /etc/lmdj/pr-agent/netcup-review.json
sudo scripts/ci/pr-agent/deploy-runner.sh install --config /etc/lmdj/pr-agent/netcup-review.json --bundle /srv/lmdj/t2-v14.tar --identity /srv/lmdj/DEPLOYMENT_IDENTITY.json --runtime-config /etc/lmdj/pr-agent/runtime.toml
```

The dispatcher must atomically write the fixed attempt input while holding the
same non-blocking slot lock, then start the fixed service only after all
prerequisites are read back; publisher and recovery read the output/ledger
separately. No command above is executed by this Task. Before a lead-authorized install/activation, an operator must provide fresh,
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
redundancy. API authentication, balance, model health, supplier success,
fallback quality, the 20-PR shadow cohort, and production publisher/cutover
remain T5/T6 acceptance, not T4 implementation evidence.

## Dedicated credential preflight

The owner selected DeepSeek-V4.1-Flash (`deepseek-flash`, no Pro fallback) and
authorized deployment admission and credential verification on 2026-09-11.
The earlier sudo failure above is historical: a fresh `visudo -c` and
noninteractive `sudo -n whoami` now pass after correcting the exact sudoers
file mode to `0440`. Runner 04's policy was independently read back as baseline
on both host and current main; its extra GitHub `elastic` label was removed and
the other ten labels plus online status read back unchanged. Neither change
proves runtime isolation, resource coexistence or T4 completion.

The manual `PR-Agent Credential Preflight` workflow runs only for the repository
owner at main, on existing Netcup `ci-general` capacity. It consumes only the
dedicated `PR_AGENT_DEEPSEEK_API_KEY` in its check step, uses a fixed HTTPS
balance endpoint and no redirects/proxy environment/retries, and outputs only
finite authentication/availability metadata. It never outputs the key, raw
supplier body/error or balance amounts, copies a secret to the host, performs
inference, publishes review/scope, or activates the review service.

After this Task is merged, the authorized operation is:

```bash
gh workflow run pr-agent-credential-preflight.yml --ref main
```

Read back the exact run/attempt and successful job plus its sanitized receipt.
Secret metadata alone and mocked tests do not prove authentication. A successful
balance check is not USD funding admission or model health: the actual engine
still requires its reviewed price/context bounds, verified monetary funding,
durable ledger, restricted runtime credential injection and measured host
admission before any paid request. Other suppliers remain disabled; full
four-supplier health/fallback acceptance, T5 cohorts and T6 cutover remain open.
Budgets remain USD 1 per attempt, USD 20 pilot and USD 20/calendar month.

## Verification performed by this Task

`tests/build/ci_pr_agent_runner_test.py` uses small meaningful tar fixtures to
exercise read-only dry-run, malformed/mismatched/tampered archive and identity
cases, traversal and isolation rejection, explicit fixture identity emulation,
state-less pristine admission, corrupt/missing-state recovery refusal,
canonical same-transition receipt reconciliation, authenticated unit
replacement, operator-state separation, idempotent install, repeated exact
rollback, reinstall-after-rollback, and retention of uncertain ledger records. An opt-in
test validates the extracted bytes, vendor tree and direct canonical release
paths against the actual pinned T2 v14 archive without invoking a paid provider
call. It does not prove non-root Linux T2 CLI startup or real systemd admission;
those remain explicit external gaps. The test never calls `systemctl`, Docker or
a live API. The correction report at
`/tmp/lmdj-pr-agent-plan/t4-deployment-correction-report.md` records original
and final HEAD/tree, individual test counts/skips, finding dispositions, and
the remaining live acceptance gaps.

## Version and documentation impact

Version impact: none. Documentation impact: required for the Portal route
`/operations/testing-and-proof/`; its `source_paths` includes this report,
the deployment entrypoint, trusted inventory and contract test. This page
describes implemented repository tooling only. It is not a deployment
receipt, a systemd activation receipt, a resource acceptance report, or proof
that T4/T5/T6 is complete.
