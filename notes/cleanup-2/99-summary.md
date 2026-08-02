# Cleanup-2 — Final Summary

**Date:** 2026-08-02 (single overnight session)
**Commits:** 19 (8 one-shot + 4 research/design + 7 implementation + 6 docs)
**Tests:** 358 → 387 backend (+29); 12 → 26 frontend (+14)
**Files:** 17 → 13 storage modules (-4); 4 dead common/ components deleted; 1 dead types.generated.ts deleted

## What got shipped

### One-shot pass (8 commits)
- ✅ `AGENT_MAX_TURNS=200` rationale doc comment
- ✅ Deleted dead `mark_needs_input_resolved` function + fixed the aspirational `mark_progress` docstring
- ✅ Deleted 146 KB of `types.generated.ts` no one imported + fixed README's "Regenerating frontend types" section
- ✅ Fixed `NextAction.priority` REAL vs int mismatch (now `float`)
- ✅ Added field-level size caps to 8 unbounded JSON columns (debrief, working_theory, premise_challenge, out_of_scope, etc.)
- ✅ Set up vitest with 3 critical smoke tests (cx, PLAN_DIFF_CATEGORY_ORDER, AgentActivityIndicator.derive)

### Phase A — trivial deletions + dead code (4 commits)
- ✅ Deleted 70 LOC of unreachable `_PLACEHOLDER_V2_SCHEMAS` dict + fallback loop
- ✅ Deleted 4 dead `common/` primitives (Badge, Divider, StateBadge, common/SourceList)
- ✅ Added `_STUCK_EXEMPT_TOOLS` whitelist + 2 lint tests (`test_progress_whitelist_covers_all_handlers`, `test_progress_mutation_tools_are_a_strict_subset_of_progress_tools`)

### Phase B — test infrastructure (4 commits)
- ✅ **`test_scheduler.py` — 13 tests pinning the 30s poll + contention path** (the highest-value test in the repo per the deep-dive)
- ✅ Exposed the broken `asyncio.run()` fallback at `sub_runtime.py:769-783` — pinned by `test_spawn_handler_when_called_inside_running_loop`
- ✅ `cx` dedup in Button, Card, Pill (3 inline reimplementations → import from `utils/cx`)
- ✅ Day-N pytest file rename: `test_day1_roundtrip.py` → `test_roundtrip_v2.py`, etc.

### Phase C — storage consolidation (1 commit)
- ✅ **17 → 13 storage files** via 3 new modules:
  - `dossier_lifecycle.py` (wake + user_notes + next_actions)
  - `audit.py` (agent_turns + budget_accounting)
  - `settings.py` (settings + tool_invocations)
- ✅ 7 thin files deleted; flat `storage.X` namespace preserved
- ✅ `tests/test_storage_imports.py` (3 tests) pins the public-surface contract

### Phase D — additive features (2 commits)
- ✅ **H-20 `last_signal_kind` column** — `dossiers.last_signal_kind TEXT NULL` via `_REQUIRED_COLUMNS` ratchet. Sync best-effort write in `_assign_tier_and_emit`. `build_state_snapshot` surfaces it as a "Last stuck signal" block.
- ✅ 3 new tests in `test_stuck.py`: storage round-trip, Dossier Pydantic surface, end-to-end through `_assign_tier_and_emit`.
- ✅ **H-21 `_coerce_legacy_items` debug log** — `logger.debug` on each coercion so a future caller that constructs the legacy `InvestigationPlanItem` is traceable.
- ⚠️ **Intake migration to `PlanItem` was reverted** — `PlanItem` has permissive defaults (question: str = "") so the "surface plan_error for malformed seeds" contract that `test_intake` pins would be silently lost. The intake contract stays on `InvestigationPlanItem` until a follow-up decides to relax the validation.

### Phase E — frontend consolidation (1 commit)
- ✅ **`dossier/SectionCard` is the single render path.** `DemoPage` now uses `dossier/SectionList` (the canonical Day-4 renderer); `sections/SectionCard.tsx` and `sections/SectionsList.tsx` deleted.
- ✅ `sections/SourceList.tsx` moved to `common/SourceList.tsx` (git mv; dossier/SectionCard now imports from common/ — the natural direction).
- ✅ **Button wired to 7 hand-rolled sites** (DemoPage, IntakePage ×2, IntakeInput, NeedsInputItem, PlanApprovalBlock ×2 with `px-5` override, ErrorBoundary). DossierListPage's Link intentionally left alone (Button is a `<button>`, not a `<Link>`).
- ✅ **26 vitest tests across 5 files** (added time.test.ts with 7 tests, format.test.ts with 7 tests). Deferred: `InvestigationLogSidebar` test (flake risk on day-bucket grouping).

