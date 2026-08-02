# Deep-dive #2 — Durability & Concurrency

Scope: how Vellum survives crashes, sleep/wake cycles, capacity pressure, and
the slow bleed of an agent that has lost its way. Read against
`backend/vellum/` on 2026-08-02. All references are `file_path:line_number`.

---

## 1. Orchestrator (`agent/orchestrator.py`)

A tiny in-memory table of running `asyncio.Task`s keyed by `dossier_id`.
Two invariants, three endpoints; the runtime and API rely on both.

**Per-dossier Task model.** `self._tasks: dict[str, asyncio.Task]` at
`orchestrator.py:100` plus `self._started_at: dict[str, str]`. Each
`start()` creates exactly one task (`orchestrator.py:172`):

```python
task = asyncio.create_task(coro, name=f"dossier-agent:{dossier_id}")
task.add_done_callback(self._make_done_callback(dossier_id))
self._tasks[dossier_id] = task
self._started_at[dossier_id] = started_at
```

`DossierAgent.run()` lives until it returns or is cancelled.
Sub-investigations execute *inside* the parent's coroutine, never as
separate orchestrator tasks (`orchestrator.py:23-26`):

> *Sub-investigation inlining. Sub-agents run inside the parent's
> ``DossierAgent.run()`` coroutine; the orchestrator never registers
> a sub-agent as a separate task.*

That's why a dossier's capacity slot is held for the entire session,
not per turn. See §7 for whether that's the right unit.

**The two guard exceptions.** Raised in the lock-protected critical
section of `start()` (`orchestrator.py:148-162`):

```python
async with self._lock:
    existing = self._tasks.get(dossier_id)
    if existing is not None and not existing.done():
        raise AgentAlreadyRunning(
            f"agent already running for dossier {dossier_id}"
        )
    active_count = sum(
        1 for task in self._tasks.values() if not task.done()
    )
    if (
        AGENT_MAX_CONCURRENT_RUNS > 0
        and active_count >= AGENT_MAX_CONCURRENT_RUNS
    ):
        raise AgentCapacityExceeded("agent capacity exceeded")
```

`AgentAlreadyRunning` is per-dossier; `AgentCapacityExceeded` is
process-wide, gated by `VELLUM_AGENT_MAX_CONCURRENT_RUNS` (default 2 —
`config.py:75`). Both become 409/429 in
`api/agent_routes.py:114-133`. The `asyncio.Lock`
(`orchestrator.py:104`) makes check-then-insert atomic; without it,
two concurrent `/resume` calls would both observe "no task" and
both create one.

**Lock-protected stop.** `stop()` takes the lock just long enough to
snapshot the task and call `task.cancel()`
(`orchestrator.py:198-205`):

```python
async with self._lock:
    task = self._tasks.get(dossier_id)
    if task is None or task.done():
        raise AgentNotRunning(...)
    started_at = self._started_at.get(dossier_id)
    task.cancel()
```

The cancel happens inside the critical section so a concurrent
`start()` can't race in and replace the task mid-shutdown. The
actual wait is *outside* the lock with
`asyncio.shield(_await_quiet(task))` and a 30s timeout
(`orchestrator.py:208-214`).

**Done-callback is the only prune path.** `_make_done_callback`
(`orchestrator.py:108-132`) pops both dict entries, then branches on
`cancelled` / `exception` / `result`. Natural end, cancel, and
uncaught exception all funnel through it — `list_active()`
(`orchestrator.py:251-300`) explicitly warns that
finished-but-not-yet-pruned tasks can briefly appear with status
`"cancelled"` or `"done"`.

**Graceful shutdown.** `shutdown()` (`orchestrator.py:302-326`)
cancels every task, then `gather(..., return_exceptions=True)` with
a 30s fence; `_await_quiet` (`orchestrator.py:329-339`) swallows
`CancelledError` and bare `Exception` so one bad task can't abort
the gather. Belt-and-braces `self._tasks.clear()` /
`self._started_at.clear()` after the fence. Called from the FastAPI
lifespan at `main.py:59`.

