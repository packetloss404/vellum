# Vellum — Cleanup-2 Research: Storage & Schema Refactor

**Scope:** deep-dive brief items #6 (thin store files), #7 (`investigation_plan` column), #9 (missing FKs), #11 (append-only retention), plus a bonus on enum CHECK constraints. All file refs are `path:line` against `D:\projects\Vellum` on 2026-08-02. **No code is being modified** — this is a research report.

**Author's note on framing.** Each item below is graded by the project's stated tolerance for risk: solo dev, 358 backend tests must keep passing at every commit, forward-only migrations, and "the user is in the loop" — auto-decisions logged, not hidden. Recommendations skew conservative; where a bigger-bang refactor is genuinely worth it, the rationale is laid out so the owner can decide.

---

## Item 1 — Consolidate the thin store files

### Current state

17 store modules under `backend/vellum/storage/`. Sorted by size (`Get-ChildItem … | Sort-Object Length`):

| File | KB | Functions | Identity |
|---|---|---|---|
| `dossier_store.py` | 34 | 17 | **Heavyweight. Stays split.** |
| `_helpers.py` | 14 | 23 | Shared. Untouched. |
| `plan_items_store.py` | 13 | 12 | **Heavyweight. Stays split.** |
| `sub_investigation_store.py` | 12 | 8 | **Heavyweight. Stays split.** |
| `session_store.py` | 11 | 11 | **Heavyweight (borderline). Stays split.** |
| `log_store.py` | 9 | 9 | **Borderline. Stays split (see §1.2).** |
| `section_store.py` | 8 | 8 | Medium. Stays split. |
| `decision_point_store.py` | 6 | 4 | Medium. Stays split. |
| `wake_store.py` | 5 | 10 | **Thin. Merge candidate.** |
| `turn_store.py` | 5 | 5 | **Thin. Merge candidate.** |
| `next_action_store.py` | 5 | 5 | **Thin. Merge candidate.** |
| `artifact_store.py` | 4 | 5 | Medium. Stays split. |
| `needs_input_store.py` | 3 | 3 | Medium. Stays split. |
| `user_note_store.py` | 3 | 3 | **Thin. Merge candidate.** |
| `budget_store.py` | 3 | 3 | **Thin. Merge candidate.** |
| `settings_store.py` | 2 | 4 | **Thin. Merge candidate.** |
| `idempotency_store.py` | 2 | 2 | **Thin. Merge candidate.** |

The brief's "17 thin files" actually enumerates **8** — the 8 marked above. The other 9 are either heavyweights or the medium modules that earn their split.

The public surface is the **flat `storage.X` namespace** defined by `storage/__init__.py:1-300`, which re-exports ~95 functions. Consumers reference it as `storage.get_dossier_wake_state(dossier_id)` from 8 different call sites across `agent/runtime.py`, `agent/scheduler.py`, `agent/self_heal.py`, `api/routes.py`, etc. The constraint is to preserve every name in the namespace — moving code is fine, renaming isn't.

### Target state

Three new modules, 7 thin files absorbed, 10 files unchanged. Net: **17 → 13 files**.

```
storage/
  _helpers.py             # unchanged
  __init__.py             # re-exports updated to add 3 new modules
  dossier_store.py        # unchanged
  plan_items_store.py     # unchanged
  sub_investigation_store.py
  session_store.py
  section_store.py
  decision_point_store.py
  artifact_store.py
  needs_input_store.py
  log_store.py            # unchanged (see §1.2)
  dossier_lifecycle.py    # NEW ← wake_store + user_note_store + next_action_store
  audit.py                # NEW ← turn_store + budget_store
  settings.py             # NEW ← settings_store + idempotency_store
```

The grouping rationale:

