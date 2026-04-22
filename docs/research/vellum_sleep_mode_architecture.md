# Vellum sleep-mode: target architecture

Status: design doc, day 6. Not code. Grounded in `backend/vellum/agent/runtime.py`, `orchestrator.py`, `stuck.py`, `lifecycle.py`, `storage.py`, and `api/agent_routes.py`. The spec handed to me referenced modules that don't exist yet (`sub_runtime.py`, `telemetry.py`, `docs/day5_live_run_diagnosis.md`, `docs/day6_moat_analysis.md`, frontend `DossierCard` / `InvestigationLogSidebar`). I note the discrepancies and design against the code that actually exists.

## 1. What sleep-mode actually requires

"Agents work while you sleep; you return to an evolved case file" is the product claim. The architecture must deliver eight capabilities. For each: what Vellum has today, and cites.

### 1.1 Execution persistence — the agent continues when the browser is closed

**Have it: yes (bounded).** The agent lives entirely server-side. `DossierAgent.run()` at `backend/vellum/agent/runtime.py:86` is an async method owned by `ORCHESTRATOR` (`backend/vellum/agent/orchestrator.py:253`); it is not coupled to any HTTP connection. Closing the browser has zero effect on the loop. The limit is that the loop is an `asyncio.Task` inside the FastAPI process — it survives the browser but not the process.

### 1.2 Crash recovery — the process dies mid-turn, work resumes

**Have it: partial.** `lifecycle.reconcile_at_startup()` at `backend/vellum/lifecycle.py:90` finds `work_sessions` rows with `ended_at IS NULL` and ends them, and drops a `[lifecycle]` note into the dossier's reasoning trail (`lifecycle.py:63`). What it does *not* do: relaunch the agent. Reconcile is janitorial, not resumption. A crash during a turn loses (a) anything in the current `response.content` that hadn't been committed via a tool call, (b) anything in-memory in `stuck._SESSION_STATE` (`backend/vellum/agent/stuck.py:61`), and (c) the per-session running token total — dossier-level state is safe because every tool call writes through `storage` synchronously. But the agent goes cold: nothing schedules it back.

### 1.3 Scheduled wake-ups — "I'll come back in 4 hours" actually happens

**Have it: no.** There is no scheduler, no cron, no APScheduler import. The orchestrator has `start`, `stop`, `status`, `list_running`, `shutdown` (`orchestrator.py:114–235`) and that is the full control surface. There is no `work_sessions.wake_after` column in `schema.sql`. An agent has no tool to say "come back later"; the closest thing is `flag_needs_input`, which is reactive to the *user*, not to time.

### 1.4 Reactive wake-ups — user answers a needs_input, agent auto-resumes

**Have it: no.** `storage.resolve_needs_input` (`storage.py:517–541`) writes the answer to the DB, logs a `change_log` entry, and returns. It does *not* call `ORCHESTRATOR.start`. The sibling hook `stuck.mark_needs_input_resolved` (`stuck.py:360`) only resets the revision-stall counter — again, no wake. The UI has to post-and-hope the user clicks "Run" again.

### 1.5 Budget bounds — hard cutoff at $X/dossier, $Y/day, $Z/month

**Have it: no.** There are two *soft* signals: `SECTION_TOKEN_BUDGET` and its 10× multiplier as a session-wide sanity ceiling (`stuck.py:67`, `config.py:18`). Both fire `StuckSignal(kind="section_budget" | "session_budget")` which surfaces a `decision_point` but does not terminate (`runtime.py:203-215`, comment is explicit that we "detect and report; we never cut the agent off mid-thought"). There is no dollar accounting. `work_sessions.token_budget_used` sums input+output tokens (`storage.py:775–780`) but is never priced. There is no per-dossier cap and no per-user daily cap.

### 1.6 Stuck detection that surfaces asynchronously

**Have it: partial.** `stuck.py` detects loops (threshold 3, `config.LOOP_DETECTION_THRESHOLD`), revision stalls (>3 upserts on same section), section budget overruns, and session budget overruns. Each surfaces as a `StuckSignal` which the runtime converts to a `check_stuck` tool call (`runtime.py:285–307`), which writes a `decision_point`. So the user *does* see the flag in the morning. What's missing: state is lost on process death (`_SESSION_STATE` is in-memory), and the "stuck overnight" story assumes the process stayed alive. Stuck doesn't trigger notifications — the user has to open the app.

### 1.7 Observability — user sees what, when, how long, how much

**Have it: partial.** Dossier-level: yes — `change_log` (`schema.sql:92`, surfaced via `storage.list_change_log_since_last_visit`) is the plan-diff. `reasoning_trail` is the "show your work" surface. `work_sessions.started_at`/`ended_at` gives wall time. What's missing: (a) per-session token counts are stored but not surfaced in the API; (b) no dollar figure; (c) no way to see "what the agent was doing at 3am" beyond the reasoning trail. There is no `telemetry.py` in the repo — the spec I was handed mentions one but none exists.

