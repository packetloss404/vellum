# Vellum backlog

**Last reconciled:** 2026-09-04
**Current baseline:** 398 backend tests passing with 2 conditional skips, 26 frontend tests passing, production deployment at `vellum.ianlan.dev`

This is the canonical queue for unfinished work. `docs/IMPLEMENTATION_PLAN.md` defines sequencing; `notes/` contains historical audits and is not an active task list.

## Status vocabulary

- **Now** — next production-quality work; should be completed before broadening scope.
- **Next** — accepted work with a known dependency on a Now item.
- **Later** — useful but not scheduled.
- **Blocked** — needs an explicit product decision or soak period.
- **Done** — retained briefly to reconcile older plans with the implementation.

## Now

### REL-01 — Close the tool-dispatch partial-replay window

**Priority:** P0
**Source:** cleanup-2 backend bug check, finding 3

The runtime records `tool_invocations` after a handler commits. A crash between the handler write and the invocation record can replay non-idempotent tools and duplicate artifacts, questions, decisions, reasoning entries, actions, or source logs.

**Acceptance criteria:**

- Invocation state distinguishes claimed, completed, and failed work.
- Each non-idempotent handler has a documented replay policy and a stable idempotency key.
- Startup/session reconciliation handles abandoned claims without silently dropping or duplicating work.
- Crash-window regression tests cover at least one create-only handler and one compound handler.

### OPS-01 — Harden and document production ingress

**Priority:** P0

The hardened stack, Caddy basic-auth example, public smoke test, and verified
backup/restore tooling are implemented. Completion now requires deploying the
new boundary and recording one production smoke and recovery exercise.

**Acceptance criteria:**

- Port 8730 is restricted to the Caddy host/trusted network.
- Caddy and Cloudflare behavior is covered by a short verification and rollback runbook.
- Backup and restore steps for `shared/data/vellum.db` are tested once.
- `/health`, the homepage, and one authenticated `/api` route are checked after every deploy.
- Anonymous application and API access is rejected at Caddy while health and
  readiness remain monitorable.

### RUN-02 — Reject new runs for terminal dossiers

**Priority:** P1

The scheduler filters delivered dossiers, but the manual start path and the runtime do not independently enforce that terminal boundary. A stale wake or direct API call must not reopen a delivered dossier.

**Acceptance criteria:**

- Agent start/resume and research-start routes return a clear conflict for terminal dossiers.
- The runtime has a defensive pre-loop guard even when invoked outside HTTP routes.
- Regression tests cover a direct manual start and a stale scheduled wake.

## Next

### DATA-01 — Normalize investigation-plan metadata

**Priority:** P1
**Depends on:** REL-01

Plan items are authoritative in `plan_items`, but plan metadata still lives in `dossiers.investigation_plan`. Introduce `dossier_plans`, backfill behind a migration sentinel, switch reads and writes, then begin a production soak.

**Acceptance criteria:**

- The migration is forward-only, idempotent, and tested against empty, current, and legacy databases.
- `dossier_plans` owns plan metadata; `plan_items` remains authoritative for items.
- No new code writes the legacy JSON column after cutover.
- Rollback is possible until the final column drop.

### DATA-02 — Add schema-level FK and CHECK constraints

**Priority:** P1
**Depends on:** DATA-01

Add the deferred foreign keys and enum CHECK constraints through a guarded table-recreation migration. Resolve `change_log.section_id` and section-deletion behavior in the same change.

**Acceptance criteria:** dry-run reporting, explicit backup/force guard, Pydantic-to-SQL enum consistency test, and migration tests with representative legacy rows.

### RUN-01 — Repair nested-loop sub-investigation dispatch

**Priority:** P1

`spawn_handler` still has a fallback that cannot run a second event loop in the same thread. Replace it with one supported execution path, most likely a dedicated thread with its own event loop, while preserving context, cancellation, and error reporting.

