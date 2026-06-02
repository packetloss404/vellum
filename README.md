# Vellum

**A durable, multi-agent investigation engine where the dossier is the primary surface, not chat.**

Built solo in 5 days for the Built with Opus 4.7 hackathon, Vellum is a durable investigation system for consequential decisions where the primary surface is a structured dossier, not a chat transcript. It is built for questions that should not be answered immediately because the user's framing may already contain unsafe assumptions. Instead of treating the prompt as the ground truth, Vellum gives an agent time, structure, and tools to challenge the premise, investigate the underlying facts, surface blockers, and deliver a case file the user can return to later.

The core idea is that many important decisions do not fit well in chat. A user might ask, "What percentage should I offer to settle this credit-card debt?" A normal chatbot may generate a negotiation strategy. Vellum's agent first asks whether that is even the right question: is the debt valid, is it past the statute of limitations, does the collector own the account, and would negotiation accidentally restart liability? In that case, the responsible answer may not be a number at all. It may be to request validation, stop contact, or avoid engaging until facts are established.

Vellum turns that kind of work into a dossier. The dossier contains a premise challenge, working theory, investigation plan, sections, sub-investigations, needs-input blocks, decision points, artifacts, and a final debrief. Each section carries state, such as confident, provisional, or blocked, so the user can distinguish established findings from tentative reasoning. The agent cannot simply ramble into the interface. Meaningful output is written through typed tools, which means the product is structured data first and prose second.

The agent also works over time. A user can leave and return later to see what changed. The right rail shows session summaries, new findings, blocked paths, ruled-out assumptions, and cost. This makes the dossier feel like an evolving case file rather than a disappearing conversation. Vellum is intentionally quiet by default: no constant notifications, no stream of partial thoughts, and no expectation that the user must babysit the agent. The user returns when they are ready and sees the investigation state.

## Under the hood: it is a real durable agent runtime

Vellum is not a "single agent writes to a structured doc" demo. The investigation surface sits on top of several hand-built subsystems that handle concurrency, durability, recursion, and runaway-cost protection:

- **Manual agentic loop over the Anthropic Messages API** (`agent/runtime.py`, `DossierAgent.run`). It streams `client.messages.stream(max_tokens=32000)`, prepends a fresh dossier-state snapshot to every turn, dispatches tool calls off-thread with `dossier_id` injected server-side, records token cost per turn, handles Anthropic's `pause_turn` for server-side `web_search`, and discards any prose not attached to a tool call. The user never sees raw model prose — all visible output flows through a closed set of ~27 typed, Pydantic-backed tools (`upsert_section`, `flag_needs_input`, `flag_decision_point`, `mark_ruled_out`, `spawn_sub_investigation`, `append_reasoning`, …).
- **Idempotent, replay-safe tool dispatch.** Every tool call is keyed on its `tool_use_id` in a `tool_invocations` table and short-circuits on replay, so the agent loop is crash- and retry-safe: a re-run never double-applies a section edit or a spawn.
- **Multi-dossier orchestrator** (`agent/orchestrator.py`). One `asyncio.Task` per dossier with bounded concurrency, `AgentAlreadyRunning` / `AgentCapacityExceeded` guards, lock-protected start/stop, graceful 30s shutdown, and done-callback pruning.
- **Sleep-mode scheduler** (`agent/scheduler.py`). Polls for dossiers ready to wake every 30s, pre-creates `trigger=scheduled` work sessions, and retries on capacity/contention without dropping the user's change — a late answer keeps `wake_pending` set rather than being lost.
- **Recursive sub-investigations** (`agent/sub_runtime.py`). `spawn_sub_investigation` launches a real second agent runtime with its own work sessions, its own narrowed (allowlisted) tool surface, its own token accounting, a depth cap, force-completion nudge logic, and `sub_investigation_id` threaded through a `ContextVar`. It returns a `return_summary` back up to the parent's tool call.
- **Tiered stuck detection** (`agent/stuck.py`, ~870 LOC). Far more than "token budgets." It tracks per-session state with exact-args loop hashing, same-tool-no-progress heuristics, per-section revision counters reset by real progress, section/session token budgets, and a three-tier escalation ladder that decides between a silent reasoning-trail note, a `decision_point`, and a forced-recommended `decision_point` — so the agent never burns cycles blindly.
- **Crash recovery at startup** (`lifecycle.py`). Reconciles orphaned work sessions and stale intakes on boot.
- **Separate intake agent** (`intake/runtime.py`). A different, prose-speaking model interviews the user and constructs the dossier before the investigation agent ever runs.
- **Soft-budget economics.** Per-turn USD cost accounting with a per-model pricing table drives live daily/session rollups (`budget_accounting`); crossing a cap surfaces a `decision_point` rather than killing the run.
- **Trust-mode auto-pilot.** Optionally converts tier-2 stuck/budget interrupts into audited auto-decisions, with notes written to the reasoning trail.

## For hackathon reviewers

- **Scope freeze** — out of scope for v1: multi-user, auth, notifications, mobile, rich-text editor, LLMs other than Claude, Postgres, Temporal. Everything listed works on localhost against the Anthropic Messages API.
- **Models** — three-model split: `claude-opus-4-7` for the dossier agent, `claude-sonnet-4-6` for intake, `claude-haiku-4-5` reserved for summarization.

## What makes it different