### 1.8 Multi-dossier concurrency — 2–3 dossiers in flight, no interference

**Have it: yes.** `AgentOrchestrator._tasks: dict[str, asyncio.Task]` (`orchestrator.py:78`) keys by `dossier_id`, `start()` enforces one-per-dossier via `AgentAlreadyRunning`, and the lock at `orchestrator.py:82` prevents the double-start race. Stuck state is per-session-id (`stuck.py:61`), so sessions don't interfere. SQLite is the only real contention point, and WAL mode handles single-writer fine for 2–3 concurrent agents.

---

## 2. The gap table

| Capability | Current state (file:line) | Missing piece | Severity |
|---|---|---|---|
| Execution persistence past browser close | `DossierAgent.run` is server-side (`runtime.py:86`); orchestrator is a process-wide singleton (`orchestrator.py:253`) | Bound to FastAPI process lifetime; no restart | degraded |
| Survives process crash | `reconcile_at_startup` ends orphan sessions (`lifecycle.py:90`); all tool calls write through `storage` synchronously | No resumption, no wake on reboot | **blocker** |
| Scheduled wake-up (timer) | No code anywhere | Scheduler loop, `wake_after` column, `schedule_wake` tool | **blocker** |
| Reactive wake-up (needs_input resolved) | `resolve_needs_input` writes DB only (`storage.py:517–541`) | Post-resolve hook into `ORCHESTRATOR.start` | **blocker** |
| Per-dossier budget cap | `token_budget_used` accumulates (`storage.py:775`); no cap | Per-dossier `budget_cap_usd`, cost-per-model table, per-turn check | **blocker** |
| Daily/monthly budget | Nothing | Rolling-window aggregation, account-level cap | degraded |
| Stuck detection survives restart | `_SESSION_STATE` in-memory (`stuck.py:61`) | Persist loop/budget counters to DB | degraded |
| Notifications when stuck | `decision_point` written; user must open app | Email/push is out of scope pre-contest; rely on pull | nice-to-have |
| Observability: tokens per session | `work_sessions.token_budget_used` (`storage.py:775`) not surfaced in API | Add to dossier response | degraded |
| Observability: dollars | No cost table, no pricing | Add model-pricing map, compute on ingest | **blocker** |
| Observability: "what happened overnight" | `change_log` + `reasoning_trail` exist; no UI pivot by session | UI surfacing of per-session change_log | degraded |
| Multi-dossier concurrency | `_tasks` dict + per-dossier lock (`orchestrator.py:78`) | — | OK |
| Agent can self-schedule | `runtime.py` loop has no "done for now" exit other than `ended_turn` | New `schedule_wake(hours_from_now)` tool | **blocker** |
| Idempotency across replays | Every tool call writes a row; retry = double-write | Idempotency keys on tool calls if we replay | **blocker (path-dependent)** |

Five blockers, several degradeds, one nice-to-have. The five blockers are: crash resumption, scheduled wake, reactive wake, budget cap, agent self-scheduling. Dollar observability is borderline — you can ship without it, but you can't defend the claim without it.

---

## 3. The four architectural paths

### Path A — Polling + SQLite scheduler (cheapest)

**What it is.** Keep everything in asyncio. Add a single background task started from `main.py`'s lifespan hook (alongside `reconcile_at_startup`) that wakes every N seconds (60s default), queries SQLite for dossiers that need attention, and calls `ORCHESTRATOR.start(dossier_id)` on them. The queue is the `dossiers` table plus two new columns. No redis, no worker pool, no external process.

**Route changes.**
- `POST /api/dossiers/{id}/schedule` — body `{"wake_at": iso_ts}` or `{"wake_after_hours": n}`; response 200 with the updated schedule.
- `DELETE /api/dossiers/{id}/schedule` — cancels a pending wake.
- `GET /api/dossiers/{id}/schedule` — returns current wake schedule.
- `GET /api/dossiers/{id}/budget` — returns `{budget_cap_usd, spent_usd, remaining_usd}`.
- `PATCH /api/dossiers/{id}/budget` — sets `budget_cap_usd`.
- `POST /api/dossiers/{id}/needs-input/{ni_id}/resolve` — extend existing handler to enqueue a reactive wake (`wake_pending = 1`) after successful resolve.