**Acceptance criteria:** the current structured-error regression becomes a success-path test, no coroutine leaks remain, and normal `asyncio.to_thread` dispatch is unchanged.

### UX-01 — Surface persisted stuck state in return-visit UI

**Priority:** P2

`last_signal_kind` reaches the next agent prompt but is not represented in the user-facing “what changed” or investigation-log surfaces.

**Acceptance criteria:** the UI explains the last stuck signal without exposing internal chain-of-thought, and includes a focused component test.

### UX-02 — Remove the intake pending-state flicker

**Priority:** P2

After an intake mutation resolves and before the refetch lands, the thinking indicator can disappear while no assistant reply is visible.

**Acceptance criteria:** update the query cache from the mutation result or keep the pending state through refetch; test the mutation/refetch gap.

### TEST-01 — Pin investigation-log day grouping

**Priority:** P2

Add a deterministic `InvestigationLogSidebar` test using a fixed clock and fixtures spanning day boundaries. This was the one frontend test intentionally deferred during cleanup-2.

### OBS-01 — Stamp orchestration-abort session reasons

**Priority:** P2

Sessions pre-created for scheduler/manual starts are sometimes closed with `end_work_session`, leaving `end_reason` null when the orchestrator rejects the run for contention or capacity. Add an explicit abort reason and use it consistently without changing retry behavior.

**Acceptance criteria:** rejected starts are distinguishable from completed sessions in storage and telemetry, and contention/capacity tests pin the reason.

## Later

### DATA-03 — Drop the legacy investigation-plan column

**Priority:** P2
**Blocked by:** DATA-01 plus a 30-day production soak with no legacy reads

This is the one-way step. Remove the column, fallback reads, and legacy-only coercion only after the soak evidence is recorded.

### OPS-02 — Add opt-in retention

**Priority:** P2
**Blocked by:** explicit retention defaults and production backup confidence

Prune internal telemetry in bounded batches for delivered/abandoned dossiers only. Never prune user-visible logs. Default off, audit every run, and test idempotency.

### API-01 — Eliminate frontend/backend type drift

**Priority:** P2

Choose one contract: keep `frontend/src/api/types.ts` explicitly hand-maintained with a drift test, or generate and consume types from OpenAPI. Do not restore an unused generated file.

### RES-01 — Calibrate long-research quality targets from real runs

**Priority:** P2

The bounded standard/deep modes, progress rollups, scheduler continuation, and UI controls are implemented. Use production runs to tune source, primary-source, domain-diversity, plan-coverage, session, and spend defaults without weakening hard caps.

**Acceptance criteria:** record representative run metrics, document any default changes, and add regression fixtures for scoring or URL-dedup changes.

## Done recently

- **RES-00:** bounded autonomous long research, evidence-quality rollups, policy/progress APIs, scheduler continuation, and dossier controls.
- **OPS-00:** production Docker/Nginx stack, persistent SQLite volume, API-token injection, configurable bind address, SSH-key deployment, and Caddy-compatible health endpoint.
- **OPS-03:** hashed Python locks, audited React Router/Vite upgrades,
  digest-pinned container bases, read-only/capability-reduced containers,
  bounded logs, CI security audits, and weekly dependency automation.
- **DOC-00:** active README, development guide, implementation plan, backlog, deployment guide, environment example, and historical-plan pointers reconciled against the implementation.
- **CLEANUP-2 A–E:** dead-code removal, scheduler tests, storage consolidation, `last_signal_kind`, frontend consolidation, and test expansion.
- **BUGFIX-2:** cleanup peer-review and bug-check fixes, excluding the explicitly queued items above.

## Explicitly outside the current v1 plan

Multi-user tenancy, end-user identity/authentication, notifications, mobile clients, rich-text editing, a database migration away from SQLite, and an orchestration platform such as Temporal are not active backlog items. Add them only after a product decision changes the single-user scope.