- **The agent challenges the framing before answering.** On a new dossier, the first move is almost never to answer the stated question — it's to audit the frame. If a user asks "what percentage should I open credit-card-debt negotiations at?", the agent refuses to propose a number until it has confirmed the debt is actually owed (statute of limitations, FDCPA validation, estate liability). Pushback on premises is the thesis, not a feature.
- **The dossier is structured data, not prose.** The agent writes only through tool calls — `upsert_section`, `flag_needs_input`, `flag_decision_point`, `mark_ruled_out`, `append_reasoning`. There's no chat surface to the user; prose that isn't attached to a tool call evaporates.
- **First-class states.** Sections carry `confident | provisional | blocked`; dossiers carry `active | paused | delivered`; needs-input and decision-point blocks are top-level surfaces, not afterthoughts.
- **Quiet by default.** No pings, no notifications, no status updates. The dossier is a destination, not a stream.
- **It survives crashes and runs unattended.** Idempotent tool dispatch, startup reconciliation, the orchestrator/scheduler pair, and tiered stuck detection mean a dossier can be paused, resumed, woken on a schedule, or recovered after a restart without losing or duplicating work.

## Stack

- **Backend:** Python + FastAPI + Pydantic (single source of truth for the dossier schema across API, DB, and agent tool schemas), SQLite + WAL, asyncio. ~12.5k LOC; largest modules `storage.py`, `tools/handlers.py`, `agent/stuck.py`, `agent/runtime.py`, `agent/sub_runtime.py`.
- **Agent:** Direct Anthropic Messages API with a manual agentic loop (no agent SDK). Default model: `claude-opus-4-7`.
- **DB:** SQLite (v1) — 17-table relational schema with runtime column/index migration.
- **Frontend:** React 18 + TypeScript + Tailwind (Vite) + react-router + @tanstack/react-query + react-markdown. ~16k LOC, ~60 components, polling for live dossier state. Serif-forward, warm, document-like. No rich-text editor.
- **Tests:** 230 test functions across 31 files — lifecycle, orchestrator, stuck-detection, sub-investigation, resume, and end-to-end roundtrip.

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

Visit `http://localhost:5173/` to start a dossier.

## Project layout

```
backend/vellum/
  agent/        # dossier agent: runtime, orchestrator, scheduler,
                # sub_runtime (recursive sub-agents), stuck detection, system prompt
  api/          # FastAPI routes (dossier CRUD, agent control, intake, settings)
  intake/       # intake conversation agent (creates dossiers)
  tools/        # ~27 typed tool handlers (upsert_section, flag_needs_input, …)
  models.py     # Pydantic source of truth for the entire schema
  schema.sql    # SQLite schema (17 tables)
  storage.py    # DB reads and writes
  lifecycle.py  # reconcile orphaned work_sessions at startup

frontend/src/
  pages/        # DossierListPage, IntakePage, DossierPage, StressPage, DemoPage, SettingsPage
  components/   # sections, needs-input, decision-points, plan-diff, intake, common
  api/          # hooks, client, types (hand-mirrored from backend/vellum/models.py)
  mocks/        # demo fixture data
```

## Notable endpoints

Most routes follow standard CRUD patterns on `/api/dossiers/{id}/...`; a few have behavior worth calling out.

- **`POST /api/dossiers/{id}/replan`** — create or reset the plan_approval decision_point for a dossier. Three outcomes:
  - `action: "backfilled"` — plan was drafted with no open plan_approval DP (legacy dossier, or prior DP was resolved with Redirect). A fresh DP is created.
  - `action: "already_pending"` — idempotent; an open plan_approval DP already exists. Returns that DP's id without creating a duplicate.
  - `action: "replanned"` — plan was already approved. Un-approves it, then creates a fresh DP so the user can re-decide.
  - Returns `{ ok, action, dossier_id, decision_point_id, plan_unapproved }`. Responds 404 if the dossier is missing, 409 if no plan has been drafted (the agent produces a plan on first turn; call this afterwards).
  - The endpoint itself does **not** wake the agent — approving the returned DP goes through the existing `resolve_decision_point` hook, which sets `wake_pending=1` and the scheduler resumes within one tick.

- **`POST /api/dossiers/{id}/visit`** — marks last-visited; empties the "since your last visit" plan-diff window.

- **`POST /api/dossiers/{id}/resume`** — explicit agent restart on an existing dossier.

- **Optional API token guard** — set `VELLUM_API_TOKEN` (single env var, server-side only) to require a bearer token for `/api/*`. In dev, the Vite proxy reads `VELLUM_API_TOKEN` at startup and injects the `Authorization: Bearer …` header on every proxied request, so the token never ships in the browser bundle. `/health` remains public. Empty token keeps localhost dev unchanged unless `VELLUM_API_AUTH_REQUIRED=true`.

- **`GET /api/settings`, `PUT /api/settings/{key}`** — DB-backed settings (sleep-mode toggle, budget caps, warn fractions, progress-forcing threshold). Soft signals only; crossing a cap surfaces a decision_point rather than terminating the agent.

- **`GET /api/budget/today`, `GET /api/budget/range?days=N`** — daily USD + token rollups. `today` includes a `state` field (`ok` | `warn` | `soft_cap_crossed`) derived from the current cap + warn-fraction settings.

## Status

v1, single-user, localhost. A polished end-to-end build that genuinely runs against a live `ANTHROPIC_API_KEY`. Optional local-token API guard exists for tunneled or shared dev instances.

## Regenerating frontend types

When the backend Pydantic schema changes, regenerate the TypeScript types:

1. Start the backend (or export the OpenAPI spec: `cd backend && python -c "from vellum.main import app; import json; f=open('openapi.json','w'); f.write(json.dumps(app.openapi(),indent=2)); f.close()"`)
2. `cd frontend && npm run types:gen`

This produces `src/api/types.generated.ts`. The hand-maintained `types.ts` re-exports the types the frontend needs and adds frontend-only types.
