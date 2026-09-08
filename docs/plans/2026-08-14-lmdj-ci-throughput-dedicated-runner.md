# LMDJ CI Throughput and Dual-Node Self-hosted Runner Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move routine trusted Linux CI workload onto a hardened Contabo Core pool and a netcup Web pool, preserve a minimal Hosted control plane, focus ordinary `main` runs by risk, and require full exact-main evidence for Product Build and release authority.

**Architecture:** GitHub-hosted Ubuntu continues to run Change Scope and PR Gate so scope/trust evidence survives a self-hosted outage. Trusted workload jobs use role labels: `ci-core` on the Contabo host shared with staging, `ci-web-heavy` on the CI-only netcup host, and `ci-general` on both. The manifest moves atomically to `lmdj.ci-scope.v2`, records `trusted_head`, and fails closed for untrusted heads. Main push later reuses the same path classifier; release tooling accepts only an exact-main run whose retained scope manifest is `full` and whose same-run Gate passed.

**Tech Stack:** GitHub Actions YAML, Python 3.11 standard library, Bash, systemd, GitHub REST API/`gh`, Contabo `cntb`, Ubuntu 24.04, GitHub Actions Runner, ccache, Emscripten 6.0.5, Node.js 22, Playwright.

## Global Constraints

- Work only in isolated worktrees and short-lived `feat/`, `fix/`, or `docs/` branches from fresh `origin/main`.
- Each repository Task below is one reviewable Conventional Commit. Operational Tasks with no tracked-file change create no commit.
- Push, PR creation, merge, branch protection, server purchase, sudo/systemd mutation, Runner registration, secret mutation, release, and deployment are separate authorization boundaries.
- Keep Change Scope and PR Gate on `ubuntu-24.04`; do not claim zero total Hosted minutes.
- Routine trusted Linux **workload** Hosted minutes target zero; control-plane Hosted Ubuntu targets at most 5 job-minutes per ordinary run.
- Preserve the existing busy -> queue behavior. Remove only token/API/no-online automatic Linux workload fallback.
- Private-fork workflows must remain disabled and must not receive write tokens, secrets, or variables.
- Re-query that repository setting immediately before every Task 6A-6F push and after every merge; any drift stops the rollout before another self-hosted job begins.
- Never run fork/untrusted head code on self-hosted infrastructure. A fork patch requires a maintainer-created same-repository branch and new evidence.
- The current Contabo services remain at existing capacity until both services no longer run as `lmdjadmin` and cannot obtain sudo, Docker, deployment secrets, or deployment-tree access.
- Keep the Contabo CI slice at or below 600% CPU and 16 GiB memory; preserve approximately 2 vCPU and 8 GiB for staging and the OS.
- Start netcup with two services. Do not add a third until dual-load benchmark evidence proves it is safe.
- Do not weaken behavior timeouts, coverage, sanitizer/stress, clean-room Proof, exact toolchain identity, LFS hydration, or No-Retry semantics.
- Full exact-main evidence is required before allocating a Product Build for team testing/release and before any release mutation.
- `main` remains non-cancelling per SHA. Focused evidence cannot substitute for a full run.
- Version impact: none. No Product, Module, Provider, Host, or product Contract version changes.
- Documentation impact: required for routing/main/release implementation Tasks. Update the current Portal pages in the same Task; do not create a Product Build snapshot.

## Dependency and Authority Gates

1. Merge the approved design/plan documentation before creating the implementation branch.
2. Owner separately authorizes the netcup purchase before Task 2.
3. Owner separately authorizes each Contabo/netcup sudo, systemd, firewall, Runner, and label mutation in Tasks 1-2.
4. Task 3's benchmark workflow must merge before it can receive `workflow_dispatch` on `main`.
5. Task 4 must pass before formal routing changes in Task 6A.
6. Live `origin/main` at `c20b9e9c` contains the standard release pipeline. Before Task 8, verify the implementation branch is based on a fresh `origin/main` that still contains `scripts/release.sh`, `tools/release/**`, and `tests/build/release_*_test.py`; do not rely on this recorded SHA as current forever.
7. Tasks 5-6F and 8 require separate push/PR/merge authorization. Do not infer those permissions from this plan.

## File Map

### New files

- `.github/actions/web-ci-proof/action.yml` — one pinned Web toolchain/setup/proof entry used by formal CI and benchmark CI.
- `.github/workflows/ci-self-hosted-benchmark.yml` — dispatch-only, non-authoritative netcup benchmark workflow.
- `tests/build/ci_benchmark_workflow_test.py` — benchmark workflow and shared-action contract.
- `tests/build/release_github_api_test.py` — strict Actions jobs/artifact/ZIP projection contracts extending the merged standard release pipeline.
- `tools/release/ci_evidence.py` — one read-only full exact-main verifier shared by release audit and prepare.
- `tests/build/release_ci_evidence_test.py` — closed verifier classification and prospective-audit contracts.
- `docs/quality/ci-runner-migration-acceptance.md` — fixed-path acceptance record populated from actual run/server evidence after cutover.

### Existing files changed by routing

- `.github/workflows/ci.yml` — Hosted control plane, manifest v2 inputs/outputs, trust conditions, role labels, no automatic Linux workload fallback.
- `scripts/ci/scope_policy.json` — v2 manifest identity, support-job map, and self-hosted job allowlist.
- `scripts/ci/change_scope.py` — `trusted_head`, v2 validation/output, later focused push behavior.
- `scripts/ci/pr_gate.py` — v2 schema, untrusted-head adjudication, and support-job inventory.
- `tests/build/ci_change_scope_test.py` — v2/trust and focused-main tests.
- `tests/build/ci_pr_gate_test.py` — untrusted, selected/skipped, and v2 Gate tests.
- `tests/build/ci_runner_fallback_test.py` — role routing and zero automatic workload fallback contracts.
- `tests/build/ci_workflow_topology_test.py` — exact job graph and Hosted control-plane topology.
- `tests/build/ci_build_acceleration_test.py` — self-hosted ccache/Web setup assertions after selector removal.
- `docs/quality/core-test-policy.md` — implemented runner topology, queue semantics, trust, timeout, and evidence.
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx` — current implemented CI routing/scope truth.

### Files changed or added by focused-main/release authority

- `docs/governance/git-workflow.md` — focused main and explicit full exact-main procedure.
- `docs/governance/version-management.md` — full manifest + same-run Gate requirement.
- `apps/architecture-portal/docs/operations/version-and-release.mdx` — release authority boundary.
- `tools/release/github_api.py` — typed Actions job/artifact projections.
- `tools/release/ci_evidence.py` — full scope/Gate/run evidence adjudication without mutation.
- `tools/release/audit.py` — full exact-main audit.
- `tools/release/prepare.py` — same full evidence precondition before preparation.
- `tests/build/release_audit_test.py` and `tests/build/release_prepare_test.py` — artifact/Gate/full-mode tests.
- `.agents/skills/lmdj-release/SKILL.md` — exact operator-facing full-evidence precondition.

---

### Task 1: Harden the Existing Contabo Runner Services

**Files:** none. This is an operational mutation with read-only evidence before and after.

**Interfaces:**
- Consumes: SSH alias `sg`; existing units `actions.runner.endaye-lmdj.contabo-lmdj-linux.service` and `actions.runner.endaye-lmdj.contabo-lmdj-linux-02.service`; work directories `/opt/actions-runner` and `/opt/actions-runner-02`.
- Produces: two online Runner services running as `lmdj-runner-01` and `lmdj-runner-02` inside `lmdj-ci.slice`, plus verified role labels for Tasks 6A-6F.

- [x] **Step 1: Record three recent successful full-main baselines**

```bash
baseline_dir="$(mktemp -d "${TMPDIR:-/tmp}/lmdj-ci-baseline.XXXXXX")"
GH_TOKEN="$(gh auth token --user endaye)"
export GH_TOKEN
gh run list --repo endaye/lmdj --workflow ci.yml --branch main --event push \
  --limit 20 --json databaseId,conclusion \
  --jq '.[] | select(.conclusion == "success") | .databaseId' \
  >"$baseline_dir/candidate-run-ids"