**Schema changes.**
```sql
ALTER TABLE dossiers ADD COLUMN wake_at TEXT;              -- scheduled wake timestamp (UTC ISO)
ALTER TABLE dossiers ADD COLUMN wake_pending INTEGER NOT NULL DEFAULT 0;  -- reactive wake flag
ALTER TABLE dossiers ADD COLUMN budget_cap_usd REAL;       -- per-dossier hard cap
ALTER TABLE dossiers ADD COLUMN spent_usd REAL NOT NULL DEFAULT 0;
CREATE INDEX idx_dossiers_wake ON dossiers(wake_at) WHERE wake_at IS NOT NULL;
CREATE INDEX idx_dossiers_wake_pending ON dossiers(wake_pending) WHERE wake_pending = 1;

ALTER TABLE work_sessions ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0;
ALTER TABLE work_sessions ADD COLUMN end_reason TEXT;      -- "ended_turn"|"scheduled"|"budget_tripped"|"crashed"|"stopped"
```

**Handler changes.** (a) Add a new tool `schedule_wake(hours_from_now, reason)` to `tools/handlers.py` that writes `dossiers.wake_at`. (b) After each `response.usage` in `runtime.py:125`, compute `cost_delta = price(input_tokens, output_tokens)`, increment `work_sessions.cost_usd` and `dossiers.spent_usd` atomically, check against `dossiers.budget_cap_usd`, and if tripped, write a `decision_point` + break the loop with `RunResult(reason="budget_tripped")`. (c) After `storage.resolve_needs_input`, set `dossiers.wake_pending = 1`. (d) The scheduler task polls both conditions and calls `ORCHESTRATOR.start`; on successful start it clears the wake field.

**Deployment changes.** None. Still one process, still one SQLite file.

**Complexity.** Low. ~500 lines. Reuses existing orchestrator wholesale.

**Right for.** Solo developer, single-machine deployment, demo and first 3 users. The 60-second polling interval is fine because users sleep for hours — latency on a reactive wake of 0–60s is imperceptible.

**Migration estimate:** 20–30 solo-dev hours.

### Path B — Job queue (arq or Dramatiq on redis)

**What it is.** Each agent turn is a discrete job enqueued to redis. A worker pool (1+ processes separate from FastAPI) dequeues and executes. Scheduling uses redis's delayed-set / arq's `enqueue_job(..., _defer_until=...)`. Crash recovery is free because redis persists the queue — if a worker dies mid-job, redis re-delivers on timeout (or you handle ack-on-complete).

**Route changes.** Same user-facing endpoints as Path A, plus:
- `GET /api/jobs/{job_id}` — job status (queued | running | done | failed).
- `DELETE /api/jobs/{job_id}` — cancel.
- Orchestrator `/start` no longer launches a task; it enqueues a job.

**Schema changes.** Same as Path A plus `jobs` table (or rely on redis, depending on whether you want audit in SQLite):
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    kind TEXT NOT NULL,          -- "agent_turn" | "agent_run"
    state TEXT NOT NULL,         -- "queued"|"running"|"done"|"failed"|"cancelled"
    idempotency_key TEXT UNIQUE, -- to avoid double-execution on redelivery
    scheduled_for TEXT,
    started_at TEXT,
    ended_at TEXT,
    error TEXT,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
