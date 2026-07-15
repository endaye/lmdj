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
