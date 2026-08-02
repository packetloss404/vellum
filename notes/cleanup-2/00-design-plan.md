# Vellum — Cleanup-2 Design + Plan

**Synthesizes:** `01-research-storage.md` (5 items), `02-research-runtime.md` (6 items), `03-research-frontend.md` (6 items).

**Goal:** Move Vellum from "great hackathon project" to "shippable v1" — the surface a maintainer could read with full confidence. Scope: 17 items, 0 breaking changes to the public API, 358 backend tests + 12 frontend tests must stay green at every commit, every commit ships independently.

**Implementation status (as of cleanup-2 close-out):**
- Phases A, B, C, D, E — **shipped** (16 commits, all pushed to main). 387 backend tests + 26 frontend vitest tests now pass (was 358+12 at session start).
- Phase F — **deferred** to a follow-up pass. The F.1 (stop serializing items into JSON) was already in place before this pass; the F.2 dossier_plans table + sentinel-guarded backfill, F.4 FK + CHECK migration, F.5 retention policy, and F.6 column drop are all multi-day efforts that should be tackled in their own dedicated session with their own soak windows. See the README "Known issues and follow-ups" section for the full list.

**Constraints (re-stated from the deep-dive):**
- Solo dev, low risk tolerance
- 358 backend tests + 12 frontend tests must pass at every commit
- Forward-only migrations (`db.py:12-16`)
- "The user is in the loop" — auto-decisions logged, not hidden
- The closed-loop enforcement ("agent never speaks to the user") is load-bearing
- The aesthetic (serif-forward, warm, document-like) is load-bearing

---

## 1. Target architecture (the 17 items, decisions made)

