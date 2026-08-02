# Backend bug-check — Vellum (post-cleanup-2, post-peer-review)

**Date:** 2026-08
**Scope:** backend runtime only. Files in `backend/vellum/agent/*`, `backend/vellum/intake/*`, `backend/vellum/api/*`, `backend/vellum/tools/handlers.py`, `backend/vellum/lifecycle.py`, `backend/vellum/db.py`, `backend/vellum/storage/*`.
**Method:** end-to-end read of every file in scope, plus a `pytest -q` baseline run.

## Headline

**Baseline:** `391 passed, 2 skipped, 1 warning in 63.47s` — matches the expected
391 + 2. No flakes on the one re-run I did.

**Bugs found:** 3 (1 HIGH/MED-leaning, 2 MED). Plus 3 LOW observations worth
fixing but not urgent. The peer-review doc's findings are excluded by the
brief.

| # | Severity | One-line | Where |
|---|----------|----------|-------|
| 1 | **MED**  | Handler success + audit-record failure mis-records `is_error=True`, hiding the real side-effect and causing duplicate writes on replay | `agent/runtime.py:610-632` |
| 2 | **MED**  | `_resolve_session` runs *outside* the `try/except`; a raise orphans the route-created `work_session` and the next user action 409s forever | `agent/runtime.py:135` (call site) + the three route handlers in `api/agent_routes.py` |
| 3 | **MED**  | Idem shim records `tool_invocations` *after* the handler runs; a crash in the gap re-executes non-idempotent handlers on the next session | `agent/runtime.py:577-604` |
| 4 | LOW  | Daemon-thread persistence for `stuck_escalation_count` / `last_signal_kind` is lost on process exit within the brief window | `agent/stuck.py:427-444` |
| 5 | LOW  | `_surface_stuck` / `_surface_budget_signal` call `handlers.dispatch` synchronously on the event loop instead of `asyncio.to_thread` | `agent/runtime.py:680-740` |
| 6 | LOW  | `resume` route lacks the orphan-cleanup the `start` route has — a crashed-without-restart dossier 409s the user | `api/agent_routes.py:197-208` vs `:85-91` |

**What I could not verify:**

- I did not run the orchestrator under real concurrent dossier load. The
  single-process invariants (`_lock`, `_tasks`, `_STATE_LOCK`) are all
  textually correct, but I cannot prove no microsecond race is left without
  a stress harness.
- I did not exercise the `sub_runtime` fallback under the exact production
  threading model. The fallback is textually correct (closes the
  never-awaited coroutine, runs a fresh one in `new_event_loop`/`run_until_complete`,
  closes the loop) but I cannot run the live deployment to confirm.
- Migration runner concurrency I verified by *reading*, not by *running two
  processes*. The conclusions are in §"Things I checked and did NOT find".

---

## 1. MED — Handler success + audit-record failure mis-records is_error

**File:** `backend/vellum/agent/runtime.py:577-632` (`_dispatch_client_tool`)

**The bug.** The idem shim and the success path share a single `try/except
Exception` that conflates two failures:

```python
try:
    result = await asyncio.to_thread(handlers.dispatch, ...)   # handler runs
    result_json = _coerce_tool_result(result)
    await asyncio.to_thread(
        storage.record_tool_invocation,                        # audit row written
        tool_use_id, self.dossier_id, tool_name,
        _hash_tool_input(tool_input), result_json, False,
    )
    return {"type": "tool_result", "tool_use_id": tool_use_id,
            "content": result_json}
except Exception as exc:
    err_content = f"{type(exc).__name__}: {exc}"
    try:
        await asyncio.to_thread(
            storage.record_tool_invocation,                    # ← records is_error=True
            tool_use_id, ..., err_content, True,
        )
    except Exception:
        pass
    return {"type": "tool_result", ..., "is_error": True}
```

If the handler succeeds, the dossier/section row is committed, and only
*then* the audit `INSERT OR IGNORE INTO tool_invocations` fails (disk
full, schema column added out-of-band, SQLite busy timeout, etc.), the
`except` block re-records the same `tool_use_id` with `is_error=True` and
the exception text as the result.

Two consequences:

1. The agent sees `is_error=True` with a string like `OperationalError:
   database is locked` and assumes the handler failed. It may retry, and
   for non-idempotent handlers (`add_artifact`, `flag_needs_input`,
   `flag_decision_point`, `append_reasoning`, `add_next_action`,
   `mark_ruled_out`, `set_next_action`, `log_source_consulted`,
   `mark_considered_and_rejected`, `add_artifact`, `add_decision_point`)
   the retry inserts a *second* row with a new id.
2. The next session's `get_tool_invocation` returns the synthetic error
   payload. Replay of that `tool_use_id` would surface the error result
   rather than re-run the handler — but if the agent doesn't trust the
   result, it issues a *new* `tool_use_id` and the same double-insert
   happens.

This is exactly the partial-replay risk the brief asks me to look at (point 8).
The idem shim's name implies it covers it, but it only covers "handler raised",
not "audit failed after handler succeeded". A code path that produces wrong
output (the agent now thinks the call failed when it didn't, and the dossier
gains duplicate rows) is the textbook definition of a MED bug.

**Reproduction sketch.** A trivial test that would catch it:

```python
async def test_handler_success_audit_failure():
    tool_id = "toolu_test_001"
    # Pre-insert nothing — first time we see this tool_id.
    # Force the SECOND `record_tool_invocation` call (the one inside `except`)
    # to raise, e.g. by patching storage.record_tool_invocation to:
    #   - return None the first call
    #   - raise sqlite3.OperationalError the second call
    #   - return None the third call
    # Then assert that the dossier has exactly one artifact row, and that the
    # returned tool_result's content reflects the actual successful handler
    # output, not the OperationalError string.
```

Without that monkeypatch, the existing tests can't see this because both
`to_thread` calls succeed.

**Suggested fix.** Split the `try/except` so the audit write is a separate
guarded step that doesn't poison the recorded result on its own failure:

```python
result = await asyncio.to_thread(handlers.dispatch, ...)
result_json = _coerce_tool_result(result)
# Audit write is best-effort and NEVER feeds back into the tool_result.
try:
    await asyncio.to_thread(storage.record_tool_invocation, ...,
                            result_json, False)
except Exception:
    logger.warning("tool_invocations audit write failed for %s",
                   tool_use_id, exc_info=True)
return {"type": "tool_result", "tool_use_id": tool_use_id,
        "content": result_json}
# Real handler errors go in their own try/except:
try:
    ...
except Exception as exc:
    err_content = f"{type(exc).__name__}: {exc}"
    try:
        await asyncio.to_thread(storage.record_tool_invocation, ...,
                                err_content, True)
    except Exception:
        pass
    return {"type": "tool_result", ..., "is_error": True,
            "content": err_content}
```

The audit write then has no effect on what the agent sees. The existing
"replay of an errored handler returns the recorded error" behavior stays,
but it's no longer triggered by audit-write failures.

---

## 2. MED — Orphan work_session when `_resolve_session` raises

**File:** `agent/runtime.py:135` (call site), `api/agent_routes.py:69-133, 168-270`

**The bug.** Look at the structure of `DossierAgent.run`:

```python
async def run(self, max_turns: int = 200) -> RunResult:
    from . import prompt as prompt_mod
    from . import stuck as stuck_mod

    session_id = self._resolve_session()       # ← outside the try/except
    stuck_mod.init_session(session_id, self.dossier_id)
    state = _LoopState()
    dossier = storage.get_dossier(self.dossier_id)
    if dossier is None:
        storage.end_work_session_with_reason(session_id, m.WorkSessionEndReason.error)
        return RunResult(reason="error", turns=0, session_id=session_id,
                         error=f"dossier {self.dossier_id} not found")
    system_prompt = prompt_mod.build_system_prompt(dossier)
    ...
    try:
        while state.turns < max_turns:
            ...
    except Exception as exc:
        _end_reason = m.WorkSessionEndReason.error
        return RunResult(reason="error", ...)
    finally:
        ...
        if _end_reason is not None:
            storage.end_work_session_with_reason(session_id, _end_reason)
        else:
            storage.end_work_session(session_id)
```

