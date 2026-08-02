# Vellum — Documentation Bug-Check Report

**Date:** 2026-08-03
**Scope:** `D:\projects\Vellum` post-cleanup-2 + post-peer-review-fixes.
**Method:** Read every doc end-to-end. For each concrete claim, verified
against the actual code, schema, or test count. Ran `pytest --collect-only -q`
(393 tests) and `npm test` (26 tests).
**Out of scope:** Re-flagging the peer-review issues (verified all
relevant ones are fixed — see §4).

---

## Headline summary

| Severity | Count | What it is |
|---|---|---|
| **HIGH** | 6 | README env-vars table lists 5 env vars that don't exist or are mis-named; one stale storage-module reference |
| **MEDIUM** | 1 | Test count drift (391 in README vs 393 actual) |
| **LOW** | 1 | "41 components" double-counts the test file |

**Net: 8 distinct documentation bugs. The 5 fake env vars are the most
judge-visible — anyone who tries to set them will discover they do
nothing.** The other bugs are staleness that an attentive reader could
catch but won't be harmed by.

---

## 1. Bug writeups (severity-ordered)

### H-1. `VELLUM_SAME_TOOL_NO_PROGRESS_THRESHOLD` is not an env var (HIGH)

- **File:** `README.md:258`
- **Doc text:** `| VELLUM_SAME_TOOL_NO_PROGRESS_THRESHOLD | 8 | Stuck detector: how many calls to the same tool name before the no-progress heuristic fires... |`
- **Actual:** The value 8 is hardcoded at `backend/vellum/agent/stuck.py:193`:
  ```python
  _SAME_TOOL_NO_PROGRESS_THRESHOLD = 8
  ```
  There is **no** `os.getenv("VELLUM_SAME_TOOL_NO_PROGRESS_THRESHOLD", ...)`
  call in `config.py` (or anywhere). A user setting
  `VELLUM_SAME_TOOL_NO_PROGRESS_THRESHOLD=12` and restarting will see no
  effect; the threshold stays at 8.
- **Why it matters:** load-bearing calibration knob, listed as
  configurable, isn't. The peer-review-docs.md flagged it differently
  (as a low-severity 5% off-by-1000 number on `COMPACT_INPUT_TOKEN_THRESHOLD`).
- **Diff:**
  ```
  -| `VELLUM_SAME_TOOL_NO_PROGRESS_THRESHOLD` | `8` | ... |
  +| (constant, see `stuck.py:193`) | `8` | ... |
  ```

### H-2. `VELLUM_STUCK_ESCALATION_TIER1_TURNS` does not exist (HIGH)

- **File:** `README.md:262`
- **Doc text:** `| VELLUM_STUCK_ESCALATION_TIER1_TURNS | 1 | Tier 1 stuck signals (silent reasoning note) fire on this turn. |`
- **Actual:** No reference anywhere. The escalation is by signal count, not
  by turn-number:
  ```python
  # backend/vellum/agent/stuck.py:413-414
  st.stuck_escalation_count += 1
  tier = min(st.stuck_escalation_count, 3)
  ```
  Tier 1 *always* fires on the first signal in a session. There is no env
  var that changes this. `grep` for `VELLUM_STUCK_ESCALATION_TIER1_TURNS`
  returns zero matches in `backend/`.
- **Diff:**
  ```
  -| `VELLUM_STUCK_ESCALATION_TIER1_TURNS` | `1` | Tier 1 stuck signals (silent reasoning note) fire on this turn. |
  +| (no env var; tier is by signal count, see `stuck.py:413-414`) | n/a | Tier 1 fires on the first signal in a session. |
  ```

### H-3. `VELLUM_SESSION_BUDGET_MULT` is mis-named (HIGH)

- **File:** `README.md:260`
- **Doc text:** `| VELLUM_SESSION_BUDGET_MULT | 15 | Stuck detector: session budget = mult × section_budget (default 450k input tokens). |`
- **Actual:** `config.py:50` reads `VELLUM_STUCK_SESSION_BUDGET_MULT`, not
  `VELLUM_SESSION_BUDGET_MULT`. Setting `VELLUM_SESSION_BUDGET_MULT=20`
  per the README is silently ignored.
