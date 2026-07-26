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
4. Wait for `Verify staging revision` and `Publish staging release` to pass.
5. Confirm `/opt/lmdj/DEPLOYED_REVISION`, the Git Tag, and the GitHub Release all point to the Actions run SHA.
6. Download the Release's `CHANGELOG-vX.Y.Z.md` asset and confirm it matches the Release body.
7. Open `https://staging.example.com` and upload a test audio file.

## Product versions and Changelog

Every newly deployed `main` SHA receives one immutable product version after
staging activation and revision verification. Web, API, Audio Worker, and the
shared packages use this one deployment version; their internal package
versions are not changed by deployment.

The first version created by this workflow is `v0.2.0`. Later versions are
calculated from all commits after the highest existing product Tag:

| Commit range | Version bump |
|---|---|
| Contains `BREAKING CHANGE:` or a Conventional Commit `!` | major |
| Otherwise contains `feat:` | minor |
| Any other non-empty forward range | patch |

For example:

```text
v0.2.0
v0.2.1   # fix, docs, maintenance, or non-Conventional commits
v0.3.0   # at least one feat
v1.0.0   # breaking change
```

Each annotated Tag points to the deployed full SHA. Its GitHub Release records
the staging environment, SHA, UTC deployment time, and Actions run. The Release
body and downloadable `CHANGELOG-vX.Y.Z.md` asset are generated from the same
Markdown file and group commits into Features, Fixes, Performance,
Documentation, Maintenance, and Other.

The first `v0.2.0` Changelog covers all repository history reachable from that
SHA. Later Changelogs cover only the range after the previous product Tag.

### Safe reruns and metadata recovery

Running `Deploy server` again for the same tagged SHA reuses its version. It
does not increment the version or replace published content.

The publication phase is resumable:

- an existing Tag with no Release gets its Release and asset;
- an existing Release with no asset gets an asset copied from the Release body;
- a complete Tag, Release, and matching asset exits successfully;
- conflicting Tag targets or differing existing assets fail without overwrite.

If staging activation succeeded but version planning or publication failed,
the Workflow reports that the deployment completed and the release metadata
failed. Resolve the reported Tag/Release conflict, then rerun `Deploy server`
with the same full `commit_sha`. Do not delete or move an existing product Tag
as an automatic recovery step.

## Roll back

Run `Deploy server` again with the previous successful full `main` SHA. The
workflow rejects SHAs that are not in `main` or do not have a successful CI
run.

A rollback SHA that already has a product Tag reuses that version and does not
create another Release. After version automation has started, an older
untagged SHA can still finish staging activation, but the post-deploy release
phase deliberately fails rather than assigning a new version out of order.
Prefer rollback targets shown in the repository's Releases page.

Before the first `v0.2.0` exists, the initial version can be assigned only to
the current `origin/main`; explicitly selecting an older SHA is rejected by the
release phase.

## Inspect

```bash
cd /opt/lmdj/current
cat /opt/lmdj/DEPLOYED_REVISION
docker compose -p lmdj --env-file /opt/lmdj/shared/.env ps
docker compose -p lmdj --env-file /opt/lmdj/shared/.env logs --tail 100 app caddy
```

The deployment keeps release directories for rollback. Remove old releases manually only after retaining the current and at least one previous successful SHA.