```

**Handler changes.** The existing `DossierAgent.run` can run unmodified inside a worker. The awkward part: to get crash-recovery-across-turns, you break the monolithic `run(max_turns=200)` loop into per-turn jobs that re-enqueue themselves. Each turn's job reads `state.messages` from somewhere (either pass them forward in the job payload — large — or persist them to a new `agent_messages` table and load by session_id — better). Each tool dispatch gets an `idempotency_key = hash(tool_use_id)` so a replayed turn does not double-write a section. The `upsert_section` storage call becomes idempotent-on-tool-use-id: add a `tool_use_id` column to `change_log` and `ON CONFLICT DO NOTHING` semantics.

**Deployment changes.** Need redis (local dev: docker, prod: managed). Need a separate worker process (`arq worker vellum.worker.settings`). Lifespan hook no longer owns the tasks; shutdown is worker-pool-shutdown, which arq handles.

**Complexity.** Medium. ~1500 lines, including the tool-use idempotency layer. Operationally meaningful: you now have two processes and a broker.

**Right for.** A small team that expects to actually deploy and needs N workers scaling out. Overkill for a solo contest demo.

**Migration estimate:** 60–90 solo-dev hours.

### Path C — Durable execution framework (Temporal / Inngest / Restate)

**What it is.** The agent loop becomes a deterministic workflow; each tool call is an activity. The framework records every decision and replay-resumes on crash. Schedules, signals (for reactive wake), and timeouts are native primitives — `workflow.sleep(timedelta(hours=4))` actually works and survives process death.

**Route changes.** Same user-facing endpoints as Path A. Internally, `ORCHESTRATOR.start` becomes `temporal_client.start_workflow(DossierAgentWorkflow.run, dossier_id, id=dossier_id)`. `stop` becomes `handle.cancel()`. `resolve_needs_input` becomes `handle.signal(DossierAgentWorkflow.needs_input_resolved, ni_id)`.

**Schema changes.** Minimal — Temporal owns workflow state. You keep your domain tables (dossiers, sections, etc.) but drop most scheduler columns. You'd still want `budget_cap_usd` on `dossiers` because budget logic is domain, not workflow.

**Handler changes.** Large. The runtime at `runtime.py:86` needs to be split: the loop body becomes workflow code (deterministic, no I/O), and every call out — `self._client.messages.create`, `storage.*`, `handlers.HANDLERS[...]` — becomes an activity. Pydantic serialization at boundaries. All nondeterminism (e.g. `datetime.now()`, uuid, the Anthropic client's retry jitter) has to be wrapped in activities. `stuck._SESSION_STATE` becomes workflow-local state (automatically durable). `check_stuck`'s `decision_point` becomes a workflow signal the workflow can `await` on.

**Deployment changes.** Temporal Cloud ($) or self-hosted Temporal server (significant ops). Inngest is simpler to host but still a third service. FastAPI becomes a thin shell.

**Complexity.** High. ~3000+ lines rewritten. A real migration, not a refactor.

**Right for.** A team past product-market-fit that needs the replay / determinism guarantees and has the ops budget. Not Ian, not now.

**Migration estimate:** 150–250 solo-dev hours.

### Path D — Anthropic-side batching / scheduled Claude runs

**What it is.** Use the Anthropic Message Batches API for fire-and-forget long runs; use any "scheduled agent sessions" primitive if it exists in the Anthropic product stack at the time of implementation. The thinnest custom code — Anthropic hosts the queue and the compute.

**Route changes.** Same user-facing endpoints. Internally `start` submits a batch; `status` polls the batch.

**Schema changes.** Add `anthropic_batch_id` on `work_sessions`. Keep the budget tracking.

**Handler changes.** The problem: Vellum's agent loop is genuinely multi-turn with tool dispatch happening *server-side against our SQLite* (`runtime.py:163–194`). Message Batches API is good for one-shot long single calls; it does not natively host an arbitrary tool-dispatch loop that mutates your database. You would need to (a) re-architect tools so Anthropic can host them (impossible for the dossier tools — they write to our DB) or (b) use batches only for the web_search-heavy parts and keep the dossier mutation loop local. Neither gets you sleep-mode for the whole agent.

If a first-party Anthropic "scheduled agent" / "cron" primitive ships that supports custom tool dispatchers over webhook, this path becomes viable overnight. As of the knowledge cutoff I'm working from, I haven't verified one exists. Flagging as speculative.

**Deployment changes.** None beyond API keys.

**Complexity.** Low for the subset it supports. Zero for the subset it doesn't.

**Right for.** A use case where the long work is a single synchronous reasoning call (research reports, for example). Not right for Vellum, which is fundamentally a tool-dispatch loop. Including it here because the spec asked, but I don't recommend it.

**Migration estimate:** 10–20 solo-dev hours for partial integration; infeasible for full sleep-mode.

---

## 4. Recommended architecture — Path A

Rationale: Ian is solo, pre-contest, pre-validation, running on one machine. The moat is not "better distributed systems"; the moat is the dossier as a product surface and the frame-audit discipline embedded in the system prompt. Any time spent on redis/Temporal is time not spent on that moat. Path A reaches all seven capabilities in Section 1 with the *smallest* deviation from code that already works, and it can be replaced by Path B later without changing the user-facing surface.

What follows is the full spec.

### 4.1 Storage changes

```sql
-- Scheduling
ALTER TABLE dossiers ADD COLUMN wake_at TEXT;
ALTER TABLE dossiers ADD COLUMN wake_pending INTEGER NOT NULL DEFAULT 0;
ALTER TABLE dossiers ADD COLUMN wake_reason TEXT;  -- "scheduled"|"needs_input_resolved"|"crash_resume"

-- Budget
ALTER TABLE dossiers ADD COLUMN budget_cap_usd REAL;       -- NULL = no cap (dev only)
ALTER TABLE dossiers ADD COLUMN spent_usd REAL NOT NULL DEFAULT 0;

-- Observability on work_sessions
ALTER TABLE work_sessions ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0;
ALTER TABLE work_sessions ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_sessions ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_sessions ADD COLUMN end_reason TEXT;  -- "ended_turn"|"turn_limit"|"stuck"|"error"|"scheduled_pause"|"budget_tripped"|"stopped"

-- Persisted stuck counters (for crash-surviving stuck state)
CREATE TABLE session_tool_counts (
    work_session_id TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    reported INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (work_session_id, args_hash),
    FOREIGN KEY (work_session_id) REFERENCES work_sessions(id) ON DELETE CASCADE
);

-- Account-level (single-user for now, multi-user later without schema change needed)
CREATE TABLE budget_accounting (
    day TEXT PRIMARY KEY,    -- "2026-04-22"
    spent_usd REAL NOT NULL DEFAULT 0
);