full_count=0
while IFS= read -r run_id; do
  run_json="$(gh api "repos/endaye/lmdj/actions/runs/$run_id")"
  head_sha="$(jq -er '.head_sha' <<<"$run_json")"
  run_dir="$baseline_dir/$run_id"
  mkdir -p "$run_dir"
  if ! gh run download "$run_id" --repo endaye/lmdj \
      --name "ci-scope-$head_sha" --dir "$run_dir" >/dev/null 2>&1; then
    continue
  fi
  if ! jq -e '.mode == "full" and .head_sha == $sha' \
      --arg sha "$head_sha" "$run_dir/ci-scope.json" >/dev/null; then
    continue
  fi
  gh api "repos/endaye/lmdj/actions/runs/$run_id/jobs?per_page=100" \
    >"$run_dir/jobs.json"
  if ! gh api "repos/endaye/lmdj/actions/runs/$run_id/timing" \
      >"$run_dir/timing.json"; then
    printf '%s\n' '{"billable":null}' >"$run_dir/timing.json"
  fi
  jq -n --argjson run "$run_json" \
    --slurpfile jobs "$run_dir/jobs.json" \
    --slurpfile timing "$run_dir/timing.json" '
      {
        run_id: $run.id,
        head_sha: $run.head_sha,
        queue_seconds: (($run.run_started_at | fromdateiso8601) - ($run.created_at | fromdateiso8601)),
        wall_seconds: (($run.updated_at | fromdateiso8601) - ($run.created_at | fromdateiso8601)),
        jobs: [$jobs[0].jobs[] | {name,runner_name,started_at,completed_at,conclusion}],
        billable: $timing[0].billable,
        timing_api_usable: (
          (($timing[0].billable.UBUNTU.jobs // 0) == 0)
          or (($timing[0].billable.UBUNTU.total_ms // 0) > 0)
        )
      }'
  full_count=$((full_count + 1))
  test "$full_count" -lt 3 || break
done <"$baseline_dir/candidate-run-ids"
test "$full_count" -eq 3
printf 'baseline_evidence_dir=%s\n' "$baseline_dir"
unset GH_TOKEN
```

Expected: three exact full manifests plus queue, wall-clock, per-job execution/runner, and GitHub billable projections are retained in the audited execution log. If the timing endpoint fails, or reports hosted job count with zero duration as observed on 2026-08-14, record billed minutes as externally unavailable; do not treat that zero as cost evidence or estimate billed minutes from wall-clock.

- [x] **Step 2: Verify the live private-fork and Runner baseline without mutation**

Run locally with the repository Owner account:

```bash
GH_TOKEN="$(gh auth token --user endaye)" gh api \
  repos/endaye/lmdj/actions/permissions/fork-pr-workflows-private-repos \
  | jq -e '
      .run_workflows_from_fork_pull_requests == false and
      .send_write_tokens_to_workflows == false and
      .send_secrets_and_variables == false
    '

GH_TOKEN="$(gh auth token --user endaye)" gh api \
  repos/endaye/lmdj/actions/runners \
  | jq '[.runners[] | {id,name,status,busy,labels:[.labels[].name]}]'
```

Expected: `jq -e` exits 0; both Contabo services are present with their current labels. If the fork expression fails, stop before any self-hosted expansion.

- [x] **Step 3: Restore the read-only Contabo asset projection through the installed CLI**

The installed `cntb 1.7` does not consume the four guessed `CNTB_OAUTH2_*` names, so do not put secrets into invented environment variables or command arguments. The Owner first configures `cntb` in a trusted terminal using the CLI's supported credential store, with the config file readable only by the Owner. Then run only these redacted/read-only checks:

```bash
cntb_config="$(cntb config view | awk '$1 == "--config" {print $2}')"
test -f "$cntb_config"
test "$(stat -f '%Lp' "$cntb_config" 2>/dev/null || stat -c '%a' "$cntb_config")" = 600
cntb config view \
  | sed -E 's/(oauth2-(client-secret|password))[[:space:]]+.*/\1 [REDACTED]/'
cntb get instances -o json \
  | jq '[.data[]? | {instanceId,displayName,status,regionName,productId,cpuCores,ramMb,diskMb}]'
```

Expected: the config projection shows non-empty credential fields only in redacted output; one exact instance maps to host `vmi3444835`; its lifecycle and SKU are recorded without any OAuth value. If the supported config path differs, resolve it from `cntb config view` and apply the same mode check before querying.

- [x] **Step 4: Reconfirm privilege and staging-health baselines before changing the first service**

```bash
ssh sg '
  id lmdjadmin
  sudo -n -u lmdjadmin sudo -n -l
  systemctl show actions.runner.endaye-lmdj.contabo-lmdj-linux.service \
    -p User -p ExecStart -p WorkingDirectory -p CPUQuotaPerSecUSec -p MemoryMax
  for container in lmdj-app-1 lmdj-caddy-1; do
    sudo docker inspect "$container" \
      --format "name={{.Name}} restart={{.RestartCount}} oom={{.State.OOMKilled}} running={{.State.Running}}"
  done
  sudo docker exec lmdj-app-1 python -c \
    "import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8000/health\", timeout=5).read().decode())"
  sudo bash -c '\''set -euo pipefail; set -a; source /opt/lmdj/shared/.env; set +a; curl -fsS --max-time 10 "https://${LMDJ_DOMAIN}/api/health"'\''
  sudo journalctl -k --since "24 hours ago" --no-pager | grep -Ei "oom|out of memory" || true
'
```

Expected baseline: `lmdjadmin` has `NOPASSWD: ALL`; the first Runner has no CPU/memory cap; both containers are running with zero OOM/restart drift; internal and public health return `{"ok":true}`. This is a required red-state observation, not acceptance.

- [x] **Step 5: Create the shared cache group, unprivileged users, and bounded slice**

After separate sudo authorization, run an audited remote shell:

```bash
ssh -t sg '
  set -euo pipefail
  sudo groupadd --system --force lmdj-ci-cache
  id lmdj-runner-01 >/dev/null 2>&1 || sudo useradd \
    --system --create-home --home-dir /var/lib/lmdj-runner-01 \
    --shell /usr/sbin/nologin --groups lmdj-ci-cache lmdj-runner-01
  id lmdj-runner-02 >/dev/null 2>&1 || sudo useradd \
    --system --create-home --home-dir /var/lib/lmdj-runner-02 \
    --shell /usr/sbin/nologin --groups lmdj-ci-cache lmdj-runner-02
  sudo install -d -o root -g lmdj-ci-cache -m 2770 /var/cache/lmdj-ccache
  sudo chgrp -R lmdj-ci-cache /var/cache/lmdj-ccache
  sudo chmod -R g+rwX /var/cache/lmdj-ccache
  sudo -u lmdj-runner-01 env CCACHE_DIR=/var/cache/lmdj-ccache ccache --max-size 8G
  sudo install -d -o root -g root -m 0755 /etc/systemd/system/lmdj-ci.slice.d
  sudo tee /etc/systemd/system/lmdj-ci.slice.d/resources.conf >/dev/null <<"EOF"
[Slice]
CPUQuota=600%
MemoryMax=16G
EOF
  sudo systemctl daemon-reload
'
```

Expected: both users exist without `sudo`/`docker`; `systemctl show lmdj-ci.slice -p CPUQuotaPerSecUSec -p MemoryMax` reports the bounded values.

- [x] **Step 6: Migrate only the first service and install a hardening drop-in**

```bash
ssh -t sg '
  set -euo pipefail
  unit=actions.runner.endaye-lmdj.contabo-lmdj-linux.service
  sudo systemctl stop "$unit"
  sudo chown -R lmdj-runner-01:lmdj-runner-01 /opt/actions-runner
  sudo install -d -o root -g root -m 0755 "/etc/systemd/system/$unit.d"
  sudo tee "/etc/systemd/system/$unit.d/10-lmdj-security.conf" >/dev/null <<"EOF"
[Service]
User=lmdj-runner-01
Group=lmdj-runner-01
Slice=lmdj-ci.slice
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
UMask=0027
ReadWritePaths=/opt/actions-runner /var/lib/lmdj-runner-01 /var/cache/lmdj-ccache
Environment=CCACHE_DIR=/var/cache/lmdj-ccache
Environment=CCACHE_UMASK=002
Environment=CMAKE_BUILD_PARALLEL_LEVEL=3
EOF
  sudo systemctl daemon-reload
  sudo systemctl start "$unit"
  sudo systemctl is-active --quiet "$unit"
'
```

Expected: the first service returns active as `lmdj-runner-01`. If it fails, leave it stopped and diagnose while service 02 remains available; do not restore root-capable execution as the fallback.

- [x] **Step 7: Prove the first service cannot cross the staging boundary**

```bash
ssh sg '
  set -euo pipefail
  ! sudo -u lmdj-runner-01 sudo -n true
  ! sudo -u lmdj-runner-01 test -r /var/run/docker.sock
  ! sudo -u lmdj-runner-01 test -r /opt/lmdj/shared/.env
  ! sudo -u lmdj-runner-01 test -w /opt/lmdj
  systemctl show actions.runner.endaye-lmdj.contabo-lmdj-linux.service \
    -p User -p Slice -p NoNewPrivileges -p ProtectSystem -p ProtectHome
'
```

Expected: all four negated access checks succeed; systemd reports the new user/slice/hardening.

- [x] **Step 8: Migrate and isolate service 02 after service 01 is healthy**

```bash
ssh -t sg '
  set -euo pipefail
  unit=actions.runner.endaye-lmdj.contabo-lmdj-linux-02.service
  sudo systemctl stop "$unit"
  sudo chown -R lmdj-runner-02:lmdj-runner-02 /opt/actions-runner-02
  sudo install -d -o root -g root -m 0755 "/etc/systemd/system/$unit.d"
  sudo tee "/etc/systemd/system/$unit.d/10-lmdj-security.conf" >/dev/null <<"EOF"
[Service]
User=lmdj-runner-02
Group=lmdj-runner-02
Slice=lmdj-ci.slice
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
UMask=0027
ReadWritePaths=/opt/actions-runner-02 /var/lib/lmdj-runner-02 /var/cache/lmdj-ccache
Environment=CCACHE_DIR=/var/cache/lmdj-ccache
Environment=CCACHE_UMASK=002
Environment=CMAKE_BUILD_PARALLEL_LEVEL=3
EOF
  sudo systemctl daemon-reload
  sudo systemctl start "$unit"
  sudo systemctl is-active --quiet "$unit"
  ! sudo -u lmdj-runner-02 sudo -n true
  ! sudo -u lmdj-runner-02 test -r /var/run/docker.sock
  ! sudo -u lmdj-runner-02 test -r /opt/lmdj/shared/.env
  ! sudo -u lmdj-runner-02 test -w /opt/lmdj
  systemctl show "$unit" \
    -p User -p Slice -p NoNewPrivileges -p ProtectSystem -p ProtectHome
'
```

Expected: service 01 stays online throughout; service 02 returns active as `lmdj-runner-02` and all four access denials pass.

- [x] **Step 9: Recheck staging health, then apply factual Contabo role labels**

```bash
ssh sg '
  for container in lmdj-app-1 lmdj-caddy-1; do
    sudo docker inspect "$container" \
      --format "name={{.Name}} restart={{.RestartCount}} oom={{.State.OOMKilled}} running={{.State.Running}}"
  done
  sudo docker exec lmdj-app-1 python -c \
    "import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8000/health\", timeout=5).read().decode())"
  sudo bash -c '\''set -euo pipefail; set -a; source /opt/lmdj/shared/.env; set +a; curl -fsS --max-time 10 "https://${LMDJ_DOMAIN}/api/health"'\''
  sudo journalctl -k --since "24 hours ago" --no-pager | grep -Ei "oom|out of memory" || true
'
```

The application restart count, OOM flag, and health must not regress during the migration.

Resolve runner IDs, then set the same custom label set on both:

```bash
for runner_name in contabo-lmdj-linux contabo-lmdj-linux-02; do
  runner_id="$(GH_TOKEN="$(gh auth token --user endaye)" gh api \
    repos/endaye/lmdj/actions/runners \
    --jq ".runners[] | select(.name == \"$runner_name\") | .id")"
  GH_TOKEN="$(gh auth token --user endaye)" gh api --method PUT \
    "repos/endaye/lmdj/actions/runners/$runner_id/labels" \
    --input - <<'JSON'
{"labels":["lmdj-linux","lmdj-linux-pool","contabo","shared-with-staging","ci-general","ci-core"]}
JSON
done
GH_TOKEN="$(gh auth token --user endaye)" gh api \
  repos/endaye/lmdj/actions/runners \
  | jq '[.runners[] | select(.name | startswith("contabo-lmdj-linux")) |
      {name,status,busy,labels:[.labels[].name]}]'
```

Expected: both runners are online and expose the default labels plus all six factual custom labels. This mutation requires its own authorization.

- [x] **Step 10: No commit**

This Task modifies only external infrastructure. Record command output and stop before netcup purchase/provisioning.

---

### Task 2: Purchase and Provision the netcup CI-only Host

**Files:** none. This is an external purchase and host mutation.

**Interfaces:**
- Consumes: Owner-approved `VPS 8000 G12 1M Rabatt` checkout; initial privileged SSH endpoint as execution input `NETCUP_BOOTSTRAP_HOST`; GitHub registration tokens.
- Produces: online `netcup-lmdj-linux` and `netcup-lmdj-linux-02` services with `ci-general` and `ci-web-heavy` labels.

- [x] **Step 1: Owner confirms the checkout boundary**

Expected invoice facts before payment: first month EUR 0; months 2-12 EUR 40.28; first-year estimate EUR 443.08; 12-month minimum/billing period; 16 shared x86 vCore, 64 GB DDR5 ECC, 2 TB NVMe, IPv4+IPv6. If checkout differs, stop and update the design rather than silently accepting a new contract.

- [x] **Step 2: Verify the fresh host before installing Runner software**

```bash
IFS= read -r NETCUP_BOOTSTRAP_HOST
test -n "$NETCUP_BOOTSTRAP_HOST"
export NETCUP_BOOTSTRAP_HOST
ssh -o BatchMode=yes "$NETCUP_BOOTSTRAP_HOST" '
  . /etc/os-release
  test "$ID" = ubuntu
  test "$VERSION_ID" = 24.04
  test "$(uname -m)" = x86_64
  test "$(nproc)" -ge 16
  awk "/MemTotal/ {exit !(\$2 >= 60000000)}" /proc/meminfo
  lsblk -b -d -o SIZE | awk "NR > 1 {if (\$1 >= 1900000000000) ok=1} END {exit !ok}"
'
```

Expected: every assertion exits 0. The CPU check proves exposed vCore count, not dedicated physical ownership.

- [x] **Step 3: Harden SSH/firewall and install pinned prerequisites**

After separate host-mutation authorization, enter the Owner's current public source address or CIDR and validate it locally. First create a named admin account from the provider-injected SSH key, and prove that login before disabling privileged SSH:

```bash
IFS= read -r NETCUP_SSH_CIDR
[[ "$NETCUP_SSH_CIDR" =~ ^[0-9A-Fa-f:.]+(/[0-9]{1,3})?$ ]]
export NETCUP_SSH_CIDR

ssh -t "$NETCUP_BOOTSTRAP_HOST" sudo bash -s <<'REMOTE'
set -euo pipefail
test -s /root/.ssh/authorized_keys
id lmdjadmin >/dev/null 2>&1 || useradd --create-home --shell /bin/bash --groups sudo lmdjadmin
install -d -o lmdjadmin -g lmdjadmin -m 0700 /home/lmdjadmin/.ssh
install -o lmdjadmin -g lmdjadmin -m 0600 \
  /root/.ssh/authorized_keys /home/lmdjadmin/.ssh/authorized_keys
printf '%s\n' 'lmdjadmin ALL=(ALL:ALL) NOPASSWD: ALL' \
  >/etc/sudoers.d/90-lmdjadmin
chmod 0440 /etc/sudoers.d/90-lmdjadmin
visudo -cf /etc/sudoers.d/90-lmdjadmin
REMOTE

NETCUP_HOST_ADDRESS="${NETCUP_BOOTSTRAP_HOST#*@}"
NETCUP_CI_HOST="lmdjadmin@$NETCUP_HOST_ADDRESS"
export NETCUP_CI_HOST
ssh -o BatchMode=yes "$NETCUP_CI_HOST" 'sudo -n true'
```

Only after that proof succeeds, install the baseline and disable password/root remote login:

```bash
ssh -t "$NETCUP_CI_HOST" sudo bash -s -- "$NETCUP_SSH_CIDR" <<'REMOTE'
set -euo pipefail
ssh_cidr="$1"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  ca-certificates curl jq unzip git git-lfs ccache cmake ninja-build \
  build-essential pkg-config python3 python3-venv python3-pip ufw gpg util-linux sysstat
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
npx --yes playwright@1.62.1 install-deps chromium webkit
install -d -o root -g root -m 0755 /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/60-lmdj-ci.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sshd -t
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow from "$ssh_cidr" to any port 22 proto tcp
ufw --force enable
systemctl reload ssh
systemctl enable --now sysstat
REMOTE
```

The NodeSource setup is accepted only for the Node 22 host tool needed to install the repository-pinned Playwright 1.62.1 system libraries; the formal action still pins Node 22 per job. Do not install Docker or release keys.

Verify:

```bash
ssh "$NETCUP_CI_HOST" '
  sudo sshd -T | grep -Fx "passwordauthentication no"
  sudo sshd -T | grep -Fx "permitrootlogin no"
  command -v git git-lfs ccache python3 node npm
  node --version | grep -E "^v22\."
  ! test -e /var/run/docker.sock
'
```

- [x] **Step 4: Create two unprivileged users and a bounded CI slice**

```bash
ssh -t "$NETCUP_CI_HOST" sudo bash -s <<'REMOTE'
set -euo pipefail
groupadd --system --force lmdj-ci-cache
for runner_number in 01 02; do
  runner_user="lmdj-runner-$runner_number"
  id "$runner_user" >/dev/null 2>&1 || useradd \
    --system --create-home --home-dir "/var/lib/$runner_user" \
    --shell /usr/sbin/nologin --groups lmdj-ci-cache "$runner_user"
done
for cache_dir in \
  /var/cache/lmdj-ccache /var/cache/lmdj-emsdk \
  /var/cache/lmdj-playwright /var/cache/lmdj-npm; do
  install -d -o root -g lmdj-ci-cache -m 2770 "$cache_dir"
done
runuser -u lmdj-runner-01 -- env CCACHE_DIR=/var/cache/lmdj-ccache ccache --max-size 100G
install -d -o root -g root -m 0755 /etc/systemd/system/lmdj-ci.slice.d
cat >/etc/systemd/system/lmdj-ci.slice.d/resources.conf <<'EOF'
[Slice]
CPUQuota=1400%
MemoryMax=48G
EOF
systemctl daemon-reload
systemctl show lmdj-ci.slice -p CPUQuotaPerSecUSec -p MemoryMax
for runner_user in lmdj-runner-01 lmdj-runner-02; do
  ! id -nG "$runner_user" | grep -qw sudo
  ! id -nG "$runner_user" | grep -qw docker
done
REMOTE
```

Expected: both users exist outside `sudo`/`docker`; all four caches are setgid and writable only by the CI cache group; ccache has a finite 100 GiB cap; the slice reports 1400% CPU and 48 GiB memory. Initial per-job `CMAKE_BUILD_PARALLEL_LEVEL` is 4.

- [x] **Step 5: Download one official Runner archive and verify its published digest**

```bash
ssh -t "$NETCUP_CI_HOST" sudo bash -s <<'REMOTE'
set -euo pipefail
runner_tmp="$(mktemp -d)"
trap 'rm -rf "$runner_tmp"' EXIT
curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
  -o "$runner_tmp/release.json"
asset_name="$(jq -er '[.assets[] | select(.name | test("^actions-runner-linux-x64-[0-9.]+[.]tar[.]gz$"))] | if length == 1 then .[0].name else error("expected one Linux x64 asset") end' "$runner_tmp/release.json")"
asset_url="$(jq -er --arg name "$asset_name" '.assets[] | select(.name == $name) | .browser_download_url' "$runner_tmp/release.json")"
asset_digest="$(jq -er --arg name "$asset_name" '.assets[] | select(.name == $name) | .digest | select(startswith("sha256:"))' "$runner_tmp/release.json")"
curl -fL "$asset_url" -o "$runner_tmp/$asset_name"
printf '%s  %s\n' "${asset_digest#sha256:}" "$runner_tmp/$asset_name" | sha256sum -c -
install -d -o lmdj-runner-01 -g lmdj-runner-01 -m 0750 /opt/actions-runner
install -d -o lmdj-runner-02 -g lmdj-runner-02 -m 0750 /opt/actions-runner-02
tar -xzf "$runner_tmp/$asset_name" -C /opt/actions-runner
/opt/actions-runner/bin/installdependencies.sh
cp -a /opt/actions-runner/. /opt/actions-runner-02/
chown -R lmdj-runner-01:lmdj-runner-01 /opt/actions-runner
chown -R lmdj-runner-02:lmdj-runner-02 /opt/actions-runner-02
REMOTE
```

Expected: calculated digest equals the official release-asset digest before extraction.

- [x] **Step 6: Register both services with exact factual labels**

Install one closed root-only registration helper that reads the token from standard input. It accepts only the two planned name/user/path tuples:

```bash
ssh "$NETCUP_CI_HOST" sudo tee /usr/local/sbin/register-lmdj-runner >/dev/null <<'REMOTE'
#!/usr/bin/env bash
set -euo pipefail
runner_name="$1"
runner_user="$2"
runner_dir="$3"
case "$runner_name:$runner_user:$runner_dir" in
  netcup-lmdj-linux:lmdj-runner-01:/opt/actions-runner|\
  netcup-lmdj-linux-02:lmdj-runner-02:/opt/actions-runner-02) ;;
  *) echo "unapproved Runner tuple" >&2; exit 2 ;;
esac
IFS= read -rs registration_token
runuser -u "$runner_user" -- "$runner_dir/config.sh" --unattended --replace \
  --url https://github.com/endaye/lmdj \
  --token "$registration_token" \
  --name "$runner_name" \
  --labels lmdj-linux,lmdj-linux-pool,netcup,ci-only-host,ci-general,ci-web-heavy \
  --work _work
unset registration_token
unit="actions.runner.endaye-lmdj.$runner_name.service"
cat >"/etc/systemd/system/$unit" <<EOF
[Unit]
Description=GitHub Actions Runner $runner_name
After=network-online.target
Wants=network-online.target

[Service]
User=$runner_user
Group=$runner_user
WorkingDirectory=$runner_dir
ExecStart=$runner_dir/runsvc.sh
Restart=always
RestartSec=5
Slice=lmdj-ci.slice
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
UMask=0027
ReadWritePaths=$runner_dir /var/lib/$runner_user /var/cache/lmdj-ccache
Environment=CCACHE_DIR=/var/cache/lmdj-ccache
Environment=CCACHE_UMASK=002
Environment=CMAKE_BUILD_PARALLEL_LEVEL=4
Environment=LMDJ_EMSDK_CACHE_ROOT=/var/cache/lmdj-emsdk
Environment=LMDJ_BROWSER_CACHE_ROOT=/var/cache/lmdj-playwright
Environment=npm_config_cache=/var/cache/lmdj-npm

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "$unit"
systemctl is-active --quiet "$unit"
REMOTE
ssh "$NETCUP_CI_HOST" sudo chmod 0700 /usr/local/sbin/register-lmdj-runner
```

In the same trusted terminal, obtain a one-hour token into a shell variable without printing it. Feed it over SSH standard input, one Runner at a time; the helper unsets it immediately after `config.sh` returns:

```bash
register_netcup_runner() {
  runner_name="$1"
  runner_user="$2"
  runner_dir="$3"
  registration_token="$(GH_TOKEN="$(gh auth token --user endaye)" gh api --method POST \
    repos/endaye/lmdj/actions/runners/registration-token --jq .token)"
  printf '%s\n' "$registration_token" | ssh "$NETCUP_CI_HOST" \
    sudo /usr/local/sbin/register-lmdj-runner \
      "$runner_name" "$runner_user" "$runner_dir"
  unset registration_token
}

register_netcup_runner netcup-lmdj-linux lmdj-runner-01 /opt/actions-runner
register_netcup_runner netcup-lmdj-linux-02 lmdj-runner-02 /opt/actions-runner-02
unset -f register_netcup_runner
ssh "$NETCUP_CI_HOST" sudo rm -f /usr/local/sbin/register-lmdj-runner
```

Registration token values must not appear in the execution transcript. If the first registration or unit fails, stop before registering the second.

- [x] **Step 7: Verify online inventory and isolation**

```bash
GH_TOKEN="$(gh auth token --user endaye)" gh api repos/endaye/lmdj/actions/runners \
  | jq '[.runners[] | select(.name | startswith("netcup-lmdj-linux")) |
      {name,status,busy,labels:[.labels[].name]}]'