The `try/except` only wraps the *loop*. `_resolve_session()` (and the
`dossier is None` branch's storage call) sit *above* it. If
`_resolve_session` raises — which it can in three documented ways
(`RuntimeError: expected work_session ... not found`,
`... belongs to ...`, `... is already ended`) — the exception propagates
out of `run()` to the orchestrator's done-callback, which only logs it.

The route handler did the right thing pre-flight:

```python
# agent_routes.py start()
session = storage.start_work_session(
    dossier_id, trigger=m.WorkSessionTrigger.manual
)
# ... then:
try:
    return await ORCHESTRATOR.start(
        dossier_id, ..., expected_session_id=session.id)
except AgentAlreadyRunning:
    try: storage.end_work_session(session.id)
    except Exception: ...
    raise HTTPException(409, ...)
```

But if `_resolve_session` raises inside the agent, the route's
`except AgentAlreadyRunning` doesn't catch it (it's not an
`AgentAlreadyRunning` — it's a bare `RuntimeError`). The `try/except
Exception` at runtime.py:431 *would* catch it, but `_resolve_session` is
above that block, so it doesn't. The result:

1. The route created `session` (an active work_session).
2. The orchestrator started a task that called `agent.run()`.
3. `_resolve_session` raised, the task errored, the done-callback logged it.
4. The route handler never sees the failure.
5. The `session` row is left with `ended_at IS NULL`.

Now the user clicks Resume (or hits any code path that checks for an
active session). The `resume` route returns 409 because there's already
an active session — but the session the user "owns" was created by the
prior `start` call and points to a dead task. The only way out is a
process restart so `lifecycle.reconcile_at_startup` reaps it.

**Reproduction sketch.** Force `_resolve_session` to raise by passing an
`expected_session_id` whose row has `ended_at IS NOT NULL` (e.g. by
manually closing the session between the route's `start_work_session` and
the agent's first await). Or call `DossierAgent(dossier_id="...",
model=...)` with a `setattr(agent, "expected_session_id", "ws_does_not_exist")`
and call `.run()`. Then SELECT work_sessions WHERE ended_at IS NULL and
observe the leak.

**Suggested fix.** Move the entire body of `run()` into the `try/except`,
or — minimally — wrap the pre-loop block:

```python
async def run(self, max_turns: int = 200) -> RunResult:
    from . import prompt as prompt_mod
    from . import stuck as stuck_mod

    session_id: Optional[str] = None
    try:
        session_id = self._resolve_session()
        stuck_mod.init_session(session_id, self.dossier_id)
        ...
        try:
            while state.turns < max_turns: ...
        except Exception as exc:
            _end_reason = m.WorkSessionEndReason.error
            return RunResult(reason="error", ...)
    except Exception as exc:
        # _resolve_session or pre-loop storage failure.
        # The route may have created a session under expected_session_id;
        # close it if we can identify it.
        if session_id is None and getattr(self, "expected_session_id", None):
            try:
                storage.end_work_session_with_reason(
                    self.expected_session_id, m.WorkSessionEndReason.error)
            except Exception:
                pass
        _end_reason = m.WorkSessionEndReason.error
        return RunResult(reason="error", turns=0,
                         session_id=session_id or getattr(self, "expected_session_id", ""),
                         error=f"{type(exc).__name__}: {exc}")
    finally:
        # existing finally
        ...
```

This way the route's `expected_session_id` always gets closed with
`reason=error` even when `_resolve_session` raises, so the user can
recover without a process restart.

---

## 3. MED — Idem shim only covers a partial-replay window

**File:** `agent/runtime.py:577-604`

**The bug.** This is the same partial-replay concern from the brief, but
it's distinct from #1. The shim *design*:

```python
prior = await asyncio.to_thread(storage.get_tool_invocation, tool_use_id)
if prior is not None:
    return {...}                  # replay → return recorded result

try:
    result = await asyncio.to_thread(handlers.dispatch, ...)
    result_json = _coerce_tool_result(result)
    await asyncio.to_thread(storage.record_tool_invocation, ...,
                            result_json, False)   # ← audit AFTER handler
    return {...}
except Exception as exc:
    ...
```

The handler runs, makes its storage writes, commits, then the audit row
is written and committed. If the process crashes (or the audit
`to_thread` raises) *between* the handler commit and the audit commit, the
next session's `get_tool_invocation` returns None, the shim doesn't
short-circuit, the handler runs *again*.

For idempotent handlers (`upsert_section` with a `section_id`,
`update_section_state`, `update_artifact`, `update_debrief`,
`update_investigation_plan`, `mark_investigation_delivered`,
`mark_considered_and_rejected` is partially idempotent via the unique
constraint path) this is fine.

For non-idempotent handlers, it's a real production risk:
`add_artifact` creates a new `m.new_id("art")` row. `flag_needs_input`
creates a new `m.new_id("ni")` row. `flag_decision_point` and
`declare_stuck` (the v2 path) create a new `m.new_id("dp")` row plus a
`reasoning_trail` entry, plus a `change_log` row. `append_reasoning`
creates a new `m.new_id("rtr")` row. `add_next_action` creates a new
`m.new_id("act")` row + `change_log` row. `mark_ruled_out` creates a
new `m.new_id("ro")` row + `change_log` row. `log_source_consulted`
creates a new `m.new_id("ilg")` row.

The `_check_stuck` and `_surface_budget_signal` paths add another layer
of risk — they're called outside `_dispatch_client_tool` so they don't
even pass through the idem shim. A non-idempotent `append_reasoning`
invoked from `_surface_stuck` runs unguarded; the user-visible behavior
on a partial failure is a duplicate reasoning note.

The brief is right to flag this. The fix is non-trivial because it
requires either:
- An outbox pattern (record the *intent* to call, dispatch the handler,
  then mark the outbox row complete — and let the next session reconcile
  any unprocessed outbox rows), or
- A handler-level contract: "this handler is idempotent on `tool_use_id`
  + `input_hash`" and the storage layer dedupes on the pair, or
- An "idempotency_key" declared on the tool schema and used to gate the
  handler dispatch *before* the side effect runs.

The cheapest mitigation today is to surface the gap explicitly in the
handler registry (a `NON_IDEMPOTENT_HANDLERS` set) and have the runtime
pre-claim the audit row *before* the handler runs, on a "claim-then-do"
pattern:

```python
# Pre-claim with a sentinel result so the next session sees the call.
await asyncio.to_thread(
    storage.record_tool_invocation,
    tool_use_id, self.dossier_id, tool_name,
    _hash_tool_input(tool_input), "__pending__", False,
)
result = await asyncio.to_thread(handlers.dispatch, ...)
result_json = _coerce_tool_result(result)
await asyncio.to_thread(
    storage.update_tool_invocation_result,  # UPDATE the existing row
    tool_use_id, result_json, False,
)
```

If the process crashes between pre-claim and the handler, the next
session sees a `__pending__` result — and on replay can either skip the
call or re-run it, depending on a policy you define per tool. The brief
calls this out explicitly as point 8; the runtime today only catches the
"audit-write failed" case (and even that, wrongly — see bug #1), not the
"audit-write never reached" case.

---

## 4. LOW — Daemon-thread persistence loss on fast process exit

**File:** `agent/stuck.py:427-444`

**The bug.** Both `_persist_escalation_count` and
`_persist_last_signal_kind` are spawned as `daemon=True` threads. The
docstring even says "best-effort" — which is fine for transient DB
errors, but `daemon=True` means the process is allowed to exit *while
the thread is still in the SQLite round-trip*. On a normal shutdown
(FastAPI lifespan), the process usually has time. On a SIGKILL or a
keyboard-interrupt at the worst possible moment, the thread is killed
mid-write. The escalation counter has been incremented in memory and
not persisted; the next session sees the previous (lower) count and
resets the tier logic.

This is a real but low-impact bug. The visible effect: the user's stuck
counter occasionally goes "backwards" on a particularly unlucky
shutdown. No data loss in the strict sense; the dossier's
`stuck_escalation_count` column is just a heuristic.

**Suggested fix.** If correctness matters, persist *before* returning
the signal — but synchronously, on the event loop. The runtime can
`await asyncio.to_thread(...)` for the SQLite write and accept the
small latency hit. Or persist on every surfaced signal via
`loop.run_in_executor(...)` and ignore the daemon-thread machinery
entirely.

---

## 5. LOW — Stuck-detection handlers block the event loop

**File:** `agent/runtime.py:680-740` (`_surface_stuck` and
`_surface_budget_signal`)

**The bug.** These call `handlers.dispatch(...)` directly — no
`asyncio.to_thread` wrap. Each call writes to the
`reasoning_trail` / `decision_points` / `investigation_log` tables
synchronously. In a single-agent deployment this is invisible. With
`AGENT_MAX_CONCURRENT_RUNS` set to anything > 1, the agent that's mid-
turn on `upsert_section` (which *does* go through `to_thread`) yields
cleanly, but a stuck-tier write happening on the same loop at the same
moment stalls *every* other agent for the SQLite write duration.

`_dispatch_client_tool` already does the right thing with
`asyncio.to_thread`; the budget/stuck surface was just never updated
to match.

**Suggested fix.** Same pattern:

```python
def _surface_stuck(self, signal):
    ...
    try:
        await asyncio.to_thread(
            handlers.dispatch, self.dossier_id,
            "append_reasoning", {...},
        )
    except Exception:
        pass
```

These methods need to be `async def` and called with `await`, but
they're already inside `DossierAgent.run`'s loop body so the
`async`/`await` chain is in place.

---

## 6. LOW — `resume` route missing the orphan-cleanup the `start` route has

**File:** `api/agent_routes.py:85-91` (start) vs `:197-208` (resume)

**The bug.** The `start` route handles the case where there's an
active `work_session` left over from a crashed process but the
orchestrator has no live task for it:

```python
# start
active = storage.get_active_work_session(dossier_id)
if active is not None:
    if _orchestrator_running(dossier_id):
        raise HTTPException(409, "agent already running for this dossier")
    storage.end_work_session_with_reason(
        active.id, m.WorkSessionEndReason.crashed
    )
```

The `resume` route does not. It just 409s:

```python
# resume
active = storage.get_active_work_session(dossier_id)
if active is not None:
    return JSONResponse(
        status_code=409,
        content={"detail": "work_session already active for this dossier",
                 "dossier_id": dossier_id,
                 "active_work_session_id": active.id},
    )
```

So a user who resumes a dossier that the *process* is still alive in
but that no orchestrator task owns (this is the case any time
`_resolve_session` raises, per bug #2, or any time a task is GC'd
without going through `done_callback`) is stuck. They can't resume
without a process restart.

**Suggested fix.** Mirror the `start` route's logic in `resume`. The
behavior should be: if there's an active session but no live task, end
it with `reason=crashed` and proceed; if there's an active session AND
a live task, 409.

---

## Things I checked and did NOT find

These are the negative results that took real time to rule out, so I
want to record them explicitly. The brief flagged several; in all cases
the implementation is correct.

- **Migration runner concurrency (`db.py:_REQUIRED_COLUMNS`, point 7).**
  `init_db` is safe under two-process concurrent startup. `CREATE TABLE
  IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN` guarded by
  `_existing_columns` are individually idempotent. `_REQUIRED_INDICES`
  uses `IF NOT EXISTS`. `_backfill_decision_point_kinds` is a
  deterministic UPDATE that lands the same value. `_close_duplicate_*`
  are guarded by a `rn > 1` filter. `_migrate_plan_items` is gated by
  a `settings` sentinel and uses `INSERT OR IGNORE` /
  `INSERT OR REPLACE`. Two processes racing on first boot is fine; the
  WAL writer/reader split means the second process waits for the
  first's commit and then runs its own no-op migrations.

- **H-20 daemon-thread race for `last_signal_kind` (point 6).** The
  dossier_id is captured under `_STATE_LOCK` and read from
  `_state(session_id).dossier_id`, which is set in `init_session` and
  immutable for the session's life. Two consecutive signals from the
  same session spawn two concurrent threads that each do
  `UPDATE dossiers SET last_signal_kind = ? WHERE id = ?`; the second
  one's write may land first, but the comment at lines 432-439 already
  documents "Last write wins" as the intended semantic. The same
  applies to `_persist_escalation_count`, except that path uses a
  SQL-level relative increment (`stuck_escalation_count + 1`) so
  concurrent writes commute correctly.

- **H-20 read-back race in the same turn (point 6).** Not possible.
  The runtime reads `last_signal_kind` from `dossiers` in
  `prompt.build_state_snapshot` at the *start* of the *next* turn. The
  daemon thread writes it at the *end* of the current turn. The signal
  itself is consumed in-memory within the current turn. The two paths
  don't race.

- **`asyncio.run()` fallback in `sub_runtime.py:769-840` (point 5).**
  In production, the parent runtime calls `spawn_handler` via
  `asyncio.to_thread(handlers.dispatch, ...)` in
  `runtime.py:592-594`, so `spawn_handler` runs in a worker thread. In
  the worker thread there is no running event loop, so `asyncio.run`
  succeeds. The `RuntimeError: ... cannot be called from a running
  event loop` path is a defensive belt for a code path that isn't
  reachable in production. The fallback itself is correct:
  - the never-awaited `inner_coro` is `.close()`-d before building a
    fresh `fallback_coro`,
  - the new loop runs the coroutine with `run_until_complete`,
  - the `BaseException` branch closes the coroutine before re-raising,
  - the outer `finally` always closes the loop.
  The parent agent sees a structured dict (success result) or a
  structured dict with `error: "..."` and `terminated_without_completion:
  True` (failure path). The "string exception bubbles to the model"
  failure mode is not present.

- **TOCTOU in `start`/`resume` routes (point 3).** The route checks
  `get_active_work_session` before calling `start_work_session`, and
  `start_work_session` raises `ActiveWorkSessionExists` on race. The
  orchestrator's `_lock` serializes the per-dossier `_tasks`
  check-then-insert. So two near-simultaneous `start` requests for the
  same dossier get one success and one 409 (or one success and one
  `AgentAlreadyRunning` mapped to 409). No orphan sessions, no
  double-launched tasks.

- **`_dispatch_client_tool` idem shim on replays of the same `tool_use_id`.**
  When the prior result was successful and the idem shim returns it,
  the `is_error` flag propagates from `prior["is_error"]`. The
  `_extract_result_section_id` then reads the content and gets the
  real section id. So `self._last_section_id` updates correctly even
  on replay. (The idem-shim path does NOT pass through the catch-all
  `except`, so bug #1 doesn't apply to this branch.)

- **`_check_budget_signals` reading the budget cap.** `get_setting` may
  return a stored JSON string or a number; both are coerced via
  `float(...) or 0`. A non-numeric string raises ValueError; the
  outer `except Exception: return` swallows it. No bug.

- **Compactor's `_split_turns` correctness.** With
  `keep_recent_turns = 5` and the standard message shape
  (first user, then alternating assistant/user pairs), the split
  correctly keeps the most recent 5 turns and compacts the rest. The
  `messages[0]` anchor is preserved via the merge in
  `compact_messages`. The 2-consecutive-user-message failure mode is
  explicitly handled.

- **Work-session creation race in scheduler `_wake_one`.** The
  orchestrator's lock and the storage's `ActiveWorkSessionExists`
  exception provide the same TOCTOU protection as the route path.
  The "created session, can't start" cleanup at lines 218-228 of
  `scheduler.py` correctly ends the pre-created session when the
  orchestrator refuses the start.

- **Stuck `init_session` double-checked locking.** The fast-path
  check inside the lock (`if st.dossier_id is not None: return`) and
  the slow-path double-check (`if st.dossier_id is None: ...`) are
  correct. A concurrent `init_session("ws_X", "dossier_X")` and
  `init_session("ws_X", "dossier_Y")` would leave the first dossier
  bound and silently drop the second — but a session is supposed to
  be bound to one dossier, so this is the intended behavior.

- **`work_sessions` unique partial index and `decision_points`
  plan_approval unique partial index.** `add_decision_point` checks
  for the existing open plan_approval both pre-emptively and as
  IntegrityError recovery. The schema-level constraint is a backstop,
  not a behavior driver.

- **Concurrent intake sessions.** The intake runtime's tool dispatch
  is sync (no `asyncio.to_thread`). Handlers are idempotent (all
  UPDATEs) or have an explicit `status == committed` guard
  (`commit_intake`). No partial-replay risk in the intake path.

- **Test baseline.** `391 passed, 2 skipped, 1 warning`. The warning is
  the pre-existing starlette multipart deprecation. No regressions
  introduced by anything I've looked at.

---

## Recommended order of work

1. **Bug #1 first.** The audit-failure mis-record is the one that
   produces real-world visible damage (duplicate artifact rows,
   duplicate needs_input, plan-diff spam) and the fix is a small,
   surgical edit. The failing test I sketched would prevent regression.
2. **Bug #2 next.** It's user-visible (a 409 the user can't recover
   from without a restart) and the fix is also small. The
   `try/except` needs to wrap `_resolve_session` and reach the
   `finally`'s session-close path.
3. **Bug #3 is a design change** (outbox or pre-claim) and is bigger
   scope. Defer to a follow-up if there's appetite.
4. Bugs #4-#6 are nice-to-haves that the existing code handles
   "well enough" for the current product surface. File them; don't
   block.
