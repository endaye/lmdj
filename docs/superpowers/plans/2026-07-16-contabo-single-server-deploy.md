# Contabo Single-Server Staging Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the current `main` revision of LMDJ to the Contabo Singapore VM as the sole persistent `staging` environment.

**Architecture:** `en` is the human administrator account reached from macOS as `ssh sg`. A separate `deploy` account, with no password login and only a GitHub Actions deploy key, receives SHA-addressed release archives under `/opt/lmdj`; Docker Compose runs the application and Caddy serves the web app plus HTTPS.

**Tech Stack:** Ubuntu, Docker Engine and Compose plugin, Caddy 2, GitHub Actions, SSH ed25519 keys, Contabo VM.

## Global Constraints

- The server is the only persistent remote environment and is named `staging`; do not run a second persistent production stack on it.
- Deploy only commits reachable from `main`; do not clone the repository or run `git pull` on the server.
- Use `en` for daily SSH administration and `deploy` only for GitHub Actions releases.
- `LMDJ_DOMAIN` is `staging.lmdj.endaye.com` and its A record must point to `185.227.134.15` before Caddy can obtain a public TLS certificate.
- Do not put root passwords, Contabo API credentials, SSH private keys, or `/opt/lmdj/shared/.env` into Git.
- For a private repository, confirm the GitHub plan supports Environment secrets before Task 4; GitHub Free does not expose Environment secrets to private repositories.

---

### Task 1: Establish the public hostname and local access

**Files:**
- Modify: local `~/.ssh/config`
- Create: DNS A record for `staging.lmdj.endaye.com`

**Interfaces:**
- Consumes: Contabo VM IPv4 `185.227.134.15` and the existing macOS `en` account key.
- Produces: `ssh sg` access and a hostname that resolves to the VM.

- [x] **Step 1: Verify the macOS SSH alias**

Run on the Mac:

```bash
ssh sg 'whoami && hostname && free -h && df -h /'
```

Expected: `en` is printed, available memory is about 24 GiB, and the root filesystem has the expected disk capacity.

- [x] **Step 2: Create the DNS record**

Create this record at the DNS provider for the domain being used:

```text
Type: A
Host: staging
Value: 185.227.134.15
TTL: 300
```

The resulting hostname is `staging.lmdj.endaye.com`.

- [x] **Step 3: Confirm public DNS propagation**

Run on the Mac after creating the record:

```bash
dig +short staging.lmdj.endaye.com A
```

Expected: exactly `185.227.134.15` is returned.

### Task 2: Install Docker and constrain inbound access

**Files:**
- Create: `/etc/apt/sources.list.d/docker.sources`
- Create: UFW rules for SSH, HTTP, and HTTPS

**Interfaces:**
- Consumes: the `en` account with sudo access.
- Produces: `docker compose` is available and only ports 22, 80, and 443 are opened by UFW.

- [x] **Step 1: Install Docker Engine from Docker's Ubuntu repository**

Run through `ssh sg`:

```bash
sudo apt update
sudo apt install -y ca-certificates curl ufw
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
```

Expected: the last command prints Docker's successful `Hello from Docker!` message.

- [x] **Step 2: Configure the host firewall**

Run through `ssh sg`:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

Expected: UFW is active and allows 22/tcp, 80/tcp, and 443/tcp.

### Task 3: Create the GitHub Actions release identity

**Files:**
- Create: `/home/deploy/.ssh/authorized_keys`
- Create: local `~/.ssh/lmdj-github-deploy` and `~/.ssh/lmdj-github-deploy.pub`

**Interfaces:**
- Consumes: Docker is installed and the administrator can run `sudo` as `en`.
- Produces: the GitHub Actions workflow can SSH as `deploy` and run Docker Compose without a password.

- [x] **Step 1: Create the non-interactive server account and release directories**

Run through `ssh sg`:

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo mkdir -p /opt/lmdj/{incoming,releases,shared}
sudo chown -R deploy:deploy /opt/lmdj
sudo -u deploy install -m 700 -d /home/deploy/.ssh
```

Expected: `id deploy` shows membership in the `docker` group and `/opt/lmdj` is owned by `deploy`.

- [x] **Step 2: Generate a dedicated, unencrypted deployment key on the Mac**

Run on the Mac:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/lmdj-github-deploy -C "lmdj-github-actions"
```

When prompted for a passphrase, leave it empty. This key is only for the GitHub Actions environment secret, not for interactive use.

- [x] **Step 3: Authorize only the public key for `deploy`**

Copy the output of this Mac command:

```bash
cat ~/.ssh/lmdj-github-deploy.pub
```

Then run on the server and paste that complete single line when `nano` opens:

```bash
sudo nano /home/deploy/.ssh/authorized_keys
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

- [x] **Step 4: Confirm key-only deployment access**

Run on the Mac:

```bash
ssh -i ~/.ssh/lmdj-github-deploy deploy@185.227.134.15 'docker compose version'
```

Expected: Docker Compose version is printed without asking for a password.

### Task 4: Configure runtime settings and GitHub environment secrets

**Files:**
- Create: `/opt/lmdj/shared/.env`
- Configure: GitHub repository Environment `staging`

**Interfaces:**
- Consumes: `staging.lmdj.endaye.com`, the `deploy` user, its private key, and the validated SSH host key.
- Produces: the existing `.github/workflows/deploy-server.yml` can upload and activate a verified `main` release.

- [x] **Step 1: Create the server-only application configuration**

Run through `ssh sg`:

```bash
sudo tee /opt/lmdj/shared/.env >/dev/null <<'EOF'
LMDJ_DOMAIN=staging.lmdj.endaye.com
LMDJ_CORS_ORIGINS=
LMDJ_JOBS_ROOT=/data/jobs
EOF
sudo chown deploy:deploy /opt/lmdj/shared/.env
sudo chmod 600 /opt/lmdj/shared/.env
```

- [x] **Step 2: Validate the SSH host key before recording it in GitHub**

Run on the Mac:

```bash
ssh sg 'sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub'
ssh-keyscan -t ed25519 -H 185.227.134.15 | ssh-keygen -lf -
ssh-keyscan -t ed25519 -H 185.227.134.15
```

Expected: the first two fingerprints are identical. Copy the final `ssh-keyscan` line only after that match.

- [x] **Step 3: Create the GitHub `staging` environment**

In GitHub repository settings, create environment `staging`, allow deployments only from `main`, and add these environment secrets:

```text
DEPLOY_HOST              185.227.134.15
DEPLOY_USER              deploy
DEPLOY_PATH              /opt/lmdj
DEPLOY_SSH_KEY           complete contents of ~/.ssh/lmdj-github-deploy
DEPLOY_SSH_KNOWN_HOSTS   verified ssh-keyscan line from Step 2
```

Expected: the environment exists before the first workflow dispatch. Environment secrets are made available only to the workflow job that references `staging`.

### Task 5: Deploy and verify the current main release

**Files:**
- Uses: `.github/workflows/ci.yml`
- Uses: `.github/workflows/deploy-server.yml`
- Uses: `scripts/deploy/package-release.sh`
- Uses: `scripts/deploy/activate-release.sh`

**Interfaces:**
- Consumes: a successful CI run for a commit reachable from `main` and all Task 4 secrets.
- Produces: a SHA-addressed release at `/opt/lmdj/releases/<sha>` with `/opt/lmdj/current` pointing to it.

- [x] **Step 1: Check the CI run for `main` is green**

Open the repository's Actions tab and confirm the current `main` commit has a successful `CI` workflow run.

Expected: all component jobs and `deploy-config` succeed.

- [x] **Step 2: Run the deployment manually**

In GitHub Actions, select `Deploy server`, click `Run workflow`, leave `commit_sha` empty, and run it from `main`.

Expected: the workflow builds the web app, archives the exact main SHA, smoke-tests it locally on the server, switches `/opt/lmdj/current`, and verifies `/` plus `/api/health` through Caddy.

- [x] **Step 3: Verify the deployed service**

Run on the Mac:

```bash
curl --fail --silent --show-error https://staging.lmdj.endaye.com/api/health
ssh sg 'cat /opt/lmdj/DEPLOYED_REVISION && cd /opt/lmdj/current && docker compose -p lmdj --env-file /opt/lmdj/shared/.env ps'
```

Expected: the health endpoint returns JSON with `"ok": true`, and `DEPLOYED_REVISION` is the SHA shown in the GitHub Actions run.

- [x] **Step 4: Perform a functional smoke test**

Open `https://staging.lmdj.endaye.com` in a browser, upload a small audio file, and wait for the job to reach `completed` or `rejected` rather than `failed`.

Expected: the UI retrieves the generated patch and sample files from the same origin.

### Task 6: Operate safely after the first deployment

**Files:**
- Uses: `docs/deploy/staging.md`

**Interfaces:**
- Consumes: the deployed hostname and GitHub `staging` environment.
- Produces: repeatable promotion and rollback without a release branch.

- [x] **Step 1: Deploy later changes**

Merge a reviewed pull request to `main`, wait for CI, then run `Deploy server` with an empty `commit_sha`.

Expected: the next release comes only from the verified current `main` SHA.

- [x] **Step 2: Inspect failures and capacity**

Run through `ssh sg`:

```bash
cd /opt/lmdj/current
sudo docker compose -p lmdj --env-file /opt/lmdj/shared/.env logs --tail 100 app caddy
sudo docker system df
df -h /opt/lmdj
free -h
```

Expected: application logs, Docker image/volume use, disk capacity, and memory availability are visible without root login.

- [ ] **Step 3: Roll back a bad release**

In GitHub Actions, rerun `Deploy server` and enter the full SHA of the previous successful `main` deployment into `commit_sha`.

Expected: the workflow deploys the older verified archive and updates `/opt/lmdj/DEPLOYED_REVISION` to that SHA.

## Self-Review

- Spec coverage: uses the existing single persistent staging design, SHA-based release archives, Caddy HTTPS, Docker volumes, smoke testing, and GitHub Environment secrets.
- Placeholder scan: the staging hostname is fixed as `staging.lmdj.endaye.com`; the plan contains no unresolved deployment values other than credentials that must remain secret.
- Interface consistency: `en` is only the daily administrator, `deploy` is the GitHub Actions principal, and all release paths match `docs/deploy/staging.md` and `scripts/deploy/activate-release.sh`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-16-contabo-single-server-deploy.md`.

Execution choice for this deployment:

1. **Guided execution** — run each server and GitHub step together in this task.
2. **Self-service execution** — follow the checkboxes, then return with the first failing command or the final deployment run URL.
