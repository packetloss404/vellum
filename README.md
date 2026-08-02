# Vellum

**A durable, multi-agent investigation engine where the dossier is the primary surface, not chat.**

Built solo in 5 days for the Built with Opus 4.7 hackathon, Vellum is a durable investigation system for consequential decisions where the primary surface is a structured dossier, not a chat transcript. It is built for questions that should not be answered immediately because the user's framing may already contain unsafe assumptions. Instead of treating the prompt as the ground truth, Vellum gives an agent time, structure, and tools to challenge the premise, investigate the underlying facts, surface blockers, and deliver a case file the user can return to later.

The core idea is that many important decisions do not fit well in chat. A user might ask, "What percentage should I offer to settle this credit-card debt?" A normal chatbot may generate a negotiation strategy. Vellum's agent first asks whether that is even the right question: is the debt valid, is it past the statute of limitations, does the collector own the account, and would negotiation accidentally restart liability? In that case, the responsible answer may not be a number at all. It may be to request validation, stop contact, or avoid engaging until facts are established.

Vellum turns that kind of work into a dossier. The dossier contains a premise challenge, working theory, investigation plan, sections, sub-investigations, needs-input blocks, decision points, artifacts, and a final debrief. Each section carries state, such as confident, provisional, or blocked, so the user can distinguish established findings from tentative reasoning. The agent cannot simply ramble into the interface. Meaningful output is written through typed tools, which means the product is structured data first and prose second.

The agent also works over time. A user can leave and return later to see what changed. The right rail shows session summaries, new findings, blocked paths, ruled-out assumptions, and cost. This makes the dossier feel like an evolving case file rather than a disappearing conversation. Vellum is intentionally quiet by default: no constant notifications, no stream of partial thoughts, and no expectation that the user must babysit the agent. The user returns when they are ready and sees the investigation state.

## Under the hood: it is a real durable agent runtime

Vellum is not a "single agent writes to a structured doc" demo. The investigation surface sits on top of several hand-built subsystems that handle concurrency, durability, recursion, and runaway-cost protection:

- **Manual agentic loop over the Anthropic Messages API** (`agent/runtime.py`, `DossierAgent.run`). It streams `client.messages.stream(max_tokens=32000)`, prepends a fresh dossier-state snapshot to every turn, dispatches tool calls off-thread with `dossier_id` injected server-side, records token cost per turn, handles Anthropic's `pause_turn` for server-side `web_search`, and discards any prose not attached to a tool call. The user never sees raw model prose — all visible output flows through a closed set of 30 dossier + 7 intake = 37 typed, Pydantic-backed tools (`upsert_section`, `flag_needs_input`, `flag_decision_point`, `mark_ruled_out`, `spawn_sub_investigation`, `append_reasoning`, …). The 30 dossier tools dispatch through `HANDLERS`; `spawn_sub_investigation` is additionally registered in `HANDLER_OVERRIDES` so the sub-investigation runs synchronously inside the parent's turn loop rather than as a stub.
- **Idempotent, replay-safe tool dispatch.** Every tool call is keyed on its `tool_use_id` in a `tool_invocations` table and short-circuits on replay, so the agent loop is crash- and retry-safe: a re-run never double-applies a section edit or a spawn.
- **Multi-dossier orchestrator** (`agent/orchestrator.py`). One `asyncio.Task` per dossier with bounded concurrency, `AgentAlreadyRunning` / `AgentCapacityExceeded` guards, lock-protected start/stop, graceful 30s shutdown, and done-callback pruning.
- **Sleep-mode scheduler** (`agent/scheduler.py`, pinned by 13 dedicated tests). Polls for dossiers ready to wake every 30s, pre-creates `trigger=scheduled` work sessions, and retries on capacity/contention without dropping the user's change — a late answer keeps `wake_pending` set rather than being lost. The contention path is the canonical "reactive wake within one tick" promise.
- **Recursive sub-investigations** (`agent/sub_runtime.py`). `spawn_sub_investigation` launches a real second agent runtime with its own work sessions, its own narrowed (allowlisted) tool surface, its own token accounting, a depth cap, force-completion nudge logic, and `sub_investigation_id` threaded through a `ContextVar`. It returns a `return_summary` back up to the parent's tool call.
- **Tiered stuck detection** (`agent/stuck.py`, 941 LOC, pinned by 25 tests). Far more than "token budgets." It tracks per-session state with exact-args loop hashing, same-tool-no-progress heuristics, per-section revision counters reset by real progress, section/session token budgets, and a three-tier escalation ladder that decides between a silent reasoning-trail note, a `decision_point`, and a forced-recommended `decision_point` — so the agent never burns cycles blindly. The `stuck_escalation_count` (H-19) and `last_signal_kind` (H-20) columns persist across sleep/wake cycles so the next session can re-surface "last time you got stuck, it was a loop not a budget."
- **Crash recovery at startup** (`lifecycle.py`). Reconciles orphaned work sessions and stale intakes on boot.
- **Separate intake agent** (`intake/runtime.py`). A different, prose-speaking model interviews the user and constructs the dossier before the investigation agent ever runs.
- **Soft-budget economics.** Per-turn USD cost accounting with a per-model pricing table drives live daily/session rollups (`budget_accounting`); crossing a cap surfaces a `decision_point` rather than killing the run. A 200-turn hard cap (`AGENT_MAX_TURNS`) is the backstop.
- **Trust-mode auto-pilot.** Optionally converts tier-2 stuck/budget interrupts into audited auto-decisions, with notes written to the reasoning trail.

