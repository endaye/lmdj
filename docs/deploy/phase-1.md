# LMDJ Phase-1 deployment

This is the single-node application stack used by the staging delivery workflow:

- Caddy terminates HTTPS, serves `apps/web/dist`, and proxies `/api/*` to the API container.
- The app image contains separate Python environments for the reference Demucs pipeline and the LMDJ-owned API packages.
- Docker volumes persist job packages and Caddy certificates across upgrades.

The design is documented in `docs/superpowers/specs/2026-07-10-lmdj-phase1-deploy-design.md`.

## Prerequisites

- A Linux host with at least 16 GB RAM.
- Docker Engine with the Compose plugin.
- A DNS A record pointing the staging hostname at the host.

## Local configuration check

```bash
cp .env.example .env
cd apps/web
npm ci
VITE_API_BASE=/api npm run build
cd ../..
docker compose config --quiet
docker compose up -d --build
curl --insecure https://localhost/api/health
docker compose down
rm .env
```

The first image build downloads CPU-only torch/torchaudio wheels, Demucs, and the `htdemucs` model, so it is substantially slower and larger than later cached builds. CUDA wheels are intentionally excluded from this single-CPU-host image.

## Operations

```bash
docker compose ps
docker compose logs --follow app
docker system df
```

Completed job packages live in the `data` volume at `/data/jobs`. Phase 1 has no
time-based or automatic Job cleanup, so monitor disk usage. Browser-owned Jobs
can be deleted manually from the upload queue or an open API-backed workbench;
active processing Jobs must reach a terminal state before deletion. In-progress
jobs do not survive an app-container restart; completed packages do.

For the normal SHA-based staging deployment and rollback flow, use `docs/deploy/staging.md` after that workflow has been installed.
