# Peer Review — Cleanup-2 Backend Changes

**Scope reviewed:** commits `77d962d` (storage consolidation), `cdf7049` (H-20 last_signal_kind), `7cc3084` (test_scheduler.py), `ba65ad2` (test_sub_runtime), `6257643` (_STUCK_EXEMPT_TOOLS), `30172da` (H-21 InvestigationPlanItem), plus the three frontend-touching commits `d2325f9`/`5cc1003`/`e830acb` and the most recent `aad2193` (Button/SectionCard wiring).
**Method:** Read each commit, the current state of every file it touched, and the related tests. Ran the affected test files individually and as a full suite (387 pass, 2 skip, 2 RuntimeWarning).

Overall, the changes are high-quality: the storage consolidation is clean, the new tests pin load-bearing contracts, and the cx refactor is a strict superset. The issues below are real but mostly small. The single most important finding is that the H-20 sync write can block the event loop and the new storage helpers are missing from `__all__` — both are easy fixes with clear value.

---

## 1. H-20 sync write blocks the event loop (high)

**File:** `backend/vellum/agent/stuck.py:416-422`
```python
try:
    storage.set_dossier_last_signal_kind(
        dossier_id_for_persist, signal.kind
    )
except Exception:
    pass
```

`storage.set_dossier_last_signal_kind` opens a SQLite connection and runs a synchronous `UPDATE` (`backend/vellum/storage/dossier_lifecycle.py:159-170`). When `_assign_tier_and_emit` is called from the runtime's event loop (which is the production path: `check_session_budget` / `check_section_budget` / `check_revision_stall` are called from the agent loop), this write blocks the loop for the duration of the SQLite round-trip.

The accompanying comment is misleading:
> "Sync (a single UPDATE is microseconds; we already released _STATE_LOCK so no coroutine is blocked on the write)."

The `_STATE_LOCK` release is about the in-memory state lock, not the event loop. A single `UPDATE` is microseconds, but a 30-call session that trips `same_tool_no_progress` repeatedly will queue 30 synchronous DB round-trips on the event loop thread. The same module's H-19 escalation-count write correctly uses `threading.Thread(target=_persist_escalation_count, …, daemon=True).start()` (line 403-407) — H-20 should mirror that pattern.

**Fix:** either reuse the daemon thread pattern (start a `threading.Thread` that calls `storage.set_dossier_last_signal_kind` with its own try/except) or, if keeping the sync write for ordering reasons, guard the call with `asyncio.get_running_loop()` and dispatch via `loop.run_in_executor` to match the H-08 philosophy the file already documents (see comment at lines 423-429).

---

## 2. `set_dossier_last_signal_kind` / `get_dossier_last_signal_kind` missing from `storage.__all__` (high)

**Files:**
- `backend/vellum/storage/__init__.py:145-146` — the new functions are *imported* here, but
- `backend/vellum/storage/__init__.py:180-302` — the `__all__` list does **not** include them
- `backend/tests/test_storage_imports.py:27-90` — the test's `expected` set mirrors `__all__` and is also missing them

This violates the cleanup-2 design statement:
> "The flat storage.X namespace is preserved — every name in `__all__` still imports."