1. **`dossier_lifecycle.py`** — wake + user_notes + next_actions are all "things the user or the runtime stamps on a dossier that aren't core dossier rows." They share the `_log_change` + `_touch_dossier` post-write pattern. Wake writes the dossier itself; user_notes + next_actions touch related side tables but all flow through the same connection lifecycle. The merged module's natural first function is `set_dossier_wake_state(...)` and its last is `reorder_next_actions(...)`.
2. **`audit.py`** — agent_turns and budget_accounting are both "append-only time-series per turn" tables, with aggregation-by-time queries. The shared pattern: `record_X(...)` appends a row, `list_X(...)` and `get_summary_X(...)` query. Merging with `log_store` was tempting (it also writes change_log entries), but `log_store` has 9 heterogeneous functions and depends on 6 different `_row_to_*` helpers; it's at the threshold of staying on its own. If the owner is comfortable, the more aggressive merge (log_store + turn_store + budget_store = single `audit.py`) is also defensible — see open question 1.
3. **`settings.py`** — settings + idempotency are both key-value tables with a small, parallel surface (`get_X` / `set_X` / `record_X`). They have no shared business logic, but the surface area is so small that splitting them across two files is pure ceremony. A 4-function + 2-function file becomes a 6-function file, and the import path stays flat.

### Migration plan

Each step is independently shippable. The hardest part is purely mechanical: cut code from one file, paste into the new file, fix the relative import (`from ._helpers import …` stays; `from .x import Y` becomes `from . import Y` if cross-module, or stays as a local def).

1. **Create `storage/dossier_lifecycle.py`.** Copy `wake_store.py` verbatim as the first section, then `user_note_store.py`, then `next_action_store.py`. Each section's header comment gets a `# ---------- Wake ----------` divider. Internal `from .x import Y` lines for any helpers used by the merged file become `from ._helpers import Y`. Update `__init__.py` to import from the new module. **Tests that import the old name must keep working** — so `__init__.py` re-exports keep the old names, and the old files are deleted in a follow-up commit.
2. **Create `storage/audit.py`.** Same pattern. `turn_store.py` + `budget_store.py`. The `_utc_day_str` helper that lives inside `budget_store.py:12-14` becomes a module-level private function in `audit.py`.
3. **Create `storage/settings.py`.** Merge `settings_store.py` + `idempotency_store.py`.
4. **Run the test suite.** All 358 backend tests must pass unchanged. The consolidation is import-only; SQL doesn't move.
5. **Delete the 7 old files** in a separate commit so `git log` shows the file deletion cleanly.
6. **Add a `tests/test_storage_imports.py`** that asserts every name in the old `__all__` list is still importable from `storage` post-merge. One commit, no risk.

### Risk assessment

- **Blast radius:** zero on SQL, near-zero on tests (the surface is flat). The only "move" risk is forgetting a relative import — `git grep "from .wake_store"` and `git grep "from .budget_store"` should return empty before deletion.
- **Test risk:** any test that imports from the old path (e.g. `from .storage.wake_store import set_dossier_wake_at`) needs to be updated. I checked: zero such imports. All consumers go through the flat `storage.X` namespace. **Verified** by ripgrep across `backend/vellum/`.
- **Rollback:** a one-commit revert restores the old files. Easier than the schema changes in §2-§4.

### Effort estimate

**Small.** Mostly mechanical. Half a day including running the suite. If the more aggressive log_store-merge is chosen, add another two hours and one extra test pass.

### Open questions

1. **Should `log_store.py` be folded into `audit.py`?** The brief says 5-7 files merged. Folding log_store in gives 8 → 3 (and removes one of the borderline files). Folding it in makes the module 18 KB with 14 functions and 6 `_row_to_*` helpers — a real but coherent module. If yes, the file lives at `audit.py` and the heading comment becomes "Reasoning trail, ruled out, investigation log, change log, considered-and-rejected, agent turns, and budget rollup." I lean **no** (log_store is a focused audit module and most of its code is unrelated to turns/budget), but the owner should decide.

---

## Item 2 — Drop `dossiers.investigation_plan`

### Current state

This is more entangled than the brief lets on. The column isn't pure dead weight — it's split into **two roles** that the current code conflates:

1. **The `items` array** — the list of plan questions. **Already shadowed by `plan_items`**, and `get_dossier` (lines 82-86) merges the table over the JSON, with the table authoritative for items. The `_migrate_plan_items` sentinel-guarded data copy (db.py:161-219) ran once at v1 of the plan-items refactor and stamped `settings.plan_items_migrated=true`. **The items array is vestigial.**
2. **The metadata fields** — `rationale`, `drafted_at`, `approved_at`, plus the `model` and `pydantic_extra` keys. These are **read directly from the JSON** at `dossier_store.py:142-148` (resume state) and `dossier_store.py:583-619` (update), and **written** on every `update_investigation_plan` and `approve_investigation_plan` call. **This is live, load-bearing data.**

