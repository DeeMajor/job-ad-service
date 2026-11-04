# Deployment runbook

The service runs as two Docker containers (API + Redis) on the Contabo VPS that also hosts the frontend (PM2 apps `findjobsza`, `justibly`, `theaisle`; nginx on 80/443). It is **internal**: the API is bound to `127.0.0.1:4310` on the host and is reached by the frontend over localhost. No authentication, by decision; never publish the port.

| | |
|---|---|
| Host | `DEPLOY_HOST` in the local `.env` (Ubuntu 24.04, 8 vCPU, 24 GB) |
| Access | `ssh -i ~/.ssh/jobad_deploy root@$DEPLOY_HOST` (dedicated key, installed 2026-11-04) |
| Install dir | `/opt/job-ad-service/` — `docker-compose.yml` + `.env` (mode 600) |
| Image | `ghcr.io/deemajor/job-ad-service` (private; host is logged in with a read-only package token) |
| Bind | `BIND_ADDR=127.0.0.1` → `127.0.0.1:4310` |
| Jobs store | Redis container `job-ad-service-redis-1` (volume `redis-data`, TTL 24 h) |
| Health | `curl http://127.0.0.1:4310/healthz` on the host |
| Metrics | `http://127.0.0.1:4310/metrics` (Prometheus text) |
| Logs | `docker compose logs api -f` — JSON lines stamped with spec / prompt versions |

## Update to a new image

Every push to `main` builds and tags `latest` and `sha-<7>` in GHCR. On the host:

```bash
cd /opt/job-ad-service
export BIND_ADDR=127.0.0.1 IMAGE_TAG=latest        # or IMAGE_TAG=sha-abc1234 to pin
docker compose pull && docker compose up -d
curl -s http://127.0.0.1:4310/healthz               # versions should show the new prompt/spec
```

Rollback = the same with the previous `IMAGE_TAG`. Jobs in flight during a restart are marked `failed` ("service restarted"); clients re-submit.

## Configuration (`/opt/job-ad-service/.env`)

`ANTHROPIC_API_KEY`, `ALLOWED_ORIGINS` (only matters for browser-side calls; server-side Next.js calls over localhost need none), `ENRICH_ENABLED` (false), `MAX_CONCURRENT_DRAFTS` (4), `DAILY_SPEND_CAP_USD` (20), `LOG_LEVEL`. Change, then `docker compose up -d` to apply.

## Frontend integration on the same host

Call `http://127.0.0.1:4310/...` from the Next.js server side (API routes / server actions). Prefer `POST /v1/draft-jobs` + polling for drafts. If the browser must call the service directly, add an nginx `location /jobad/ { proxy_pass http://127.0.0.1:4310/; }` under the frontend's server block and set `ALLOWED_ORIGINS` to that origin.

## Reaching it from a workstation

The port is private to the host. From a machine with the deploy key, open a tunnel and use `localhost:4311`:

```bash
ssh -N -L 127.0.0.1:4311:127.0.0.1:4310 -i ~/.ssh/jobad_deploy root@$DEPLOY_HOST
# then http://127.0.0.1:4311/docs  — healthz shows jobs_store: redis, which distinguishes it from a local dev server
```

## Checks

```bash
docker compose ps                                   # both containers healthy
docker compose logs api --tail 50
curl -s http://127.0.0.1:4310/healthz | jq .spend   # today's estimated spend vs cap
```

Spend cap reached → drafts return 429 `daily_spend_cap` until midnight UTC; raise `DAILY_SPEND_CAP_USD` and `up -d` if intended.

## Not done yet

- Observability wiring into the Hostinger Grafana/Prometheus/Loki stack (this host is outside that fleet and VPN).
- Image size (≈ 465 MB) carries scikit-learn/pandas used only by the benchmark; a slimmer runtime image is a later tidy-up.