CREATE INDEX idx_dossiers_wake_at ON dossiers(wake_at) WHERE wake_at IS NOT NULL;
CREATE INDEX idx_dossiers_wake_pending ON dossiers(wake_pending) WHERE wake_pending = 1;
```

Migration strategy: ship as a new SQL block in `schema.sql` with `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE` guarded at the Python layer by a `PRAGMA user_version` check in `db.init_db()`. SQLite's `ALTER TABLE ADD COLUMN` is online and cheap.

### 4.2 Routes

All routes are on the existing `/api` prefix (`api/agent_routes.py:26`).

| Method | Path | Body | Response | Errors |
|---|---|---|---|---|
| POST | `/api/dossiers/{id}/schedule` | `{"wake_at"?: ISO, "wake_after_hours"?: float, "reason"?: string}` | `{"dossier_id", "wake_at", "wake_reason"}` | 404 no dossier, 400 both or neither time specified, 400 wake_at in the past |
| GET  | `/api/dossiers/{id}/schedule` | — | `{"wake_at", "wake_pending", "wake_reason"}` | 404 |
| DELETE | `/api/dossiers/{id}/schedule` | — | `{"ok": true}` | 404 |
| GET  | `/api/dossiers/{id}/budget` | — | `{"budget_cap_usd", "spent_usd", "remaining_usd", "last_session_cost_usd"}` | 404 |
| PATCH | `/api/dossiers/{id}/budget` | `{"budget_cap_usd": float}` | `{"budget_cap_usd", "spent_usd"}` | 404, 400 negative cap |
| GET  | `/api/budget/today` | — | `{"day", "spent_usd"}` | — |
| GET  | `/api/dossiers/{id}/sessions` | — | `[{"id","started_at","ended_at","cost_usd","input_tokens","output_tokens","end_reason"}]` | 404 |
| POST | `/api/dossiers/{id}/needs-input/{ni_id}/resolve` (**extended**) | as today | as today, but also triggers `dossiers.wake_pending = 1` | as today |

The existing `POST /api/dossiers/{id}/agent/start` and `/stop` keep current semantics. The scheduler is an additional triggering path, not a replacement.

### 4.3 Scheduler design

One coroutine, `vellum.scheduler.run_forever`, started in `main.py`'s lifespan hook right after `reconcile_at_startup()`:

```
async def run_forever():
    while True:
        try:
            await tick()
        except Exception: log
        await asyncio.sleep(POLL_SECONDS)  # 60 default

async def tick():
    now = utc_now()
    # 1. Find all dossiers due for a scheduled wake
    scheduled = storage.find_dossiers_due_for_wake(now)
    # 2. Find all dossiers with a pending reactive wake
    reactive  = storage.find_dossiers_with_wake_pending()
    # 3. For each, check: no active agent already? budget remains?
    for d in scheduled + reactive:
        if ORCHESTRATOR.status(d.id)["running"]: continue
        if budget_exhausted(d): continue
        try:
            await ORCHESTRATOR.start(d.id, max_turns=MAX_TURNS_AUTO_WAKE,
                                     trigger=WorkSessionTrigger.scheduled)
            storage.clear_wake(d.id)   # atomic: clear wake_at & wake_pending
        except AgentAlreadyRunning: pass
```

Shutdown: the task is added to a shutdown list in lifespan; `app.on_shutdown` cancels the scheduler coroutine before `ORCHESTRATOR.shutdown()` so it doesn't spawn new work during teardown.

Single-instance assumption holds because Vellum is one process; no distributed lock needed. If we ever run two FastAPI processes, the scheduler would need a `SELECT ... FOR UPDATE SKIP LOCKED`-style claim — Postgres gives this natively, SQLite does not, so that's the fault line where Path A tips into Path B.

### 4.4 Budget guard

Pseudocode, fires once per model turn, right after `response.usage` is read in `runtime.py:125`:

```
input_tokens  = response.usage.input_tokens or 0
output_tokens = response.usage.output_tokens or 0
cost_delta = price_per_model[self.model].price(input_tokens, output_tokens)

# Atomic update: session + dossier + daily rollup
storage.record_usage(session_id, dossier_id,
                     input_tokens, output_tokens, cost_delta,
                     day=utc_now().date().isoformat())

dossier = storage.get_dossier(dossier_id)
if dossier.budget_cap_usd is not None and dossier.spent_usd >= dossier.budget_cap_usd:
    storage.append_reasoning(dossier_id, ReasoningAppend(
        note=f"[budget] Hit dossier cap ${dossier.budget_cap_usd:.2f}. Stopping and asking for direction.",
        tags=["budget", "stop"]), session_id)
    storage.add_decision_point(dossier_id, DecisionPointCreate(
        title="Hit your budget cap for this dossier",
        options=[
            DecisionOption(label=f"Raise the cap by $5", implications="Continue working", recommended=False),
            DecisionOption(label="Stop and review", implications="Deliver current state", recommended=True),
            DecisionOption(label="Mark delivered", implications="Freeze as-is", recommended=False),
        ]), session_id)
    return RunResult(reason="budget_tripped", turns=state.turns, session_id=session_id)