**What happens if a task crashes mid-turn?** The orchestrator's
done-callback just logs — it does NOT close the `work_session`. The
runtime's `finally` block (`runtime.py:439-522`) does:

```python
except Exception as exc:
    _end_reason = m.WorkSessionEndReason.error
    return RunResult(reason="error", turns=state.turns,
                    session_id=session_id, error=f"{type(exc).__name__}: {exc}")
finally:
    ...
    storage.end_work_session_with_reason(session_id, _end_reason)
    ...
    if _end_reason == m.WorkSessionEndReason.error:
        self_heal_mod.on_session_failure(self.dossier_id, kind="error")
```

So a mid-turn crash leaves: the work_session closed with
`end_reason=error`, the dossier's `consecutive_error_count` incremented
by self_heal, and either a `wake_at` set `backoff_seconds(N)` later, an
immediate `wake_pending=1` for the first crash (`self_heal.py:135-139`),
or a `quarantined_at` if the streak reaches `ERROR_RETRY_MAX=5`
(`self_heal.py:84-115`).

**How is the next resume detected?** Three paths:

1. **Process died mid-turn** → `lifecycle.reconcile_at_startup()` at next
   boot finds `work_sessions WHERE ended_at IS NULL`, ends them as
   `crashed`, calls `self_heal.on_session_failure(kind="crash")`, which
   schedules a retry (`lifecycle.py:59-89`). The scheduler picks it up
   on its next tick.
2. **Task raised but process survived** → the runtime's finally closes
   the session, self_heal sets `wake_at`/`wake_pending`, scheduler wakes
   on next tick.
3. **User wants a manual resume** → `POST /api/dossiers/{id}/resume`
   (`agent_routes.py:168-270`) calls `clear_dossier_quarantine` (which
   resets the error counter), opens a `trigger=resume` session, fires
   `ORCHESTRATOR.start` fire-and-forget.

The process-died case is what proves the durability story: the DB is
the only durable state, and on next boot both `lifecycle` and the
scheduler find their work without any external coordinator.

---

## 2. Sleep-mode scheduler (`agent/scheduler.py`)

A single asyncio coroutine polls SQLite every `VELLUM_SCHEDULER_POLL_SECONDS`
seconds (default 30 — `config.py:86`).

**The poll loop.** `Scheduler._run` (`scheduler.py:88-105`):

```python
while not self._stopping.is_set():
    try:
        await self._tick()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("scheduler tick raised; continuing")
    try:
        await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_seconds)
    except asyncio.TimeoutError:
        continue
```

First tick runs immediately (no leading sleep), so crash-resume picks up
as soon as lifespan finishes booting. Every tick is wrapped in
`try/except Exception` so a DB blip never kills the scheduler.

**The wake_store data model.** `storage/wake_store.py` is a thin wrapper
over four fields on the `dossiers` table:

- `wake_at` — set by the agent via the `schedule_wake` tool
  (`set_dossier_wake_at`, `wake_store.py:12-22`).
- `wake_pending` (INTEGER 0/1) — set by `lifecycle` and by
  `storage.resolve_needs_input` on a user answer
  (`mark_wake_pending`, `wake_store.py:25-31`).
- `wake_reason` — the `WakeReason` enum value, e.g. `crash_resume`,
  `error_retry`, `scheduled`, `user_answer`.
- `quarantined_at` — set by `set_dossier_quarantined`
  (`wake_store.py:103-114`); quarantined dossiers are excluded by
  `list_dossiers_ready_to_wake`.

The query that powers the tick (`wake_store.py:43-72`):

```sql
SELECT id AS dossier_id, wake_at, wake_pending, wake_reason
  FROM dossiers
 WHERE status != 'delivered'
   AND quarantined_at IS NULL
   AND (
         wake_pending = 1
         OR (wake_at IS NOT NULL AND wake_at <= ?)
       )
 ORDER BY COALESCE(wake_at, ''), id
```

Both `wake_pending` rows and `wake_at` rows can come back; if both are
set (e.g. crash-resume on a row the agent also pre-scheduled), H-28 in
`_wake_one` (`scheduler.py:139-159`) defers to the future `wake_at`.