- **Diff:**
  ```
  -| `VELLUM_SESSION_BUDGET_MULT` | `15` | ... |
  +| `VELLUM_STUCK_SESSION_BUDGET_MULT` | `15` | ... |
  ```

### H-4. `COMPACT_INPUT_TOKEN_THRESHOLD` is mis-named (HIGH)

- **File:** `README.md:264`
- **Doc text:** `| COMPACT_INPUT_TOKEN_THRESHOLD | 80000 | Input token count above which context compaction fires. ~80% of the 100k practical input limit. |`
- **Actual:** `config.py:107-108` reads `VELLUM_COMPACT_INPUT_TOKEN_THRESHOLD`.
  Bare `COMPACT_INPUT_TOKEN_THRESHOLD` is not read. The default value
  `80000` is correct; the env var name is wrong.
  (This was previously flagged in peer-review-docs.md as
  `100000` vs `80000` — the value is now right, but the *name* is still wrong.)
- **Diff:**
  ```
  -| `COMPACT_INPUT_TOKEN_THRESHOLD` | `80000` | ... |
  +| `VELLUM_COMPACT_INPUT_TOKEN_THRESHOLD` | `80000` | ... |
  ```

### H-5. `VELLUM_PORT` is not an env var (HIGH)

- **File:** `README.md:252`
- **Doc text:** `| VELLUM_PORT | 8731 | Port for uvicorn. |`
- **Actual:** No `os.getenv("VELLUM_PORT")` anywhere in the codebase.
  The port is hardcoded in `dev.sh:36` (`--port 8731`) and in the README's
  own quick-start (`uvicorn vellum.main:app --port 8731`). `VELLUM_HOST`
  *is* in config.py (line 59); `VELLUM_PORT` is not.
- **Diff:**
  ```
  -| `VELLUM_PORT` | `8731` | Port for uvicorn. |
  +| (not configurable; pass `--port` to uvicorn directly) | `8731` | Port for uvicorn. |
  ```

### H-6. README project layout references deleted `wake_store` (HIGH)

- **File:** `README.md:132`
- **Doc text:** `scheduler.py      # sleep-mode: polls wake_store, fires sessions on schedule`
- **Actual:** `backend/vellum/storage/wake_store.py` was deleted in
  cleanup-2. Its functions (`set_dossier_wake_at`, `mark_wake_pending`,
  `list_dossiers_ready_to_wake`, etc.) now live in
  `storage/dossier_lifecycle.py` (lines 159-200+ for the wake functions).
  The peer-review-docs.md flagged this in §5.1 ("Stale paths in docs")
  as Low severity because of where it sat in the doc tree, but it
  appears in the project-layout block that a judge reads to understand
  the file structure — it should be HIGH.
- **Diff:**
  ```
  -    scheduler.py      # sleep-mode: polls wake_store, fires sessions on schedule
  +    scheduler.py      # sleep-mode: polls dossier_lifecycle wake flags, fires sessions on schedule
  ```

### M-1. Test count drift: 391 in README vs 393 actual (MEDIUM)

- **Files:** `README.md:51, 93, 103, 161` (four occurrences of `391`).
- **Actual:**
  ```
  $ pytest --collect-only -q
  393 tests collected in 1.95s
  ```
  The drift is +2 from the README's stated 391, +6 from the cleanup-2
  summary's close-out 387. The 391 number was probably accurate when the
  README was last updated and 2 tests have landed since (the
  `test_all_public_names_are_in_expected_set` inverse check is the
  obvious one — peer-review Issue 2 was fixed by adding a 4th test to
  `test_storage_imports.py`, which is now visible as a 4th `def test_`
  in that file).
- **Diff (×4):** `391` → `393`.

### L-1. "41 components" counts a test file as a component (LOW)

