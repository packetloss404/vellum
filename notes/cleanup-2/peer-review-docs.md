# Vellum — Cleanup-2 Docs & Dead-Code Peer Review

**Date:** 2026-08-02
**Scope:** `D:\projects\Vellum` post-cleanup-2.
**Method:** read README, design plan, three research reports, spot-checked
storage/`__init__.py`, ran `pytest --collect-only -q` (387 tests) and
`npm test` (26 tests), and grep'd for the dead-code items called out
in the user's brief.

**Bottom line:** the cleanup-2 pass is well-executed and most of the
README is in sync. The remaining issues are small but two are judge-
visible (a wrong default value in the env-var table, a stale test
filename in the project layout), and one is a wrong claim about
**what was deleted** (HANDLER_OVERRIDES is still very much alive).

---

## Headline summary (top 5, prioritized for what a hackathon judge sees first)

1. **`README.md:263` — `COMPACT_INPUT_TOKEN_THRESHOLD` default is listed as `100000`, but the actual default in `backend/vellum/config.py:107-109` is `80000`.** Judges who try to override the env var will hit a different value than the doc claims. **High severity.** This is the single most judge-visible contradiction.
2. **`README.md:177` lists `test_day1_roundtrip.py`** — that file was renamed to `test_roundtrip_v2.py` in Phase B and does not exist in `backend/tests/`. The README also lists `test_runtime_hooks.py` **twice** (lines 176 and 178) and is **missing** `test_agent_prompts.py` (a 19-test file present in the directory). **High severity.** This sits in the project layout the README is supposed to reflect faithfully.
3. **`backend/vellum/tools/handlers.py:1267` still defines `HANDLER_OVERRIDES`** and it is actively populated by `sub_runtime.py:869` (registration of `spawn_sub_investigation → spawn_handler`). The user said this was "already gone" — it is not. It is a load-bearing extension point used in production. **Medium severity.** Either the README/design plan should mention it, or the cleanup-2 should actually delete it (it can't be deleted without also rewriting how sub-investigations are spawned).
4. **`README.md:22` says `stuck.py` is "~890 LOC"; actual is 1028 lines.** `README.md:50` says "~55 components"; actual is 40 .tsx files in `frontend/src/components/` (67 if you count every `.tsx`/`.ts` in `src/`). `README.md:119/163` says `test_stuck.py` is "21 tests"; actual is 22. **Medium severity.** These are off-by-a-few stale numbers — the kinds of things a careful judge cross-checks.
5. **`stuck.py:40-41`** still has the aspirational comment "A separate ``mark_progress`` hook was planned but never wired up; the inline clear is the load-bearing behavior." The design plan's item #2 ("`mark_progress` docstring one-liner fix") is marked "✅ shipped" but the reference is still there. The comment is technically still informative (it documents *why* the inline clear matters), so this is **low-medium** — but if the plan claims a docstring fix shipped, the docstring should at least be reframed as intentional.

---

## 1. Stale claims in `README.md`

| # | Severity | Location | Stale text | Actual | Suggested fix |
|---|---|---|---|---|---|
| 1.1 | **High** | `README.md:263` | `\| `COMPACT_INPUT_TOKEN_THRESHOLD` \| `100000` \| Input token count above which context compaction fires. \|` | Default is `80000` (`backend/vellum/config.py:107-109`). The `80000` is even explained in the same file's comment: "Default 80000 (~80% of the 100k practical input limit)." | Change `100000` → `80000` in the env-var table. |
| 1.2 | **High** | `README.md:177` | `test_self_heal.py, test_db_migrations.py, test_day1_roundtrip.py,` | The file is `test_roundtrip_v2.py` (renamed in Phase B; present in `backend/tests/`). `test_day1_roundtrip.py` does not exist. | Remove the entry; `test_roundtrip_v2.py` is already listed on line 172. |
| 1.3 | **High** | `README.md:178` | `test_jit_loading.py, test_runtime_hooks.py, test_prompt_caching.py,` | `test_runtime_hooks.py` is duplicated — already listed on line 176. | Remove the duplicate `test_runtime_hooks.py` from line 178. |
| 1.4 | **High** | `README.md:168-180` (project layout test list) | The list enumerates 35 of the 36 actual `test_*.py` files. | Missing: `test_agent_prompts.py` (19 tests, present in `backend/tests/`). | Insert `test_agent_prompts.py` somewhere in lines 168-180. |
| 1.5 | Medium | `README.md:22` | "Tiered stuck detection (`agent/stuck.py`, ~890 LOC, pinned by 21 tests)." | `stuck.py` is 1028 lines (per `(Get-Content stuck.py).Count`); `test_stuck.py` is 22 tests (per `pytest --collect-only -q`). | Change "~890 LOC" → "1028 LOC" and "21 tests" → "22 tests." |
| 1.6 | Medium | `README.md:50` | "React 18 + TypeScript + Tailwind (Vite) + ... **~55 components**, polling for live dossier state." | Actual `frontend/src/components/` contains **40** `.tsx` files (67 if every `.tsx`/`.ts` in `src/` is counted; 41 if you count `.tsx` only). | Change "~55 components" → "~40 components" (or "~67 TS/TSX files" if you mean the entire src tree). |
| 1.7 | Medium | `README.md:119` and `README.md:163` | "test_stuck.py (21 tests)" (×2) | 22 tests per `pytest --collect-only -q tests/test_stuck.py`. | Change "21 tests" → "22 tests" at both locations. |
| 1.8 | Low | `README.md:82,88` | "# Backend (387 tests, ~50s)" / "# Frontend (26 tests, <5s)" | 387 and 26 are accurate as of 2026-08-02. | No change; flagging as a regression risk if the count drifts. The next doc pass should re-run `pytest --collect-only -q` to verify. |
| 1.9 | Low | `README.md:97-100` | "test_scheduler.py (13 tests) ... test_storage_imports.py (3 tests) ... test_runtime_v2.py" | 13 / 3 / 16 (no count given for `runtime_v2`) are accurate. | Consider adding the `runtime_v2` count for parity. |
| 1.10 | Low | `README.md:134/155` | "flat re-export of all 119 public names" | `__all__` is 105 names; `dir(storage)` (excluding dunders/imports) is 119. The 119 figure matches the broader count. | No change. |

**Notes on the README's quantitative claims that are *correct*:** the "30 dossier + 7 intake = 37 typed, Pydantic-backed tools" line at `:17` is accurate (30 entries in `tools/handlers.py:681` HANDLERS dict + 7 entries in `intake/tools.py:317` HANDLERS dict). The "22-table relational schema" at `:49` and `:157` is accurate (`schema.sql` has 22 `CREATE TABLE` statements). The "13 storage files after cleanup-2" at `:120` is accurate (12 source files + `__init__.py` + `_helpers.py` = 14 total; "13" if you exclude `__init__.py` per the research's original framing). The "387 backend pytest tests across 36 files" and "26 frontend vitest tests across 5 files" are both accurate.