ssh "$NETCUP_CI_HOST" '
  set -euo pipefail
  systemctl is-active --quiet sysstat
  systemctl show lmdj-ci.slice -p CPUQuotaPerSecUSec -p MemoryMax
  df -h / /var/cache
  for runner_user in lmdj-runner-01 lmdj-runner-02; do
    ! sudo -u "$runner_user" sudo -n true
    ! sudo -u "$runner_user" test -e /var/run/docker.sock
  done
  for unit in \
    actions.runner.endaye-lmdj.netcup-lmdj-linux.service \
    actions.runner.endaye-lmdj.netcup-lmdj-linux-02.service; do
    systemctl show "$unit" \
      -p ActiveState -p User -p Slice -p NoNewPrivileges -p ProtectSystem -p ProtectHome
  done
  sar -u 1 3
  free -h
'
```

Expected: exactly two online runners with `netcup`, `ci-only-host`, `ci-general`, and `ci-web-heavy`; neither user has sudo/Docker/release/deploy access.

- [x] **Step 8: No commit**

Stop with both nodes online. Do not route formal jobs yet.

---

### Task 3: Add a Non-authoritative netcup Benchmark Workflow

**Files:**
- Create: `.github/actions/web-ci-proof/action.yml`
- Create: `.github/workflows/ci-self-hosted-benchmark.yml`
- Create: `tests/build/ci_benchmark_workflow_test.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: pinned `LMDJ_EMSDK_REVISION`, Emscripten `6.0.5`, Node 22, Python 3.11, stable scripts `scripts/web-toolchain-conformance.sh proof`, `scripts/web-runtime-host.sh proof`, and `scripts/creator-web.sh proof`.
- Produces: composite action `./.github/actions/web-ci-proof` with inputs `lane` and `install-system-deps`; dispatch-only workflow inputs `lane` and `revision`.

