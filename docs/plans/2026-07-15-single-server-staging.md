# Single-Server Staging Delivery Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CI plus a manually approved, SHA-based deployment workflow for one persistent `staging` server, with an ephemeral smoke stack and rollback support.

**Architecture:** The existing Phase-1 plan first produces the Docker Compose application stack. This plan adds parallel PR/main CI, deterministic release archives, a remote activation script that validates an isolated `lmdj-smoke` project before switching the persistent `lmdj` project, and a manual GitHub Actions workflow bound to the `staging` Environment.

**Tech Stack:** GitHub Actions, Bash, Git archive, SSH/SCP, Docker Compose, Caddy, Python 3.11, Node.js 22.

## Global Constraints

- Execute `docs/plans/2026-07-10-phase1-deploy.md` first; this plan consumes its `Dockerfile`, `compose.yml`, `Caddyfile`, `.env.example`, and environment-variable changes.
- `main` is the only long-lived branch and the only source of server deployments.
- The only persistent remote environment is GitHub Environment `staging`; do not create `production` yet.
- The smoke stack uses Compose project `lmdj-smoke`; the persistent stack uses project `lmdj`.
- Release identity is a full 40-character commit SHA reachable from `origin/main`.
- The server does not clone the repository or run `git pull`; GitHub Actions uploads a release archive.
- Runtime configuration remains only in `/opt/lmdj/shared/.env` on the server.
- PR workflows cannot read staging Environment secrets.
- Do not run persistent staging and production stacks on the same server.

---

## File Structure

- Create `.github/workflows/ci.yml`: PR and `main` validation across all owned packages and deployment configuration.
- Create `.github/workflows/deploy-server.yml`: manual main-SHA verification, Web build, release upload, and remote activation.
- Create `compose.smoke.yml`: app-only localhost port override for the ephemeral smoke project.
- Create `scripts/deploy/package-release.sh`: deterministic archive builder that adds the untracked Web `dist` and a `REVISION` file.
- Create `scripts/deploy/activate-release.sh`: server-side extraction, smoke check, atomic `current` switch, staging health check, and rollback.
- Create `scripts/deploy/tests/test-package-release.sh`: archive-builder contract test using a temporary Git repository.
- Create `scripts/deploy/tests/test-activate-release.sh`: activation-script success and rollback tests using stubbed Docker and curl commands.
- Create `docs/deploy/staging.md`: exact server bootstrap, GitHub Environment secret setup, deployment, and rollback runbook.

---

### Prerequisite: Complete the Phase-1 Compose stack

Execute every unchecked step in `docs/plans/2026-07-10-phase1-deploy.md` before Task 1. The prerequisite is complete only when these files exist and the existing plan's verification passes:

```text
Dockerfile
.dockerignore
compose.yml
Caddyfile
.env.example
docs/deploy/phase-1.md
```

Expected commits from that plan:

```text
feat(api): env-configurable cors and jobs root
feat(web): read api base from vite environment
feat(deploy): add single-node compose stack
```

---

### Task 1: Repository CI

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Python package paths, `apps/web/package-lock.json`, and the prerequisite Compose files.
- Produces: required checks named `core-models`, `patchify`, `audio-worker`, `api`, `web`, and `deploy-config`.

- [ ] **Step 1: Create the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  core-models:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: packages/core-models/pyproject.toml
      - run: python -m pip install -e "packages/core-models[test]"
      - run: python -m pytest packages/core-models/tests -q

  patchify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: |
            packages/core-models/pyproject.toml
            packages/patchify/pyproject.toml
      - run: python -m pip install -e packages/core-models -e "packages/patchify[test]"
      - run: python -m pytest packages/patchify/tests -q

  audio-worker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: |
            packages/core-models/pyproject.toml
            packages/patchify/pyproject.toml
            workers/audio/pyproject.toml
      - run: python -m pip install -e packages/core-models -e packages/patchify -e "workers/audio[test]"
      - run: python -m pytest workers/audio/tests -q

  api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: |
            packages/core-models/pyproject.toml
            packages/patchify/pyproject.toml
            workers/audio/pyproject.toml
            apps/api/pyproject.toml
      - run: python -m pip install -e packages/core-models -e packages/patchify -e workers/audio -e "apps/api[test]"
      - run: python -m pytest apps/api/tests -q

  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v6
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - run: npm ci
      - run: npm test
      - run: npm run build
        env:
          VITE_API_BASE: /api

  deploy-config:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: cp .env.example .env
      - run: docker compose config --quiet
      - run: >-
          docker run --rm
          -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro"
          caddy:2 caddy validate
          --config /etc/caddy/Caddyfile
          --adapter caddyfile