### Docs & cleanup (6 commits)
- ✅ README: expanded counts (30+7=37 tools, 22 tables, 387+26 tests), added "How the agent stays honest" section, "Test suite quick reference", "Known issues and follow-ups", "Fixture dossiers" subsection, expanded Notable endpoints (3 more), expanded env vars (9 → 16 entries including all stuck-detector thresholds).
- ✅ `notes/cleanup-2/00-design-plan.md`: tagged each item shipped/partial/deferred
- ✅ `storage/__init__.py` docstring: updated to mention the cleanup-2 layout

## What got deferred (Phase F)

| Item | Why deferred | Recommended next step |
|---|---|---|
| F.2: `dossier_plans` table + sentinel-guarded backfill | Multi-day migration. New table + 4-phase sequence (stop writing items → migrate plan metadata → stop writing JSON → drop column). | Open a dedicated follow-up PR with its own soak window. |
| F.3: stop writing `investigation_plan` JSON | Depends on F.2 | After F.2 |
| F.4: 5 new FKs + 9 CHECK constraints | Table-recreate script is risky. The `change_log.section_id` FK is the highest-risk change (requires `delete_section` to nullify the FK in the same transaction). | Open a dedicated follow-up. Write the script with dry-run + `--force` guards, modeled on `scripts/abandon_zombie_subs.py`. |
| F.5: opt-in retention policy | New infrastructure: `agent/retention.py` module + scheduler hookup + per-table TTL settings + change_log entries on every prune. | Open a dedicated follow-up. Default off (matches the "user is in the loop" rule). |
| F.6: drop `investigation_plan` column | One-way door. Requires the 30-day-soak zero-reads observation window. | After F.2 + F.3 + 30 days in production. |
| `asyncio.run()` fallback fix at `sub_runtime.py:769-783` | The fix is to run the sub-investigation in a separate thread with its own event loop. Not trivial. | Open a dedicated follow-up. Pinned by `test_spawn_handler_when_called_inside_running_loop`. |
| `intake/tools.py` migration to `PlanItem` | Reverted because `PlanItem` is too permissive (question: str = "" default). Would silently lose the "surface plan_error for malformed seeds" contract. | Requires deciding to relax the intake validation contract. Open a follow-up that re-reads the intake semantics. |

## Key files changed

### Created
- `backend/vellum/storage/dossier_lifecycle.py` (370 LOC) — wake + user_notes + next_actions
- `backend/vellum/storage/audit.py` (240 LOC) — agent_turns + budget_accounting
- `backend/vellum/storage/settings.py` (160 LOC) — settings + tool_invocations
- `backend/tests/test_scheduler.py` (~390 LOC) — 13 tests
- `backend/tests/test_storage_imports.py` (~150 LOC) — 3 tests
- `frontend/src/utils/time.test.ts` (~60 LOC) — 7 tests
- `frontend/src/utils/format.test.ts` (~50 LOC) — 7 tests
- `notes/cleanup-2/` — research + design + plan + this summary

### Modified (key)
- `README.md` — counts, sections, env vars, endpoints all updated
- `backend/vellum/storage/__init__.py` — flat re-exports of all 119 public names
- `backend/vellum/storage/_helpers.py` — `_row_to_dossier` reads `last_signal_kind`
- `backend/vellum/models.py` — `Dossier.last_signal_kind`, `MAX_DOSSIER_BLOB_*` constants, debug log on `_coerce_legacy_items`
- `backend/vellum/db.py` — `dossiers.last_signal_kind TEXT` in `_REQUIRED_COLUMNS`
- `backend/vellum/agent/stuck.py` — top-level `storage` import, H-20 sync write, `_STUCK_EXEMPT_TOOLS` whitelist
- `backend/vellum/agent/prompt.py` — "Last stuck signal" block in `build_state_snapshot`
- `frontend/src/pages/DemoPage.tsx` — uses `dossier/SectionList`, `Button`
- `frontend/src/components/dossier/SectionCard.tsx` — imports `SourceList` from `common/`
- `frontend/src/components/common/{Button,Card,Pill}.tsx` — `cx` from `utils/cx`
- 7 component files — `Button` wiring with imports
- `frontend/src/test-setup.ts` — vitest config

### Deleted
- `backend/vellum/agent/stuck.py::mark_needs_input_resolved` function
- `backend/vellum/tools/handlers.py::_PLACEHOLDER_V2_SCHEMAS` dict (70 LOC) + fallback loop
- `backend/vellum/storage/{wake,user_note,next_action,turn,budget,settings,idempotency}_store.py` (7 files)
- `frontend/src/api/types.generated.ts` (146 KB)
- `frontend/src/components/common/{Badge,Divider,StateBadge,SourceList}.tsx` (4 files)
- `frontend/src/components/sections/{SectionCard,SectionsList}.tsx` (2 files)
- `frontend/src/components/sections/SourceList.tsx` (moved to common/ — git mv)
- `backend/tests/test_day{1_roundtrip,2_autonomous,3_lifecycle}.py` (3 files — git mv to behavior-named)