The new helpers are reachable as `storage.set_dossier_last_signal_kind` (because they're imported), so this is not a *broken* surface, but it is a contract violation. The first time someone runs `pytest tests/test_storage_imports.py -v` and sees 105 names, then runs `dir(storage)` and sees 107 (the two extras being these), they'll be confused. Worse, a future cleanup that prunes `__init__.py` imports could remove them, and nothing would catch it.

The `test_storage_imports.py` test asserts the *forward* direction (every name in `expected` is in `storage`) but the function under test — "the public surface is preserved" — is not symmetric. It needs an inverse assertion:

```python
extras = (set(dir(storage)) - expected) - {"_helpers", "_dt", ...}
assert not extras, f"new public storage functions not in expected: {sorted(extras)}"
```

**Fix:** add `"set_dossier_last_signal_kind"` and `"get_dossier_last_signal_kind"` to both `__all__` (in the Wake section) and the test's `expected` set; then add a guard test that fails when a new public function is added to the imports without being added to the expected set.

---

## 3. `asyncio.run()` fallback leaks the coroutine (high)

**File:** `backend/vellum/agent/sub_runtime.py:769-781`
```python
if "asyncio.run() cannot be called" in str(exc):
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            run_sub_investigation(...)
        )
    finally:
        loop.close()
else:
    raise
```

When the outer loop is already running, `loop.run_until_complete(run_sub_investigation(...))` raises "Cannot run the event loop while another event loop is running". The `run_until_complete` does **not** close the coroutine in that case — it propagates the `RuntimeError` and the coroutine object becomes garbage. CPython's `_warn_unawaited_coroutine` fires:

```
RuntimeWarning: coroutine 'run_sub_investigation' was never awaited
```

I confirmed this with `pytest -W error::RuntimeWarning` — the warning is raised twice (once for the inner `asyncio.run` attempt, once for the fallback's `run_until_complete`), and the test only happens to pass because the conftest doesn't promote warnings to errors. The commit message for `ba65ad2` acknowledges the fallback is broken, but the warning is a real defect, not just a cosmetic one — in a long-running process, accumulating un-awaited coroutines that hold references to local frames is a memory pressure risk.

**Fix (in the test pin):** before `run_until_complete`, the fallback should wrap the coroutine in a `try/finally` that calls `coro.close()` on failure paths. Or, more pragmatically, the broken-fallback path should catch the second `RuntimeError` and call `coro.close()` before re-raising so the outer `except Exception` block at line 784 receives a clean state.

---

## 4. No test for the `build_state_snapshot` H-20 block (medium)

**File:** `backend/vellum/agent/prompt.py:394-404`
```python
if d.last_signal_kind:
    lines.append("## Last stuck signal (last session)")
    lines.append(
        f"kind: {d.last_signal_kind} — last session ended with this stuck "
        ...
    )
```

The research notes (`notes/cleanup-2/02-research-runtime.md:235-237`) called for a test `test_last_signal_kind_loads_into_state_snapshot`. It was not added. I confirmed by hand-running `build_state_snapshot` on a dossier with `last_signal_kind="loop"` — the block renders correctly, but there's no automated test guarding it. If someone refactors `build_state_snapshot` and accidentally drops the block, no test fails. The block is also the user-visible payoff of the entire H-20 column; an untested surface is a maintenance liability.

**Fix:** add a test in `test_jit_loading.py` (or a new `test_h20_snapshot.py`):
```python
def test_last_signal_kind_block_in_snapshot(fresh_db):
    dossier = storage.create_dossier(...)
    storage.set_dossier_last_signal_kind(dossier.id, "loop")
    full = storage.get_dossier_full(dossier.id)
    snapshot = prompt.build_state_snapshot(full)
    assert "Last stuck signal" in snapshot
    assert "kind: loop" in snapshot
    assert "declare_stuck" in snapshot  # the action recommendation
```

---

## 5. Lint test `test_progress_whitelist_covers_all_handlers` allows whitelist bloat (medium)

**File:** `backend/tests/test_stuck.py:492-518`

The test asserts `registered - covered == empty`, but does **not** assert the symmetric property. The current `covered - registered` is exactly `{"web_search"}` (verified) — the server-side tool that lives in `_EXEMPT_FROM_NO_PROGRESS` without being in `HANDLERS`. A typo in a whitelist entry — e.g. `"add_artifac"` instead of `"add_artifact"` — would:
- Be picked up by `if tool_name in _STUCK_EXEMPT_TOOLS` at runtime, but the typo never matches, so the tool is silently treated as progress.
- Not be caught by the existing lint.

I checked the actual sets: `_PROGRESS_TOOL_NAMES ∪ _PROGRESS_MUTATION_TOOL_NAMES ∪ _EXEMPT_FROM_LOOP ∪ _EXEMPT_FROM_NO_PROGRESS ∪ _STUCK_EXEMPT_TOOLS ∪ _UPSERT_TOOL_NAMES` minus registered HANDLERS is `{"web_search"}`. That's the only legitimate extra.

**Fix:** add `expected_extras = {"web_search"}` and assert `covered - registered == expected_extras`. This pins the "web_search is the only server-side tool we whitelist" assumption, and a future typo fails the test.

---

## 6. Commit message vs. test count drift (low)

**File:** `cdf7049` commit message:
> "3 new tests in test_stuck.py: storage round-trip, Dossier Pydantic surface, end-to-end through `_assign_tier_and_emit`."

The actual file has **5** new H-20 tests:
- `test_last_signal_kind_visible_after_assign_tier_and_emit` (line 544)
- `test_last_signal_kind_persisted_on_loop_signal` (line 574)
- `test_last_signal_kind_persisted_on_session_budget_signal` (line 599)
- `test_last_signal_kind_null_for_clean_dossier` (line 624)
- `test_last_signal_kind_visible_in_dossier_pydantic` (line 638)

The test that I initially read into the issue tracker as "missing" turned out to exist (my first read was truncated at line 603). The docstring in `test_last_signal_kind_visible_after_assign_tier_and_emit` (lines 549-552) correctly references the two companion tests — that part is fine. The only real issue is that the commit body undercounts the work, which is mildly misleading if someone is reading the commit log.

---

## 7. `test_last_signal_kind_persisted_on_loop_signal` uses `web_search` to drive the loop (low)

**File:** `backend/tests/test_stuck.py:586-589`
```python
sig = stuck.record_tool_call(
    session_id, "web_search", {"q": "loop kind test"}
)
```

`web_search` is in `_EXEMPT_FROM_NO_PROGRESS` (line 152) but **not** in `_EXEMPT_FROM_LOOP`. The exact-args loop detector therefore fires correctly on the 11th call (default `LOOP_DETECTION_THRESHOLD=10`). The test works today.

The brittleness: if a future maintainer moves `web_search` into `_EXEMPT_FROM_LOOP` (a reasonable-looking refactor, since it makes 30-call research bursts quieter), the test will silently fail to fire any signal — `sig` stays `None`, the assertion `assert sig is not None` fails. The test won't *crash* from a wrong reason, but the connection to the loop kind will be lost.

**Fix:** use a tool not in any whitelist (e.g. `flag_needs_input`) for the loop-kind test, or pin a comment explaining the `web_search` choice.

---

## 8. No test for the `_REQUIRED_COLUMNS` ratchet (low)

**File:** `backend/vellum/db.py:17-64`

The ratchet is the load-bearing mechanism for every additive column since day 1. There is no test that:
- Confirms a new entry actually runs `ALTER TABLE` on a fresh DB
- Confirms `_ensure_columns` is idempotent (re-running it on a DB that already has the column is a no-op)
- Confirms the schema in `schema.sql` matches `_REQUIRED_COLUMNS` (drift here means fresh DBs work but upgraded DBs don't, or vice versa)

A trivial test would catch a future maintainer who drops a tuple from `_REQUIRED_COLUMNS` thinking the schema.sql already covers it (or vice versa).

**Fix:** add a test in a new `tests/test_db_migrations.py` that:
1. Runs `init_db` on a fresh DB
2. Asserts every column in `_REQUIRED_COLUMNS` exists in the right table
3. Runs `init_db` again on the same DB and asserts no error
4. Asserts that `schema.sql` includes every column from `_REQUIRED_COLUMNS` (string-grep)

---

## 9. `_coerce_legacy_items` lazy `import logging` (low)

**File:** `backend/vellum/models.py:597-601`
```python
if n_legacy:
    import logging
    logging.getLogger(__name__).debug(
        "plan_update: coerced %d legacy InvestigationPlanItem -> PlanItem",
        n_legacy,
    )
```

The `import logging` is inside the validator. It runs every time `_coerce_legacy_items` is called and `n_legacy > 0`. The `import` is cached by `sys.modules` so the cost is small (a dict lookup), but it's stylistically inconsistent — every other module-level `logger` in the codebase is at the top of the file. The other lazy import in this codebase (`_emit_investigation_log` in `stuck.py:336`) is justified because the module is at a top-of-tree position with explicit one-way-dependency comments. This one has no such justification.

**Fix:** move `import logging` to the top of `models.py` and add a module-level `logger = logging.getLogger(__name__)`.

---

## 10. No test for `revision_stall` and `same_tool_no_progress` kind writes (low)

**File:** `backend/tests/test_stuck.py:574-621`

The two companion tests for `loop` and `session_budget` mirror the production paths through `record_tool_call` and `check_session_budget`. The other two signal kinds (`revision_stall`, `same_tool_no_progress`) are also routed through `_assign_tier_and_emit` but are not exercised for H-20. Since both routes go through the same `storage.set_dossier_last_signal_kind(signal.kind)` call, the coverage gap is mostly *defensive* — the test would fail only if `signal.kind` were wrong for those paths. The risk is low but the test cost is small.

**Fix:** add two short tests that drive `record_tool_call` until `check_revision_stall` or `same_tool_no_progress` returns a signal, then assert `last_signal_kind` is the expected value.

---

## 11. `dossier_lifecycle.py` `set_dossier_last_signal_kind` doesn't touch `updated_at` (informational)

**File:** `backend/vellum/storage/dossier_lifecycle.py:159-170`

The function writes `last_signal_kind` but not `dossiers.updated_at`. This is consistent with `_persist_escalation_count` (also no `updated_at` touch), and likely intentional — stuck signals are noise that shouldn't drive the dossier list's sort order. The lack of a docstring note explaining *why* makes the contract implicit.

**Fix (optional):** add a one-line comment in `set_dossier_last_signal_kind` and `_persist_escalation_count` saying "intentionally does not touch `updated_at`; stuck signals are not user-visible state changes for the dossier list."

---

## Notes on items NOT flagged

- The 7→3 storage consolidation is mechanically clean. The flat `storage.X` namespace is preserved (verified by running `dir(storage)` against the new files and matching every name from the old `__all__`). The 3 new modules' docstrings accurately describe the merge rationale.
- The `_STUCK_EXEMPT_TOOLS` set and the two lint tests are well-targeted. Every HANDLER is in at least one set (`registered - covered == empty`), and the `_PROGRESS_MUTATION_TOOL_NAMES ⊂ _PROGRESS_TOOL_NAMES` test is correct.
- The `cx` refactor is a strict superset: `cx` in `utils/cx.ts` accepts `null` in addition to `false/undefined/empty`, so the three sites (Button, Card, Pill) lose no capability.
- The `test_scheduler.py` 13 tests cover the load-bearing contention path (`scheduler.py:202-216`) with explicit monkeypatched `ORCHESTRATOR.start` raising `AgentAlreadyRunning`, `AgentCapacityExceeded`, and a generic `RuntimeError` — exactly the three branches. The pre-session cleanup invariant is also pinned.
- H-21's revert-to-`InvestigationPlanItem` is well-reasoned: the commit message explains the `plan_error` contract that test_intake pins would be silently lost if `PlanItem` (with its permissive defaults) were used. The added `logger.debug` is the right signal.
- The `d2325f9` `cx` dedup is clean; the inline definitions were byte-identical to the local-cx pattern.
- The day-N renames preserve blame (`git mv`) and update docstrings; the day-N prose stays at the top of each file as a development-log reference. The `test_day2_smoke_auto_resolve.py` exception is correctly explained in the commit message.