```

- [ ] **Step 2: Validate YAML and local command parity**

Run:

```bash
cd /Users/endaye/Projects/lmdj
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml", aliases: true); puts "yaml OK"'
packages/core-models/.venv/bin/python -m pytest packages/core-models/tests -q
packages/patchify/.venv/bin/python -m pytest packages/patchify/tests -q
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
apps/api/.venv/bin/python -m pytest apps/api/tests -q
cd apps/web && npm test && VITE_API_BASE=/api npm run build
```

Expected: `yaml OK`; every pytest/vitest suite passes; Vite build exits 0.

- [ ] **Step 3: Commit CI**

```bash
cd /Users/endaye/Projects/lmdj
git add .github/workflows/ci.yml
git commit -m "ci: validate app packages and deploy config"
```

---

### Task 2: Deterministic release archive

**Files:**
- Create: `scripts/deploy/package-release.sh`
- Create: `scripts/deploy/tests/test-package-release.sh`

**Interfaces:**
- Consumes: `package-release.sh FULL_SHA OUTPUT_TAR`; optional `LMDJ_ROOT` override exists only to make the script testable.
- Produces: a gzip tar archive containing the exact Git tree, `apps/web/dist`, and a root `REVISION` file containing `FULL_SHA` plus a newline.

- [ ] **Step 1: Write the failing archive contract test**

Create `scripts/deploy/tests/test-package-release.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/package-release.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

REPO="$TMP/repo"
mkdir -p "$REPO/apps/web/dist"
git -C "$REPO" init -q
git -C "$REPO" config user.name test
git -C "$REPO" config user.email test@example.com
printf 'tracked\n' > "$REPO/tracked.txt"
git -C "$REPO" add tracked.txt
git -C "$REPO" commit -qm init
SHA="$(git -C "$REPO" rev-parse HEAD)"
printf '<!doctype html>\n' > "$REPO/apps/web/dist/index.html"

ARCHIVE="$TMP/release.tar.gz"
LMDJ_ROOT="$REPO" "$PACKAGE_SCRIPT" "$SHA" "$ARCHIVE"

mkdir "$TMP/unpacked"
tar -xzf "$ARCHIVE" -C "$TMP/unpacked"
test "$(cat "$TMP/unpacked/REVISION")" = "$SHA"
test "$(cat "$TMP/unpacked/tracked.txt")" = "tracked"
test "$(cat "$TMP/unpacked/apps/web/dist/index.html")" = "<!doctype html>"

if LMDJ_ROOT="$REPO" "$PACKAGE_SCRIPT" not-a-sha "$TMP/bad.tar.gz" 2>/dev/null; then
  echo "invalid SHA unexpectedly succeeded" >&2
  exit 1
fi