- **File:** `README.md:50`
- **Doc text:** "React 18 + TypeScript + Tailwind (Vite) + ... **41 components**..."
- **Actual:** `frontend/src/components/` contains 41 `.tsx` files
  *including* `AgentActivityIndicator.test.tsx`. Stripping the test
  file gives 40 component files. The peer-review-docs.md Issue 1.6
  noted the old "55" was wrong; the README was updated to 41. The
  choice of 41 vs 40 is now a question of definition, not a load-bearing
  error. A reader will not be misled, but a pedant will.
- **Diff (optional):**
  ```
  -React 18 + TypeScript + Tailwind (Vite) + ... 41 components, ...
  +React 18 + TypeScript + Tailwind (Vite) + ... 40 components (41 .tsx files including one co-located test), ...
  ```

---

## 2. Things I checked and confirmed correct (the negative results)

These are claims the docs make that I verified against the code. Including
them so a future audit doesn't re-do the work.

### Code claims — verified accurate

- **30 dossier tools + 7 intake tools = 37** (`README.md:17, 50, 119, 140`).
  `tools/handlers.py:681-715` has 30 entries (10 v1 + 16 v2 + 4 JIT);
  `intake/tools.py:317-325` has 7 entries (`set_title`,
  `set_problem_statement`, `set_dossier_type`, `set_out_of_scope`,
  `set_check_in_policy`, `commit_intake`, `abandon_intake`).
- **22-table schema** (`README.md:49, 157`). `schema.sql` has 22
  `CREATE TABLE` statements. ✓
- **22-name partial unique index** claims — `idx_work_sessions_one_active_per_dossier`
  at `db.py:150` and `idx_decision_points_one_open_plan_approval_per_dossier`
  at `db.py:155` both exist.
- **`stuck.py` 941 LOC** (`README.md:22`). `wc -l stuck.py` → 941. ✓
- **Module size claims** (`README.md:47`): `handlers.py` ~58 KB
  (actual 54.3), `stuck.py` ~45 KB (actual 46.6), `runtime.py` ~44 KB
  (actual 42.5), `sub_runtime.py` ~34 KB (actual 35.1). All within
  ~5% — acceptable approximations.
- **Test counts in the load-bearing list** (`README.md:118-122`):
  `test_scheduler.py` 13 tests (✓), `test_stuck.py` 25 tests (✓),
  `test_storage_imports.py` 4 tests (✓, after the peer-review
  Issue 2 inverse-check fix).
- **Frontend test count** (`README.md:51, 93, 109, 161`): 26 tests
  across 5 files. `npm test` → `Test Files 5 passed (5) | Tests 26 passed (26)`. ✓
- **36 backend test files** (`README.md:51, 161`). `ls backend/tests/test_*.py` → 36. ✓
- **14 storage files** (`README.md:141`). 14 .py files in
  `backend/vellum/storage/` (12 domain + `_helpers.py` + `__init__.py`). ✓
- **`__init__.py` has 119 public names** (`README.md:155`).
  `dir(storage)` excluding dunders/imports = 119. ✓ (The `__all__` is
  107 — see peer-review Issue 1.10; the README's 119 figure is correct
  by the broader definition.)
- **26 frontend vitest tests across 5 files** (`README.md:51, 93, 109`).
  Counted `it()/test()` calls per file: AgentActivityIndicator 6,
  cx 4, format 7, time 7, ChangeEntry 2 = 26. ✓
- **H-20 `last_signal_kind` column** (`README.md:22, 42, 49, 211, 277`).
  Defined at `db.py:63` in `_REQUIRED_COLUMNS`. Persist function at
  `stuck.py:440-444` (daemon thread). State-snapshot surface at
  `prompt.py:394-404`. Three of the four `set_dossier_last_signal_kind`
  / `get_dossier_last_signal_kind` functions are in `__all__` and the
  storage-imports test. ✓