The `update_investigation_plan` flow at `dossier_store.py:563-650`:
- Reads the current JSON.
- Builds a new `InvestigationPlan` model with merged items (which are then re-serialized into the JSON, even though the table is the source of truth — see line 615 "items list is empty — authoritative items live in the plan_items table"; the comment is correct but the code still serializes the items array into JSON, wasting a few hundred bytes per write).
- Writes the new JSON to the column.
- Writes the items to the table.

So today, **stopping the JSON write is two steps, not one**: stop serializing `items` into the JSON, then later stop writing the JSON at all. Stopping **only** the items write is a one-line change at line 615 that buys a 60% reduction in JSON size.

### Target state

Two phases, **each independently shippable**.

**Phase 1 — Stop serializing `items` into the JSON blob.** ~1-day task. Change `update_investigation_plan` to build the JSON with `items=[]` regardless of the items table contents. The merge at `get_dossier` lines 82-86 (and the identical block at lines 96-100 in `list_dossiers`, and lines 243-247 in `get_dossier_full`) continues to overlay the table over the JSON's empty items. **Behavior is unchanged** because the merge was already authoritative. New dossiers created via `commit_intake` get the items directly from the table. The read-side merge is the only path to `InvestigationPlan.items` for clients.

**Phase 2 — Promote the metadata fields to columns (or a side table).** The two real options:

- **(2a) Columns on `dossiers`**: add `plan_rationale TEXT`, `plan_drafted_at TEXT`, `plan_approved_at TEXT`. Simplest, but spreads dossier state across columns that all relate to "the plan."
- **(2b) A new `dossier_plans` table**: one row per dossier, primary key `dossier_id`, holding rationale / drafted_at / approved_at. Cleaner, more extensible (future "plan status" field is a one-line additive schema change). Forward-only compatible.

I recommend **(2b)** because the `_ORDER_STEP`-style ratchet is "add a table, not a column" when the data has its own identity.

**Phase 3 — Stop writing the JSON, keep reading it.** Switch `update_investigation_plan` and `approve_investigation_plan` to write to the new table only. The `get_dossier` merge path now has nothing to merge from the JSON, so the conditional `if dossier.investigation_plan is not None:` block at line 82 simplifies to always reading the plan_items table. **But the read path still has to read the JSON** until we drop the column, because legacy dossiers created before this migration have all their metadata in JSON. The "stop writing, keep reading" window is **the lifetime of the oldest legacy dossier** plus a grace period.

**Phase 4 — Drop the column.** Add a `plan_metadata_in_db` sentinel to `settings` (mirroring the `plan_items_migrated` pattern). When a dossier is read, if its `dossier_plans` row is present, use it; if not, fall back to the JSON. **The decision criterion to drop the column**: when a 30-day sliding window has zero reads of legacy dossier plan metadata from the JSON, the column can be dropped. Concretely: log every read of the JSON in `get_dossier_resume_state`; once that count is 0 for 30 days, run the drop migration.

**Phase 5 — Add the column drop.** Forward-only means we can't roll back, so this is a one-way door. The drop is a `ALTER TABLE dossiers DROP COLUMN investigation_plan` — SQLite supports it since 3.35.0. The project's `db.py:14-16` comment is explicit that the ratchet is "never drop or rename here," so the drop lives in a **side-channel migration function** invoked by a one-shot script (the project already has precedent: `scripts/abandon_zombie_subs.py` is a production-grade cleanup with dry-run + `--force` guards).

### Migration plan

1. **Today (1 day, low risk):** Phase 1. Stop serializing items into the JSON. Add a test that asserts `get_dossier(d.id).investigation_plan.items` matches the `plan_items` table exactly after a `update_investigation_plan` call. The 17 existing `test_plan_items.py` tests should still pass.
2. **This week (1-2 days, medium risk):** Phase 2. Add `dossier_plans` table; backfill from JSON in a sentinel-guarded `_migrate_plan_metadata` function. Read path queries the table and falls back to JSON. Write path writes to the table. JSON column continues to be written for now (redundant, but safe).
3. **Next sprint (1 day, low risk):** Phase 3. Stop writing the JSON column. Read path becomes "read table, no JSON." Add a `settings.plan_metadata_migrated` sentinel so a manual test that re-runs init_db won't re-rewrite the JSON.
4. **30+ days later (1 day, low risk):** Phase 5. Add a `settings.json_plan_read_count_30d` counter or just a `read_json_plan_count` total; the drop script reads it and refuses to run if non-zero. Run as a one-shot script. After success, the sentinel flips to "column dropped."