echo "package-release tests passed"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
bash scripts/deploy/tests/test-package-release.sh
```

Expected: FAIL because `scripts/deploy/package-release.sh` does not exist.

- [ ] **Step 3: Implement the archive builder**

Create `scripts/deploy/package-release.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${LMDJ_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SHA="${1:-}"
OUTPUT="${2:-}"

if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: package-release.sh FULL_SHA OUTPUT_TAR" >&2
  exit 2
fi
if [ -z "$OUTPUT" ]; then
  echo "usage: package-release.sh FULL_SHA OUTPUT_TAR" >&2
  exit 2
fi
git -C "$ROOT" cat-file -e "${SHA}^{commit}"
test -f "$ROOT/apps/web/dist/index.html" || {
  echo "apps/web/dist/index.html is missing; build the web app first" >&2
  exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$ROOT" archive "$SHA" | tar -x -C "$TMP"
mkdir -p "$TMP/apps/web"
cp -R "$ROOT/apps/web/dist" "$TMP/apps/web/dist"
printf '%s\n' "$SHA" > "$TMP/REVISION"
mkdir -p "$(dirname "$OUTPUT")"
tar -C "$TMP" -czf "$OUTPUT" .
```

- [ ] **Step 4: Make scripts executable and verify the test passes**

Run:

```bash
chmod +x scripts/deploy/package-release.sh scripts/deploy/tests/test-package-release.sh
bash scripts/deploy/tests/test-package-release.sh
```

Expected: `package-release tests passed`.

- [ ] **Step 5: Commit the archive builder**

```bash
git add scripts/deploy/package-release.sh scripts/deploy/tests/test-package-release.sh
git commit -m "feat(deploy): package commit-addressed releases"
```

---

### Task 3: Ephemeral smoke and atomic staging activation

**Files:**
- Create: `compose.smoke.yml`
- Create: `scripts/deploy/activate-release.sh`
- Create: `scripts/deploy/tests/test-activate-release.sh`

**Interfaces:**
- Consumes: `activate-release.sh RELEASE_TAR DEPLOY_PATH`; archive root must contain `REVISION`, `compose.yml`, and `compose.smoke.yml`; `DEPLOY_PATH/shared/.env` must exist.
- Produces: `DEPLOY_PATH/current -> DEPLOY_PATH/releases/FULL_SHA`, persistent Compose project `lmdj`, and no remaining `lmdj-smoke` project.

- [ ] **Step 1: Add the smoke override**

Create `compose.smoke.yml`:

```yaml
services:
  app:
    ports:
      - "127.0.0.1:${LMDJ_SMOKE_PORT:-18000}:8000"
    restart: "no"
```

- [ ] **Step 2: Write the failing activation tests**

Create `scripts/deploy/tests/test-activate-release.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTIVATE_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/activate-release.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_BIN="$TMP/bin"
mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/docker" <<'EOF'
#!/usr/bin/env bash
printf 'docker %s\n' "$*" >> "$DEPLOY_TEST_LOG"
if [ "${DEPLOY_TEST_DOCKER_FAIL_EXEC:-0}" = "1" ] && [[ "$*" == *" exec -T app "* ]]; then
  exit 1
fi
exit 0
EOF
cat > "$FAKE_BIN/curl" <<'EOF'
#!/usr/bin/env bash
printf 'curl %s\n' "$*" >> "$DEPLOY_TEST_LOG"
exit 0
EOF
chmod +x "$FAKE_BIN/docker" "$FAKE_BIN/curl"

make_archive() {
  local sha="$1" output="$2" root="$TMP/archive-$sha"
  mkdir -p "$root"
  printf '%s\n' "$sha" > "$root/REVISION"
  printf 'services: {app: {image: test}, caddy: {image: test}}\n' > "$root/compose.yml"
  printf 'services: {app: {ports: ["127.0.0.1:18000:8000"]}}\n' > "$root/compose.smoke.yml"
  printf 'test\n' > "$root/Caddyfile"
  tar -C "$root" -czf "$output" .
}

DEPLOY_PATH="$TMP/deploy"
mkdir -p "$DEPLOY_PATH/shared"
printf 'LMDJ_DOMAIN=staging.example.com\n' > "$DEPLOY_PATH/shared/.env"
export DEPLOY_TEST_LOG="$TMP/deploy.log"
export PATH="$FAKE_BIN:$PATH"

SHA1="1111111111111111111111111111111111111111"
SHA2="2222222222222222222222222222222222222222"
make_archive "$SHA1" "$TMP/one.tar.gz"
make_archive "$SHA2" "$TMP/two.tar.gz"

"$ACTIVATE_SCRIPT" "$TMP/one.tar.gz" "$DEPLOY_PATH"
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA1"
grep -q 'lmdj-smoke' "$DEPLOY_TEST_LOG"
grep -q -- '-p lmdj ' "$DEPLOY_TEST_LOG"

: > "$DEPLOY_TEST_LOG"
if DEPLOY_TEST_DOCKER_FAIL_EXEC=1 "$ACTIVATE_SCRIPT" "$TMP/two.tar.gz" "$DEPLOY_PATH"; then
  echo "failed health check unexpectedly succeeded" >&2
  exit 1
fi
test "$(basename "$(readlink "$DEPLOY_PATH/current")")" = "$SHA1"

echo "activate-release tests passed"
```

- [ ] **Step 3: Run the activation test and verify it fails**

Run:

```bash
bash scripts/deploy/tests/test-activate-release.sh
```

Expected: FAIL because `scripts/deploy/activate-release.sh` does not exist.

- [ ] **Step 4: Implement atomic activation and rollback**

Create `scripts/deploy/activate-release.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
DEPLOY_PATH="${2:-}"
if [ -z "$ARCHIVE" ] || [ -z "$DEPLOY_PATH" ]; then
  echo "usage: activate-release.sh RELEASE_TAR DEPLOY_PATH" >&2
  exit 2
fi
test -f "$ARCHIVE"
test -f "$DEPLOY_PATH/shared/.env"

SHA="$(tar -xOf "$ARCHIVE" ./REVISION | tr -d '\r\n')"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "archive REVISION is not a full commit SHA" >&2
  exit 1
fi

RELEASES="$DEPLOY_PATH/releases"
RELEASE="$RELEASES/$SHA"
CURRENT="$DEPLOY_PATH/current"
PREVIOUS=""
mkdir -p "$RELEASES" "$RELEASE"
if [ -L "$CURRENT" ]; then PREVIOUS="$(readlink -f "$CURRENT")"; fi

rm -rf "$RELEASE"
mkdir -p "$RELEASE"
tar -xzf "$ARCHIVE" -C "$RELEASE"
test "$(cat "$RELEASE/REVISION")" = "$SHA"
test -f "$RELEASE/compose.yml"
test -f "$RELEASE/compose.smoke.yml"
DOMAIN="$(sed -n 's/^LMDJ_DOMAIN=//p' "$DEPLOY_PATH/shared/.env" | tail -n 1)"
if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "LMDJ_DOMAIN must be a hostname without scheme or path" >&2
  exit 1
fi

smoke_down() {
  docker compose -p lmdj-smoke \
    --env-file "$DEPLOY_PATH/shared/.env" \
    -f "$RELEASE/compose.yml" -f "$RELEASE/compose.smoke.yml" \
    down -v --remove-orphans >/dev/null 2>&1 || true
}
trap smoke_down EXIT
smoke_down
docker compose -p lmdj-smoke \
  --env-file "$DEPLOY_PATH/shared/.env" \
  -f "$RELEASE/compose.yml" -f "$RELEASE/compose.smoke.yml" \
  up -d --build app
curl --fail --silent --show-error --retry 12 --retry-delay 5 \
  --retry-connrefused http://127.0.0.1:18000/health >/dev/null
smoke_down
trap - EXIT

rm -f "$DEPLOY_PATH/current.next"
ln -s "$RELEASE" "$DEPLOY_PATH/current.next"
mv -Tf "$DEPLOY_PATH/current.next" "$CURRENT"

if ! (
  cd "$CURRENT"
  docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" up -d --build
  docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" exec -T app \
    /opt/app-venv/bin/python -c \
    'import json, urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8000/health"))["ok"] is True'
  curl --fail --silent --show-error --retry 12 --retry-delay 5 \
    --retry-connrefused --insecure --resolve "$DOMAIN:443:127.0.0.1" \
    "https://$DOMAIN/" >/dev/null
  curl --fail --silent --show-error --retry 12 --retry-delay 5 \
    --retry-connrefused --insecure --resolve "$DOMAIN:443:127.0.0.1" \
    "https://$DOMAIN/api/health" >/dev/null
); then
  (
    cd "$CURRENT"
    docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" logs --tail 100
  ) || true
  if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
    rm -f "$DEPLOY_PATH/current.rollback"
    ln -s "$PREVIOUS" "$DEPLOY_PATH/current.rollback"
    mv -Tf "$DEPLOY_PATH/current.rollback" "$CURRENT"
    (
      cd "$CURRENT"
      docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" up -d --build
    )
  else
    (
      cd "$CURRENT"
      docker compose -p lmdj --env-file "$DEPLOY_PATH/shared/.env" down --remove-orphans
    ) || true
    rm -f "$CURRENT"
  fi
  exit 1