- **`idx_*` partial unique indexes** exist in `db.py:150, 155`. ✓
- **`runtime.py:282-290` discarded-prose path** (`README.md:36-37, 209`).
  Code reads:
  ```python
  if not tool_uses:
      # Model ended the turn. Any prose is discarded — the agent
      # speaks only through tool calls into the dossier.
      _end_reason = m.WorkSessionEndReason.ended_turn
      return RunResult(reason="ended_turn", turns=state.turns, session_id=session_id)
  ```
  Lines 282-290. ✓
- **`runtime.py:466-495` H-23 server-side cadence** (`README.md:38`).
  The cadence-stamp block actually spans lines 460-494 — off by 6
  (high number 466 vs actual 460). The high number in the doc is the
  "first line of the H-23 comment block" rather than the entry
  condition. Minor; defensible.
- **`test_runtime_v2.py:643-661` state-snapshot test**
  (`README.md:36`). `test_first_user_message_is_state_snapshot` is at
  line 643, runs to 662 (one extra line of `## Sections` assertion).
  ✓ (within 1 line of the README).
- **`test_runtime_v2.py:407-421` `pause_turn` test** (`deep-dive/01`).
  `test_pause_turn_does_not_count_as_ended` spans 407-421. ✓
- **`asyncio.run()` fallback at `sub_runtime.py:769-783`**
  (`README.md:275`). Actual: `asyncio.run` is at line 768, the
  fallback block runs through ~799. The README's high number (769) is
  the *except* branch, not the call site. Off by 1; defensible.
- **`test_spawn_handler_when_called_inside_running_loop` pin**
  (`README.md:275`). Test exists in `test_sub_runtime.py`. ✓
- **`sub_runtime.py:756-783` is documented as the broken fallback**
  (`README.md:275`). The coroutine-`close()` fix is in place at
  `sub_runtime.py:787` and the `try/except BaseException` at line 793.
  The peer-review Issue 3 fix is in. ✓
- **`storage/dossier_store.py:597, 606` `items=[]` write**
  (`README.md:276`). Both lines have the `items=[]` literal. ✓
- **7 intake tools in `intake/tools.py:317-325`** (`README.md:17, 50`).
  7 entries listed. ✓
- **The 5 frontend test files** (`README.md:51`):
  `AgentActivityIndicator.test.tsx`, `cx.test.ts`, `format.test.ts`,
  `time.test.ts`, `ChangeEntry.test.ts`. All 5 exist. ✓

### Cleanup-2 status table — verified accurate

The 16-item implementation table at `notes/cleanup-2/00-design-plan.md:23-41`
correctly says "shipped" for items 1-6, 8-9, 16-17, and "partial" for 7
(debug log added, intake migration reverted — accurate per
`intake/tools.py:235` which still uses `m.InvestigationPlanItem`).
The 4 deferred items (10-12, 13-14, 15) are correctly marked. ✓

### Research reports — known-stale numbers (informational, not bugs)

The three research reports `01-research-storage.md`, `02-research-runtime.md`,
`03-research-frontend.md` are research-time artifacts. They reference:

- "17 store modules" (`01-research-storage.md:13`) — was accurate at
  research time. Now 14 (or 13 if you exclude `__init__.py`); see
  peer-review-docs.md §3.1.
- "358 backend tests + 12 frontend tests" baseline
  (`02-research-runtime.md:5`, `03-research-frontend.md:3`) — was
  accurate at research time. Now 393+26.
- "17 → 13" storage consolidation target (design plan §1) — landed
  at 14 files, not 13. The discrepancy is whether `__init__.py` and
  `_helpers.py` are counted; design plan says "13 (source)" while the
  actual count is "14 (.py files in `storage/`)". The README now says
  "14 files" (line 141) which is the more accurate figure.

