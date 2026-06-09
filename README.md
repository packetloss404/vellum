# Vellum

**A durable investigation system where the dossier is the primary surface, not chat.**

Built solo in 5 days for the Built with Opus 4.7 hackathon, Vellum is a durable investigation system for consequential decisions where the primary surface is a structured dossier, not a chat transcript. It is built for questions that should not be answered immediately because the user's framing may already contain unsafe assumptions. Instead of treating the prompt as the ground truth, Vellum gives an agent time, structure, and tools to challenge the premise, investigate the underlying facts, surface blockers, and deliver a case file the user can return to later.

The core idea is that many important decisions do not fit well in chat. A user might ask, "What percentage should I offer to settle this credit-card debt?" A normal chatbot may generate a negotiation strategy. Vellum's agent first asks whether that is even the right question: is the debt valid, is it past the statute of limitations, does the collector own the account, and would negotiation accidentally restart liability? In that case, the responsible answer may not be a number at all. It may be to request validation, stop contact, or avoid engaging until facts are established.

Vellum turns that kind of work into a dossier. The dossier contains a premise challenge, working theory, investigation plan, sections, sub-investigations, needs-input blocks, decision points, artifacts, and a final debrief. Each section carries state, such as confident, provisional, or blocked, so the user can distinguish established findings from tentative reasoning. The agent cannot simply ramble into the interface. Meaningful output is written through typed tools, which means the product is structured data first and prose second.

The agent also works over time. A user can leave and return later to see what changed. The right rail shows session summaries, new findings, blocked paths, ruled-out assumptions, and cost. This makes the dossier feel like an evolving case file rather than a disappearing conversation. Vellum is intentionally quiet by default: no constant notifications, no stream of partial thoughts, and no expectation that the user must babysit the agent. The user returns when they are ready and sees the investigation state.

## For hackathon reviewers

- **Scope freeze** — out of scope for v1: multi-user, auth, notifications, mobile, rich-text editor, LLMs other than Claude, Postgres, Temporal. Everything listed works on localhost against the Anthropic Messages API.

## What makes it different

- **The agent challenges the framing before answering.** On a new dossier, the first move is almost never to answer the stated question — it's to audit the frame. If a user asks "what percentage should I open credit-card-debt negotiations at?", the agent refuses to propose a number until it has confirmed the debt is actually owed (statute of limitations, FDCPA validation, estate liability). Pushback on premises is the thesis, not a feature.
- **The dossier is structured data, not prose.** The agent writes only through tool calls — `upsert_section`, `flag_needs_input`, `flag_decision_point`, `mark_ruled_out`, `append_reasoning`. There's no chat surface to the user; prose that isn't attached to a tool call evaporates.
- **First-class states.** Sections carry `confident | provisional | blocked`; dossiers carry `active | delivered`; needs-input and decision-point blocks are top-level surfaces, not afterthoughts.
- **Sleep-mode async runtime.** The agent can sleep and wake on a schedule. `schedule_wake(hours_from_now=N)` parks the session; the scheduler resumes it within one tick. Check-in cadence (daily / weekly / material-changes-only) is configurable at intake and auto-enforced.
- **Sub-investigations.** The agent can spawn parallel child investigations (`spawn_sub_investigation`), each running their own turn loop, and fold results back into the parent dossier's plan items.
- **Context compaction.** Long sessions automatically compact their message history via a summarizer call (default `claude-haiku-4-5`) so they never hit the context ceiling.
- **Quiet by default.** No pings, no notifications, no status updates. The dossier is a destination, not a stream.
- **Stuck detection with escalation.** Repeated-tool-call detection, revision stalls, and token-budget signals surface clean decision_points — escalating across tiers until the user or agent resolves the loop. Escalation state persists across sleep/wake cycles.

## Stack

- **Backend:** Python + FastAPI + Pydantic (single source of truth for the dossier schema across API, DB, agent tool schemas)
- **Agent:** Direct Anthropic Messages API with a manual agentic loop. Default model: `claude-opus-4-7`. Intake and compaction use `claude-sonnet-4-6` and `claude-haiku-4-5` respectively.
- **DB:** SQLite (v1)
- **Frontend:** React + TypeScript + Tailwind (Vite). Serif-forward, warm, document-like. No rich-text editor.

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
  agent/
    runtime.py        # main agentic turn loop
    sub_runtime.py    # sub-investigation turn loop
    orchestrator.py   # concurrency cap, session lifecycle
    scheduler.py      # sleep-mode: polls wake_store, fires sessions on schedule
    compactor.py      # context compaction (summariser call when token budget is low)
    stuck.py          # stuck detection: loop/stall/budget signals, escalation tiers
    prompt.py         # system prompt assembly (main agent)
    sub_prompt.py     # system prompt assembly (sub-investigations)
    telemetry.py      # per-turn token/cost logging
  api/                # FastAPI routes (dossier CRUD, agent control, intake, settings)
  intake/             # intake conversation agent (creates dossiers from conversation)
  tools/              # agent tool handlers (upsert_section, flag_needs_input, …)
  storage/            # per-entity DB stores (one file per entity type)
    dossier_store.py, session_store.py, plan_items_store.py,
    decision_point_store.py, needs_input_store.py, wake_store.py,
    sub_investigation_store.py, artifact_store.py, section_store.py,
    budget_store.py, turn_store.py, log_store.py, …
  models.py           # Pydantic source of truth for the entire schema
  schema.sql          # SQLite schema + migrations
  db.py               # connection management + init_db + migration runner
  lifecycle.py        # reconcile orphaned work_sessions at startup

frontend/src/
  pages/        # DossierListPage, IntakePage, DossierPage, StressPage, DemoPage, SettingsPage
  components/   # dossier, needs-input, decision-points, plan-diff, intake, common
  api/          # hooks, client, types.ts (hand-maintained), types.generated.ts (generated)
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

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Anthropic API key. |
| `VELLUM_MODEL` | `claude-opus-4-7` | Main dossier agent model. |
| `VELLUM_INTAKE_MODEL` | `claude-sonnet-4-6` | Intake conversation model. |
| `VELLUM_SUMMARY_MODEL` | `claude-haiku-4-5` | Compaction summariser model. |
| `VELLUM_API_TOKEN` | unset | Bearer token for `/api/*`. Required when binding to a non-loopback address. |
| `VELLUM_DB_PATH` | `vellum.db` | SQLite database file path. |
| `VELLUM_HOST` | `127.0.0.1` | Bind address for uvicorn. |
| `VELLUM_PORT` | `8731` | Port for uvicorn. |
| `COMPACT_INPUT_TOKEN_THRESHOLD` | `100000` | Input token count above which context compaction fires. |

## Status

v1, single-user, localhost. A startup warning is emitted (and the server can be configured to refuse to start) if `VELLUM_API_TOKEN` is unset and the bind address is not loopback.

## Regenerating frontend types

When the backend Pydantic schema changes, regenerate the TypeScript types:

1. Start the backend (or export the OpenAPI spec: `cd backend && python -c "from vellum.main import app; import json; f=open('openapi.json','w'); f.write(json.dumps(app.openapi(),indent=2)); f.close()"`)
2. `cd frontend && npm run types:gen`

This produces `src/api/types.generated.ts`. The hand-maintained `types.ts` re-exports the types the frontend needs and adds frontend-only types.