fi

printf '%s\n' "$SHA" > "$DEPLOY_PATH/DEPLOYED_REVISION"
echo "deployed $SHA"
```

- [ ] **Step 5: Make scripts executable and run both deploy tests**

Run:

```bash
chmod +x scripts/deploy/activate-release.sh scripts/deploy/tests/test-activate-release.sh
bash scripts/deploy/tests/test-package-release.sh
bash scripts/deploy/tests/test-activate-release.sh
docker compose -f compose.yml -f compose.smoke.yml config --quiet
```

Expected: both scripts print `tests passed`; Compose config exits 0.

- [ ] **Step 6: Commit smoke activation**

```bash
git add compose.smoke.yml scripts/deploy/activate-release.sh scripts/deploy/tests/test-activate-release.sh
git commit -m "feat(deploy): smoke and activate staging releases"
```

---

### Task 4: Manual staging workflow

**Files:**
- Create: `.github/workflows/deploy-server.yml`

**Interfaces:**
- Consumes: optional `workflow_dispatch.inputs.commit_sha`; Environment secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_SSH_KNOWN_HOSTS`, and `DEPLOY_PATH`.
- Produces: one uploaded archive, a remote activation run, and a GitHub deployment record for Environment `staging`.

- [ ] **Step 1: Create the manual workflow**