- [x] **Step 1: Write the failing benchmark workflow contract**

Create `tests/build/ci_benchmark_workflow_test.py` using the repository's existing workflow-test loading pattern and add these exact assertions:

```python
def test_benchmark_is_dispatch_only_and_non_authoritative(self):
    source = BENCHMARK.read_text(encoding="utf-8")
    self.assertIn("workflow_dispatch:", source)
    self.assertNotRegex(source, r"(?m)^  (?:pull_request|push|schedule):")
    self.assertIn("permissions:\n  contents: read", source)
    self.assertNotIn("PR Gate", source)
    self.assertNotIn("pr_gate.py", source)

def test_benchmark_targets_only_the_web_role(self):
    source = BENCHMARK.read_text(encoding="utf-8")
    self.assertIn(
        "runs-on: [self-hosted, Linux, X64, lmdj-linux, "
        "lmdj-linux-pool, ci-web-heavy]",
        source,
    )
    for lane in ("web_toolchain", "web_runtime_host", "creator"):
        self.assertIn(f"- {lane}", source)

def test_benchmark_revision_is_the_dispatched_trusted_sha(self):
    source = BENCHMARK.read_text(encoding="utf-8")
    self.assertIn('[[ "$REVISION" =~ ^[0-9a-f]{40}$ ]]', source)
    self.assertIn('[[ "$REVISION" == "$TRUSTED_SHA" ]]', source)
    self.assertIn("TRUSTED_SHA: ${{ github.sha }}", source)

def test_formal_and_benchmark_workflows_share_one_proof_action(self):
    formal = FORMAL.read_text(encoding="utf-8")
    benchmark = BENCHMARK.read_text(encoding="utf-8")
    for source in (formal, benchmark):
        self.assertIn("uses: ./.github/actions/web-ci-proof", source)
```

- [x] **Step 2: Run the test and observe the intended failure**

Run:

```bash
python3 -m unittest tests.build.ci_benchmark_workflow_test -v
```

Expected: FAIL because both new files and shared action are absent.

- [x] **Step 3: Implement the shared composite action**

The action must:

- validate `lane` against `web_toolchain|web_runtime_host|creator` before any proof;
- run setup-python 3.11, setup-node 22, and `configure-build-acceleration` with ccache false;
- on Hosted, restore/install/activate the exact emsdk revision/version already declared by `ci.yml` through `actions/cache`;
- on self-hosted, use `$LMDJ_EMSDK_CACHE_ROOT/$LMDJ_EMSDK_REVISION-$LMDJ_EMSDK_VERSION`, serialize first installation with `flock`, install into a temporary sibling, activate there, atomically rename it, and never let two services mutate one toolchain tree;
- run locked `npm ci` in `tests/platform/web`, and additionally `apps/creator-web` only for Creator;
- after locked install, derive the pinned Playwright package version and set `PLAYWRIGHT_BROWSERS_PATH=$LMDJ_BROWSER_CACHE_ROOT/$playwright_version` on self-hosted; restore the normal Actions Playwright cache on Hosted;
- use the service-provided npm download cache, but always run locked `npm ci` and never share `node_modules` across checkouts;
- run `playwright install --with-deps chromium webkit` only when `install-system-deps == 'true'`; use `playwright install chromium webkit` on pre-provisioned self-hosted nodes;
- verify exact Emscripten identity for `web_runtime_host`;
- source `build/toolchains/emsdk/emsdk_env.sh` and dispatch exactly one existing stable proof script.

The final dispatch shell must be closed:

```bash
case "${{ inputs.lane }}" in
  web_toolchain) scripts/web-toolchain-conformance.sh proof ;;
  web_runtime_host) python3 tools/web-runtime/verify_emscripten.py && scripts/web-runtime-host.sh proof ;;
  creator) scripts/creator-web.sh proof ;;
  *) echo "unsupported Web CI lane" >&2; exit 2 ;;
esac
```

- [x] **Step 4: Refactor the three formal jobs to call the shared action without changing routing**

Keep current `runs-on`, `needs`, `if`, checkout/LFS, timeout, and job names. Replace only duplicated setup/proof steps with:

```yaml
- uses: ./.github/actions/web-ci-proof
  with:
    lane: web_runtime_host
    install-system-deps: "true"
```

Use `web_toolchain` in Web Toolchain, `web_runtime_host` in Web Runtime Host, and `creator` in Creator. Web Runtime Lab keeps its existing proof path in this Task because it does not share the same emsdk/Playwright setup contract.