**`schedule_wake(hours_from_now=N)` parks a session.** The agent-side
tool calls `set_dossier_wake_at(dossier_id, datetime, reason)` — a
single `UPDATE dossiers SET wake_at = ?, wake_reason = ?`. There is no
separate "parked session" object; the wake is a row-level state.

**Late-answer correctness — verified.** The README's claim is the
contention-handling block at `scheduler.py:202-216`:

```python
except (AgentAlreadyRunning, AgentCapacityExceeded) as exc:
    # ... a long comment explaining why we keep wake_pending set ...
    if pre_created_session_id is not None:
        try:
            await asyncio.to_thread(
                storage.end_work_session, pre_created_session_id
            )
        except Exception:
            ...
    return
```

When the scheduler pre-creates a session (`scheduler.py:182-188`) and
then `ORCHESTRATOR.start()` raises `AgentAlreadyRunning` (a user clicked
Resume between the SELECT and the orchestrator call) or
`AgentCapacityExceeded` (process is saturated), the scheduler:
1. **Closes** the session it just created (so it doesn't leak as an
   orphan).
2. **Does NOT** call `clear_dossier_wake`. The dossier's `wake_pending`
   (or `wake_at`) stays set.

The next tick retries. The comment is explicit about why clearing
would be wrong: the currently-running session snapshotted state at its
own start and can't see the new user answer; if we cleared the flag, the
user's change would silently die. The 30s poll is cheap enough that
sustained contention just keeps retrying until the conflicting run
ends. **Verified: a late user answer keeps `wake_pending=1`.**

The opposite path (a different exception in `ORCHESTRATOR.start`,
`scheduler.py:235-250`) also keeps the flag and closes the pre-created
session, with the comment *"Do NOT clear wake fields — next tick will
retry."*

**Check-in cadence.** H-23 server-side cadence enforcement in
`runtime.py:466-495`. When a session ends without delivering
(`_end_reason not in (delivered, error)`), the runtime reads the
dossier's `check_in_policy.cadence`. If it's `daily`/`weekly` AND no
`wake_pending`/`wake_at` is already set, the runtime stamps a wake
`1d`/`7d` from now via `storage.set_dossier_wake_at`. This removes the
failure mode where the agent forgets to call `schedule_wake` and never
wakes up.

---

## 3. Stuck detection (`agent/stuck.py` — ~890 LOC)

The biggest file in the repo. Module docstring at `stuck.py:1-46`
documents the "soft signals, never hard caps" principle and lists
calibration knobs. State model: one `threading.Lock` guarding a
module-level `dict[str, _SessionState]` (`stuck.py:137-138`):

```python
_STATE_LOCK = threading.Lock()
_SESSION_STATE: dict[str, _SessionState] = {}
```

The lock is `threading.Lock`, not `asyncio.Lock` — runtime coroutines
acquire it on every tool call, so lock-held time matters. Several
call sites deliberately drop the lock before I/O (see H-08
comments).

### 3a. Loop hashing with exact-args

The hash at `stuck.py:279-284`:

```python
def _hash_args(args: dict) -> str:
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except TypeError:
        blob = repr(sorted(args.items(), key=lambda kv: str(kv[0])))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()
```

The comparison key in `_state.tool_call_counts` is
`(tool_name, args_hash)` (`stuck.py:418`). Two `web_search` calls with
different queries get different keys; two `upsert_section` calls with the
same body get the same key. A "loop" is detected when
`count >= LOOP_DETECTION_THRESHOLD` (default 3 — `config.py:43`) and the
key is not already in `st.loop_reported` (`stuck.py:456-497`).

`update_debrief` and `update_investigation_plan` are exempt
(`stuck.py:145, 451-454`) — designed to be called iteratively with
similar args.

### 3b. Same-tool-no-progress heuristic

Counted by `tool_name_counts[tool_name]` regardless of args
(`stuck.py:425-427`); each tool's first call snapshots
`sections_created` (`stuck.py:426`). Signal fires at
`_SAME_TOOL_NO_PROGRESS_THRESHOLD = 8` (`stuck.py:506-548`):

