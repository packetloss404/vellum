# Vellum

**A durable investigation system where the dossier is the primary surface, not chat.**

The unit isn't a chat session — it's a **dossier**: a structured, typed case file that an agent works on over hours or days, and that you return to on your own schedule. Close the laptop. Come back. The dossier has evolved — new sections, revised conclusions, flagged open questions, surfaced decision points. A plan-diff sidebar shows what changed since you were last here.

Vellum is for the kind of question that doesn't belong in a chat window — a consequential decision with several unknowns, where the obvious answer may be dangerous if key facts are wrong.

## For hackathon reviewers

- **[SUMMARY.md](./SUMMARY.md)** — three-paragraph project summary (problem / product / architecture).
- **[NARRATION.md](./NARRATION.md)** — 3-minute demo video script with timing and shot list.
- **Demo dossiers** — the repo's SQLite DB ships with three fully-worked investigations (credit-card debt, housing/proximity decision, fertility/ambivalence) that demonstrate premise challenges, working theories, sub-investigations, plan approval, and delivered-state sweep.
- **Scope freeze** — out of scope for v1: multi-user, auth, notifications, mobile, rich-text editor, LLMs other than Claude, Claude Agent SDK migration, Postgres, Temporal. Everything listed works on localhost against the Anthropic Messages API.

## What makes it different

- **The agent challenges the framing before answering.** On a new dossier, the first move is almost never to answer the stated question — it's to audit the frame. If a user asks "what percentage should I open credit-card-debt negotiations at?", the agent refuses to propose a number until it has confirmed the debt is actually owed (statute of limitations, FDCPA validation, estate liability). Pushback on premises is the thesis, not a feature.
- **The dossier is structured data, not prose.** The agent writes only through tool calls — `upsert_section`, `flag_needs_input`, `flag_decision_point`, `mark_ruled_out`, `append_reasoning`. There's no chat surface to the user; prose that isn't attached to a tool call evaporates.
- **First-class states.** Sections carry `confident | provisional | blocked`; dossiers carry `active | paused | delivered`; needs-input and decision-point blocks are top-level surfaces, not afterthoughts.
- **Quiet by default.** No pings, no notifications, no status updates. The dossier is a destination, not a stream.
- **Stuck detection.** Token budgets and repeated-tool-call detection surface a clean decision_point to the user — never burn cycles blindly.

## Stack

- **Backend:** Python + FastAPI + Pydantic (single source of truth for the dossier schema across API, DB, agent tool schemas)
- **Agent:** Direct Anthropic Messages API with a manual agentic loop. Default model: `claude-opus-4-7`.
- **DB:** SQLite (v1)
- **Frontend:** React + TypeScript + Tailwind (Vite). Serif-forward, warm, document-like. No rich-text editor.

## Local dev

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

Visit `http://localhost:5173/demo` for the fixture-driven hero demo, or `/` to start a real dossier.

## Project layout

```
backend/vellum/
  agent/        # dossier agent: runtime, orchestrator, system prompt, stuck detection
  api/          # FastAPI routes (dossier CRUD, agent control, intake)
  intake/       # intake conversation agent (creates dossiers)
  tools/        # agent tool handlers (upsert_section, flag_needs_input, …)
  models.py     # Pydantic source of truth for the entire schema
  schema.sql    # SQLite schema
  storage.py    # DB reads and writes
  lifecycle.py  # reconcile orphaned work_sessions at startup

frontend/src/
  pages/        # DossierListPage, IntakePage, DossierPage, DemoPage, NotFoundPage
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

- **Optional API token guard** — set `VELLUM_API_TOKEN` on the backend and `VITE_VELLUM_API_TOKEN` on the frontend to require a bearer token for `/api/*`. `/health` remains public. Empty token keeps localhost dev unchanged unless `VELLUM_API_AUTH_REQUIRED=true`.

- **`GET /api/settings`, `PUT /api/settings/{key}`** — DB-backed settings (sleep-mode toggle, budget caps, warn fractions, progress-forcing threshold). Soft signals only; crossing a cap surfaces a decision_point rather than terminating the agent.

- **`GET /api/budget/today`, `GET /api/budget/range?days=N`** — daily USD + token rollups. `today` includes a `state` field (`ok` | `warn` | `soft_cap_crossed`) derived from the current cap + warn-fraction settings.

## Status

v1, single-user, localhost. Optional local-token API guard exists for tunneled or shared dev instances. Out of scope: multi-user, notifications, mobile, rich text, LLMs other than Claude.
