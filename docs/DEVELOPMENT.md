# Vellum development guide

**Last reconciled:** 2026-09-04

This is the maintainer-facing guide. The root README explains the product and provides a quick start; [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) and [`BACKLOG.md`](../BACKLOG.md) own future work.

## Prerequisites

- Python 3.11 or newer
- Node.js 22 or newer for the current lockfile/build environment
- An Anthropic API key for real agent runs; offline tests do not require one

## Local setup

Backend:

```bash
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-dev.lock
```

Create `backend/.env` from `backend/.env.example` and set `ANTHROPIC_API_KEY` only when running the real agent.

Frontend:

```bash
cd frontend
npm ci
```

Run the services in separate terminals:

```bash
cd backend
python -m uvicorn vellum.main:app --reload --port 8731
```

```bash
cd frontend
npm run dev
```

Vite serves `http://localhost:5173` and proxies `/api` to the backend on port 8731.

## Verification

```bash
cd backend
python -m pytest
```

```bash
cd frontend
npm test
npm run build
npm audit --audit-level=moderate
```

Runtime and development dependencies are fully resolved with hashes in
`requirements.lock` and `requirements-dev.lock`. Change the direct pins in
`pyproject.toml`, then regenerate both files with Python 3.13:

```bash
cd backend
python -m piptools compile --generate-hashes --strip-extras \
  --output-file=requirements.lock pyproject.toml
python -m piptools compile --extra=dev --generate-hashes --strip-extras \
  --allow-unsafe --output-file=requirements-dev.lock pyproject.toml
```

CI rejects stale locks and audits both the Python runtime lock and the complete
npm tree. Dependabot proposes weekly Python, npm, image-digest, and CI-action
updates; updates still require the normal test/build review.

The reconciled baseline is 446 backend tests passing with 3 conditional skips, plus 28 frontend tests passing. Treat the test output—not this sentence—as authoritative when the suite changes, then update the active docs.

## Runtime map

1. Intake creates a dossier and optionally seeds an unapproved investigation plan.
2. The orchestrator owns one task per active dossier and enforces process-wide concurrency.
3. The dossier runtime prepends a fresh state snapshot, calls Claude, and accepts user-visible changes only through typed tools.
4. Storage writes structured dossier state to SQLite; tool invocations and turns carry replay/cost telemetry.
5. The scheduler wakes queued dossiers, including bounded long-research continuations.
6. Stuck detection and budget controls surface structured decisions rather than allowing unbounded work.
7. The frontend polls coarse activity/progress state and renders the dossier, not raw model prose.

The long-research control path is split deliberately:

- `agent/autonomy.py` decides whether another bounded session may be scheduled.
- `storage/research.py` computes durable policy and progress rollups from existing dossier data.
- `/api/dossiers/{id}/research*` exposes policy, progress, start, and pause operations.
- `ResearchControl.tsx` is the user control/measurement surface.

## Data and migration rules

- SQLite runs in WAL mode; production stores the database outside release directories.
- `schema.sql` defines fresh databases; `db.py` contains forward-only compatibility migrations.
- Every migration must be safe to run more than once and must be tested against legacy rows.
- Never make a destructive column/table change in the same release that introduces its replacement.
- Back up production data and validate restore before a one-way migration.
- `plan_items` is authoritative for investigation-plan items. Plan metadata remains in the legacy JSON column until DATA-01 lands.

## API and frontend contracts

Backend Pydantic models are the semantic source of truth. `frontend/src/api/types.ts` is currently a hand-maintained mirror, so backend response changes must update it and its consuming hooks/components in the same change. API-01 in the backlog tracks adding an automated drift guard or a consumed OpenAPI-generated contract.

The application supports optional bearer-token enforcement. Local loopback development may leave it disabled. Any non-loopback deployment must set both `VELLUM_API_TOKEN` and `VELLUM_API_AUTH_REQUIRED=true`; the production Nginx layer injects the private token for browser API requests.

## Production workflow

Production uses `docker-compose.prod.yml`: a private backend container and a
hardened Nginx web container with a configurable host bind. See
[`deploy/README.md`](../deploy/README.md) for Caddy routing, ingress
allowlisting, health/readiness checks, verified backup/restore, and rollback.

Do not publish backend port 8731. If Caddy is on another host, bind 8730 to the
application server's LAN address, set `VELLUM_TRUSTED_PROXY_IP`, and enforce the
same source restriction at the host firewall. `/health` is liveness; `/ready`
is the deployment and container-readiness gate.

## Documentation ownership

- `README.md` — product description, quick start, architecture summary, endpoint/env reference, current status.
- `docs/DEVELOPMENT.md` — maintainer workflow and engineering invariants.
- `docs/IMPLEMENTATION_PLAN.md` — accepted sequencing and phase gates.
- `BACKLOG.md` — canonical unfinished-work queue.
- `deploy/README.md` — deployment and reverse-proxy operations.
- `notes/` — dated research, reviews, and historical plans; useful evidence, not the active roadmap.

When behavior changes, update the smallest owning active document and any cross-reference affected by the change. Do not copy the same backlog into multiple files.