```python
if (signal is None
    and tool_name not in _EXEMPT_FROM_NO_PROGRESS
    and tool_count >= _SAME_TOOL_NO_PROGRESS_THRESHOLD
    and tool_name not in st.same_tool_no_progress_reported):
    baseline = st.tool_name_first_sections_snapshot.get(tool_name, 0)
    if st.sections_created == baseline:
        ...signal = StuckSignal(kind="same_tool_no_progress", ...)
```

**Progress** here means *strictly: a new section was created since
that tool's first call.* A turn that calls `upsert_section` with no
`section_id` increments `sections_created` (`stuck.py:432-433`).
Editing an existing section doesn't count.

`log_source_consulted` and `web_search` are exempt
(`stuck.py:150, 504-505`); reading many sources is work, not spin.

### 3c. Per-section revision counters

Ticked at `stuck.py:436-439`:

```python
if tool_name in _UPSERT_TOOL_NAMES:   # {"upsert_section"}
    section_id = args.get("section_id") or args.get("after_section_id")
    if section_id:
        st.upsert_counts_since_resolve[section_id] += 1
```

`after_section_id` is the *preceding* anchor (a "place after this
section" hint), not the section being edited — the comment at
`stuck.py:343-353` warns against using it for token attribution, but
*is* used here for revision counting. This is fine for the heuristic
because we're counting "any upsert affecting this section" and the
anchor and the actual section are usually adjacent. The threshold is
`_REVISION_STALL_THRESHOLD = config.STUCK_REVISION_STALL_THRESHOLD`
(default 5 — `config.py:51-53`), strict-greater-than in the check
(`stuck.py:636`).

**Reset path.** The docstring at `stuck.py:36-39` claims
`mark_progress` is called from storage-mutating handlers. **It is
not.** The function doesn't exist anywhere in the repo (grep
confirms). The actual reset path is the in-line check at
`stuck.py:444-446`:

```python
if tool_name in _PROGRESS_MUTATION_TOOL_NAMES:   # {"add_artifact", "spawn_sub_investigation"}
    st.upsert_counts_since_resolve.clear()
    st.revision_stall_reported.clear()
```

Note `.clear()` — every section's counter resets, not just one. And
`mark_needs_input_resolved()` at `stuck.py:776-784` is defined but is
**only called from the self-test** (`stuck.py:939`); production never
reaches it. The user-answer path resets via `resolve_needs_input`'s
`wake_pending=1` flag (which causes a new session to start), but the
*in-memory* `_SessionState` is then destroyed on `reset_session`
(`stuck.py:881-886`, called from `runtime.py:520`). So the effective
reset is: a new session starts with zero counters. See §6 for the
implication.

### 3d. Section vs session budgets

Recorded by `record_input_tokens` (`stuck.py:555-568`):

```python
def record_input_tokens(session_id, section_id, tokens):
    if tokens <= 0:
        return
    with _STATE_LOCK:
        st = _state(session_id)
        st.session_tokens += tokens
        if section_id:
            st.section_tokens[section_id] += tokens
```

- **Per-section** (`check_section_budget`, `stuck.py:571-624`): fires
  once per section when `used > SECTION_TOKEN_BUDGET` (default 30,000
  — `config.py:42`). The "section" is the one the agent is currently
  upserting, attributed via `_last_section_id` (`runtime.py:354-357`).
- **Per-session** (`check_session_budget`, `stuck.py:684-754`): fires
  when `session_tokens > SESSION_BUDGET_MULTIPLIER *
  SECTION_TOKEN_BUDGET` (default 15 × 30k = 450,000). H-15 makes it
  re-fire every `_SESSION_BUDGET_REPEAT_INTERVAL = 50,000` additional
  tokens over the ceiling (`stuck.py:696-708`).

These are *session-scoped*, not dossier-scoped. A section edited
across three sessions accumulates from zero each session. Correct as a
"per-session over-investment" metric; can't tell you "this section is
90k deep in cumulative work."

### 3e. Three-tier escalation ladder

Tier is assigned in `_assign_tier_and_emit` (`stuck.py:343-394`):