## For hackathon reviewers

- **Scope freeze** — out of scope for v1: multi-user, auth, notifications, mobile, rich-text editor, LLMs other than Claude, Postgres, Temporal. Everything listed works on localhost against the Anthropic Messages API.
- **Models** — three-model split: `claude-opus-4-7` for the dossier agent, `claude-sonnet-4-6` for intake, `claude-haiku-4-5` reserved for summarization.

## What makes it different

- **The agent challenges the framing before answering.** On a new dossier, the first move is almost never to answer the stated question — it's to audit the frame. If a user asks "what percentage should I open credit-card-debt negotiations at?", the agent refuses to propose a number until it has confirmed the debt is actually owed (statute of limitations, FDCPA validation, estate liability). Pushback on premises is the thesis, not a feature.
- **The dossier is structured data, not prose.** The agent writes only through tool calls — `upsert_section`, `flag_needs_input`, `flag_decision_point`, `mark_ruled_out`, `append_reasoning`. There's no chat surface to the user; prose that isn't attached to a tool call evaporates. The closed-loop enforcement is verified by `test_runtime_v2.py:643-661` (state-snapshot prepending) and `runtime.py:282-290` (discarded-prose path).
- **First-class states.** Sections carry `confident | provisional | blocked`; dossiers carry `active | paused | delivered`; needs-input and decision-point blocks are top-level surfaces, not afterthoughts. The two partial unique indexes (`idx_work_sessions_one_active_per_dossier`, `idx_decision_points_one_open_plan_approval_per_dossier`) are the load-bearing invariants the code-level guards protect.
- **Sleep-mode async runtime.** The agent can sleep and wake on a schedule. `schedule_wake(hours_from_now=N)` parks the session; the scheduler resumes it within one tick. Check-in cadence (daily / weekly / material-changes-only) is configurable at intake and auto-enforced server-side (H-23 in `runtime.py:466-495` — the agent can't accidentally drop the wake).
- **Sub-investigations.** The agent can spawn parallel child investigations (`spawn_sub_investigation`), each running their own turn loop with a narrowed allowlisted tool surface, and fold results back into the parent dossier's plan items.
- **Context compaction.** Long sessions automatically compact their message history via a summarizer call (default `claude-haiku-4-5`) so they never hit the context ceiling.
- **Quiet by default.** No pings, no notifications, no status updates. The dossier is a destination, not a stream. The 3-second polling on the activity indicator is the only "is the agent alive" affordance.
- **Stuck detection with escalation.** Repeated-tool-call detection, revision stalls, and token-budget signals surface clean decision_points — escalating across tiers until the user or agent resolves the loop. The escalation tier (H-19) and the kind of signal that fired (H-20, `last_signal_kind`) both persist across sleep/wake so the next session can re-surface "last time you got stuck, it was a loop not a budget."
- **It survives crashes and runs unattended.** Idempotent tool dispatch (keyed on Anthropic's `tool_use_id`), startup reconciliation (orphaned work sessions auto-close as `crashed`), the orchestrator/scheduler pair, and tiered stuck detection mean a dossier can be paused, resumed, woken on a schedule, or recovered after a restart without losing or duplicating work. The retention guard (`ERROR_RETRY_MAX=5` consecutive errored sessions) quarantines a sick dossier instead of looping it.

## Stack

- **Backend:** Python + FastAPI + Pydantic (single source of truth for the dossier schema across API, DB, and agent tool schemas), SQLite + WAL, asyncio. Largest modules: `tools/handlers.py` (~58 KB), `agent/stuck.py` (~45 KB), `agent/runtime.py` (~44 KB), `agent/sub_runtime.py` (~34 KB).
- **Agent:** Direct Anthropic Messages API with a manual agentic loop (no agent SDK). Default model: `claude-opus-4-7`. Intake uses `claude-sonnet-4-6`; compaction summarisation uses `claude-haiku-4-5`.
- **DB:** SQLite (v1) — **22-table relational schema** with runtime column/index migration. The schema-level **partial unique indexes** (`idx_work_sessions_one_active_per_dossier`, `idx_decision_points_one_open_plan_approval_per_dossier`) are the load-bearing invariants the code-level guards protect.
- **Frontend:** React 18 + TypeScript + Tailwind (Vite) + react-router + @tanstack/react-query + react-markdown. 41 components, polling for live dossier state. Serif-forward, warm, document-like. No rich-text editor.
- **Tests:** **393 backend pytest tests** across 36 files (lifecycle, orchestrator, scheduler, stuck-detection, sub-investigation, resume, end-to-end roundtrip, plan items, intake, runtime, telemetry, prompt caching, db migrations, API auth, and the `test_storage_imports.py` public-surface lint) plus **26 frontend vitest tests** across 5 files (cx utility, time/format utilities, plan-diff category order, agent activity indicator state machine, and the time/format tests).

## Local dev

Full local stack for real agent runs:

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate         # or .venv/Scripts/activate on Windows
pip install -e .
cp .env.example .env              # then fill in ANTHROPIC_API_KEY

# Frontend
cd ../frontend
npm install

# Run both together
cd ..
./dev.sh                          # uvicorn on :8731, vite on :5173
```

Visit `http://localhost:5173/` to start a dossier. Use `/stress`, `/stress2`, `/stress3`, `/stress4`, or `/demo` to load pre-built fixture dossiers without a backend (see "Fixture dossiers" below).

### Fixture dossiers

`/demo`, `/stress`, `/stress2`, `/stress3`, `/stress4` each load a pre-built fixture from `frontend/src/mocks/`. The fixture host (`components/FixtureHost.tsx`) mounts a fresh `QueryClient` pre-seeded with the fixture data so the dossier page renders the same as a live dossier would. This is what the submission video captures — the demos are reproducible without an API key.

### Running individual subsystems

```bash
# Backend with auto-reload (no frontend)
cd backend
uvicorn vellum.main:app --reload --port 8731

# Frontend with a mock API
cd frontend
npm run dev    # vite on :5173, proxy to localhost:8731 for /api

# Backend in offline / smoke-test mode (no real LLM)
cd backend
python -m pytest -m "not live"    # 393 tests, ~50s

# Backend with the live LLM test (one scenario, costs ~$2-6)
cd backend
VELLUM_RUN_AUTONOMOUS_TESTS=1 ANTHROPIC_API_KEY=… python -m pytest tests/test_autonomous_live.py
```

## Test suite quick reference

```bash
# Backend (393 tests, ~50s)
cd backend && python -m pytest

# Backend with the live autonomous test (requires ANTHROPIC_API_KEY)
VELLUM_RUN_AUTONOMOUS_TESTS=1 ANTHROPIC_API_KEY=… python -m pytest -m live

# Frontend (26 tests, <5s)
cd frontend && npm test

# Frontend type-check + production build
cd frontend && npm run build
```

The most load-bearing test files:

- `test_scheduler.py` (13 tests) — pins the late-answer correctness contract at `agent/scheduler.py:202-216`. The "reactive wake within one tick" claim.
- `test_stuck.py` (25 tests) — every stuck-detection signal kind, every exempt-tool carve-out, the `_STUCK_EXEMPT_TOOLS` whitelist contract, the H-20 `last_signal_kind` persistence, and the daemon-thread dispatch contract.
- `test_storage_imports.py` (4 tests) — pins the flat `storage.X` namespace contract: every public name importable, no old per-entity modules leak, no submodule attribute access, and no new public name added to `__all__` without being added to the expected set.
- `test_runtime_v2.py` — the dispatch loop, state-snapshot prepending, `pause_turn` handling, idempotent tool dispatch.
- `test_sub_runtime.py` — sub-agent tool filter, `ContextVar` for `sub_investigation_id`, prod-then-force-complete path, the broken `asyncio.run()` fallback's actual current behavior.

## Project layout

```
backend/vellum/
  agent/
    runtime.py        # main agentic turn loop
    sub_runtime.py    # sub-investigation turn loop (recursive sub-agents)
    orchestrator.py   # concurrency cap, session lifecycle
    scheduler.py      # sleep-mode: polls wake_store, fires sessions on schedule
    compactor.py      # context compaction (summariser call when token budget is low)
    stuck.py          # stuck detection: loop/stall/budget signals, escalation tiers
    prompt.py         # system prompt assembly (main agent)
    sub_prompt.py     # system prompt assembly (sub-investigations)
    telemetry.py      # per-turn token/cost logging
  api/                # FastAPI routes (dossier CRUD, agent control, intake, settings)
  intake/             # intake conversation agent (creates dossiers)
  tools/              # 30 typed tool handlers (upsert_section, flag_needs_input, …)
  storage/            # per-entity DB stores (14 files after cleanup-2)
    dossier_store.py        # core dossier CRUD
    plan_items_store.py     # first-class plan items
    sub_investigation_store.py
    session_store.py        # work sessions
    section_store.py
    decision_point_store.py
    artifact_store.py
    needs_input_store.py
    log_store.py            # reasoning/ruled_out/investigation_log/change_log
    dossier_lifecycle.py   # wake + user_notes + next_actions (merged)
    audit.py                # agent_turns + budget_accounting (merged)
    settings.py             # settings + tool_invocations (merged)
    _helpers.py             # shared row-converters + _ORDER_STEP
    __init__.py             # flat re-export of all 119 public names
  models.py           # Pydantic source of truth for the entire schema
  schema.sql          # SQLite schema (22 tables) + migrations
  db.py               # connection management + init_db + migration runner
  lifecycle.py        # reconcile orphaned work_sessions at startup

backend/tests/        # 393 backend tests across 36 files
  conftest.py
  test_stuck.py             # 25 tests — loop/section/session budget, revision stall,
                            # _STUCK_EXEMPT_TOOLS whitelist lint, last_signal_kind H-20,
                            # daemon-thread dispatch contract
  test_scheduler.py         # 13 tests — 30s poll, contention path, late-answer
                            # correctness contract, exception containment
  test_storage_imports.py   # 4 tests — flat namespace contract + inverse check
  test_intake.py, test_intake_e2e.py, test_plan_items.py,
  test_plan_approval.py, test_dossier_extensions.py,
  test_orchestrator.py, test_runtime_v2.py, test_sub_runtime.py,
  test_sub_investigations.py, test_sub_completion_reliability.py,
  test_resume.py, test_roundtrip_v2.py, test_lifecycle_crash_recovery.py,
  test_autonomous_live.py, test_compactor.py, test_telemetry.py,
  test_tool_surface.py, test_artifacts.py, test_user_notes.py,
  test_considered_and_rejected.py, test_investigation_log.py,
  test_day2_smoke_auto_resolve.py, test_runtime_hooks.py,
  test_self_heal.py, test_db_migrations.py,
  test_jit_loading.py, test_prompt_caching.py,
  test_agent_prompts.py, test_agent_status.py, test_agent_turns.py,
  test_api_auth.py, test_config_cost.py, test_trace_id.py

frontend/src/
  pages/         # DossierListPage, IntakePage, DossierPage, DemoPage, SettingsPage,
                 # StressPage (×4 for fixture variants), NotFoundPage
  components/
    dossier/         # SectionList, SectionCard, SubInvestigationList,
                     # DecisionPointItem, PlanBlock, PlanDiffSidebar, …
    needs-input/     # NeedsInputBlock, NeedsInputItem
    decision-points/ # DecisionPointBlock, DecisionPointItem
    plan-diff/       # PlanDiffSidebar, PlanDiffSidebarView, ChangeEntry, …
    plan-approval/   # PlanApprovalBlock
    intake/          # IntakeInput, IntakeThread, IntakeStateSummary
    common/          # Button, Card, Pill, DossierHero, EmptyState,
                     # ErrorBoundary, RelativeTime, SourceList
    layout/          # Header
    sections/        # RuledOutList, ReasoningTrail (demo-only)
  api/           # hooks.ts, client.ts, types.ts (hand-maintained mirror)
  utils/         # cx, time, format, useDocumentTitle
  mocks/         # demo fixture data (4 stress cases + demo)
  test-setup.ts  # vitest setup (jest-dom matchers)
  *.test.{ts,tsx} # 5 vitest files: 26 tests
```

## How the agent stays honest

The runtime enforces three load-bearing invariants that distinguish Vellum from a chat-shaped wrapper around Claude:

1. **No prose reaches the user.** Every model turn that ends with only a text block (no `tool_use`) is silently discarded by `runtime.py:282-290`. The user never sees raw model output; the only visible surface is the dossier, which is updated exclusively via typed tool calls.
2. **Tool calls are idempotent.** The `tool_invocations` table is keyed on Anthropic's `tool_use_id`. A crash, retry, or replay of the same tool call short-circuits to the recorded result — the dossier cannot be double-edited by a re-run.
3. **Stuck detection is a real, multi-heuristic system.** `agent/stuck.py` watches for exact-args loops, same-tool-no-progress spin, per-section revision stalls, and per-section/session token budgets. A three-tier escalation ladder decides whether the next move is a silent reasoning note, a user-facing decision point, or a forced-recommended decision point. The escalation tier (and the kind of signal that fired) persist across sleep/wake via `stuck_escalation_count` and `last_signal_kind` columns, so a flaky agent doesn't get to "forget" it was stuck.

## Notable endpoints

Most routes follow standard CRUD patterns on `/api/dossiers/{id}/...`; a few have behavior worth calling out.

- **`POST /api/dossiers/{id}/replan`** — create or reset the plan_approval decision_point for a dossier. Three outcomes:
  - `action: "backfilled"` — plan was drafted with no open plan_approval DP (legacy dossier, or prior DP was resolved with Redirect). A fresh DP is created.
  - `action: "already_pending"` — idempotent; an open plan_approval DP already exists. Returns that DP's id without creating a duplicate.
  - `action: "replanned"` — plan was already approved. Un-approves it, then creates a fresh DP so the user can re-decide.
  - Returns `{ ok, action, dossier_id, decision_point_id, plan_unapproved }`. Responds 404 if the dossier is missing, 409 if no plan has been drafted (the agent produces a plan on first turn; call this afterwards).
  - The endpoint itself does **not** wake the agent — approving the returned DP goes through the existing `resolve_decision_point` hook, which sets `wake_pending=1` and the scheduler resumes within one tick.

- **`POST /api/dossiers/{id}/visit`** — marks last-visited; empties the "since your last visit" plan-diff window. The visit-before-diff timing in `DossierPage.tsx:54-67` snapshots the change log *before* the `POST /visit` invalidates it.

- **`POST /api/dossiers/{id}/resume`** — explicit agent restart on an existing dossier. Returns 409 if a work session is already active; returns 404 if the dossier is missing or quarantined.

- **`GET /api/dossiers/{id}/resume-state`** — read-only snapshot for the UI to decide whether to offer a resume action. Returns `{ active_work_session_id, wake_pending, wake_at, wake_reason, consecutive_error_count, quarantined_at }`.

- **`GET /api/agents/running`** — list of all in-flight agent runs (powers the "Researching" pill on every dossier card in the list view; avoids an N+1 fanout). One request, not N.

- **`GET /api/agent/status`** — the running state of the agent for a single dossier. Used by `AgentActivityIndicator` to derive the 4-state `running | waking | scheduled | idle` machine.

- **Optional API token guard** — set `VELLUM_API_TOKEN` (single env var, server-side only) to require a bearer token for `/api/*`. In dev, the Vite proxy reads `VELLUM_API_TOKEN` at startup and injects the `Authorization: Bearer …` header on every proxied request, so the token never ships in the browser bundle. `/health` remains public. Empty token keeps localhost dev unchanged unless `VELLUM_API_AUTH_REQUIRED=true`.

- **`GET /api/settings`, `PUT /api/settings/{key}`** — DB-backed settings (sleep-mode toggle, budget caps, warn fractions, progress-forcing threshold). Soft signals only; crossing a cap surfaces a decision_point rather than terminating the agent.

- **`GET /api/budget/today`, `GET /api/budget/range?days=N`** — daily USD + token rollups. `today` includes a `state` field (`ok` | `warn` | `soft_cap_crossed`) derived from the current cap + warn-fraction settings.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Anthropic API key. |
| `VELLUM_MODEL` | `claude-opus-4-7` | Main dossier agent model. |
| `VELLUM_INTAKE_MODEL` | `claude-sonnet-4-6` | Intake conversation model. |
| `VELLUM_SUMMARY_MODEL` | `claude-haiku-4-5` | Compaction summariser model. |
| `VELLUM_API_TOKEN` | unset | Bearer token for `/api/*`. Required when binding to a non-loopback address. |
| `VELLUM_API_AUTH_REQUIRED` | `false` | If `true`, refuse to start without `VELLUM_API_TOKEN` set. |
| `VELLUM_DB_PATH` | `vellum.db` | SQLite database file path. |
| `VELLUM_HOST` | `127.0.0.1` | Bind address for uvicorn. |
| `VELLUM_PORT` | `8731` | Port for uvicorn. |
| `VELLUM_AGENT_MAX_TURNS` | `200` | Hard backstop on agent turn count per session. Soft budget signals fire first; this is the runaway-loop safety net. At 32k max tokens and Opus 4.7 pricing, this is roughly a $30 ceiling per session. |
| `VELLUM_SUB_AGENT_MAX_TURNS` | `60` | Same backstop for sub-investigations (their tool surface is narrower so the limit can be tighter). |
| `VELLUM_AGENT_MAX_CONCURRENT_RUNS` | `2` | Process-wide concurrency cap. The orchestrator raises `AgentCapacityExceeded` past this. |
| `VELLUM_SCHEDULER_POLL_SECONDS` | `30` | How often the sleep-mode scheduler polls for wake-ready dossiers. |
| `VELLUM_LOOP_DETECTION_THRESHOLD` | `3` | Stuck detector: how many identical-args tool calls before a loop signal fires. |
| `VELLUM_SAME_TOOL_NO_PROGRESS_THRESHOLD` | `8` | Stuck detector: how many calls to the same tool name before the no-progress heuristic fires (only fires if no new sections were created in the window). |
| `VELLUM_SECTION_TOKEN_BUDGET` | `30000` | Stuck detector: per-section input-token budget before a section_budget signal. |
| `VELLUM_SESSION_BUDGET_MULT` | `15` | Stuck detector: session budget = `mult × section_budget` (default 450k input tokens). |
| `VELLUM_STUCK_REVISION_STALL_THRESHOLD` | `5` | Stuck detector: revisions to the same section before a revision_stall signal (resets on `add_artifact` or `spawn_sub_investigation`). |
| `VELLUM_STUCK_ESCALATION_TIER1_TURNS` | `1` | Tier 1 stuck signals (silent reasoning note) fire on this turn. |
| `VELLUM_ERROR_RETRY_MAX` | `5` | Self-heal: consecutive errored sessions before the dossier is quarantined. |
| `COMPACT_INPUT_TOKEN_THRESHOLD` | `80000` | Input token count above which context compaction fires. ~80% of the 100k practical input limit. |
| `VELLUM_RUN_AUTONOMOUS_TESTS` | unset | For `test_autonomous_live.py` — when `1` with `ANTHROPIC_API_KEY` set, the live autonomous-agent test runs. Otherwise it skips. |

## Status

v1, single-user, localhost. Runs against a live `ANTHROPIC_API_KEY`. A startup warning is emitted if `VELLUM_API_TOKEN` is unset and the bind address is not loopback — the server can be configured to refuse to start in that case.

## Known issues and follow-ups

Things surfaced during the cleanup-2 audit that are deferred to a follow-up pass:

- **The `asyncio.run()` fallback at `agent/sub_runtime.py:769-783` is broken.** When `spawn_handler` is called from inside a running event loop, the inner `loop.run_until_complete` raises "Cannot run the event loop while another loop is running" — the fallback doesn't actually do anything. The outer except at line 784 catches the error and the call returns a structured error response. The right fix is to run the sub-investigation in a separate thread with its own event loop. Pinned by `test_sub_runtime.py::test_spawn_handler_when_called_inside_running_loop`.
- **`dossiers.investigation_plan` JSON column carries a redundant `items` list** (the first-class `plan_items` table is authoritative). The `items=[]` serialization already happens at write time (`storage/dossier_store.py:597, 606`); the column itself will be dropped in a 30-day-soak migration once we're confident no legacy dossier needs the JSON read.
- **The `InvestigationPlanItem` legacy model and its `_coerce_legacy_items` validator** are load-bearing for the JSON-blob read path on pre-v2 dossiers. The intake-layer `commit_intake` continues to use it (the model is stricter than `PlanItem` — `question` is required, not defaulted) so the "surface `plan_error` for malformed seeds" contract holds. The coercion now emits a `logger.debug` line so a future caller that accidentally constructs the legacy model is traceable.
- **The `last_signal_kind` column is read by the prompt but not yet threaded through `lastVisitedAt`-style "what changed since you last visited" UI surfaces.** Today the user sees "Last stuck signal" only on the next session's first turn.

## Frontend types

`frontend/src/api/types.ts` is hand-maintained and mirrors `backend/vellum/models.py` and `backend/vellum/intake/models.py`. ISO datetime strings come through as `string`; Pydantic `Optional` fields use `field?: T | null` so JSON `null` isn't conflated with JS `undefined`.

When the backend Pydantic schema changes, update `types.ts` by hand. An auto-generated `types.generated.ts` is not currently wired up — a previous version shipped dead weight (no file imported it), so the file was removed. The two-file seam is a future refactor: either commit to hand-maintenance and keep the current shape, or wire the OpenAPI generator into the build and have `types.ts` re-export from it.