```

Hard stop, not soft — this is the one place the product departs from "budgets are soft signals." Ian's stated directive (`stuck.py:8-9`) is that the *stuck-detection* budget is a soft signal; the *dollar* budget is a different animal and is a hard cap by default. Users can raise it, but they can't un-see that they hit it. Soft notification variant (budget warning at 80%) is a nice-to-have.

### 4.5 Crash recovery protocol

Server comes back up. `main.py` lifespan runs:

1. `reconcile_at_startup()` — existing. Ends orphan `work_sessions`, adds `[lifecycle]` note. Sets `end_reason = "crashed"` (new).
2. **New step: `schedule_crash_resumes()`** — for every dossier that had an orphan `work_sessions.ended_at IS NULL` row ended in step 1, set `dossiers.wake_pending = 1` and `wake_reason = "crash_resume"`. The dossier will be picked up on the next scheduler tick within 60s.
3. Scheduler starts. Picks up the `wake_pending` dossiers; `ORCHESTRATOR.start` creates a *new* work_session with `trigger=resume`. The new agent reads the current dossier state (which is consistent because every prior tool call committed through storage). In-flight but uncommitted model prose from before the crash is lost — that's fine; the dossier contract is "prose in the chat is discarded" (`runtime.py:18-20`).

No replay, no idempotency keys needed, because tool calls are the commit points. The one thing lost is `stuck._SESSION_STATE`, which is why we persist it (see 4.1). On startup, re-hydrate `_SESSION_STATE` from `session_tool_counts` for any session we resume.

### 4.6 Reactive wake protocol

1. Browser: user answers a `needs_input` and POSTs to `/api/dossiers/{id}/needs-input/{ni_id}/resolve`.
2. `storage.resolve_needs_input` writes the answer and the `change_log` entry (unchanged).
3. **New step:** handler sets `dossiers.wake_pending = 1`, `wake_reason = "needs_input_resolved"`.
4. Scheduler (60s tick or less) sees `wake_pending=1`, checks no active agent, checks budget, and calls `ORCHESTRATOR.start(id, trigger=WorkSessionTrigger.resume)`.
5. Scheduler clears `wake_pending` atomically on successful start.

From the user's perspective, typing an answer at 7am and closing the laptop results in the agent picking up by 7:01am at latest. The UI shows "picking up where I left off…" once `/agents/running` reports it.

### 4.7 Quiescent self-scheduling

Add one new tool: `schedule_wake(hours_from_now: float, reason: str)`. Handler writes `dossiers.wake_at = utc_now() + hours_from_now`, appends a reasoning_trail entry tagged `scheduled_wake`, and returns `{"wake_at": iso}`. Importantly, *the agent must still end the turn in the same turn it schedules the wake* — `schedule_wake` is not a terminator. The typical shape is:

```
upsert_section(... final draft ...)
append_reasoning(note="Waiting for morning news cycle before re-validating...", tags=["scheduled_wake"])
schedule_wake(hours_from_now=6.0, reason="re-check AG bulletin page")
# then: end turn (no further tool_use blocks)
```

The runtime's existing "no tool_uses → ended_turn" (`runtime.py:151-158`) handles the termination. The loop ends cleanly; the session closes; the dossier sits with `wake_at=T+6h`; the scheduler picks it up on the next tick after T+6h.

Alternative considered: a special `RunResult(reason="paused_for_schedule")` from a magic return value of another tool. Rejected — a dedicated tool is more legible to both the model and the user, and it keeps the runtime's control flow stupid.

### 4.8 Idempotency (minimal)

Path A doesn't replay turns, so we don't strictly need per-tool idempotency keys. The one case to handle: the scheduler might double-call `ORCHESTRATOR.start` for the same dossier across ticks. `orchestrator.py:127` already handles this via `AgentAlreadyRunning`; we just swallow the exception and move on. The `wake_pending` flag clear happens after successful start, so a concurrent tick that saw `wake_pending=1` and was racing us will get `AgentAlreadyRunning` and bail. Good.

---

## 5. What the user sees

When the user closes the laptop mid-run, nothing changes in the UI except the tab goes dark. The agent is on the server. On reopen, the existing "plan diff since your last visit" (`storage.list_change_log_since_last_visit`, `storage.py:795`) surfaces everything that happened while they were away — this is already the core UX and it is already the right one. Sleep-mode layers four additions on top.

**The header (`frontend/src/components/layout/Header.tsx`) gains a budget strip.** Something like `$3.12 / $25.00 today · 2 dossiers working`. Click it to see per-dossier budget and the option to pause all. This is the single most important piece of new UI because "how much will this cost me" is the question Ian will be asked first by every contest judge and every real user. Without it, the product fails its own honesty standard.

**The plan-diff sidebar (`components/plan-diff/PlanDiffSidebar.tsx`) gets session grouping.** Today `change_log` entries render as a flat list. They should group under session headers: "Session 3 · 2:14am–2:47am · 94 tool calls · $0.73 · ended: turn limit" collapsible into its changes. The user scanning the diff in the morning sees "something happened at 2am" at a glance. This is a small addition to `PlanDiffSidebarView` — we already have `work_session_id` on every `ChangeLogEntry` (`models.py:180–187`).

**The dossier page gets a single "status" line between the title and the sections.** Four states:
- `working now` (green, with a spinner) — `ORCHESTRATOR.status(id).running === true`.
- `scheduled to resume at 6:00am` — `wake_at` set.
- `waiting on you` — open `needs_input` exists.
- `quiet` — everything else.

**Budget configuration** lives on the dossier settings drawer (existing, extended with a `budget_cap_usd` input) and a global default in the app settings. "Kill a runaway" is already the `POST /api/dossiers/{id}/agent/stop` endpoint; we just surface it as a red button on the working-now state. There is no separate cost dashboard — the header strip and per-session cost in the plan-diff are sufficient for day 1.

One deliberate omission from the UI story: no notifications, no emails, no push. The product contract is "you return to the dossier," not "the dossier pings you." A notification layer can come later; it fights the core premise today.

(Note: the spec I was handed mentions `DossierCard` and `InvestigationLogSidebar` components. The repo doesn't contain these — the actual components that evolve are `PlanDiffSidebar`, `Header`, and the dossier page shell at `pages/DossierPage.tsx`. I've designed against what exists.)

---

## 6. What to build first — the minimum viable sleep-mode

Scope for a 1–2 week solo sprint that produces a demoable "I closed my laptop and came back" story. Ruthless cuts where needed.

**Ship:**
1. **Schema migration.** `wake_at`, `wake_pending`, `wake_reason`, `budget_cap_usd`, `spent_usd` on `dossiers`; `cost_usd`, `input_tokens`, `output_tokens`, `end_reason` on `work_sessions`. Persist nothing else (skip `session_tool_counts` for MVP — live with stuck-state loss on crash for now).
2. **Price-per-model table.** Hard-coded dict in `config.py`: `{"claude-opus-4-7": {"input_per_mtok": X, "output_per_mtok": Y}}`. Update if the model name changes.
3. **Budget guard in `runtime.py`.** Post-usage: increment `spent_usd`, check against `budget_cap_usd`, hard stop with a `decision_point` if tripped. Per-turn check, not per-tool.
4. **Scheduler coroutine** started from `main.py` lifespan. 60s tick. Queries due-wakes and pending-wakes. Calls `ORCHESTRATOR.start`. Eats `AgentAlreadyRunning`. ~80 lines.
5. **Reactive wake hook.** One line change in `storage.resolve_needs_input`: set `wake_pending=1` after successful resolve.
6. **Crash resumption hook.** After `reconcile_at_startup`, set `wake_pending=1` on each recovered dossier with `wake_reason="crash_resume"`.
7. **`schedule_wake` tool** — new entry in `tools/handlers.py` and a schema append in `tool_schemas()`. One system-prompt paragraph explaining when to use it.
8. **Budget strip in `Header.tsx`.** Calls `GET /api/budget/today` on mount + every 30s. Pure additive. No per-dossier UI for budget yet — the global default is fine for MVP.
9. **Session grouping in `PlanDiffSidebarView.tsx`.** Group `ChangeLogEntry` by `work_session_id`, header shows `started_at`, `ended_at`, `cost_usd`, `end_reason`.

**Defer:**
- Per-dossier budget override UI (use a config default).
- Persisted stuck counters (accept state loss on crash for MVP).
- `/api/dossiers/{id}/budget` and `/api/dossiers/{id}/schedule` endpoints with full CRUD — just the reads plus the tool-driven writes are enough.
- Status line on dossier page — "working now" is already derivable from `/api/agents/running`.

**Acceptance demo.** Open a dossier, set budget to $2. Start agent. Wait for it to make a few turns. Close the laptop. Open the laptop an hour later. The dossier has visibly evolved (new sections, reasoning notes) OR the agent has hit the budget and posted a decision_point. Answer a `needs_input`; come back in 5 minutes — the agent has resumed and done new work. Kill the FastAPI process mid-turn; restart it; the agent resumes within 60 seconds. That's the demo. Total: ~7 days of work; extra days for polish, error handling, the schedule_wake tool's prompt integration.

---

## 7. What NOT to build

Explicit anti-scope. Things that would be premature, given Ian is solo and pre-validation:

- **Multi-user auth.** Post-contest. Add it when you have a paying user asking for shared accounts. For now, the app is single-tenant; budgets are global.
- **Cross-dossier memory.** The moat framing belongs to a future product; it is 6+ months away. Resist any urge to let one dossier "learn from" another.
- **Hosted deployment.** Do not spin up a cloud server before you have validated the thesis with three real users on localhost or a single-user VPS. Ops time is not product time.
- **Cost-monitoring dashboards beyond a daily-spend line.** Graphs, breakdowns by dossier, projections — no. One number in the header, one number per session. Anything more is premature optimization of a problem you don't have yet.
- **Redis, Temporal, any external queue.** Until SQLite polling actually hurts, it's faster and cheaper. It won't hurt at 1–3 concurrent dossiers.
- **Notification/email/push infrastructure.** The product is "you return to the dossier." Don't break that.
- **Worker scale-out, horizontal FastAPI, anything with the word "cluster" in it.** One process, one SQLite file, until contention proves otherwise.
- **Per-tool idempotency keys.** Only needed if you replay turns (Path B/C). Path A doesn't, so don't pay the cost.
- **A full "agent debugger" UI.** The reasoning trail + plan diff + session cost is already the observability surface. Don't build a second one.
- **Agent-initiated emails or external actions.** The system prompt at `agent/prompt.py:220-222` is explicit: `read + reason + write-to-dossier`. Sleep-mode does not expand that; it makes the existing surface more durable. A scheduled wake is not an "external action" — it's an internal timer.

---

## 8. Honest caveats

Where this doc is guesswork or depends on judgment I can't make from the code:

**The price table is fictional.** I don't have current Anthropic pricing for `claude-opus-4-7`. Ian will need to plug in the real numbers, and they'll change. Architecture is insensitive to this; only the dictionary changes.

**The 60-second poll interval is a guess.** For "I slept 8 hours" it is obviously fine. For "I typed an answer and walked across the room" it is the difference between "picked it right back up" and "why is nothing happening." If the first-impression UX suffers, drop it to 10s — SQLite can handle the read pressure trivially and the tradeoff is negligible.

**I'm asserting that the dossier contract handles crash recovery without idempotency.** This is true *if* every tool handler commits synchronously before the model sees the result. Spot check: `runtime.py:271` does `await asyncio.to_thread(handler, ...)`, and the storage functions commit in an `UPDATE/INSERT` inside `with connect() as conn`. I believe this closes the transaction. If anywhere a handler returns before commit (batching, deferred writes), the claim breaks. Worth a grep before shipping.

**"Reactive wake within 60 seconds" is a polling guarantee, not a push guarantee.** If Ian wants true push (user answers → agent starts within 100ms), he needs an asyncio Event or a SQLite `NOTIFY` shim. I deliberately didn't propose that — it's more mechanism for very little user-perceptible benefit at the current scale.

**Stuck-state persistence.** The persisted `session_tool_counts` table is straightforward but adds write pressure on every tool call (one more UPDATE). At 1–3 concurrent agents this is noise. At 100 agents it might not be — but at 100 agents Ian should be on Path B anyway.

**The "sleep-mode" moat framing.** The spec references a `day6_moat_analysis.md` I couldn't locate. One thing the sleep-mode story adds to any moat framing that focuses on the dossier-as-artifact: *accumulated wall-clock time* becomes a defensible product attribute. A competitor's agent that only runs while the user watches it, by construction, cannot deliver a dossier that evolved over 14 hours. The moat is not "we have a better loop"; the moat is "our loop ran for 14 hours while theirs ran for 4 minutes." Sleep-mode is not a feature of the product — it is the *condition* under which the dossier-as-artifact accumulates enough signal to matter. Any moat doc that treats sleep-mode as one-of-many features is undercounting.

**Budget as hard cap vs. soft signal.** I've proposed hard stop on dollar budget, contrary to the soft-signal doctrine for token budgets in `stuck.py:8-9`. This is a judgment call. The defense: token budgets protect against degradation in quality; dollar budgets protect the user from real-world harm (surprise bills). Different severity, different treatment. Ian may disagree — if so, the change is tiny: replace the `return RunResult(reason="budget_tripped")` with another `_surface_stuck`-style decision_point write and keep looping.

**What Ian has to decide, not me.** Whether the budget is per-dossier or per-account or both. Whether `schedule_wake` is exposed to the model (I think yes) or the system infers it from cadence policy (I think no, but it's defensible). Whether a crashed-and-resumed dossier shows the user a visible lifecycle note (I think yes — honest) or hides it (I think no, but some users prefer it). Whether Path A's single-process SQLite assumption is acceptable for contest day (I think yes; if judges hammer it concurrently, SQLite WAL will hold, but this is untested).