```python
with _STATE_LOCK:
    st = _state(session_id)
    st.stuck_escalation_count += 1
    tier = min(st.stuck_escalation_count, 3)
    dossier_id_for_persist = st.dossier_id
signal.tier = tier
if tier >= 3 and signal.options_for_user:
    for i, opt in enumerate(signal.options_for_user):
        opt["recommended"] = (i == 0)
```

Then it spawns a daemon thread to bump the DB
(`stuck.py:376-381`), and `loop.run_in_executor` for the
investigation_log write (`stuck.py:389-393`).

**What each tier produces** (per `runtime._surface_stuck`,
`runtime.py:742-830`):

- **Tier 1** (first signal in a session): silent. A reasoning note
  tagged `["stuck", "stuck_L1"]` is appended; **no** decision_point.
  The agent reads it on the next state snapshot and is expected to
  narrow + continue. (`runtime.py:764-778`).
- **Tier 2** (second signal): standard `check_stuck` decision_point
  with the original options. (`runtime.py:816-830`).
- **Tier 3+** (third+ signal): `check_stuck` decision_point where
  `_assign_tier_and_emit` has already forced `recommended=True` on the
  first option and `False` on the rest (`stuck.py:369-371`). The
  default UI treats the first option as "what the agent wants to do."

The promotion is by *count* of surfaced signals, not by severity. A
single `session_budget` hit that crosses the ceiling and re-fires every
50k tokens after will keep promoting: signal 1 = tier 1, signal 2 =
tier 2, signal 3 = tier 3, signal 4 = tier 3 (clamped). The
recommendation flip is the visible consequence.

### 3f. State persistence across sleep/wake cycles

This is the most fragile part of the design. The `_SessionState`
dataclass (`stuck.py:86-135`) splits into two layers:

- **In-memory only** (lost when `reset_session` runs at session end):
  `tool_call_counts`, `section_tokens`, `session_tokens`,
  `upsert_counts_since_resolve`, `tool_name_counts`, `sections_created`,
  `turns_since_progress`, and all the `*_reported` dedup sets.
- **Persisted to `dossiers.stuck_escalation_count`** (INTEGER, schema
  migration in `db.py:50-52`): just the tier counter. Loaded by
  `_load_persisted_escalation_count` (`stuck.py:210-224`) and bumped by
  `_persist_escalation_count` (`stuck.py:227-246`).

So a new session restarts the loop detector, the section/session
budgets, the revision counters, and the no-progress counter, but the
*escalation tier* survives. The rationale (H-19) is in
`stuck.py:125-131`: a flaky agent that always trips the same stall
should reach tier 3 across sleep/wake cycles without the user
babysitting. The DB write is an in-SQL `+ 1` increment that commutes
under concurrent daemon threads; `init_session`'s double-checked
locking (`stuck.py:249-276`) loads the value from DB *outside* the
lock to keep I/O off the hot path.

---

## 4. Lifecycle / crash recovery (`lifecycle.py`)

`reconcile_at_startup()` (`lifecycle.py:121-206`) is the single boot-time
recovery entry point. It runs from `main.py:55` before the scheduler
starts. The lifecycle report returns counts of what was actually
recovered (`LifecycleReport` at `lifecycle.py:30-37`).

**Orphans detected.** The query at `lifecycle.py:42-46`:

```python
rows = conn.execute(
    "SELECT id, dossier_id FROM work_sessions WHERE ended_at IS NULL"
).fetchall()
```

**How each is resolved.** `_recover_one_work_session`
(`lifecycle.py:49-118`):