This Task must not move Web jobs off their current formal runners.

- [x] **Step 5: Implement the dispatch-only benchmark workflow**

Before checkout, the workflow must require `inputs.revision` to be 40-hex and exactly equal to the dispatch's trusted `${{ github.sha }}`; this prevents an arbitrary fork/unreviewed object from being supplied to the self-hosted benchmark. Then checkout that exact revision with LFS, set the same emsdk env values as formal CI, target only `ci-web-heavy`, call the shared action with `install-system-deps: "false"`, upload Playwright traces on failure, and print runner name/CPU/memory/cache/timing evidence. It must not call `pr_gate.py` or create a required check contract.

- [x] **Step 6: Run focused and full local contracts**

```bash
python3 -m unittest tests.build.ci_benchmark_workflow_test -v
python3 -m unittest \
  tests.build.ci_build_acceleration_test \
  tests.build.ci_runner_fallback_test \
  tests.build.ci_workflow_topology_test -v
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
```

Expected: all pass; formal runner routing is unchanged.

- [x] **Step 7: Commit**

```bash
git add \
  .github/actions/web-ci-proof/action.yml \
  .github/workflows/ci-self-hosted-benchmark.yml \
  .github/workflows/ci.yml \
  tests/build/ci_benchmark_workflow_test.py
git diff --cached --check
git commit -m "feat(ci): add self-hosted web benchmark"
```

- [x] **Step 8: Stop for push/PR/merge authorization**

The new workflow cannot receive `workflow_dispatch` until it exists on `main`. Push, PR, full CI, and merge are separate authorizations. This small PR intentionally leaves formal routing unchanged.

---

### Task 4: Benchmark the netcup Web Pool

**Files:** none. This Task produces remote Actions evidence only.

**Interfaces:**
- Consumes: merged `.github/workflows/ci-self-hosted-benchmark.yml`; exact `main` SHA; two online `ci-web-heavy` services.
- Produces: cold/warm and idle/contention run IDs that authorize or block Task 5.

- [x] **Step 1: Dispatch one cold run per heavy lane**

```bash
target_sha="$(git ls-remote git@github.com:endaye/lmdj.git refs/heads/main | awk '{print $1}')"
for lane in web_toolchain web_runtime_host creator; do
  GH_TOKEN="$(gh auth token --user endaye)" gh workflow run \
    ci-self-hosted-benchmark.yml --repo endaye/lmdj --ref main \
    -f lane="$lane" -f revision="$target_sha"
done
```

Expected: every job's API `runner_name` begins with `netcup-lmdj-linux`; cache status is cold/miss where applicable.

- [x] **Step 2: Dispatch three warm runs per lane serially**

Wait for each run to complete before the next. Record run ID, runner name, queue seconds, execution seconds, CPU/load/memory, cache status, and semantic result. Do not rerun a semantic failure; diagnose and create a new run only after an environment/code correction.

- [x] **Step 3: Run dual-load contention pairs**

Dispatch `web_runtime_host` and `creator` together, then `web_toolchain` and `web_runtime_host` together. Preserve traces for every failure.

- [x] **Step 4: Apply the benchmark gate**

Proceed only when:

- each lane has at least three consecutive warm successes;
- at least one success occurs under dual load;
- dual-load execution is no more than 25% slower than that lane's idle median;
- neither service exceeds the 48 GB slice or causes OOM;
- all proof assertions/timeouts remain unchanged.

If the gate fails, reduce per-job parallelism from 4 to 3 and repeat as new benchmark evidence. Do not add a third service or relax test timeouts.

- [x] **Step 5: No commit**

Stop with the accepted run IDs. Formal routing is still unchanged.

---

### Task 5: Migrate the CI Manifest and Trust Gate Atomically to v2

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/ci/scope_policy.json`
- Modify: `scripts/ci/change_scope.py`
- Modify: `scripts/ci/pr_gate.py`
- Modify: `tests/build/ci_change_scope_test.py`
- Modify: `tests/build/ci_pr_gate_test.py`
- Modify: `tests/build/ci_runner_fallback_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `docs/quality/core-test-policy.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

**Interfaces:**
- Consumes: accepted Task 4 run IDs and current `lmdj.ci-scope.v1` producer/Gate.
- Produces: atomic `lmdj.ci-scope.v2`, manifest field `trusted_head: bool`, job output `trusted-head`, and fail-closed workload conditions. It deliberately preserves every current `runs-on` value and the Linux selector for the progressive cutover Tasks.

- [x] **Step 1: Write failing v2/trust tests**

Add tests that require:

```python
def test_manifest_v2_records_closed_trust(self):
    manifest = self.classify(["docs/guide.md"], trusted_head=True)
    self.assertEqual(manifest["schema"], "lmdj.ci-scope.v2")
    self.assertIs(manifest["trusted_head"], True)
    broken = dict(manifest)
    broken["trusted_head"] = "true"
    with self.assertRaisesRegex(ValueError, "trusted head"):
        self.module.validate_manifest(broken, self.policy)

def test_untrusted_selected_self_hosted_lane_fails_gate(self):
    manifest = self.manifest(lanes={"core_ubuntu"}, trusted_head=False)
    report = evaluate(manifest, self.results(core_ubuntu="skipped"), self.policy)
    self.assertFalse(report.ok)
    self.assertIn("untrusted fork blocked from self-hosted CI", report.errors)
```

Update topology tests to require Change Scope/PR Gate on `ubuntu-24.04`, retain `select-ubuntu-runner`, and prove every future self-hosted workload job includes the trusted-head condition before any static route is introduced.

- [x] **Step 2: Run the tests and observe v1/selector failures**

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test \
  tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test \
  tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test -v
```

Expected: FAIL on schema v1, absent trust field, absent job output, and absent closed trust conditions.

- [x] **Step 3: Change the policy atomically**

In `scope_policy.json`:

- set `manifest_schema` to `lmdj.ci-scope.v2`;
- retain the current `select-ubuntu-runner` entries in `lane_jobs` until each dependent lane is cut over;
- keep `select-macos-runner`, `macos-primary`, `core-macos`, and `core-asan-macos` unchanged;
- add closed `self_hosted_jobs` containing exactly Docs/static, Portal, CI Contract, Core Ubuntu/ASan/Coverage, all four Web jobs, Deploy Contract, Chameleon Lab, and Package;
- keep the 14 lane names and all path ownership/full rules unchanged.

Update policy validation to reject a missing, extra, duplicate, or non-formal self-hosted job.

- [x] **Step 4: Add trust to the v2 producer**

Change `build_manifest` to accept keyword-only `trusted_head: bool`; add it to `ALLOWED_MANIFEST_KEYS` and the encoded manifest. Reject non-boolean values. Add CLI `--head-repository`; derive:

```python
trusted_head = (
    args.event != "pull_request"
    or args.head_repository == args.repository
)
```

Write `trusted-head=true|false` to `$GITHUB_OUTPUT`, include Trust in the job summary, and pass `HEAD_REPOSITORY` from the workflow event. Do not derive trust from PR title, labels, code, or changed paths.

- [x] **Step 5: Make PR Gate fail closed for an untrusted selected workload**

Validate `trusted_head` before results. When false and any required job is in `policy["self_hosted_jobs"]`, prepend the exact error:

```text
untrusted fork blocked from self-hosted CI
```

The selected skipped jobs remain ordinary errors too. A trusted head keeps the existing selected-success/unselected-skipped truth table.

- [x] **Step 6: Add the trust condition without changing routing**

Keep:

```yaml
change-scope:
  runs-on: ubuntu-24.04

pr-gate:
  runs-on: ubuntu-24.04
```

Every self-hosted job condition must include:

```yaml
needs.change-scope.outputs.trusted-head == 'true'
```

Add that condition now to every job named by `self_hosted_jobs`, including jobs still Hosted during the rollout. Keep all current `runs-on`, `needs`, selector outputs, ccache settings, and Web system-dependency behavior unchanged. This makes an accidental future repository setting change fail closed before the first static self-hosted route exists.

- [x] **Step 7: Preserve existing main-full behavior in this Task**

Do not edit the line that forces ordinary push full yet. Task 5 changes schema/trust only, so the merge's exact main SHA receives a full run on the current routing.

- [x] **Step 8: Update implemented documentation in the same commit**

Update `core-test-policy.md` and `/operations/testing-and-proof/` to state:

- Change Scope/Gate Hosted control-plane exception;
- `lmdj.ci-scope.v2` trust field and private-fork block;
- Contabo `shared-with-staging` Core/general role and resource boundary;
- netcup CI-only Web role and two-service concurrency;
- current selector behavior remains temporarily in place for lanes not yet cut over;
- busy queues and unmatched jobs auto-cancel after GitHub's 24-hour queue limit;
- real `runner_name`, queue, execution, worker time, and wall-clock remain separate evidence.

Documentation impact: required. Affected Portal route: `/operations/testing-and-proof/`.

- [x] **Step 9: Run all CI contract and Portal verification**

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test \
  tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test \
  tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test \
  tests.build.ci_benchmark_workflow_test -v
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
```

Expected: all tests pass; Portal builds; v2 producer/Gate/tests move together; routing remains unchanged.

- [x] **Step 10: Commit**

```bash
git add \
  .github/workflows/ci.yml \
  scripts/ci/scope_policy.json scripts/ci/change_scope.py scripts/ci/pr_gate.py \
  tests/build/ci_change_scope_test.py tests/build/ci_pr_gate_test.py \
  tests/build/ci_runner_fallback_test.py tests/build/ci_workflow_topology_test.py \
  docs/quality/core-test-policy.md \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --check
git commit -m "feat(ci): add closed trust evidence"
```

- [x] **Step 11: Stop for remote transition authorization**

Before push, re-verify private-fork workflows remain disabled. Push/PR/`ci:full`/merge are separate boundaries. The merge remains full because central CI files changed.

---

### Task 6A: Route Web Toolchain to the netcup Role

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/build/ci_runner_fallback_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tests/build/ci_build_acceleration_test.py`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