### Risk assessment

- **Blast radius for Phase 1**: only `update_investigation_plan`. The merge logic is unchanged, so the API contract is preserved. Tests pin the contract.
- **Blast radius for Phase 2-3**: read path is the only consumer. `get_dossier_resume_state` reads the JSON for `has_plan` / `plan_approved`; this becomes a table read. Other call sites that read the JSON: `agent/prompt.py` (dossier state snapshot), `agent/sub_prompt.py` (sub-investigation prompt), `intake/tools.py:122-295` (commit_intake). All flow through `get_dossier` or `get_dossier_full`, so changing the merge suffices.
- **Blast radius for Phase 5**: any test that asserts on the JSON column directly. I checked: zero tests import or query the column by name. The read-path tests assert on the merged `InvestigationPlan` model, which is what the table provides.

### Effort estimate

**Medium.** Total ~5-7 working days across 4-5 PRs over a 1-2 month window. Each phase is independently shippable.

### Open questions

2. **Where does "plan approval" semantics live?** `approved_at` is currently a JSON field. The new `dossier_plans` table is the obvious home. But the `idx_decision_points_one_open_plan_approval_per_dossier` partial unique index (db.py:148-152) is a sibling invariant — there's already a `decision_points` row that mirrors "this dossier has an open plan_approval." Is the plan_approval DP the source of truth for `plan_approved_at`? Probably yes — the DP gets resolved when the user clicks Approve, and the JSON's `approved_at` should be set in the same transaction. Today's `approve_investigation_plan` does the JSON write but doesn't create a DP; `commit_intake` does. Worth tracing before the refactor lands.
3. **Phase 5 — drop criterion.** The 30-day-zero-reads heuristic is conservative. Is the project OK with a 30-day tail, or should the drop happen as soon as every dossier has a `dossier_plans` row (which would be right after Phase 2's backfill completes)? The conservative answer is "wait 30 days" because some legacy dossiers may only be re-woken in long-tail sleep-mode cycles.

---

## Item 3 — Add the missing foreign-key constraints

### Current state

The brief lists 5 columns, but the actual count is **6** (the synthesis brief undercounted). All are TEXT columns storing surrogate IDs (`dos_*`, `sec_*`, `pli_*`, `art_*`, `sub_*`, `chn_*`).

| Column | Reads | Writes | CASCADE candidate? | Today |
|---|---|---|---|---|
| `intake_sessions.dossier_id` | many | 1 (`commit_intake`) | `ON DELETE SET NULL` | no FK |
| `sub_investigations.parent_section_id` | 2 | 1 (`spawn_sub_investigation`) | no — section deletion is rare and shouldn't kill sub history | no FK |
| `sub_investigations.plan_item_id` | many | 1 (`spawn_sub_investigation`) | `ON DELETE SET NULL` | no FK |
| `artifacts.supersedes` | 1 | 1 (`update_artifact`) | `ON DELETE SET NULL` | no FK |
| `change_log.section_id` | 2 | many | `ON DELETE SET NULL` | no FK |
| `agent_turns.sub_investigation_id` | 3 | 1 | `ON DELETE SET NULL` | no FK |

`PRAGMA foreign_keys = ON` is set both in `schema.sql:1` and re-asserted per-connection at `db.py:250`, so new FKs will be enforced.

The blanket recommendation in synthesis #9 ("add the FK") is the right instinct, but the **CASCADE mode matters**. CASCADE-delete cycles (sub ↔ section) are the trap: if a section FK cascades a sub-investigation delete, and the sub-investigation is the only reason the section is referenced from anywhere, you get a self-referential delete cascade that wipes data the user wanted preserved. The fix is **`ON DELETE SET NULL`** on every one of these: when the parent row is gone, the child keeps its history with the FK column nulled.

### Target state

Per-column decision:

| Column | Decision | Rationale |
|---|---|---|
| `intake_sessions.dossier_id` | **Add FK `ON DELETE SET NULL`** | The intake conversation has audit value even after the dossier is deleted (the user might want to see "you said X 3 months ago" in a re-opened intake). One row in `intake_sessions` is the only place this lives. |
| `sub_investigations.parent_section_id` | **Keep no-FK + add a comment** | Section deletion (`delete_section` tool) is user-initiated and should not silently cascade-kill every sub-investigation that referenced the section. The runtime should `UPDATE … SET parent_section_id = NULL` when a section is deleted, in a single transaction, but DB-level enforcement is too aggressive. Add a SQL comment: "Intentionally no FK: section deletion would cascade-wipe audit-rich sub-investigations. Runtime nullifies on delete." |
| `sub_investigations.plan_item_id` | **Add FK `ON DELETE SET NULL`** | Plan items are plan-time; sub-investigations are runtime. Deleting a plan item should not delete the sub-investigation that did the work — the sub is the **evidence** that the plan item was executed. Null the back-reference. |
| `artifacts.supersedes` | **Add FK `ON DELETE SET NULL`** | When an artifact is deleted, artifacts that supersede it should not be cascaded. Same logic as plan items. |
| `change_log.section_id` | **Add FK `ON DELETE SET NULL`** | `change_log` is append-only audit. When the referenced section is deleted, the audit row survives with `section_id = NULL`. This is exactly the "the audit doesn't depend on the entity it audited" pattern. |
| `agent_turns.sub_investigation_id` | **Add FK `ON DELETE SET NULL`** | Telemetry rows keep their per-turn cost data even if the sub-investigation row is purged. |

Net: 5 new FKs with `ON DELETE SET NULL`, 1 column explicitly kept no-FK with a comment.

### Migration plan

SQLite requires table-recreation to add a FK to an existing column (unlike adding a new column). The pragma version is on the project's required floor (3.35+), but adding a column with a FK via `ALTER TABLE … ADD COLUMN … REFERENCES …` does work for **new** columns. Since these are existing columns, the standard recipe is:

```sql
PRAGMA foreign_keys=OFF;
BEGIN;
CREATE TABLE x_new (… with FK …);
INSERT INTO x_new SELECT * FROM x;
DROP TABLE x;
ALTER TABLE x_new RENAME TO x;
COMMIT;
PRAGMA foreign_keys=ON;
```

That's a destructive pattern that's hard to make forward-only-safe. **Better path**: add a one-shot Python migration script `scripts/add_missing_fks.py` (modeled on `scripts/abandon_zombie_subs.py`) that:
1. Checks `PRAGMA foreign_key_list(x)` for each table to confirm the FK is missing.
2. Runs the table-recreate dance inside `db.connect()` with `PRAGMA foreign_keys=OFF`.
3. Runs `PRAGMA foreign_key_check` and asserts zero violations.
4. Re-enables FKs and runs the test suite in a subprocess to confirm.

Ship the script, run it once on the dev DB, commit, and the ratchet is complete. The schema.sql file gets the FK inline for fresh DBs (so the next `init_db` on a new file gets it for free).

### Risk assessment

- **Blast radius for `intake_sessions.dossier_id`:** if a dossier is deleted via the `delete_dossier` tool (rare; the only delete path), the linked `intake_sessions` row has its `dossier_id` nulled. The intake history is preserved; the `dossier_id` field on the session row shows `NULL`. This is the desired behavior.
- **Blast radius for `sub_investigations.plan_item_id`:** the existing `set_plan_item_status` is the only writer; a `DELETE FROM plan_items WHERE …` path is hypothetical (no current tool deletes individual plan items; `bulk_replace_plan_items` is delete-all-for-dossier). The FK is preventative, not load-bearing today.
- **Blast radius for `change_log.section_id`:** `change_log` rows are append-only; the `delete_section` tool calls a `DELETE FROM sections WHERE id = ?`, which (with CASCADE on `sections.dossier_id`) cascades to `change_log` if it had a dossier_id FK. But it doesn't cascade to `change_log` because `change_log.dossier_id` has its own CASCADE that's already enforced. The new `section_id` FK is a separate concern. The `delete_section` tool needs to be updated to `UPDATE change_log SET section_id = NULL WHERE section_id = ?` before the delete, in the same transaction. **This is the highest-risk change** because `change_log` has 6+ writers and the new FK will be checked on every write.
- **Blast radius for the `sub_investigations.parent_section_id` no-FK decision:** zero, by design. The comment explains the tradeoff.
- **Test risk:** every tool that deletes a section (only `delete_section`) needs a test that asserts `change_log.section_id` is nulled post-delete. The new `scripts/add_missing_fks.py` will also serve as a live integration test.

### Effort estimate

**Small-medium.** 1-2 days for the script + 1 day for the `delete_section` `change_log` fix + a half-day of test polish. The 5 new FKs are declarative SQL; the hard part is the `change_log` section_id update-on-delete path.

### Open questions

4. **`sub_investigations.parent_section_id` — should the runtime nullify the column when a section is deleted?** Adding a no-FK with a comment is the safe default. Adding a runtime nullification on section delete is a 5-line `update_sub_investigation` call in the `delete_section` tool — cheap. Recommend yes; it's the "user is in the loop, nothing is silently stale" instinct.

---

## Item 4 — Append-only retention policy

### Current state

The 6 unbounded tables, in the order the brief lists them:

| Table | Rows per 200-turn session | User-visible? | Idempotency-critical? | Currently grows? |
|---|---|---|---|---|
| `tool_invocations` | 30-200 | no (runtime audit) | **yes** (PK is `tool_use_id`) | yes |
| `agent_turns` | 200 | no (cost dashboard) | no | yes |
| `investigation_log` | 30-80 | yes ("47 sources" counter) | no | yes |
| `reasoning_trail` | 10-40 | no (private agent notes) | no | yes |
| `change_log` | 50-200 | yes (plan-diff sidebar) | no | yes |
| `intake_messages` | 5-30 | yes (intake transcript) | no | yes |

The `schema.sql:234-239` comment on `tool_invocations` is important: **"Stable only within one successful response from Anthropic (SDK retries regenerate IDs)."** That means the dedup window is, in practice, very short — a single response cycle, maybe a few minutes. After that, the `tool_use_id` is dead; replaying it is impossible (the SDK never regenerates the same id). So the constraint "don't prune a `tool_use_id` that might be replayed" is much weaker than it looks.

The 30 tools × 200 max turns × N sessions × N dossiers math in the brief is roughly right: with realistic usage (5 tools per turn, 50 turns avg, 10 dossiers, 20 sessions each), you're looking at ~50,000 rows in `tool_invocations` and ~10,000 in `agent_turns` — about 5 MB on disk. Not a problem today. Will be a problem in a year for a power user.

### Target state

The retention policy, table by table:

| Table | Retention | Rationale | Constraint |
|---|---|---|---|
| `tool_invocations` | **7 days** | The dedup window is one response cycle (schema.sql:237-239). 7 days is 1000x the practical window. Pruning older rows is safe. | None — by the time a tool_use_id is 7 days old, no replay path exists. |
| `agent_turns` | **30 days** | The cost dashboard rolls up to per-day `budget_accounting`; a 30-day window is enough to see month-over-month cost trends. | None — `budget_accounting` already keeps the rolled-up totals forever. |
| `investigation_log` | **forever (or `dossier.deleted`)** | This is the "47 sources / 4 sub-investigations" evidence-of-work counter the user sees. Losing it is a UX regression. Rows are ~200 bytes; even at 1M rows it's 200 MB. | None — the volume is bounded by user-visible dossier activity, not the agent's internal churn. |
| `reasoning_trail` | **90 days** | Private agent cross-session notes. Useful for the duration of an investigation (which typically wraps in weeks, not months). The user never sees these directly; the session_summary persists the salient ones. | None. |
| `change_log` | **forever (or `dossier.deleted`)** | This is the user-visible "what changed since you last visited" plan-diff surface. Losing it would erase the audit trail the project sells as a feature. | None — same as `investigation_log`. |
| `intake_messages` | **forever (or `intake_session.deleted`)** | Intake conversations are short (5-30 messages) and represent the user's stated problem. The intake row is the canonical "what was the question." | None. |

A compact SQL migration rule: "Prune append-only rows older than the per-table TTL where the parent dossier is in a terminal state (`delivered` or `abandoned`)." For active dossiers, **never prune** — the user might still be looking at a stale tab.

### Migration plan

1. **Add a `retention.py` module under `agent/`** with a `RetentionPolicy` dataclass and a `prune_once(conn, now)` function. The function is pure SQL inside `with connect() as conn:`, with each `DELETE` guarded by a `LIMIT 1000` to keep individual transactions small.
2. **Hook into `agent/scheduler.py`.** A second coroutine on the same lifespan task list: `agent/retention.py:run_retention_loop(poll_seconds=86400)`. The 24h cadence is fine; you could also do weekly (`604800`). The loop runs at startup and every `poll_seconds` after.
3. **Add a `settings.retention_ttl_days` key** seeded with the table-level defaults (tool_invocations=7, agent_turns=30, reasoning_trail=90; the rest are infinite). A future "I want to keep more history" toggle goes here.
4. **Add a one-line `change_log`-style log entry on every prune run** so the user can see "retention: pruned 1234 tool_invocations, 56 agent_turns." **This is the "the user is in the loop" rule** — no silent cleanup.
5. **Tests:** a `test_retention.py` that pre-fills the 6 tables with dated rows and asserts the right rows survive each pass. Idempotency test: running the pruner twice doesn't break anything. Active-dossier test: a 90-day-old `tool_invocations` row on a non-delivered dossier is **not** pruned.

### Risk assessment

- **Idempotency story risk:** the brief is right that pruning `tool_use_id` rows would break dedup. But the 7-day TTL is so far past the practical dedup window (one response cycle, see `schema.sql:237-239`) that this is a non-issue in practice. The test pins it.
- **Active-dossier risk:** the "only prune terminal dossiers" rule is critical. If a user's tab is open on a 2-year-old dossier that they never marked delivered, the rows must survive. The retention query joins on `dossiers.status` to enforce this.
- **WAL/lock risk:** `agent/scheduler.py` runs `asyncio.to_thread(...)` for DB operations; the retention pruner should also run in a `to_thread`. The `LIMIT 1000` per `DELETE` keeps transactions short.
- **Blast radius:** limited to the 6 tables. Nothing else reads them with a "give me all rows forever" query (verified by ripgrep — every reader takes a `dossier_id` or `limit` parameter).

### Effort estimate

**Medium.** 2-3 days for the pruner + 1 day for the scheduler hookup + 1 day of tests. The hard part is the active-dossier check and the per-table TTL configurability.

### Open questions

5. **Should retention be opt-in or on by default?** The brief implies on-by-default. I'd ship with retention **off by default** (seed a `retention_enabled=false` setting) and let the owner flip it after watching the dev DB for a week. This matches the project's "the user is in the loop" rule.
6. **Should `intake_messages` and `change_log` be eligible for archival rather than deletion?** "Archive" here means "move to a JSON dump file in `~/.vellum/archive/`." The owner should decide whether the cleanup is destructive (DELETE) or archival (EXPORT then DELETE). I'd default to DELETE for tool_invocations/agent_turns/reasoning_trail and **archive** for change_log/intake_messages because they're user-visible.

---

## Item 5 (bonus) — CHECK constraints on enum-stored TEXT columns

### Current state

The Pydantic models in `models.py` define the enums. The SQL schema in `schema.sql` stores the values as `TEXT` with no DB-level constraint. The closed-loop test in `test_tool_surface.py:25` verifies every tool's prompt, not the column shape. A bad string would parse as a Pydantic error at the API boundary but would land in the DB if a future internal write path bypasses validation.

The candidate columns and their enums:

| Column | Enum | Members |
|---|---|---|
| `dossiers.status` | `DossierStatus` | `active`, `delivered` |
| `dossiers.dossier_type` | `DossierType` | (8 members) |
| `sections.state` | `SectionState` | `confident`, `provisional`, `blocked` |
| `decision_points.kind` | `DecisionPointKind` | `generic`, `plan_approval`, `stuck_resolution` |
| `sub_investigations.state` | `SubInvestigationState` | `running`, `completed`, `abandoned`, `blocked` |
| `plan_items.status` | `PlanItemStatus` | `planned`, `in_progress`, `completed`, `abandoned` |
| `artifacts.state` | `ArtifactState` | (3 members: `draft`, `final`, `archived`) |
| `intake_sessions.status` | `IntakeStatus` | (4 members) |
| `investigation_log.entry_type` | `InvestigationLogEntryType` | (12+ members) |
| `agent_turns.stop_reason` | open (free-text) | not enum-able |

### Target state

Add a CHECK constraint to every column with a closed enum. The 9 candidate columns above. The 10th (`agent_turns.stop_reason`) is free-text from the Anthropic SDK and should stay unbounded.

The constraint shape: `CHECK (status IN ('active', 'delivered'))`. SQLite supports CHECK constraints natively, has since 3.3.0, and the project requires 3.35+ for the `DROP COLUMN` work, so it's well within floor.

The maintenance trap: a hardcoded enum list means a new enum value requires a migration. Today, Pydantic is the source of truth; SQL is downstream. The forward-only ratchet means the SQL list and the Pydantic enum can drift.

### Migration plan

1. **Single Python helper** in `db.py` that introspects a Pydantic enum and emits the CHECK constraint SQL. Example signature: `def _check_constraint_for_enum(table: str, column: str, enum_cls: type[Enum]) -> str: ...`. This is the **codification step** that keeps Pydantic authoritative.
2. **Apply the constraints via table-recreate** (SQLite can't `ALTER TABLE ADD CONSTRAINT`). The same `scripts/add_missing_fks.py` pattern from §3 works here — one script that handles both the FK adds and the CHECK adds.
3. **A `pre-commit` hook (or a `make check-schema-consistency` script)** that compares the generated CHECK SQL against the schema.sql. The owner runs it manually for now; a `pre-commit` integration is a follow-up.

### Risk assessment

- **Blast radius:** zero on the read path. Writes that don't go through Pydantic validation (e.g. a direct `INSERT` from an admin script) are now rejected. This is the desired behavior.
- **Migration risk:** a `CHECK` constraint that's too strict will fail on legacy data. The `_close_duplicate_unresolved_plan_approvals` and `_backfill_decision_point_kinds` boot-time migrations already cover the legacy `kind` data. For `dossiers.status`, legacy data is `active` or `delivered` — both are in the enum. For `sections.state`, the enum is exhaustive. The migration is safe.
- **Test risk:** the Pydantic enum and the SQL enum must match. The `pre-commit` script catches drift.

### Effort estimate

**Small.** 1 day for the helper + 1 day for the script + half a day of test coverage.

### Open questions

7. **Should the `pre-commit` hook be wired up, or is "run `make check-schema-consistency` before pushing" enough?** The project has no `pre-commit` framework today (verified — `package.json` has no husky/lint-staged, and the backend has no `.pre-commit-config.yaml`). Adding one is a side quest.

---

## Sequencing & cross-cutting recommendations

The five items are mostly independent. The natural order, with a one-liner on dependencies:

1. **Item 1** (consolidation) — no dependencies, pure refactor. Land first; touches no SQL.
2. **Item 5** (CHECK constraints) — depends on the schema ratchet but not on Item 1. Low risk.
3. **Item 3** (FKs) — depends on the table-recreate script; independent of Items 1, 5. Medium risk on `change_log`.
4. **Item 4** (retention) — independent of Items 1, 3, 5. Ship with the setting off by default.
5. **Item 2** (`investigation_plan` drop) — depends on the project having a `dossier_plans` table; the longest tail; ship last.

**Cross-cutting:**
- The 358 backend tests must keep passing at every commit. Item 1 is the only one that's likely to break a test by import (mitigated by `tests/test_storage_imports.py`). Items 2-5 are schema/data changes; the test risk is bounded to the specific test that pins the relevant invariant (e.g. the existing `test_plan_items.py` for Item 2).
- Every Item has a forward-only path that matches `db.py:12-16`. None of the recommendations require a rollback.
- The "user is in the loop" rule is satisfied: the retention job logs to `change_log`; the schema changes are silent at the API layer (the API surface is unchanged); the consolidation is invisible.

## Open questions summary

1. Should `log_store.py` be folded into `audit.py`, or kept separate?
2. Where does "plan approval" semantics live — on `dossiers`, in a new `dossier_plans` table, or in the `decision_points` row?
3. Phase-5 drop criterion: 30 days of zero reads, or just "after the backfill completes"?
4. Should the runtime nullify `sub_investigations.parent_section_id` when a section is deleted (the "no silent staleness" rule)?
5. Retention opt-in or on by default?
6. Retention destructive (DELETE) or archival (EXPORT then DELETE) for user-visible tables?
7. Wire a `pre-commit` schema-consistency check, or document a manual run?