| # | Item | Decision | Risk | Source |
|---|---|---|---|---|
| 1 | Delete `_PLACEHOLDER_V2_SCHEMAS` dict + fallback | **Delete.** Unreachable in merged tree (verified). | Trivial | runtime #5 | ✅ shipped |
| 2 | `mark_progress` docstring one-liner fix | **Fix.** Docstring is now self-inconsistent with the code. | Trivial | runtime (synthesis #3 residual) | ✅ shipped |
| 3 | Add `test_scheduler.py` (12 tests, <5s, deterministic) | **Add.** Highest-value test in the repo. | Small | runtime #1 | ✅ shipped (13 tests) |
| 4 | Hard-test the `_PROGRESS_*` whitelists | **Add a test.** Catches the maintenance trap. | Trivial | runtime #3 | ✅ shipped (2 lint tests) |
| 5 | Document the `asyncio.run()` fallback in sub_runtime | **Add comments + a test.** Don't remove the fallback. | Small | runtime #4 | ✅ shipped (test exposes broken fallback) |
| 6 | Add `last_signal_kind` column on `dossiers` | **Add.** Additive, NULL-tolerant, ~50 LOC. | Small | runtime #2 | ✅ shipped |
| 7 | Migrate `InvestigationPlanItem` callers → `PlanItem` | **Migrate now; delete later.** Two-step. | Small-medium | runtime #6 | ⚠️ partial — debug log added, intake migration reverted (PlanItem is too permissive, breaks the plan_error contract) |
| 8 | Consolidate thin store files (7 → 3) | **Consolidate.** 17 → 13 files. Pure import refactor. | Small | storage #1 | ✅ shipped |
| 9 | Stop serializing `items` into `investigation_plan` JSON | **Phase 1 of 5-phase plan.** | Small | storage #2 | ✅ already in place pre-cleanup |
| 10 | Promote plan metadata to `dossier_plans` table | **Phase 2 of 5-phase plan.** | Small-medium | storage #2 | ⏸ deferred |
| 11 | Stop writing `investigation_plan` JSON | **Phase 3 of 5-phase plan.** | Small | storage #2 | ⏸ deferred (depends on 10) |
| 12 | Drop `investigation_plan` column (after 30d zero reads) | **Phase 4 of 5-phase plan.** Final, one-way door. | Small | storage #2 | ⏸ deferred (depends on 11) |
| 13 | Add 5 new FKs with `ON DELETE SET NULL` | **Add via table-recreate script.** | Small-medium | storage #3 | ⏸ deferred |
| 14 | Add CHECK constraints on 9 enum-stored columns | **Add via same script.** Pydantic-introspected. | Small | storage #5 (bonus) | ⏸ deferred |
| 15 | Append-only retention policy (opt-in) | **Add as opt-in, default off.** Honors "user is in the loop." | Medium | storage #4 | ⏸ deferred |
| 16 | Consolidate frontend: SectionCard/SourceList, common/ cleanup, cx, day-N rename | **All in scope.** Visual identity preserved. | Small-medium | frontend #1-#5 | ✅ shipped |
| 17 | Expand vitest (7 new tests; ship 6, defer 1) | **Ship 6; defer `InvestigationLogSidebar` (flaky risk).** | Low-medium | frontend #6 | ✅ shipped (5 files, 26 tests; deferred only the one flaky test) |

### Default decisions on the 13 open questions (callable as `ask_user` if the owner disagrees):

| Open question | Default | Why |
|---|---|---|
| `log_store.py` → fold into `audit.py`? | **Keep separate.** log_store is heterogeneous (6+ different `_row_to_*` helpers). Folding would make `audit.py` 18 KB with 14 functions. Easier to revert if kept separate. |
| Where does "plan approval" live? | **`dossier_plans` table** (research's option 2b). The `decision_points` row is the *user-facing* artifact; the table is the *storage* layer. They stay in sync via the existing `approve_investigation_plan` flow. |
| `investigation_plan` drop criterion? | **30-day zero-reads** (conservative). Even after backfill, a long-tail sleep-mode wake could read a legacy dossier. 30 days is cheap insurance. |
| Nullify `sub_investigations.parent_section_id` on section delete? | **Yes, in the runtime** (5-line `update_sub_investigation` in `delete_section` tool). DB-level stays no-FK. "User is in the loop, nothing is silently stale." |
| Retention: opt-in or on by default? | **Opt-in.** Default `retention_enabled=False`. Matches "user is in the loop" rule. Owner flips after watching dev DB for a week. |
| Retention: DELETE or archival? | **Mixed.** DELETE for `tool_invocations`, `agent_turns`, `reasoning_trail`. KEEP (no prune) for `change_log`, `intake_messages`, `investigation_log` (user-visible). |
| Pre-commit schema-consistency hook? | **Defer.** No pre-commit framework today. Document the manual `make check-schema-consistency` (or python equivalent) instead. |
| SectionCard visual change on `/demo`? | **Accept the change.** The whole point of the cleanup is one render path; aligning the demo with the live aesthetic is the right outcome. |
| Wire `ButtonLink` for `<Link>` elements? | **Defer.** Out of scope. `<Button>` is a `<button>`, not a `<Link>`. One hand-rolled site (`DossierListPage.tsx:29`) stays hand-rolled. |
| Ship all 7 vitest expansions or defer 1? | **Ship 6.** Defer `InvestigationLogSidebar` to a follow-up; the day-bucket grouping is high-value but high-flake-risk. |
| `_coerce_legacy_items` validator — migrate or delete? | **Add a debug log; migrate callers (Phase 7); defer deletion to a later cleanup.** Two-step. |
| `asyncio.run()` fallback — keep or remove? | **Keep with a test.** Removal is "loud failure over silent fallback" — that's a project-owner-style choice, not a one-shot refactor decision. |
| `add_artifact` and `spawn_sub_investigation` as progress signals — keep current whitelist? | **Yes, but add a fixture-based test** that asserts new tools not in either list are intentional (a PR-time guard). |

---

## 2. Phase plan (5 phases, ordered by risk and dependency)

### Phase A — Trivial pure-deletions and dead-code cleanup (1 day)

**Items:** #1, #2, #4, partial #16 (delete `common/SourceList.tsx`, `Badge.tsx`, `Divider.tsx`, `StateBadge.tsx`)

**Why first:** Zero behavior change. Pure deletions + comment updates. The 358+12 tests cannot regress.

**Commits (each independently shippable):**
- `chore(handlers): delete _PLACEHOLDER_V2_SCHEMAS unreachable fallback` (tools/handlers.py:985-1092, ~70 LOC)
- `docs(stuck): fix mark_progress docstring to match actual code` (stuck.py:36-41)
- `chore(frontend): delete dead common/ primitives` (Badge.tsx, Divider.tsx, StateBadge.tsx, common/SourceList.tsx)
- `test(stuck): pin _PROGRESS_* whitelist contract` (test_stuck.py: new fixture-style test)

**Checkpoint:** `git diff --stat` shows ~100 lines deleted. `pytest` and `npm test` both green.

---

### Phase B — Test infrastructure (1 day)

**Items:** #3, partial #16 (cx dedup, day-N rename), #5

**Why second:** Tests-first. Once the test infrastructure lands, the refactors in C/D/E have a safety net.

**Commits:**
- `test(scheduler): add test_scheduler.py — 12 tests pinning the 30s poll + contention path` (~150 LOC, model after `test_orchestrator.py` + `test_resume.py`)
- `docs(sub_runtime): document the asyncio.run() fallback + add a test that exercises both paths` (sub_runtime.py:756-783 + 1 new test)
- `chore(frontend): dedupe cx to utils/cx` (Button.tsx, Card.tsx, Pill.tsx — delete 3 inline copies)
- `chore(tests): rename test_day*_*.py to behavior-named files` (3 git mv + docstring updates; day-N prose stays at top of each)

**Checkpoint:** Total test count: 358 backend + 24+ frontend (12 existing + 6 new vitest expansions added in Phase E). The day-N files renamed. cx centralized.

---

### Phase C — Storage consolidation (1 day)

**Item:** #8

**Why third:** Touches no SQL, no behavior. The 7→3 file merge is a pure import refactor. The risk is mechanical: forgetting to update a relative import.

**Commits:**
- `refactor(storage): merge 7 thin store files into 3 new modules` (dossier_lifecycle.py, audit.py, settings.py; total 17 → 13 files)
- `test(storage): assert every name in old __all__ is importable from storage` (tests/test_storage_imports.py)

**Checkpoint:** All 358 backend tests still pass. `git grep "from .wake_store"` returns empty. The 3 new modules are self-contained.

---

### Phase D — Additive runtime + schema features (1-2 days)

**Items:** #6, partial #7 (migrate InvestigationPlanItem callers)

**Why fourth:** Additive (no data migration). Small surface. The schema column is NULL-tolerant. The runtime change is best-effort.

**Commits:**
- `feat(dossiers): add last_signal_kind column` (db.py:_REQUIRED_COLUMNS + wake_store.py:set_dossier_last_signal_kind + stuck.py:write in _assign_tier_and_emit + prompt.py:build_state_snapshot surface)
- `refactor(intake): migrate InvestigationPlanItem → PlanItem` (intake/tools.py:229 + 4 test files)
- `chore(intake): add debug log to _coerce_legacy_items` (models.py:548-570; logs N=count of coerced items)

**Checkpoint:** New column visible in DB; old dossiers have `last_signal_kind=NULL`. The legacy validator still works but logs the coercion. The intake commit path uses `PlanItem` directly.

---

### Phase E — Frontend consolidation (1-2 days)

**Item:** #16, all parts, plus #17 vitest expansion

**Why fifth:** Most visible changes; want the test infra from Phase B and the type fixes from Phase D in place first. The vitest expansion at the end ensures the new render paths are pinned.

**Commits (each visually verified on `/demo` before commit):**
- `refactor(frontend): collapse two SectionCard paths → dossier/SectionCard` (DemoPage.tsx:4 import + 2 file deletions)
- `chore(frontend): wire Button to 8 hand-rolled sites` (preserves px-5 on PlanApprovalBlock CTAs)
- `test(frontend): add 6 vitest tests (time, format, useDocumentTitle, useChangeLogSinceVisit, IntakeInput IME, PlanDiffSidebarView)`
- `docs(frontend): defer InvestigationLogSidebar test to follow-up` (note in vitest config or a `.todo` file)

**Checkpoint:** All 12+6=18 vitest tests pass. The `/demo` page renders with the dossier treatment. Hand-rolled `bg-accent text-paper ... rounded` sites are gone (except the one `<Link>`).

---

### Phase F — Schema hardening (2-3 days)

**Items:** #9, #10, #11, #12, #13, #14, #15

**Why last and split:** The biggest-bang refactors. Each requires the project owner to validate the migration in a dev DB before production.

**Commits (each independently shippable; gated on dev-DB validation):**
- `chore(dossiers): stop serializing items into investigation_plan JSON` (#9; storage/dossier_store.py:563-650)
- `feat(dossiers): add dossier_plans table + sentinel-guarded backfill` (#10; new table + _migrate_plan_metadata)
- `chore(dossiers): stop writing investigation_plan JSON` (#11; write to dossier_plans only)
- `chore(dossiers): add 5 FKs + 9 CHECK constraints via table-recreate script` (#13 + #14; scripts/add_schema_constraints.py, modeled on scripts/abandon_zombie_subs.py)
- `feat(agent): add opt-in retention policy` (#15; agent/retention.py + scheduler hook + change_log entries; default off)

**Checkpoint:** Each of these lands with a 1-week soak period in dev before the next. The 30-day zero-reads window for #12 is observed.

**Phase F has its own sub-plan because each item is a multi-day PR with rollback considerations.** The detailed sub-plan is in §3 below.

---

## 3. Phase F sub-plan (the meatiest part)

### F.1 — Stop serializing items into investigation_plan JSON (1 day)

**Change:** `storage/dossier_store.py:563-650` — when serializing the new `InvestigationPlan` JSON, set `items=[]` regardless. The merge at lines 82-86 (and the matching blocks at 96-100, 243-247) continues to overlay the table.

**Test:** `tests/test_plan_items.py` — new test that `get_dossier(id).investigation_plan.items` matches `plan_items` table exactly after `update_investigation_plan` call.

**Risk:** Low. The merge was already authoritative. API contract preserved.

**Rollback:** Revert the one line that sets `items=[]` back to `items=merged`.

---

### F.2 — Add `dossier_plans` table + backfill (1-2 days)

**Change:** New table:
```sql
CREATE TABLE dossier_plans (
  dossier_id TEXT PRIMARY KEY REFERENCES dossiers(id) ON DELETE CASCADE,
  rationale TEXT NOT NULL DEFAULT '',
  drafted_at TEXT,
  approved_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

New sentinel-guarded `_migrate_plan_metadata` in `db.py` (mirroring `_migrate_plan_items`). Reads `settings.plan_metadata_migrated`; if not set, iterates dossiers with non-empty `investigation_plan` JSON and copies `rationale`/`drafted_at`/`approved_at` to the new table, then sets the sentinel.

**Read path:** `get_dossier` queries `dossier_plans` for the metadata. If row exists, use it. If not, fall back to JSON (for legacy dossiers during the migration window).

**Write path:** `update_investigation_plan` and `approve_investigation_plan` write to the table. Continue writing JSON for now (redundant, but safe).

**Test:** `tests/test_plan_items.py` — assertion that `dossier_plans` row exists after a write. Test for the backfill function (sentinel-guarded).

**Risk:** Medium. The read path is a fallback chain; if it doesn't match, the resume state or prompt snapshot could be wrong. Mitigated by the test.

**Rollback:** Sentinel in settings. Re-running `init_db` with sentinel=false re-does the backfill. Drop the table via a side-channel script (mirroring the `abandon_zombie_subs.py` pattern).

---

### F.3 — Stop writing `investigation_plan` JSON (1 day)

**Change:** `update_investigation_plan` and `approve_investigation_plan` write to `dossier_plans` only. The JSON column is no longer updated.

**Test:** `tests/test_plan_items.py` — assertion that `dossiers.investigation_plan` JSON is unchanged after a write (or null, if F.2 already cleared it).

**Risk:** Low. Read path is the only consumer; it's a fallback to JSON for legacy data, table for new data.

**Rollback:** Restore the JSON write in `update_investigation_plan`.

---

### F.4 — Add 5 FKs + 9 CHECK constraints (1-2 days)

**Change:** New script `scripts/add_schema_constraints.py` (modeled on `scripts/abandon_zombie_subs.py`):
1. `PRAGMA foreign_keys=OFF`
2. For each table that needs FKs or CHECKs, run the table-recreate dance:
   ```sql
   CREATE TABLE x_new (… with FKs and CHECKs …);
   INSERT INTO x_new SELECT * FROM x;
   DROP TABLE x;
   ALTER TABLE x_new RENAME TO x;
   ```
3. `PRAGMA foreign_key_check` and `PRAGMA integrity_check` — assert zero violations.
4. `PRAGMA foreign_keys=ON`.

Update `schema.sql` to include the new constraints for fresh DBs.

**Pydantic introspection helper** in `db.py`:
```python
def _check_constraint_for_enum(table: str, column: str, enum_cls: type[Enum]) -> str:
    return f"CHECK ({column} IN ({','.join(repr(m.value) for m in enum_cls)}))"
```

The script uses this for the 9 enum-stored columns. The FK additions are hand-coded for the 5 columns (per the per-column decision in research-storage §3).

**Test:** Run the script against the dev DB; run the full test suite; assert zero foreign-key violations. Plus a unit test for the Pydantic-introspection helper.

**Risk:** Medium. The `change_log.section_id` FK is the highest-risk change — `delete_section` tool must `UPDATE change_log SET section_id = NULL WHERE section_id = ?` before the section delete, in the same transaction. New test in `test_section_store.py` (or wherever section-delete is tested) pins this.

**Rollback:** Reverse the table-recreate. Side-channel script to revert (mirror of `add_schema_constraints.py`).

---

### F.5 — Add opt-in retention policy (1-2 days)

**Change:** New module `backend/vellum/agent/retention.py` with:
- `RetentionPolicy` dataclass (per-table TTL).
- `prune_once(conn, now)` function — pure SQL inside `with connect() as conn:`. Each `DELETE` is `LIMIT 1000` per table.
- `run_retention_loop(poll_seconds=86400)` — async coroutine.

Hook into `agent/scheduler.py`: a second coroutine on the same lifespan task list, runs at startup and every `poll_seconds` after.

New settings:
- `retention_enabled` (default `False`)
- `retention_ttl_days` (per-table defaults: tool_invocations=7, agent_turns=30, reasoning_trail=90; the rest are infinite)

Every prune run writes a `change_log` entry: `("retention", "pruned N tool_invocations, M agent_turns")` — honors "user is in the loop."

**Active-dossier rule:** the pruner's `DELETE` queries join on `dossiers.status` to enforce "never prune rows for a dossier in `active` or `paused` state." Only `delivered` or `abandoned` dossiers are eligible.

**Test:** `tests/test_retention.py`:
- Pre-fills each table with dated rows; asserts the right rows survive each pass.
- Idempotency test: running the pruner twice doesn't break anything.
- Active-dossier test: a 90-day-old `tool_invocations` row on a non-delivered dossier is **not** pruned.
- The change_log entry is written on every prune.

**Risk:** Medium. The active-dossier check is the most important thing to test. The "user is in the loop" rule means the pruner must log every run.

**Rollback:** `retention_enabled=False`. Stop the retention coroutine. Existing data is unchanged.

---

### F.6 — Drop `investigation_plan` column (30+ days after F.3)

**Decision criterion:** when the 30-day sliding window has zero reads of legacy dossier plan metadata from the JSON column.

**Change:** A one-shot script `scripts/drop_investigation_plan.py` (modeled on `abandon_zombie_subs.py`):
1. Counts reads of `investigation_plan` JSON in the last 30 days. If non-zero, refuse.
2. If zero: `ALTER TABLE dossiers DROP COLUMN investigation_plan`.
3. Update `schema.sql` to remove the column.
4. Update `dossier_store.get_dossier` to remove the fallback chain.
5. Run full test suite.

**Risk:** This is the only one-way door. The script refuses if there's recent activity.

**Rollback:** None. The column is gone. Any pre-F.6 dossier in a long-tail sleep cycle is now read-only via `dossier_plans`. Mitigation: the 30-day soak period is the safety net.

---

## 4. Cross-cutting concerns

### Test discipline

Every commit must:
- Land with the 358 backend + 12+ frontend tests green
- Add at least one new test for any new code path
- Add a regression test for any fix to a previously-undiscovered bug

### Commit hygiene

- One commit per Phase-A/B/C/D item (small, atomic)
- Phase-E commits each visually verified on `/demo` before commit (the visual change is real and intentional)
- Phase-F commits each require a dev-DB smoke test (`scripts/day2_smoke.py` against a non-critical dossier) before the next lands

### Open questions the project owner should answer before Phase F starts

These are the ones I made defaults for, but the owner should confirm:

1. **Retention default: opt-in or on-by-default?** (Default: opt-in. Reasoning: matches "user is in the loop" rule. Owner override welcome.)
2. **Phase F.6 drop criterion: 30-day zero-reads or "after backfill completes"?** (Default: 30 days. Reasoning: long-tail sleep-mode wake could read a legacy dossier. Owner override: "after backfill" is faster if the owner is comfortable with the risk.)
3. **InvestigationLogSidebar test in Phase E.7 (the deferred one):** ship now with flake risk, or defer entirely? (Default: defer entirely to a follow-up pass. Reasoning: the day-bucket grouping is complex and flake-prone. The 5 other vitest expansions cover more critical seams.)

### What the project owner should NOT do

- Don't merge all 17 items in one PR. Each item is independently shippable. Reviewer fatigue is the #1 risk to landing this cleanly.
- Don't skip the test infra (Phase B) before the refactors (Phase C-F). The tests are the safety net.
- Don't run F.5 retention with `retention_enabled=True` in production until 1 week of `False` has elapsed in dev (verify the change_log entries look right).
- Don't run F.6 column drop without the 30-day soak.

---

## 5. Rough effort estimate

| Phase | Effort | Risk | Calendar |
|---|---|---|---|
| A | 0.5 day | Trivial | Day 1 |
| B | 1 day | Small | Day 2 |
| C | 1 day | Small | Day 3 |
| D | 1-2 days | Small | Days 4-5 |
| E | 1-2 days | Small-medium | Days 6-7 |
| F | 5-7 days | Medium | Days 8-14 (with soaks) |
| F.6 column drop | 30+ days later | One-way | Day 45+ |

**Total: 2 weeks of focused work for Phases A-E, plus 5-7 days spread over 30+ days for Phase F.**

---

## 6. What "shippable v1" looks like when this lands

- **17 → 13 storage files.** Per-entity indirection reduced; the heavy files (dossier, plan_items, sub_investigation) stay split; the thin ones are gone.
- **Schema is type-safe at the DB level.** 5 new FKs, 9 CHECK constraints. The Pydantic-introspection helper guarantees the SQL enum list can never drift from the model.
- **`investigation_plan` is gone.** Plan metadata lives in `dossier_plans`. The 30-day soak is observed.
- **`last_signal_kind` is the new stuck-history field.** A flaky agent that always trips the same heuristic now has a memory across sleep/wake.
- **Retention is opt-in and logged.** The user sees every prune run in `change_log`. Destructive for tool_invocations/agent_turns/reasoning_trail; non-destructive for change_log/intake_messages/investigation_log.
- **Scheduler has 12 dedicated tests.** The late-answer correctness contract at `scheduler.py:202-216` is no longer "trust the deep-dive quote" — it's pinned.
- **Frontend has 18+ vitest tests.** cx is centralized; SectionCard is one render path; the 8 hand-rolled buttons are wired to the `Button` component.
- **12 of 13 open questions have defaults the project owner can override.** The 13th (the InvestigationLogSidebar test) is explicitly deferred.

The 358 backend tests + 18+ frontend tests, plus the 12 new ones added in this pass, give a maintainer the confidence to read the surface end-to-end. The 17 → 13 storage file count is a small win, but it's the kind of win that compounds — every future PR is one fewer file to scan.

---

## 7. Next step

**Recommend:** start with Phase A today (1 day, trivial risk), then Phase B tomorrow (1 day, the scheduler test is the highest-value test in the repo). Phases C-E are next week's work. Phase F is a 2-week tail with a 30-day soak for the column drop.

If the project owner wants a different ordering, the most common swap is "do Phase E (frontend) first because the visual changes are more rewarding to see." That works too — the phases are independent, only the test-infrastructure comes first.