- [x] **Step 1: Make the routing test fail**

Require `web-toolchain-conformance` to have exact `runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-web-heavy]`, retain `needs: change-scope`, include `trusted-head == 'true'`, and call `web-ci-proof` with `lane: web_toolchain` plus `install-system-deps: "false"`.

```bash
python3 -m unittest tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test tests.build.ci_build_acceleration_test -v
```

Expected: FAIL because Web Toolchain is still Hosted.

- [x] **Step 2: Change only Web Toolchain routing and current Portal truth**

Make exactly the tested YAML change. Preserve checkout/LFS, timeout, proof assertions, artifacts, and all other jobs. Update `/operations/testing-and-proof/` to show only Web Toolchain as cut over.

- [x] **Step 3: Verify and commit**

```bash
python3 -m unittest tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test tests.build.ci_build_acceleration_test -v
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git add .github/workflows/ci.yml tests/build/ci_runner_fallback_test.py \
  tests/build/ci_workflow_topology_test.py tests/build/ci_build_acceleration_test.py \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --check
git commit -m "feat(ci): route web toolchain to netcup"
```

- [x] **Step 4: Prove three consecutive formal successes before continuing**

After separately authorized push/PR/full merge, dispatch lane `web_toolchain` three times on the merged exact `main` SHA. For every run, use the Jobs API to prove `runner_name` starts with `netcup-lmdj-linux`, Gate succeeds, no semantic rerun occurred, and execution/resource thresholds pass. Roll back only this commit if any of the three fails.

---

### Task 6B: Route Creator to the netcup Role

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/build/ci_runner_fallback_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tests/build/ci_build_acceleration_test.py`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

- [x] **Step 1: Add a failing Creator route contract**

Require `creator-web` to use exact role `ci-web-heavy`, preserve `needs: change-scope` and the trust condition, and call `web-ci-proof` with `lane: creator` and `install-system-deps: "false"`.

```bash
python3 -m unittest tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test tests.build.ci_build_acceleration_test -v
```

Expected: FAIL because Creator is still Hosted.

- [x] **Step 2: Implement only that route and update current Portal truth**

Do not change Web Runtime Host/Lab or the selector. Run:

```bash
python3 -m unittest tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test tests.build.ci_build_acceleration_test -v
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
```

- [x] **Step 3: Commit and prove the lane**

```bash
git add .github/workflows/ci.yml tests/build/ci_runner_fallback_test.py \
  tests/build/ci_workflow_topology_test.py tests/build/ci_build_acceleration_test.py \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --check
git commit -m "feat(ci): route creator to netcup"
```

After separately authorized push/PR/full merge, dispatch `creator` three times on exact `main`; require netcup `runner_name`, Gate success, unchanged semantics, and accepted resource/timing evidence before Task 6C.

---

### Task 6C: Route Web Runtime Host to the netcup Role

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/ci/scope_policy.json`
- Modify: `tests/build/ci_change_scope_test.py`
- Modify: `tests/build/ci_pr_gate_test.py`
- Modify: `tests/build/ci_runner_fallback_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tests/build/ci_build_acceleration_test.py`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

- [x] **Step 1: Write failing route/support-map tests**

Require `web-runtime-host` to use `ci-web-heavy`, remove `select-ubuntu-runner` from its `needs` and `lane_jobs.web_runtime_host`, keep its exact Emscripten identity check, and use `web-ci-proof` with `install-system-deps: "false"`. Require the selector condition/result guard to retain only lanes that still depend on it.

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test -v
```

Expected: FAIL on the Hosted/selector route and support map.

- [x] **Step 2: Implement the single-lane cutover**

Change only the tested job, support map, Gate projections derived from policy, tests, and current Portal route. Do not change Web Runtime Lab or Core/Package selector dependencies.

- [x] **Step 3: Verify and commit**

Run and stage the exact declared files:

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test -v
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git add .github/workflows/ci.yml scripts/ci/scope_policy.json \
  tests/build/ci_change_scope_test.py tests/build/ci_pr_gate_test.py \
  tests/build/ci_runner_fallback_test.py tests/build/ci_workflow_topology_test.py \
  tests/build/ci_build_acceleration_test.py \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --check
git commit -m "feat(ci): route web runtime host to netcup"
```

- [x] **Step 4: Prove three consecutive merged-main dispatches**

Dispatch lane `web_runtime_host` three times. Require netcup `runner_name`, exact Emscripten identity, same-run Gate success, trace retention on failure, and thresholds before Task 6D.

---

### Task 6D: Route Web Runtime Lab to the netcup Role

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/ci/scope_policy.json`
- Modify: `tests/build/ci_change_scope_test.py`
- Modify: `tests/build/ci_pr_gate_test.py`
- Modify: `tests/build/ci_runner_fallback_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tests/build/ci_build_acceleration_test.py`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

- [x] **Step 1: Make route/support-map tests fail**

Require `web-runtime-lab` to use `ci-web-heavy`, remove its selector dependency from YAML and `lane_jobs.web_runtime_lab`, preserve its separate stable proof steps/timeouts, and keep only Core/ASan/Coverage/Package in the Linux selector guard.

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test -v
```

Expected: FAIL on the selector route and support map.

- [x] **Step 2: Implement, verify, and commit only the Lab cutover**

Run and stage the exact declared files:

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test -v
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git add .github/workflows/ci.yml scripts/ci/scope_policy.json \
  tests/build/ci_change_scope_test.py tests/build/ci_pr_gate_test.py \
  tests/build/ci_runner_fallback_test.py tests/build/ci_workflow_topology_test.py \
  tests/build/ci_build_acceleration_test.py \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --check
git commit -m "feat(ci): route web runtime lab to netcup"
```

- [x] **Step 3: Prove three consecutive merged-main dispatches**

Dispatch lane `web_runtime_lab` three times and require netcup `runner_name`, Gate success, unchanged behavior assertions, and accepted timing/resources before Task 6E.

---

### Task 6E: Route General Linux Jobs to the Dual-node General Role

**Files:** `.github/workflows/ci.yml`, `tests/build/ci_runner_fallback_test.py`, `tests/build/ci_workflow_topology_test.py`, `docs/quality/core-test-policy.md`, and `apps/architecture-portal/docs/operations/testing-and-proof.mdx`.

- [x] **Step 1: Write exact general-role assertions**

Require Docs/static, Portal, CI Contract, Deploy Contract, and Chameleon Lab to use `[self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-general]`, retain only `change-scope`/existing reusable-workflow dependencies, and include the trust condition. Change Scope and PR Gate must remain `ubuntu-24.04`.

```bash
python3 -m unittest tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test -v
```

Expected: FAIL because these workload jobs are still Hosted.

- [x] **Step 2: Route only those five jobs**

Do not change the native Core selector. Update the two current documentation sources to distinguish the Hosted control plane from general self-hosted workload.

- [x] **Step 3: Verify, commit, and prove**

Run, stage, inspect, and commit:

```bash
python3 -m unittest tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test -v
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git add .github/workflows/ci.yml tests/build/ci_runner_fallback_test.py \
  tests/build/ci_workflow_topology_test.py docs/quality/core-test-policy.md \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --check
git commit -m "feat(ci): route general workload to dual-node pool"
```

After separately authorized merge, run three dispatches selecting `docs_static,portal,ci_contract,deploy_contract,chameleon_lab`. Require every workload `runner_name` to be one of the four role-matching services and Change Scope/Gate to remain Hosted.

---

### Task 6F: Route Native Core and Remove Linux Automatic Hosted Fallback

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/ci/scope_policy.json`
- Modify: `tests/build/ci_change_scope_test.py`
- Modify: `tests/build/ci_pr_gate_test.py`
- Modify: `tests/build/ci_runner_fallback_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tests/build/ci_build_acceleration_test.py`
- Modify: `docs/quality/core-test-policy.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`

- [x] **Step 1: Write the final fail-closed topology tests**

Require Core Ubuntu, Core ASan, Core Coverage, and Package to use exact `ci-core`; require native Core ccache; remove `select-ubuntu-runner` from all four `lane_jobs`; require the selector job, result key, token, API probe, and every `ubuntu-24.04` workload fallback string to be absent. Keep macOS selector behavior unchanged.

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test -v
```

Expected: FAIL while native jobs still consume the selector and automatic Hosted fallback exists.

- [x] **Step 2: Implement the final selector removal atomically**

Remove the Linux selector, all remaining `needs`/output/result references, and the `SELF_HOSTED_RUNNER_READ_TOKEN` Linux use. Preserve busy-to-queue as the platform behavior: a matching saturated pool queues, an offline/missing role stays queued until GitHub's 24-hour limit, and no routine Linux workload buys Hosted capacity. Update current docs with the final topology.

- [x] **Step 3: Run verification and commit**

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test tests.build.ci_benchmark_workflow_test -v
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git add .github/workflows/ci.yml scripts/ci/scope_policy.json \
  tests/build/ci_change_scope_test.py tests/build/ci_pr_gate_test.py \
  tests/build/ci_runner_fallback_test.py tests/build/ci_workflow_topology_test.py \
  tests/build/ci_build_acceleration_test.py docs/quality/core-test-policy.md \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx
git diff --cached --check
git commit -m "feat(ci): route native core to contabo"
```

- [x] **Step 4: Prove native routing and the no-fallback failure mode**

After authorized merge, dispatch `core_ubuntu,core_asan,core_coverage,package` three times and require Contabo `runner_name` plus Gate success. In a separately authorized maintenance window, stop one redundant `ci-core` service and prove jobs still use the other; do not stop both merely to test the 24-hour failure path. Prove no Hosted workload through Jobs API and billing categorization.

---

### Task 7: Prove Final Formal Role Routing on PR and Full Main

**Files:** none. Remote CI evidence only.

**Interfaces:**
- Consumes: Tasks 5-6F commits and four online services.
- Produces: one PR full run and one merged-main full run with exact runner assignments.