Create `.github/workflows/deploy-server.yml`:

```yaml
name: Deploy server

on:
  workflow_dispatch:
    inputs:
      commit_sha:
        description: Full main commit SHA; leave empty for current main
        required: false
        type: string

permissions:
  contents: read
  actions: read

concurrency:
  group: deploy-staging
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v6
        with:
          ref: main
          fetch-depth: 0

      - name: Resolve and verify main SHA
        id: target
        env:
          GH_TOKEN: ${{ github.token }}
          REQUESTED_SHA: ${{ inputs.commit_sha }}
        run: |
          git fetch origin main
          target="${REQUESTED_SHA:-$(git rev-parse origin/main)}"
          if [[ ! "$target" =~ ^[0-9a-f]{40}$ ]]; then
            echo "commit_sha must be a full 40-character lowercase SHA" >&2
            exit 1
          fi
          git cat-file -e "${target}^{commit}"
          git merge-base --is-ancestor "$target" origin/main || {
            echo "$target is not reachable from origin/main" >&2
            exit 1
          }
          run_id="$(gh run list --commit "$target" --workflow ci.yml --status success \
            --json databaseId --jq '.[0].databaseId')"
          test -n "$run_id" || {
            echo "no successful CI run found for $target" >&2
            exit 1
          }
          echo "sha=$target" >> "$GITHUB_OUTPUT"
          git checkout --detach "$target"

      - uses: actions/setup-node@v6
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json

      - name: Build web
        working-directory: apps/web
        env:
          VITE_API_BASE: /api
        run: npm ci && npm run build

      - name: Package release
        env:
          TARGET_SHA: ${{ steps.target.outputs.sha }}
        run: scripts/deploy/package-release.sh "$TARGET_SHA" "$RUNNER_TEMP/lmdj-$TARGET_SHA.tar.gz"

      - name: Configure SSH
        env:
          DEPLOY_SSH_KEY: ${{ secrets.DEPLOY_SSH_KEY }}
          DEPLOY_SSH_KNOWN_HOSTS: ${{ secrets.DEPLOY_SSH_KNOWN_HOSTS }}
        run: |
          install -m 700 -d "$HOME/.ssh"
          printf '%s\n' "$DEPLOY_SSH_KEY" > "$HOME/.ssh/id_ed25519"
          chmod 600 "$HOME/.ssh/id_ed25519"
          printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" > "$HOME/.ssh/known_hosts"
          chmod 600 "$HOME/.ssh/known_hosts"

      - name: Upload release
        env:
          TARGET_SHA: ${{ steps.target.outputs.sha }}
          DEPLOY_HOST: ${{ secrets.DEPLOY_HOST }}
          DEPLOY_USER: ${{ secrets.DEPLOY_USER }}
          DEPLOY_PATH: ${{ secrets.DEPLOY_PATH }}
        run: |
          ssh "$DEPLOY_USER@$DEPLOY_HOST" "mkdir -p '$DEPLOY_PATH/incoming'"
          scp "$RUNNER_TEMP/lmdj-$TARGET_SHA.tar.gz" \
            "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_PATH/incoming/$TARGET_SHA.tar.gz"
          scp scripts/deploy/activate-release.sh \
            "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_PATH/incoming/activate-release.sh"

      - name: Activate staging release
        env:
          TARGET_SHA: ${{ steps.target.outputs.sha }}
          DEPLOY_HOST: ${{ secrets.DEPLOY_HOST }}
          DEPLOY_USER: ${{ secrets.DEPLOY_USER }}
          DEPLOY_PATH: ${{ secrets.DEPLOY_PATH }}
        run: |
          ssh "$DEPLOY_USER@$DEPLOY_HOST" \
            "bash '$DEPLOY_PATH/incoming/activate-release.sh' \
             '$DEPLOY_PATH/incoming/$TARGET_SHA.tar.gz' '$DEPLOY_PATH'"
```