1. `storage.end_work_session_with_reason(session_id, crashed)` — close
   the row, stamp `end_reason='crashed'`. (DB failure here returns
   False; the recovery counter doesn't tick.)
2. `self_heal.on_session_failure(dossier_id, kind="crash")` — first
   crash = immediate `wake_pending`; subsequent = exponential backoff;
   `ERROR_RETRY_MAX` consecutive = quarantine. The **only** path
   that gives crashed sessions retry discipline.
3. `storage.append_reasoning(...)` with a `[lifecycle]` note so the
   reasoning_trail surfaces "interrupted, nothing was lost."

**Stale intakes.** `intake_storage.abandon_stale_intakes(7 * 24 * 60 *
60)` (`lifecycle.py:27, 163`). 7-day-old `gathering` intakes are
flipped to `abandoned`; fresh ones are left alone.

**Idempotency on the SQLite WAL.** Three layers:

1. **WAL mode** (`db.py:231-232`): `PRAGMA journal_mode=WAL` plus
   `synchronous=NORMAL`. The comment at `db.py:228-230` is explicit:
   WAL is required because the runtime dispatches handlers in
   `asyncio.to_thread` across parallel dossiers.
2. **Schema-level guarantee** at `db.py:144-147`:
   ```sql
   CREATE UNIQUE INDEX IF NOT EXISTS idx_work_sessions_one_active_per_dossier
   ON work_sessions(dossier_id)
   WHERE ended_at IS NULL
   ```
   A partial unique index — even if every code-level guard fails, the
   DB refuses a second active session per dossier.
3. **Boot-time duplicate sweeper** at `db.py:94-113`
   (`_close_duplicate_active_work_sessions`): a `WITH ranked AS ...`
   window that closes everything but the most recent. Catches a
   pre-sleep-mode DB or a manual edit that violated the index.

`start_work_session` (`session_store.py:35-58`) is itself idempotent:
SELECT for existing active session before INSERT, and catches
`sqlite3.IntegrityError` as a second line of defense
(`session_store.py:54-58`). Tool idempotency is layered on top via
`record_tool_invocation` in `runtime._dispatch_client_tool`
(`runtime.py:557-632`): the same `tool_use_id` is never dispatched
twice. The smoke test in `lifecycle.py:259-274` calls
`reconcile_at_startup()` twice and asserts the second call is a
no-op.

---

## 5. Trust-mode auto-pilot

`trust_mode_enabled` is a `settings` row, default `False`
(`config.py:197`). Two surfaces use it.

**Tier-2 stuck auto-dismiss.** In `runtime._surface_stuck`
(`runtime.py:780-814`): if tier 2 and trust_mode is on, pick the
`recommended` option (or the first if none flagged), append a
`[trust_mode:auto]` reasoning note with the chosen label and
summary, **return without surfacing a decision_point**. Tier 3+
*still* surfaces a DP — `config.py:194-197` says *"Plan approval
gates are NEVER skipped by trust mode"* and the tier-3 path skips
the trust check entirely (`runtime.py:816-830`).

**Budget auto-dismiss.** Same pattern in `_surface_budget_signal`
(`runtime.py:680-708`): the daily cap and per-session cap each get
their own signal; trust mode turns both into silent
`[trust_mode:auto]` log entries.

**"Audited" = reasoning_trail entry.** Every auto-decision appends a
note tagged `["stuck", "stuck_auto_dismissed", "trust_mode"]` (or
`["budget", "budget_auto_dismissed", "trust_mode"]`) including
which path was taken and the original summary. The user's plan-diff
view shows these in chronological order — visible, not hidden.

---

## 6. Concurrency hazards

Sharp edges, none verified as failures, all places a reviewer should look:

- **`mark_needs_input_resolved` is dead code in production.**
  `stuck.py:776-784` defines it; the self-test at `stuck.py:939` calls
  it; no production path does. `resolve_needs_input`
  (`storage/needs_input_store.py:43`) only sets `wake_pending=1`. So
  the user's answer doesn't reset the in-memory revision counter; the
  counter dies with the session via `reset_session`. The docstring at
  `stuck.py:36-39` also mentions `mark_progress`, which doesn't exist
  anywhere in the repo. The actual reset is the broad `.clear()` in
  `record_tool_call` (`stuck.py:444-446`) for `add_artifact` /
  `spawn_sub_investigation`. The comment is aspirational.

- **In-memory only loop/budget/revision counters across sessions.** A
  flaky agent that trips 4 loops, ends, and restarts gets a tier-3 DP
  (because `stuck_escalation_count` survives), but its loop counter
  is back at 1. The tier survives; the signal history doesn't.

- **`asyncio.to_thread` calls everywhere.** Every storage call in
  `runtime.py` is wrapped in `to_thread` because handlers are sync
  (`runtime.py:592-594, 615-624`). Each turn fans out ~10
  thread-pool tasks. Under load, this is a probable bottleneck.

- **Stuck uses `threading.Lock` (not `asyncio.Lock`).** `stuck.py:137`.
  Runtime coroutines call into stuck code on every tool call
  (`runtime.py:376, 387, 400, 520`). The lock is held only for
  in-memory dict mutations (H-08, `stuck.py:359-360`); the
  investigation_log write is scheduled via `loop.run_in_executor`
  (`stuck.py:389-393`) and the DB escalation count via a daemon
  thread (`stuck.py:376-381`). Today no caller introduces I/O under
  the lock; that's worth checking on every PR.

- **`start_work_session` race window.** `session_store.py:35-58` does
  SELECT-then-INSERT, with the partial unique index as the hard
  backstop. Two concurrent calls *will* hit `IntegrityError`; the
  recovery at `session_store.py:54-58` re-reads via
  `get_active_work_session` (fresh connection, safe under WAL).

- **`scheduler._wake_one` is multi-step non-transactional.**
  `scheduler.py:165-265`: close stale → create new → start → clear
  wake. Each step is its own connection. If the process dies between
  (a) and (b), reconcile catches the orphan. If it dies between (c)
  and (d), the next tick sees `wake_pending=1` and an already-running
  task → `AgentAlreadyRunning` → wake deferred, fields preserved
  (`scheduler.py:256-262`).

- **`record_turn_usage` vs `record_session_usage`.** Two functions in
  `session_store.py:108-197`. `record_session_usage` (108-138) only
  updates `work_sessions`; `record_turn_usage` (141-197) rolls up to
  `budget_accounting` too. The runtime calls the latter
  (`runtime.py:209-213`), so the daily budget stays consistent. But
  `record_session_usage` is exported — a future caller that picks it
  will skip the rollup. Small footgun.

- **`shutdown` clear-vs-callback race.** `orchestrator.py:325-326`
  clears `self._tasks` and `self._started_at` after the 30s fence.
  If a done-callback is still in flight, its `pop()` is a no-op (safe)
  but its `self._started_at.get(dossier_id)` returns None — it only
  logs, so no crash, just a None in the log line.

- **`list_active` admits zombie entries.** `orchestrator.py:251-300`
  explicitly documents that finished-but-not-yet-pruned tasks can
  appear as `cancelled` or `done`. Telemetry must treat this as
  "just finished", not as a stuck task.

---

## 7. Honest assessment

**Genuinely well-engineered:**

- The single-path done-callback cleanup in the orchestrator is
  textbook.
- The contention path in the scheduler (`scheduler.py:202-216`) is
  a *correctness* property, not just a retry. The comment
  explaining "the currently-running session took its state snapshot
  at its own start and has no way to see a needs_input answer that
  landed after that" is one of the most important lines in the
  repo.
- H-23 server-side cadence enforcement (`runtime.py:466-495`)
  removes a whole class of "agent forgot to schedule" bugs.
- The schema-level partial unique index (`db.py:144-147`) is a
  hard guarantee no code bug can quietly violate.
- The tier persistence (H-19) is a clever answer to "what
  survives sleep/wake" — the one thing you really want to
  remember is the one thing that does.
- Trust-mode reasoning-trail notes — the auto-decision is
  visible to the user later, not hidden.
- The double-checked locking in `init_session`
  (`stuck.py:249-276`) keeps the lock-held window to an in-memory
  counter bump; the DB load is outside the lock.

**Where complexity bites back:**

- 890 LOC of stuck detection. Seven heuristics, two overlapping
  (no_progress vs session_budget both ask "is the agent still
  moving?"). Tier assignment, investigation_log emit, and
  persistence all live in one function. A cleaner decomposition:
  detectors → escalation → side-effects.
- The `_PROGRESS_TOOL_NAMES` whitelist (`stuck.py:182-199`) is a
  maintenance trap — a new "actually-moves-the-investigation"
  tool that someone forgets to add will silently inflate the
  no-progress counter.
- The per-dossier Task model is the right unit for "long-lived
  investigation thread" but the wrong unit for "agent got stuck
  — let's cancel and retry from the last snapshot." Per-turn
  would let the scheduler cancel a stuck turn and re-queue. For a
  2-concurrent cap, per-dossier is fine; for higher caps, per-turn
  is more honest.
- The in-memory `_SessionState` doesn't survive sleep/wake. The
  tier count does, but not the *reason* (which heuristic fired).
  A "last_signal_kind" column on `dossiers` would help.

**What a reviewer would push back on:**

- `mark_needs_input_resolved` is dead code; the docstring is
  aspirational. Either wire it up or delete the function and the
  comment.
- The same-tool-no-progress heuristic and the per-tool loop
  detector cover overlapping ground. Why are both needed? (The
  answer is that exact-args loop detection exempts by *tool* but
  the no-progress detector is by *name* — not obvious from the
  code.)
- The escalation tier is a count, not a *kind* — a
  session_budget signal that re-fires every 50k tokens promotes
  to tier 3 just like `same_tool_no_progress` does. A reviewer
  would call that "a measure of how many times we've asked, not
  how sick the agent is."
- Soft signals everywhere mean a 200-turn runaway on a 450k
  ceiling with cached prompts is *plausible*. `AGENT_MAX_TURNS=200`
  is the hard cap; a reviewer would ask whether 200 turns is a
  real safety net or a number someone picked.

---

## 8. Notable design choices

**Decision_point instead of kill on budget overflow.**
`runtime.py:404-413` and `stuck.py:8-9`. The agent gets a soft
decision_point; the user (or trust mode) decides. The alternative
would be `task.cancel()` on budget pressure, which loses state
mid-turn. The current design is a 200-turn hard backstop plus a
soft budget advisory. *Why it matters:* preserves the "user is
in the loop" ethos — the agent doesn't have authority to decide
it's done.

**30-second poll cadence.** `config.py:86`. A wake fires at most
30s after the trigger; a tighter cadence would burn CPU and DB
load for nothing. With 2-concurrent runs the polling is trivial.
*Why it matters:* the system is essentially event-driven but
implemented as poll-driven. Bounded penalty (30s p99 wake
latency), no external broker.

**Per-dossier Task model.** `orchestrator.py:100, 172`. The unit
of parallelism is "one long-lived investigation thread per
dossier." Sub-investigations are inlined. *Why it matters:*
in-memory `stuck` state and message history are bound to task
lifetime; cancellation = "give up on this dossier right now."
Capacity is honest (2 dossiers = 2 tasks = 2 API streams). The
cost: a stuck task holds its slot until it returns.

**Tier persistence (H-19).** `stuck.py:210-246`. The only
in-memory stuck state that survives a sleep/wake is the
escalation count. *Why it matters:* a dossier that has been
"stuck three times" is genuinely sick; the user shouldn't have
to re-watch the agent trip the same heuristic after every wake.
Cost: one SQL `UPDATE` per signal in a daemon thread.

**Schema-level unique index on active work_sessions.**
`db.py:144-147`. Hard guarantee that no two work_sessions for
the same dossier can be `ended_at IS NULL`. *Why it matters:*
even if every code-level guard is bypassed, the DB refuses.

**Server-side cadence enforcement (H-23).** `runtime.py:466-495`.
If the agent ends a session without delivering AND without
calling `schedule_wake`, the runtime stamps `wake_at` based on
the dossier's `check_in_policy.cadence`. *Why it matters:*
removes the "agent died and the dossier never woke up" failure
mode.

**Soft budget signals with a hard turn cap.** `config.py:73-75`
(`AGENT_MAX_TURNS=200`, `AGENT_MAX_CONCURRENT_RUNS=2`). The cap
is a backstop; the budget is advisory. *Why it matters:* the
product's promise is "the agent thinks, the user decides." A
hard budget kill violates that.

**Trust-mode reasoning-trail notes.** `runtime.py:696-708,
800-813`. Auto-decisions are logged with `[trust_mode:auto]` and
tags. *Why it matters:* the user can audit what the system
decided for them later — the audit trail lives in the same place
the user already looks (the reasoning_trail), not in a separate
log.