- [x] **Step 1: Push and open the routing PR only after authorization**

Declare `CI mode: full`, all 14 lanes selected, none skipped, and Documentation impact required for `/operations/testing-and-proof/`.

- [x] **Step 2: Apply `ci:full` and rerun all jobs for the current head**

Expected manifest: `lmdj.ci-scope.v2`, `trusted_head=true`, `mode=full`, 14 selected lanes, no `select-ubuntu-runner` support job.

- [x] **Step 3: Verify exact runner assignment through the Jobs API**

Expected:

- Web Toolchain, Web Runtime Host, Creator, Web Runtime Lab -> `netcup-lmdj-linux*`;
- Core Ubuntu, ASan, Coverage, Package -> `contabo-lmdj-linux*`;
- Change Scope and PR Gate -> GitHub-hosted Ubuntu;
- macOS policy remains unchanged.

Reject registration-only or label-only evidence.

- [x] **Step 4: Merge only after separate authorization**

Because `.github/workflows/ci.yml` and `scripts/ci/**` are full rules, the resulting main SHA must run full before Task 8 changes main scope. Verify all formal results and the same-run Gate.

- [x] **Step 5: Roll back only the routing commit if evidence fails**

Do not re-enable automatic Hosted workload fallback. If netcup is unstable, route only the affected Web lane back under a separately reviewed temporary selector or leave it blocked while diagnosing.

---

### Task 8: Focus Main Pushes and Bind Release Authority to Full Exact-main Evidence

**Prerequisite:** fresh `origin/main` contains the standard release pipeline files listed in Dependency Gate 6. If any are absent, stop; do not implement focused main without its release evidence consumer.

**Files:**
- Modify: `scripts/ci/change_scope.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/build/ci_change_scope_test.py`
- Modify: `tests/build/ci_workflow_topology_test.py`
- Modify: `tools/release/github_api.py`
- Create: `tools/release/ci_evidence.py`
- Modify: `tools/release/audit.py`
- Modify: `tools/release/prepare.py`
- Modify: `tests/build/release_audit_test.py`
- Modify: `tests/build/release_prepare_test.py`
- Create: `tests/build/release_github_api_test.py`
- Create: `tests/build/release_ci_evidence_test.py`
- Modify: `tests/build/release_skill_test.py`
- Modify: `.agents/skills/lmdj-release/SKILL.md`
- Modify: `docs/governance/git-workflow.md`
- Modify: `docs/governance/version-management.md`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`

**Interfaces:**
- Consumes: v2 manifest/Gate from Task 5; release intent `merged_main_run_id`; standard release `GitHubClient`.
- Produces: focused ordinary push; `CiScopeProjection`; release audit/prepare that requires exact SHA, `mode=full`, and same-run Gate success.

- [x] **Step 1: Write failing focused-push tests**

Replace `test_main_and_dispatch_are_full` with explicit cases:

```python
def test_docs_main_push_is_focused(self):
    manifest = self.classify(["docs/guide.md"], event_name="push")
    self.assertEqual(manifest["mode"], "focused")
    self.assertEqual(self.true_lanes(manifest), {"docs_static"})

def test_dispatch_without_lanes_is_still_full(self):
    manifest = self.classify(["docs/guide.md"], event_name="workflow_dispatch")
    self.assertEqual(manifest["mode"], "full")

def test_unverifiable_push_base_is_full(self):
    manifest = self.classify_unverifiable_push(base_sha="0" * 40)
    self.assertEqual(manifest["mode"], "full")
    self.assertIn("unverifiable push base", manifest["reasons"])
```

Keep Product Assembly, Contract, CI control, unknown path, incomplete inventory, and three-expensive-family push cases full.

- [x] **Step 2: Write failing release evidence tests**

Extend the fake GitHub client with exact scope and job projections. Define independent test constants `LANES` for the exact 14 v2 lane names and `FULL_REQUIRED_JOBS` for the full formal/support job set; do not derive the expected values from production code. Require tests for:

```python
def test_release_accepts_only_full_exact_main_ci(self):
    self.github.scope = CiScopeProjection(
        schema="lmdj.ci-scope.v2", base_sha="a" * 40, head_sha=TARGET,
        mode="full", trusted_head=True,
        selected_lanes=tuple(sorted(LANES)),
        required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
    )
    self.github.jobs = [
        RunJobProjection(1, 123, "Change Scope", "completed", "success", "Core CI", TARGET),
        RunJobProjection(2, 123, "PR Gate", "completed", "success", "Core CI", TARGET),
    ]
    self.assertIsNone(audit_module._ci_problem(self.context(), self.intent()))

def test_release_rejects_focused_or_wrong_sha_or_missing_gate(self):
    for mode, sha, gate in (
        ("focused", TARGET, "success"),
        ("full", "c" * 40, "success"),
        ("full", TARGET, "skipped"),
    ):
        with self.subTest(mode=mode, sha=sha, gate=gate):
            self.github.scope = CiScopeProjection(
                schema="lmdj.ci-scope.v2",
                base_sha="a" * 40,
                head_sha=sha,
                mode=mode,
                trusted_head=True,
                selected_lanes=tuple(sorted(LANES)),
                required_jobs=tuple(sorted(FULL_REQUIRED_JOBS)),
            )
            self.github.jobs = [
                RunJobProjection(1, 123, "Change Scope", "completed", "success", "Core CI", sha),
                RunJobProjection(2, 123, "PR Gate", "completed", gate, "Core CI", sha),
            ]
            problem = audit_module._ci_problem(self.context(), self.intent())
            self.assertIsNotNone(problem)
```

Test both successful `push` full and successful `workflow_dispatch` full. A run conclusion alone is not sufficient.

Create `release_github_api_test.py` with transport-level tests that require complete pagination for run jobs/artifacts, reject duplicate job/artifact identities, reject zero/multiple/expired matching scope artifacts, verify authenticated binary download, and reject ZIP traversal, duplicate members, extra scope manifests, duplicate JSON keys, wrong schema, or non-boolean trust.

Create `release_ci_evidence_test.py` with closed result tests for valid full `push`, valid full `workflow_dispatch`, focused mode, wrong SHA/branch/workflow, missing/expired artifact, malformed artifact identity, missing/duplicate/failed Gate, API outage, and a releasable intent with no remote tag. The last case must prove audit no longer returns prospective `ok` before evaluating CI.

- [x] **Step 3: Run the focused-main and release tests to observe failure**

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test \
  tests.build.ci_workflow_topology_test \
  tests.build.release_github_api_test \
  tests.build.release_ci_evidence_test \
  tests.build.release_audit_test \
  tests.build.release_prepare_test -v
```

Expected: push still full and release tooling has no scope/job projection.

- [x] **Step 4: Implement focused push with fail-closed ancestry handling**

Change only empty `workflow_dispatch` to unconditional full. For `push`, evaluate the exact changed-file inventory like Ready PR. If `before` is zero, missing, not a commit, not an ancestor of head, or the inventory is incomplete, emit full with a concrete reason and do not guess paths. Keep per-SHA `cancel-in-progress: false` unchanged.

- [x] **Step 5: Add typed scope/job projections to release GitHub API**

Add frozen dataclasses:

```python
@dataclass(frozen=True)
class CiScopeProjection:
    schema: str
    base_sha: str
    head_sha: str
    mode: str
    trusted_head: bool
    selected_lanes: tuple[str, ...]
    required_jobs: tuple[str, ...]

@dataclass(frozen=True)
class RunJobProjection:
    id: int
    run_id: int
    name: str
    status: str
    conclusion: str | None
    workflow_name: str
    head_sha: str

@dataclass(frozen=True)
class ActionsArtifactProjection:
    id: int
    name: str
    size_in_bytes: int
    api_url: str
    archive_download_url: str
    expired: bool
    run_id: int
    repository_id: int
    head_repository_id: int
    head_branch: str
    head_sha: str
    expires_at: str
```

Add strict, complete-pagination methods for `/actions/runs/{run_id}/jobs?filter=latest&per_page=100` and `/actions/runs/{run_id}/artifacts?per_page=100`, binding every job's run/workflow/head identities and every artifact's embedded `workflow_run.id`, repository identity, branch, and head SHA to the selected run. Retrieve exactly one non-expired artifact whose name is `ci-scope-` followed by that run's exact 40-hex head SHA.

Download through the authenticated artifact API URL without forwarding `Authorization` across the 302. Accept only HTTPS redirects matching the observed closed GitHub Actions artifact host family `productionresultssa[0-9]+.blob.core.windows.net`, with no userinfo/port/fragment and a signed query; fail closed if GitHub changes that family. Require status 200, `application/zip`, ZIP magic, and a compressed/uncompressed size cap of 1 MiB. Reject traversal, symlink, duplicate/extra members, parse exactly one root `ci-scope.json` with duplicate-key rejection, require the exact v2 top-level key set, exact 14-lane key set with every lane true in full mode, and closed required-job/type invariants, and never log the signed redirect URL.

- [x] **Step 6: Enforce full exact-main evidence in audit and prepare**

Implement `ci_evidence.py` as one read-only verifier used by `audit.py` and `prepare.py`. Extend `PrepareContext`'s GitHub protocol with the exact job/artifact methods. The verifier must require:

- recorded run ID matches the target SHA;
- event is `push` or `workflow_dispatch`;
- head branch is `main`;
- workflow is `Core CI`, completed/success;
- retained scope artifact is `lmdj.ci-scope.v2`, `head_sha == target`, `mode == full`, `trusted_head is True`;
- exactly one `Change Scope` and one `PR Gate` job completed successfully in that run.

Run the verifier in audit before the existing “no remote tag/Release” prospective success return for every actionable `releasable` state; a releasable intent without full evidence is not audit-clean. Terminal published-state audit does not require an expired ephemeral artifact to rewrite history; it continues to validate immutable tag/Release/asset/plan-marker evidence. Preserve the narrow historical pre-pipeline exception only for its exact recorded cancelled push, and never let it authorize prepare.