- [ ] **Step 2: Validate workflow syntax and secret isolation**

Run:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/deploy-server.yml", aliases: true); puts "yaml OK"'
rg -n "environment: staging|workflow_dispatch|DEPLOY_" .github/workflows/deploy-server.yml
! rg -n "pull_request:" .github/workflows/deploy-server.yml
```

Expected: `yaml OK`; the workflow uses `staging` and manual dispatch; it has no PR trigger.

- [ ] **Step 3: Commit the workflow**

```bash
git add .github/workflows/deploy-server.yml
git commit -m "ci(deploy): add manual staging workflow"
```

---

### Task 5: Staging runbook and repository controls

**Files:**
- Create: `docs/deploy/staging.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior tasks and the GitHub repository `endaye/lmdj`.
- Produces: server bootstrap instructions, exact secret names, deployment/rollback procedure, GitHub Environment `staging`, and protected `main`.

- [ ] **Step 1: Write the staging runbook**

Create `docs/deploy/staging.md` with these exact operational sections:

````markdown
# LMDJ staging deployment

The only persistent remote environment is `staging`. The server root is `/opt/lmdj`; runtime configuration stays on the server.

## Server bootstrap

```bash
sudo useradd --create-home --shell /bin/bash deploy
sudo usermod -aG docker deploy
sudo mkdir -p /opt/lmdj/{incoming,releases,shared}
sudo chown -R deploy:deploy /opt/lmdj
sudo -u deploy install -m 700 -d /home/deploy/.ssh
```

Install the public half of the dedicated GitHub Actions deploy key in `/home/deploy/.ssh/authorized_keys`. Verify the server's SSH host key from a trusted console before storing it in GitHub.

Create `/opt/lmdj/shared/.env`:

```dotenv
LMDJ_DOMAIN=staging.example.com
LMDJ_CORS_ORIGINS=
LMDJ_JOBS_ROOT=/data/jobs
```

Replace `staging.example.com` with the staging DNS name whose A record points to this server. Do not commit this file.

## GitHub Environment

Create Environment `staging`, restrict deployment branches to `main`, and add:

- `DEPLOY_HOST`
- `DEPLOY_USER` (`deploy`)
- `DEPLOY_SSH_KEY`
- `DEPLOY_SSH_KNOWN_HOSTS`
- `DEPLOY_PATH` (`/opt/lmdj`)

## Deploy

1. Merge a PR into `main`.
2. Wait for the `CI` workflow on that `main` SHA to pass.
3. Run `Deploy server`; leave `commit_sha` empty for current `main`.
4. Confirm `/opt/lmdj/DEPLOYED_REVISION` matches the Actions run SHA.
5. Open `https://staging.example.com` and upload a test audio file.

