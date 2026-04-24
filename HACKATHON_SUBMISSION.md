# Vellum Hackathon Submission

## One-line pitch

Vellum is a durable investigation system where the primary surface is a structured dossier, not a chat transcript.

## Problem

Consequential questions often fail before the answer begins. A user may ask for a negotiation number, a go/no-go decision, or a recommendation, but the question can hide assumptions that are unsafe: whether a debt is actually owed, whether the statute of limitations has expired, whether a housing decision is really about commute or care obligations, or whether a family-planning question is masking a values conflict.

Chat is a poor fit for that work. It rewards immediate answers, loses structure over time, and makes it hard to distinguish confirmed findings from provisional reasoning. For high-stakes questions, confident output against a misframed prompt can be worse than no output.

## Product

Vellum turns the unit of work into a dossier: a typed case file an agent can work on over hours or days, and that the user can revisit on their own schedule.

Core behaviors:

- The agent challenges the premise before answering. A premise-challenge block captures the original question, hidden assumptions, a safer reframe, and evidence needed before a recommendation is responsible.
- The agent writes through typed tools, not freeform chat. Meaningful changes become sections, decision points, needs-input blocks, working theory updates, artifacts, or investigation-plan changes.
- The dossier has first-class state. Sections are `confident`, `provisional`, or `blocked`; user-facing blockers become needs-input or decision-point cards; delivered dossiers show the final answer and what changed along the way.
- The user returns to a changed object. The right rail shows what moved since the last visit, session summaries, confirmed facts, ruled-out paths, blockers, and cost.

## Demo Path

For the submission video, use the fixture route:

```text
http://localhost:5173/stress
```

That route renders a fully worked dossier from local fixture data. It does not require the backend, Anthropic API access, or a SQLite demo database. This keeps the recording reproducible for reviewers and safe for a public repo.

Suggested recording flow:

1. Open `/stress` and show the dossier as the product surface.
2. Expand or focus the premise-challenge block to show the agent pushing back on the user's frame.
3. Scroll through working theory, plan, sub-investigations, and section states.
4. Use the right rail to show the while-you-were-away diff and session/cost summaries.
5. End on the delivered-state dossier, emphasizing that this is not a chat transcript but a durable case file.

## Architecture

- Backend: Python, FastAPI, Pydantic, SQLite.
- Agent runtime: direct Anthropic Messages API with a manual loop and Pydantic-derived tool schemas.
- Frontend: React, TypeScript, Tailwind, Vite.
- Persistence: SQLite stores dossiers, sections, decision points, needs-input blocks, work sessions, change log, budget usage, and settings.
- Scheduler: a lightweight asyncio polling loop resumes paused work when user actions or scheduled wakes make progress possible.
- Safety valves: max turns, sub-agent turn limits, global concurrency caps, stuck detection, plan approval, idempotency guards, and soft-signal budget limits.

## What Is In Scope

- Single-user localhost product.
- Dossier creation through intake.
- Long-running agent work against the Anthropic Messages API.
- Structured dossier updates through typed tools.
- Premise challenge, plan approval, needs-input, decision points, sub-investigations, sections, artifacts, debrief, and delivered state.
- Fixture demo routes for public review without committing local data or API keys.

## What Is Not In Scope

- Multi-user auth or accounts.
- Production hosting.
- Notifications.
- Mobile-specific UI.
- Rich-text editing.
- Model providers other than Anthropic.
- Postgres or distributed workflow infrastructure.

## Running Locally

Frontend-only fixture demo:

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173/stress`.

Full local stack:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # or .venv/Scripts/activate on Windows
pip install -e .
cp .env.example .env
# Fill ANTHROPIC_API_KEY in backend/.env

cd ../frontend
npm install

cd ..
./dev.sh
```

Then open `http://localhost:5173/` to create a real dossier.

## Public Repo Notes

- No API key or SQLite database is required for the fixture demo.
- `.env`, local SQLite databases, build output, caches, and `node_modules` are gitignored.
- `backend/.env.example` contains placeholders only.
- Local CI target: backend pytest suite plus frontend TypeScript/Vite build.
