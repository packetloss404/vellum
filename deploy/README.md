# Production deployment and recovery

The production stack is defined in `docker-compose.prod.yml`:

- `backend` is a non-root, read-only FastAPI container. SQLite is the only
  writable persistent mount, at `./data`.
- `web` serves the immutable React/docs build and injects the private API
  token only while forwarding `/api/` to the backend.
- Both containers drop privileges/capabilities, use bounded local logs, and
  put their required scratch paths on size-limited `tmpfs` mounts.
- Nginx accepts requests only from loopback and `VELLUM_TRUSTED_PROXY_IP`.
  This is defense in depth; the host firewall must enforce the same boundary.

## First-time configuration

Create `.env.production` beside the Compose file with private permissions. The
real file is ignored by Git and excluded from Docker build contexts:

```bash
umask 077
install -m 0600 /dev/null .env.production
```

Set:

```dotenv
ANTHROPIC_API_KEY=...
VELLUM_API_TOKEN=...at-least-32-random-bytes...
VELLUM_BIND_ADDRESS=10.80.12.12
VELLUM_TRUSTED_PROXY_IP=10.80.13.11
```

Use `127.0.0.1` for both addresses when Caddy is on the application host.
For the current split-host layout, Caddy is `10.80.13.11` and Vellum is
`10.80.12.12`. Permit TCP/8730 on the Vellum host only from `10.80.13.11`;
do not publish backend port 8731.

The `data` directory must be writable by UID 1000, the backend container user:

```bash
umask 077
mkdir -p -m 0700 data data/backups
sudo chown 1000:1000 data
chmod 0700 data data/backups
```

## Caddy edge

The Nginx bearer token protects the backend from bypassing the application
gateway. It is not end-user authentication: Nginx injects it for permitted
requests, and the browser never receives it.

Vellum is intentionally a single-user trusted-use tool and does not place an
application login at Caddy. Install the site block from
`deploy/Caddyfile.example`, validate it, and reload Caddy:

```bash
caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

The current public DNS name is internet-reachable. If network-private access is
later required, put the hostname behind a VPN, private DNS, or an identity-aware
edge such as Cloudflare Access; that is a separate product decision from adding
an application login. A 522 means Cloudflare cannot reach Caddy. A 525 means
the origin TLS handshake failed.

## Deploy

From the immutable release directory:

```bash
sudo docker compose -p vellum \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  config --quiet

sudo docker compose -p vellum \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d --build --remove-orphans
```

The backend container becomes healthy only when `/ready` confirms that the
database is usable. `/health` is the less strict process-liveness endpoint.

## Deploy verification

Run the public-route smoke script from a trusted workstation. It checks
liveness/readiness, the homepage, docs, API, and the application security
headers. Set `VELLUM_REQUIRE_HSTS=true` when the Caddy HSTS policy is active.

```bash
sh deploy/smoke.sh https://vellum.ianlan.dev
```

Also inspect container state on the application host:

```bash
sudo docker compose -p vellum \
  --env-file .env.production \
  -f docker-compose.prod.yml ps
```

## Verified SQLite backup

Backups use SQLite's online backup API, so they are consistent even while the
WAL-mode API is running. The command performs a full `integrity_check`, writes
the database atomically, and creates SHA-256 and JSON metadata sidecars.

```bash
sudo docker compose -p vellum \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  exec backend python -m vellum.ops.sqlite_backup backup \
  --database /app/data/vellum.db --output-dir /app/data/backups
```

Verify any snapshot independently:

```bash
sudo docker compose -p vellum \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  exec backend python -m vellum.ops.sqlite_backup verify \
  /app/data/backups/vellum.TIMESTAMP.sqlite3
```

A backup on the same disk is only a recovery checkpoint. Copy the `.sqlite3`,
`.sha256`, and `.json` files together to encrypted off-host storage and test a
restore periodically.

## Guarded restore

Restore requires downtime, the checksum sidecar, a full integrity check, and
an exact `--confirm-replace` path. Before replacement it creates and verifies
a timestamped copy of the current database. If any step fails, the target is
left untouched or the error names the pre-restore copy.

```bash
sudo docker compose -p vellum \
  --env-file .env.production \
  -f docker-compose.prod.yml stop backend

sudo docker compose -p vellum \
  --env-file .env.production \
  -f docker-compose.prod.yml run --rm --no-deps backend \
  python -m vellum.ops.sqlite_backup restore \
  /app/data/backups/vellum.TIMESTAMP.sqlite3 \
  --database /app/data/vellum.db \
  --confirm-replace /app/data/vellum.db \
  --confirm-backend-stopped \
  --pre-restore-dir /app/data/backups

sudo docker compose -p vellum \
  --env-file .env.production \
  -f docker-compose.prod.yml up -d backend
```

Run `sh deploy/smoke.sh` after restore. Do not delete the pre-restore snapshot
until the application and dossier contents have been checked.

## Rollback

1. Keep release directories immutable and keep `.env.production` and `data/`
   outside them.
2. Take and verify an online backup before every schema-affecting deployment.
3. To roll back code, repoint the `current` symlink to the previous release and
   run the same Compose `up -d --build --remove-orphans` command.
4. Forward-only schema changes may not be compatible with older code. Restore
   the pre-deploy database only after confirming that data loss since the
   backup is acceptable and following the guarded restore procedure above.