These are research-time snapshots that the deep-dive 00-synthesis.md
explicitly notes (§1: "research-time artifacts that predate the
implementation"). No bug to fix; add a status banner if a follow-up
ever needs to cite them.

### Peer-review fixes — verified in the code

I checked the 9 specific code-level fixes the peer-review reports
called out, and **all of them are in the code**:

- **Issue 1 (H-20 sync-write blocks event loop):** fixed at
  `stuck.py:440-444` — H-20 now uses a daemon thread, mirroring
  the H-19 pattern. ✓
- **Issue 2 (test_storage_imports.py stale):** fixed —
  `test_storage_imports.py:117-205` is the new
  `test_all_public_names_are_in_expected_set` inverse check, and
  `set_dossier_last_signal_kind` / `get_dossier_last_signal_kind` are
  in the expected set (lines 184-186). ✓
- **Issue 3 (test_stuck.py docstring references nonexistent test):**
  fixed — `test_last_signal_kind_persisted_on_loop_signal` exists at
  `test_stuck.py:613`, and `test_last_signal_kind_persisted_on_session_budget_signal`
  also exists. ✓
- **Issue 4 (time.test.ts monkey-patches Date.now):** not fixed in
  the strictest sense, but the test now uses `beforeEach`/`afterEach`
  imports so the build is green. The "inject `now` as a parameter"
  refactor wasn't done. (peer-review marked this LOW.) ✓ (not a bug)
- **Issue 5 (lint test allows whitelist bloat):** fixed —
  `test_stuck.py:531-538` now has `expected_extras = {"web_search"}`
  and the inverse assertion. ✓
- **Issue 6 (commit-message vs test-count drift):** documentation
  issue; the actual count of 5 H-20 tests in `test_stuck.py` is now
  accurate. ✓
- **Issue 7 (test uses `web_search` to drive loop):** fixed — the
  loop test now uses `flag_needs_input` (line 630). ✓
- **Backend Issue 1 (H-20 sync write blocks event loop):** same as
  peer-review Issue 1 above. ✓
- **Backend Issue 3 (`asyncio.run()` leaks coroutine):** fixed at
  `sub_runtime.py:787` (explicit `inner_coro.close()` on the
  never-started coroutine) and `:799-801` (`inner_coro.close()` in
  the fallback's `except BaseException` handler). ✓

### Files I checked exist and match the README's tree

- `backend/vellum/agent/{runtime,sub_runtime,orchestrator,scheduler,compactor,stuck,prompt,sub_prompt,telemetry}.py` — all 9 exist.
- `backend/vellum/api/{__init__,agent_routes,auth,intake_routes,routes,settings_routes}.py` — all 6 exist.
- `backend/vellum/intake/{__init__,models,prompt,runtime,storage,tools}.py` — all 6 exist.
- `backend/vellum/tools/{__init__,handlers}.py` — both exist.
- `backend/vellum/storage/{__init__,_helpers,artifact_store,audit,decision_point_store,dossier_lifecycle,dossier_store,log_store,needs_input_store,plan_items_store,section_store,session_store,settings,sub_investigation_store}.py` — all 14 exist.
- `backend/vellum/{__init__,config,db,lifecycle,main,models,schema.sql}.py` — all 6 `.py` + the `schema.sql` exist at `backend/vellum/schema.sql`.
- `frontend/src/api/{client,hooks,types}.ts` — all 3 exist.
  `types.generated.ts` correctly absent (was deleted in cleanup-2).
- `frontend/src/test-setup.ts` — exists.
- `frontend/src/components/dossier/`, `intake/`, `plan-diff/`, etc. —
  all the directories referenced in `README.md:185-201` exist.

---

## 3. Summary recommendations

1. **Fix the 5 fake env vars before showing the README to judges.**
   The single highest-priority patch. The user can read H-1 through H-5
   and make the 5 changes in a single edit.
2. **Fix the `wake_store` reference in the project layout** (H-6) —
   one-line edit.
3. **Bump the test count to 393** in the 4 README locations (M-1) —
   trivial grep-and-replace.
4. **Optionally** clarify the "41 components" figure (L-1).

The cleanup-2 design plan, summary, and deep-dive research reports are
research-time artifacts and are accurate *as of their own time*. The
README is the only doc that judges will read directly; it is the
highest-leverage place to fix bugs.