## Roll back

Run `Deploy server` again with the previous successful full `main` SHA. The workflow rejects SHAs that are not in `main` or do not have a successful CI run.

## Inspect

```bash
cd /opt/lmdj/current
cat /opt/lmdj/DEPLOYED_REVISION
docker compose -p lmdj --env-file /opt/lmdj/shared/.env ps
docker compose -p lmdj --env-file /opt/lmdj/shared/.env logs --tail 100 app caddy
```

The deployment keeps release directories for rollback. Remove old releases manually only after retaining the current and at least one previous successful SHA.
````

- [ ] **Step 2: Link the runbook from README**

Add under `README.md`'s documentation entry list:

```markdown
- [docs/deploy/staging.md](docs/deploy/staging.md)：单服务器 staging 的部署、回滚与运维。
```

- [ ] **Step 3: Validate documentation and all repository changes**

Run:

```bash
git diff --check
test -f docs/deploy/staging.md
rg -n "docs/deploy/staging.md" README.md
bash scripts/deploy/tests/test-package-release.sh
bash scripts/deploy/tests/test-activate-release.sh
cp .env.example .env
docker compose config --quiet
docker compose -f compose.yml -f compose.smoke.yml config --quiet
rm .env
```

Expected: no whitespace errors; both deploy tests pass; both Compose configurations parse.

- [ ] **Step 4: Commit documentation**

```bash
git add docs/deploy/staging.md README.md
git commit -m "docs(deploy): add staging operations runbook"
```

- [ ] **Step 5: Push the feature branch and open a PR**

```bash
git push -u origin codex/feat-single-server-deploy
gh pr create --base main --head codex/feat-single-server-deploy \
  --title "feat(deploy): add single-server staging delivery" \
  --body-file /tmp/lmdj-staging-pr.md
```

The PR body must list the CI jobs, release archive contract, smoke/rollback behavior, local verification, and the remaining server-secret setup.

- [ ] **Step 6: Create the staging Environment after merge**

Run with an authenticated `endaye` GitHub CLI session:

```bash
gh api --method PUT repos/endaye/lmdj/environments/staging \
  --input - <<'JSON'
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
JSON

gh api --method POST repos/endaye/lmdj/environments/staging/deployment-branch-policies \
  -f name=main -f type=branch
```

Expected: Environment `staging` exists and its only deployment branch policy is `main`.

- [ ] **Step 7: Protect main after the merged CI has completed once**

Run:

```bash
gh api --method PUT repos/endaye/lmdj/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["core-models", "patchify", "audio-worker", "api", "web", "deploy-config"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": true
}
JSON
```

Expected: direct pushes and force pushes to `main` are blocked; PRs require all six current CI contexts; no second-person approval is required yet.

---

## Final Verification

Before claiming implementation complete:

```bash
git status --short --branch
git diff --check origin/main...HEAD
bash scripts/deploy/tests/test-package-release.sh
bash scripts/deploy/tests/test-activate-release.sh
packages/core-models/.venv/bin/python -m pytest packages/core-models/tests -q
packages/patchify/.venv/bin/python -m pytest packages/patchify/tests -q
workers/audio/.venv/bin/python -m pytest workers/audio/tests -q
apps/api/.venv/bin/python -m pytest apps/api/tests -q
cd apps/web && npm test && VITE_API_BASE=/api npm run build
cd ../.. && cp .env.example .env
docker compose config --quiet
docker compose -f compose.yml -f compose.smoke.yml config --quiet
rm .env
```

Then verify on GitHub:

1. The feature PR's six CI jobs are green.
2. The PR merges into `main`.
3. The `main` CI run is green.
4. Environment `staging` exists and only permits `main`.
5. Branch protection requires the six CI contexts.

Real server deployment remains blocked until the user supplies the five staging Environment secret values and `/opt/lmdj/shared/.env` exists on the server. Once supplied, run `Deploy server` and verify Web upload through the public staging URL.