---

## 2. Stale claims in `notes/cleanup-2/00-design-plan.md`

The design plan has been retro-fitted with an "Implementation status" section (lines 7-9) that correctly summarizes the close-out, so most stale claims have been fixed. A few remain:

| # | Severity | Location | Stale text | Actual | Suggested fix |
|---|---|---|---|---|---|
| 2.1 | Medium | `00-design-plan.md:5,13,93,107,298,352` | "358 backend tests + 12 frontend tests" | The plan was scoped against the pre-cleanup-2 baseline (358 + 12); the actual final state is **387 + 26**. The plan correctly adds a status block (line 8) but doesn't reconcile these earlier references. | Either add "pre-cleanup-2 baseline: 358 + 12" qualifier on line 5, or rewrite as "387 + 26 must stay green at every commit." |
| 2.2 | Medium | `00-design-plan.md:31` | Item #7 status: "⚠️ partial — debug log added, intake migration reverted (PlanItem is too permissive, breaks the plan_error contract)" | This is **accurate** — `intake/tools.py:235` still uses `m.InvestigationPlanItem.model_validate(i)` — but the README's "Known issues" section (`README.md:275-276`) **also** notes this. Good. | No change; this is one of the few places the partial-state is properly documented in two places. |
| 2.3 | Medium | `00-design-plan.md:5` | "Scope: 17 items, 0 breaking changes to the public API" | The cleanup-2 preserved the public surface — *except* it never delivered on the implicit promise of removing `HANDLER_OVERRIDES` (see §3.1 below). The plan did not claim to remove it, so this is fine. | No change. |
| 2.4 | Low | `00-design-plan.md:344` | "Scheduler has 12 dedicated tests" (item #3) | Actual is 13 tests in `test_scheduler.py`. The status column on line 27 acknowledges this ("✅ shipped (13 tests)") but the body text on line 344 still says 12. | Change "12" → "13" in the body text. |

---

## 3. Stale claims in the research reports

The three research docs (`01-research-storage.md`, `02-research-runtime.md`, `03-research-frontend.md`) are **research-time** artifacts and predate the implementation. I did not find any retrofitted status blocks, so the original numbers in them (e.g. "17 store files", "358 backend tests") are now stale by definition but are historically accurate snapshots. These are internal notes (severity **low**) — a small status banner at the top of each ("as of 2026-08-02: implemented; see 00-design-plan.md close-out") would be sufficient.

| # | Severity | Location | Notes |
|---|---|---|---|
| 3.1 | Low | `01-research-storage.md:13` | "17 store modules" is a pre-cleanup-2 count; the implementation landed at 14 (13 source + `__init__.py`) — see §4.1. |
| 3.2 | Low | `02-research-runtime.md:5` and `03-research-frontend.md:3` | Both reference the 358-test / 12-vitest baseline. |
| 3.3 | Low | `02-research-runtime.md:18` | "`grep` for `mark_needs_input_resolved` returns only the deep-dive notes" — confirmed; the function is fully deleted. |

---

## 4. Dead code / misleading comments

### 4.1 `HANDLER_OVERRIDES` is still load-bearing, not dead

**Severity: Medium.** The user's prompt says "`HANDLER_OVERRIDES` (already gone)" — this is **incorrect**.

- **Where:** `backend/vellum/tools/handlers.py:1254-1277`
- **Evidence:** The dict is defined at `:1267`, the dispatcher at `:1277` consults it (`impl = HANDLER_OVERRIDES.get(tool_name) or HANDLERS.get(tool_name)`), and `backend/vellum/agent/sub_runtime.py:866-869` populates it on import:
  ```python
  if not hasattr(handlers, "HANDLER_OVERRIDES"):
      handlers.HANDLER_OVERRIDES = {}  # type: ignore[attr-defined]
  handlers.HANDLER_OVERRIDES["spawn_sub_investigation"] = spawn_handler
  ```
  Runtime verification: `python -c "import vellum.agent.sub_runtime; from vellum.tools.handlers import HANDLER_OVERRIDES; print(list(HANDLER_OVERRIDES.keys()))"` prints `['spawn_sub_investigation']`.
- **Tests reference it too:** `backend/tests/conftest.py:34-40`, `backend/tests/test_runtime_hooks.py:26-35,142`, `backend/tests/test_sub_runtime.py:127-151`.

This is **not** a "forgotten deletion" — removing `HANDLER_OVERRIDES` would require also rewriting how sub-investigations are spawned (the override is what makes `spawn_sub_investigation` synchronous-blocking in the parent agent loop rather than a stub). The cleanup-2 plan didn't claim to remove it.

**Suggested fix:** update the user's mental model. Either:
- (a) Leave `HANDLER_OVERRIDES` in place and add a one-line `README.md:119` note: "30 typed tool handlers + 1 extension point (`HANDLER_OVERRIDES['spawn_sub_investigation']` for sub-investigations)."
- (b) Or do a separate cleanup pass that replaces the override with a properly-typed function-pointer or an `if tool_name == "spawn_sub_investigation"` branch in the dispatcher. But this is real work, not a one-liner.

### 4.2 `mark_progress` comment in `stuck.py` is still aspirational

**Severity: Low-medium.** Design plan item #2 ("`mark_progress` docstring one-liner fix") is marked "✅ shipped" (`00-design-plan.md:26`), but the actual change in `stuck.py:40-41` reads:
> "A separate ``mark_progress`` hook was planned but never wired up; the inline clear is the load-bearing behavior."

This is the **same** aspirational framing the design plan said to fix. The comment is informative (it explains *why* `_PROGRESS_MUTATION_TOOL_NAMES` is the load-bearing reset path), so it has value — but the design plan shouldn't claim it was "fixed" if the text is unchanged.

**Suggested fix:** mark item #2 in the design plan as "informational comment retained; not a code fix" or reword the comment to:
> "The per-section revision counters reset in `record_tool_call` itself via the `_PROGRESS_MUTATION_TOOL_NAMES` set. An earlier sketch proposed a `mark_progress` hook; the inline clear is the canonical path."

### 4.3 `handlers.py:1097-1098` "v2 model hasn't landed" comment is now misleading

**Severity: Low.** Lines 1097-1098 read:
> "v2 model hasn't landed — publish a permissive placeholder so the surface count is stable and the agent won't break on day-1 wiring."

But all three referenced models exist in `backend/vellum/models.py`:
- `ArtifactUpdate` at `:654`
- `SubInvestigationComplete` at `:714`
- `SubInvestigationUpdate` at `:725`

The else-branch (lines 1099-1111, 1129-1141, 1158-1172) is **unreachable in production**. Runtime verification: importing `vellum.tools.handlers` populates `_INPUT_MODELS` with all three v2 models via the lazy `getattr` pattern at lines 830-841.

**Suggested fix:** change the comment to a "fallback for a hypothetical model-removal branch" framing, e.g.:
> "Defensive: if a future refactor removes the v2 model, fall back to a permissive schema so the agent doesn't break. The else-branch is unreachable today; the v2 models are load-bearing."

Or, since the fallback is dead, delete it (this would be a Phase F item).

### 4.4 "day-2" / "day-1" / "day-3" day-N comments in code

**Severity: Low.** These are dev-time markers that have lost their meaning post-cleanup-2 (the phases are no longer "day 1, 2, 3" — they're the v1/v2/JIT tool split). Found in:
- `backend/vellum/agent/orchestrator.py:254` — "This is the day-2 observability entry point"
- `backend/vellum/agent/stuck.py:11` — "v2 (day 2): every surfaced StuckSignal also emits an investigation_log entry"
- `backend/vellum/agent/stuck.py:16` — "Calibration rationale (day 5)"
- `backend/vellum/agent/telemetry.py:226-227` — "day-2 schema doesn't add one"
- `backend/vellum/intake/tools.py:11` — "Unlike the day-1 dossier handlers"
- `backend/vellum/intake/tools.py:130,161` — "day-3 polish", "day-3 shape"
- `backend/vellum/intake/tools.py:149` — "the day-2 agent"
- `backend/vellum/tools/handlers.py:1098` — "day-1 wiring"
- `backend/vellum/tools/handlers.py:1254` — "Extension points for day-2 agents"

These are all internal developer-journal markers. None are wrong, but a judge reading `stuck.py` will see "day 2", "day 5" with no context. A one-line replacement ("v2 tool split", "calibration rationale from 5-day build") would help.

### 4.5 `investigation_plan` JSON column is still being written to (not deleted)

**Severity: Low** (expected per design plan Phase F deferral). The README's "Known issues" section at `:275` already documents this:
> "The `items=[]` serialization already happens at write time (`storage/dossier_store.py:597, 606`); the column itself will be dropped in a 30-day-soak migration once we're confident no legacy dossier needs the JSON read."

Verified: the JSON is still written by `update_investigation_plan` (line 597 region), `approve_investigation_plan`, and `replan_dossier` (`decision_point_store.py:135-146`); the read path still falls back to JSON for legacy dossiers.

This is **correctly deferred** to Phase F; no action needed.

### 4.6 InvestigationPlanItem model — intake never migrated

**Severity: Medium** (documented in design plan close-out but worth re-surfacing). The design plan's item #7 says "Migrate now; delete later. Two-step" and the close-out marks it "⚠️ partial." The migration of `intake/tools.py:229` to `PlanItem` was reverted because `PlanItem` is too permissive (`question` is defaulted, not required) — the strict "surface `plan_error` for malformed seeds" contract is preserved by keeping `InvestigationPlanItem` in the intake path. The `_coerce_legacy_items` validator at `models.py:567-595` handles the runtime conversion. The README at `:276` documents this accurately. **No action needed** beyond what the design plan already says.

### 4.7 The "30 typed tool handlers" count is correct

`backend/vellum/tools/handlers.py:681-714` (HANDLERS dict) has **30 entries**: 10 v1 + 16 v2 + 4 JIT. The README's "30 typed tool handlers" at `:119` is accurate. The intake agent has 7 handlers (`intake/tools.py:317-325`). Total = 37. The README's "30 dossier + 7 intake = 37" at `:17` is accurate.

### 4.8 `frontend/src/components/sections/` still has 2 demo-only files

**Severity: Low (by design).** Per the design plan, the SectionCard consolidation left `ReasoningTrail.tsx` and `RuledOutList.tsx` in `sections/` as demo-only files. The README at `:175-176` documents this correctly. **No action needed.**

---

## 5. Stale paths in docs

| # | Severity | Location | Notes |
|---|---|---|---|
| 5.1 | Low | `README.md:111` | `storage/polling for wake_store, fires sessions on schedule` — the file `wake_store.py` no longer exists. The function lives in `dossier_lifecycle.py`. Same for "tool_invocations" lives in `settings.py`, "agent_turns" in `audit.py", "budget_accounting" in `audit.py`. |
| 5.2 | Low | `README.md:155` | "shared row-converters + `_ORDER_STEP`" — verified; `_helpers.py` does export `_ORDER_STEP`. |

`README.md:111` and `:130-133` correctly enumerate the new module layout (`dossier_lifecycle.py`, `audit.py`, `settings.py`), so the stale references in the agent sub-list on line 111 are an inconsistency within the README itself. **Suggested fix:** rewrite the `agent/` sub-list (line 108-116) to use the new storage function names, e.g. "polls `storage.list_dossiers_ready_to_wake` (dossier_lifecycle.py), fires sessions on schedule."

---

## 6. Summary of what to fix before showing to judges

**Must-fix (high severity, judge-visible):**
- `README.md:263` — `COMPACT_INPUT_TOKEN_THRESHOLD` default `100000` → `80000`.
- `README.md:177` — remove `test_day1_roundtrip.py` (file doesn't exist; was renamed to `test_roundtrip_v2.py` on line 172).
- `README.md:178` — remove the duplicate `test_runtime_hooks.py` (already on line 176).
- `README.md:168-180` — add `test_agent_prompts.py` (missing from the layout).

**Should-fix (medium severity):**
- `README.md:22` — `stuck.py` "~890 LOC" → "1028 LOC"; "21 tests" → "22 tests".
- `README.md:50` — "~55 components" → "~40 components" (or count and state explicitly).
- `README.md:119,163` — `test_stuck.py` "21 tests" → "22 tests" (×2).
- Either delete `HANDLER_OVERRIDES` (real work — see §4.1) or document it in the README as a load-bearing extension point. Currently both the design plan and the user's brief are wrong about its status.

**Nice-to-have (low severity, internal polish):**
- `stuck.py:40-41` — reword the `mark_progress` comment to match the design plan's "shipped" status, or mark item #2 in the design plan as "intentionally retained" (see §4.2).
- `handlers.py:1097-1098` — reword the "v2 model hasn't landed" comment, or delete the unreachable fallback (see §4.3).
- `handlers.py:1254`, `orchestrator.py:254`, `telemetry.py:226`, `intake/tools.py:11,130,161,149` — replace day-N markers with v1/v2/JIT vocabulary (see §4.4).
- `00-design-plan.md:5,13,93,107,298,344,352` — reconcile the "358+12" baseline with the "387+26" close-out (see §2.1, §2.4).

**Out-of-scope (deferred by design):**
- `dossiers.investigation_plan` JSON column drop (Phase F.6) — documented in README `:275` and design plan §F.6.
- `dossier_plans` table backfill (Phase F.2) — documented in design plan §F.2.
- 5 FKs + 9 CHECK constraints (Phase F.4) — deferred per design plan §F.4.
- Append-only retention policy (Phase F.5) — deferred per design plan §F.5.
- `InvestigationPlanItem` deletion (blocked on the intake contract — see §4.6).

**Items confirmed-removed and no longer dead code:**
- `mark_needs_input_resolved` — fully deleted (grep confirms zero matches in `backend/`).
- `_PLACEHOLDER_V2_SCHEMAS` dict — fully replaced by the lazy `getattr(m, "ArtifactUpdate", None)` pattern; the old else-branches at `handlers.py:1099-1111, 1128-1141, 1158-1172` are still present as defensive fallbacks but the dict itself is gone.
- `frontend/src/components/common/{Badge,Divider,StateBadge}.tsx` — all three deleted (folder now contains Button, Card, DossierHero, EmptyState, ErrorBoundary, Pill, RelativeTime, SourceList).
- `frontend/src/api/types.generated.ts` — deleted (confirmed; folder contains only `client.ts`, `hooks.ts`, `types.ts`).
- `sections/SourceList.tsx` — the duplicate is gone; `common/SourceList.tsx` remains as the canonical.
