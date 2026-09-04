# Vellum implementation plan

**Last reconciled:** 2026-09-04
**Canonical work queue:** [`BACKLOG.md`](../BACKLOG.md)

This plan sequences the accepted backlog. It replaces the cleanup-2 phase plan as the active roadmap; `notes/cleanup-2/00-design-plan.md` remains the historical plan for that completed audit.

## Current baseline

- Single-user FastAPI/SQLite application with a React dossier UI.
- Durable orchestrator, scheduler, crash reconciliation, stuck detection, sub-investigations, and cost telemetry.
- Bounded autonomous long research with standard/deep policies, measurable evidence targets, multi-session continuation, and UI controls.
- Production Docker stack: private backend, Nginx web/API gateway, persistent SQLite, and Caddy-compatible host listener.
- Verification baseline: 446 backend tests passing with 3 conditional skips, 28 frontend tests passing, and a successful frontend production build.

## Phase 1 — Reliability and production boundary

**Backlog:** REL-01, RUN-02, OPS-01

1. Design an invocation state machine for claimed/completed/failed tool calls.
2. Inventory handlers by replay behavior: naturally idempotent, idempotent with a stable entity key, or create-only/compound.
3. Implement claim, completion, and abandoned-claim reconciliation with crash-window tests.
4. Reject delivered/terminal dossiers at route, scheduler, and runtime boundaries.
5. Deploy the implemented Nginx/host source allowlist and Caddy TLS boundary,
   then verify Cloudflare/Caddy origin behavior with `sh deploy/smoke.sh`.
6. Exercise the implemented checksummed online backup and guarded restore
   tooling against a disposable copy and record the production recovery test.
7. Keep the active docs and runbook synchronized with the result.

**Exit gate:** no known duplicate-write window for create-only tools; deploy verification and restore verification are repeatable.

## Phase 2 — Plan-storage and schema hardening

**Backlog:** DATA-01, DATA-02

1. Add `dossier_plans` and an idempotent, sentinel-guarded metadata backfill.
2. Dual-read while validating backfill results; keep `plan_items` authoritative for item rows.
3. Switch plan metadata writes to `dossier_plans`; instrument any legacy JSON reads.
4. Stop writes to `dossiers.investigation_plan` and begin the 30-day soak.
5. Build a dry-run table-recreation migration for the deferred FKs and CHECK constraints.
6. Validate against a copied production database before applying the constraint migration.

**Exit gate:** normalized plan reads/writes are stable, migrations are forward-only and idempotent, and the legacy column is read-only pending soak.

## Phase 3 — Runtime and user-facing seams

**Backlog:** RUN-01, UX-01, UX-02, TEST-01, OBS-01, API-01

1. Replace the nested-loop fallback with a supported thread/event-loop boundary.
2. Surface persisted stuck-state summaries in return-visit UI without exposing private reasoning.
3. Remove the intake mutation/refetch flicker.
4. Add deterministic investigation-log grouping tests.
5. Stamp an explicit abort reason when a pre-created session is rejected by orchestration.
6. Choose and enforce one frontend API type ownership strategy.

**Exit gate:** the known runtime fallback is fixed, deferred UX gaps have focused tests, and schema drift has an automated guard.

## Phase 4 — Operational maturity and measured research tuning

**Backlog:** OPS-02, RES-01, DATA-03

1. Collect real standard/deep research run metrics before changing evidence or spend defaults.
2. Add retention in disabled/audit-only mode, then validate it against copied data.
3. After the plan-storage soak proves zero legacy reads, execute the guarded one-way column drop.

**Exit gate:** research defaults are evidence-based, retention is opt-in and auditable, and legacy plan storage is removed only with recorded soak evidence.

## Change discipline

- Keep each migration or reliability change independently reviewable.
- Add a regression test for every fixed bug and a migration test for every data-shape change.
- Run backend tests, frontend tests, and the production build before merging.
- For deployment changes, run `sh deploy/smoke.sh`; it verifies `/health`,
  `/ready`, `/`, `/docs/`, security headers, and an `/api` route through the
  public proxy.
- Update `BACKLOG.md` in the same change: move completed items, record blockers, and avoid duplicating work in README Known Issues.