Classify transport/pagination/download outages as `external-error`, absent/expired retained evidence as `unverifiable`, and malformed/conflicting identity, focused mode, wrong SHA, or missing/failed/duplicate Gate as `conflict`. Prepare maps every non-success result to `PrepareError`. Do not infer full from path type or workflow conclusion.

- [x] **Step 7: Update governance and release skill in the same commit**

Document:

- ordinary main merges use focused/full path classification;
- Product Build/release operators dispatch empty-lane full CI for the exact main SHA when its push was focused;
- `scripts/release.sh audit --remote` and prepare reject focused evidence;
- the current 14-day scope-artifact retention is a hard prospective-evidence lifetime; after expiry, rerun all jobs for the exact recorded Actions run while that run is retained, preserving its run ID/SHA and producing a fresh latest attempt. If rerun is unavailable, only a newly authorized exact-SHA full run plus an updated release intent may replace it; never infer or reconstruct evidence;
- no release mutation is authorized by a full dispatch alone.

Documentation impact: required. Affected Portal routes: `/operations/testing-and-proof/` and `/operations/version-and-release/`.

- [x] **Step 8: Run all relevant verification**

```bash
python3 -m unittest \
  tests.build.ci_change_scope_test \
  tests.build.ci_pr_gate_test \
  tests.build.ci_workflow_topology_test \
  tests.build.release_github_api_test \
  tests.build.release_ci_evidence_test \
  tests.build.release_audit_test \
  tests.build.release_prepare_test \
  tests.build.release_skill_test \
  tests.build.release_transitions_test -v
bash tests/build/test_active_tree.sh
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
```

Expected: focused docs push passes; all unsafe push cases full; release rejects focused and accepts only full exact-main + same-run Gate.

- [x] **Step 9: Commit**

```bash
git add \
  .github/workflows/ci.yml scripts/ci/change_scope.py \
  tests/build/ci_change_scope_test.py tests/build/ci_workflow_topology_test.py \
  tools/release/github_api.py tools/release/ci_evidence.py \
  tools/release/audit.py tools/release/prepare.py \
  tests/build/release_github_api_test.py tests/build/release_audit_test.py \
  tests/build/release_ci_evidence_test.py tests/build/release_prepare_test.py \
  tests/build/release_skill_test.py \
  .agents/skills/lmdj-release/SKILL.md \
  docs/governance/git-workflow.md docs/governance/version-management.md \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx \
  apps/architecture-portal/docs/operations/version-and-release.mdx
git diff --cached --check
git commit -m "feat(ci): focus main and bind full release evidence"
```

- [x] **Step 10: Stop for push/PR/merge authorization**

This Task changes release authority and main CI behavior. It must not share an unreviewed remote transition with any release operation.

---

### Task 9: Prove Focused Main and Full Release Evidence Remotely

**Files:** none. Remote evidence only.

**Interfaces:**
- Consumes: Task 8 commit and release audit command.
- Produces: real docs-focused main SHA, high-risk full main SHA, and explicit full dispatch evidence.

- [ ] **Step 1: Push/open/merge only under separate authorizations**

PR itself is full because it changes the central CI control plane and release authority. Verify exact v2 manifest and all formal results before merge.

- [ ] **Step 2: Verify the merged control-plane SHA is full**

The Task 8 merge changes `.github/workflows/ci.yml` and `scripts/ci/**`, so its own main push must classify full. Record exact run ID and Gate.

- [ ] **Step 3: Prove a later docs-only main merge is focused**

Use an independently authorized docs-only PR. Expected main manifest selects only policy-owned docs/portal lanes, remains per-SHA non-cancelling, and completes within 3-5 minutes.

- [ ] **Step 4: Prove legitimate single-Core and single-Web main classifications**

Use the next independently authorized real Core-only and Web-only merges; do not create dummy product changes for evidence. The exact main manifests must select the policy-owned Core family for the first and Web family for the second without unrelated lanes. If either representative merge does not occur during the observation window, record the criterion as unresolved and do not claim migration acceptance.

- [ ] **Step 5: Dispatch full CI on the same docs-only main SHA**

Run empty-lane `workflow_dispatch` against the exact SHA. Expected: mode full, 14 lanes, same-run Gate success.

- [ ] **Step 6: Prove release audit discrimination without mutation**

Point a rehearsal/fake release intent first at the focused run ID: audit must reject it. Point it at the explicit full run ID: audit may pass the CI finding if every other release source is valid. Do not prepare/tag/release.

---

### Task 10: Observe for Seven Days and Record Acceptance

**Files:**
- Create: `docs/quality/ci-runner-migration-acceptance.md`

**Interfaces:**
- Consumes: at least five representative full runs, docs-focused runs, all benchmark IDs, server health logs, and Actions billing categorization.
- Produces: one immutable review record stating pass/fail per design criterion without claiming release/deployment.

- [ ] **Step 1: Collect normalized evidence for seven days**

For every run record event, SHA, manifest mode, lane set, runner name, queue, execution, critical path, worker time, Hosted control-plane minutes, Hosted workload minutes, and fallback authorization. Separately record Contabo OOM/container restarts/health and netcup CPU/memory/cache.

- [ ] **Step 2: Create the fixed acceptance document with actual values only**

The document must contain these closed sections:

```markdown
# CI Runner Migration Acceptance

## Observation window
## Runner inventory and isolation
## Correctness runs
## Performance distribution
## Hosted control-plane versus workload minutes
## Contabo staging health
## Netcup contention
## Release full-evidence discrimination
## Acceptance decision
## Unresolved external state
```

Do not write unfinished markers, estimates, or inferred success. A failed criterion is recorded as failed with its exact evidence.

- [ ] **Step 3: Apply acceptance thresholds**

- docs-only PR/main: 3-5 minute target;
- at least five full runs: median <= 20 minutes and P95 <= 25 minutes;
- online/idle matching queue <= 30 seconds;
- routine trusted Linux workload Hosted minutes = 0;
- Hosted control plane <= 5 Ubuntu job-minutes per ordinary run;
- three consecutive successful Web heavy runs including dual load;
- docs-only, single-Core, single-Web, and CI-control exact-main manifests match policy ownership;
- no Contabo OOM, application restart, or health failure;
- full release evidence accepts exact full and rejects focused.

- [ ] **Step 4: Verify documentation and commit**

```bash
git diff --check
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git add docs/quality/ci-runner-migration-acceptance.md
git diff --cached --check
git commit -m "docs(ci): record runner migration acceptance"
```

- [ ] **Step 5: Report terminal state precisely**

Separate designed, implemented, committed, pushed, merged, observed, and accepted. No acceptance result authorizes release, deployment, or Channel promotion.

## Version Management

Version impact: none.

Reason: every Task changes CI classification, evidence, infrastructure, routing, or documentation only. No Product Build, Module SemVer, Provider SemVer, Host SemVer, or product Contract SemVer changes. `lmdj.ci-scope.v2` is an internal CI schema migrated atomically by its producer, Gate, tests, and release consumer.

## Documentation Impact

Documentation impact: required for Tasks 5-6F, 8, and 10.

Affected current Portal routes:

- `/operations/testing-and-proof/`
- `/operations/version-and-release/`

Affected governance/operations sources:

- `docs/quality/core-test-policy.md`
- `docs/governance/git-workflow.md`
- `docs/governance/version-management.md`
- `docs/quality/ci-runner-migration-acceptance.md`

Task 3's benchmark harness does not change current formal routing and may declare Documentation impact: none with that concrete reason. No Task creates a permanent Product Build snapshot.

## Final Verification Bundle

Before declaring repository implementation complete, rerun from a clean implementation worktree:

```bash
python3 -m unittest \
  tests.build.ci_benchmark_workflow_test \
  tests.build.ci_change_scope_test \
  tests.build.ci_pr_gate_test \
  tests.build.ci_runner_fallback_test \
  tests.build.ci_workflow_topology_test \
  tests.build.ci_build_acceleration_test \
  tests.build.release_github_api_test \
  tests.build.release_ci_evidence_test \
  tests.build.release_audit_test \
  tests.build.release_prepare_test \
  tests.build.release_skill_test \
  tests.build.release_transitions_test -v
bash tests/build/test_active_tree.sh
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/architecture-portal.sh check
git status --short
```

Expected: all tests/checks pass and the worktree is clean. Remote acceptance additionally requires the Task 7/9/10 evidence; local green output cannot substitute for actual `runner_name`, exact SHA, manifest, Gate, billing, or host-health proof.

## Execution Record

Recorded 2026-08-16. Task 1 through Task 8 are complete; Task 9 is in
progress; Task 10 has not started.

- Task 4 accepted on exact main a71c62d4: creator cold 31874245751; warm
  triples per lane; dual-load pairs 31877033907/31877035224 and
  31877379993/31877381526; max dual-load slowdown +10.7%.
- Task 5 merged as 3a3c9828 (#147).
- Task 6A merged 0714ba48 (#152), proofs
  31905679866/31907020625/31907346757.
- Task 6B merged 4881633d (#157), proofs
  31908789094/31910183068/31910481345.
- Task 6C merged cf54d66f (#158), proofs
  31912077771/31913054564/31913422166.
- Task 6D merged 91568415 (#159), proofs
  31914552984/31915206858/31915245909.
- Task 6E merged 5d21b32f (#160), proofs
  31916688311/31917395338/31917533491.
- Task 6F merged 77f08a57 (#161), proofs
  31919294555/31920149016/31920531523.
- Task 7 evidence: PR full run 31918465836 (attempt 2), merged-main full
  run 31919292579.
- Task 8 merged f7531c9d (#162); its main push run 31923067376 classified
  full with 19 non-skipped jobs.
- Supporting fixes merged along the way: #144 creator open-transition,
  #145 scope rule for .claude, #146/#148/#149/#150/#151 release identity
  audit chain (audit green from b7e8608c), #156 dispatch lane reasons.
