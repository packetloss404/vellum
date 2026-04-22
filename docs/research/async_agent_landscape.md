# Async Agent Runtimes: Landscape Survey for Vellum

**Audience:** a builder with one week to pick an architecture for Vellum's "sleep mode."
**Problem statement:** today the runtime is `asyncio.create_task(agent.run(...))` inside a FastAPI process. Close the laptop, the process dies, the agent stops. The product thesis — *"agents work while you sleep, and you return to an evolved case file"* — requires durability across process crashes, host reboots, and laptop-closed gaps, plus the ability to wake up on a schedule or an external event.

**Scope of this doc:** survey prior art in durable execution, agent-specific async primitives, job queues, scheduling, human-in-the-loop patterns, budget safety, and crash recovery. End with three credible paths Vellum could take and an honest recommendation.

**Epistemic disclaimers:** Today is 2026-04-22. I am drawing on documentation seen through training plus inference from API shapes. Where I can't cite a current docs page, I flag features as "reported, unconfirmed." 2023–24 sources are called out as potentially stale. Anthropic's 2026 background-jobs story is the area I am least certain about — I say "I am not sure" rather than invent behavior.

---

## 1. Durable execution frameworks

Durable execution frameworks record every step of a workflow and can replay it on any worker, so a crash (or laptop lid) loses at most the in-flight step. That primitive maps extremely well to an agent loop — each turn is a step, each tool call is an activity, and "sleep 6 hours" is a first-class operation.

### 1.1 Temporal

**What it is.** A workflow engine (Go server, polyglot SDKs — Python one is mature) where you write workflow code that deterministically describes the work, and "activities" that do side-effectful work. The server persists events; if a worker dies, another worker replays the workflow up to the last recorded event and continues.

**What it offers for agents.** `workflow.sleep_until(datetime)` gives durable timers (close laptop, come back tomorrow, timer fires). `workflow.wait_condition(predicate)` pauses until a signal updates state. **Signals** (external code sends a named message into a running workflow) are the natural primitive for "user answered needs_input → resume." **Schedules** are first-class cron-like scheduling. **Activities** hold tool calls with retry policies — at-least-once, you control backoff and idempotency.

**What it costs.** You run a Temporal server (self-hosted cluster or Temporal Cloud — ~$200/mo floor, reported 2024). For a single-user localhost product this is real deployment burden. Determinism discipline: workflow code cannot call `datetime.now()`, `random`, or arbitrary async I/O — you route everything through the SDK. Workflow code runs in a sandbox; `import anthropic` must happen in an activity, not in the workflow. The agent loop structure inverts: the *workflow* orchestrates turns; each LLM call and each tool call is an activity.

**FastAPI/Pydantic integration shape.** `@workflow.defn` classes and `@activity.defn` functions. Pydantic models pass across activity boundaries; Temporal added first-class Pydantic support in the 1.6+ Python SDK (reported). FastAPI becomes a thin shim: routes call `client.start_workflow(...)` or `client.get_workflow_handle(id).signal(...)`. The FastAPI process no longer holds the agent loop — Temporal does.

**Minimum viable slice.** Run `temporal server start-dev` in a side terminal (single binary, SQLite-backed), write a `DossierWorkflow` that loops on turns, each turn calls a `run_model_turn` activity and a `dispatch_tool_call` activity, sleeps on `needs_input`, resumes on signal. Real, but a full week of work to get right.

**Verdict:** overkill for single-user localhost day 1, but the *correct* long-term target if Vellum becomes a hosted product with multi-tenant durable cases.

### 1.2 Restate

**What it is.** A newer durable-execution system (Rust; Java/TS/Python SDKs), pitched as "like Temporal but lighter." Model: "virtual objects" (durable actors with per-key state) and a per-invocation "journal" that records each step for replay. Single binary, embedded persistence (RocksDB) — no separate database.

**Useful for agents?** Promising. A `Dossier` virtual object keyed by `dossier_id` maps directly to Vellum's concept: one durable actor per dossier, holding state, inbox, and timers. `ctx.sleep(...)` and `ctx.awakeable()` give the sleep-then-resume primitives. Virtual objects are single-in-flight per key — matching Vellum's day-1 constraint of one work session per dossier.

**Costs.** Smaller community than Temporal. Hosted offering exists; I am not sure of current pricing. Docs are shallower past the happy path. Python SDK is newer; I am not sure of its 2026 maturity.

**Verdict:** most credible "Temporal-without-the-cluster" alternative. Worth a prototype day — not a week-one bet without piloting.

### 1.3 Inngest

**What it is.** Event-driven durable workflows. TypeScript-first, with a Python SDK. You define "functions" triggered by events; inside, you use `step.run`, `step.sleep`, `step.sleepUntil`, and `step.waitForEvent`. Inngest persists step results so retries and resumes are free.

**`step.waitForEvent` for "wait for user answer"?** Yes — this is the canonical Inngest pattern. The agent function calls `step.waitForEvent("dossier.input.provided", { match: "data.dossier_id" })`, Inngest pauses the function, the FastAPI route fires the event when the user submits, the function resumes. Similarly `step.sleepUntil("2026-04-23T03:00:00Z")` is exactly the "check back at 3am" primitive.

**Deployment shape.** Inngest has a dev server (a single binary, local) and a managed cloud. Your app registers HTTP endpoints that Inngest invokes — it's a pull model (Inngest Cloud calls *you*). For a localhost product this is awkward: Inngest Cloud can't reach a laptop. The Inngest dev server can, but "durable across laptop-closed" doesn't hold if both Inngest and your FastAPI are on the same dying laptop.

**Verdict:** Excellent primitives, but the deployment model assumes your app is a reachable HTTP target. For a hosted Vellum beta this is a genuinely strong pick. For strict localhost, it's a poor fit.

### 1.4 DBOS

**What it is.** Postgres-native durable execution. The pitch: "your database is the workflow engine." Decorator-based Python API; durability comes from writing workflow events to Postgres inside the same transaction as your business writes, so exactly-once semantics fall out. No separate server.

**On SQLite?** DBOS is explicitly Postgres-only as of everything I've seen (reported; may have added SQLite — I am not sure). Their whole model leans on Postgres-specific features (LISTEN/NOTIFY, advisory locks, logical decoding for some features). A SQLite port would be a rewrite, not a config flip.

**Implication for Vellum.** Vellum is SQLite today, explicitly with "don't foreclose Postgres on Railway later" as a stack decision. If you move to Postgres for the hosted beta, DBOS becomes a very interesting option — you'd get durable execution with no new infrastructure beyond the DB you already run. For localhost SQLite day 1, it's a non-starter.

**Verdict:** Park this. Revisit at the "move to Postgres" moment.

### 1.5 LangGraph and LangGraph Cloud

**What it is.** LangGraph models an agent as a graph of nodes (functions) with a shared state object. Key primitives for durability:
- **Checkpointers** (`MemorySaver`, `SqliteSaver`, `PostgresSaver`) — the graph's state is snapshotted at each super-step into a checkpoint store. Resume from a checkpoint to continue a run.
- **Interrupts** (`interrupt()` inside a node) — halt the graph at a specific point, persist state, return control to the caller. Later, invoke the graph with `Command(resume=...)` and it picks up inside the interrupted node.
- **LangGraph Cloud / LangGraph Platform** — the hosted runtime. Adds scheduled runs, webhooks, human-in-the-loop primitives, and long-lived "assistants" with "threads."

**Are checkpoints the right primitive for "close laptop → resume tomorrow"?** They are *a* right primitive, with caveats:
- Checkpointer writes to SQLite or Postgres. Vellum already has SQLite — a `SqliteSaver` fits without new infra.
- Checkpoints cover the *graph state*, not in-flight HTTP calls. If the model call is in flight when the process dies, LangGraph retries the node on resume. Your LLM call is at-least-once; your tool call is at-least-once. Idempotency is on you.
- Interrupts + `Command(resume=value)` is the cleanest "HITL pause until user answers" primitive I've seen outside Temporal signals.

**Minimum viable slice.** Wrap Vellum's current loop as a single LangGraph node (or split it: `call_model`, `dispatch_tools`, `check_stuck`). Use `SqliteSaver` pointed at Vellum's existing DB (or a sibling DB). Wake-ups: an external scheduler (apscheduler, cron) invokes the graph with the checkpoint id. Needs_input: model a `plan_approval` node that calls `interrupt()`; the FastAPI route resumes with `Command(resume=answer)`.

**Verdict:** This is the lowest-activation-energy option that is *still a real durable runtime*. The deployment is "just add a library" — no new service to run. LangGraph Cloud is the "I want it hosted" knob to pull later.

**Caveat.** LangGraph's abstractions have moved faster than its docs. 2023–24 material is actively misleading. Prefer the 0.2+ docs (2025+). Some LangGraph internals (particularly around "subgraphs" and "interrupt before/after") have breaking changes between minors; budget time for version pinning.

---

## 2. Agent-specific async primitives from model vendors

### 2.1 OpenAI Assistants API

**Model.** Create `assistant` + `thread` + `messages`, then a `run`. The run executes server-side; you poll `run.status` (`queued | in_progress | requires_action | completed | failed | cancelled | expired`). `requires_action` means the model produced tool calls and is waiting for you to submit outputs. State lives on OpenAI servers; you hold only identifiers.

**Lessons.** Polling-based async is viable when the server holds state — an HTTP handler can ask "is this run done?" and act on the answer. `requires_action` is a clean HITL-ish pattern: the server pauses until you supply outputs. Threads accumulate state across runs — the "durable conversation" primitive.

**Limits for Vellum.** Vellum's state is a *structured dossier*, not a message thread; the Assistants "thread" abstraction forces messages as the unit of memory. Also: OpenAI, not Anthropic — and the stack decisions lock Claude.

### 2.2 Anthropic Message Batches API

**Model (as I understand it in April 2026; flag as subject to revision):** Submit up to 10,000 message requests in a single batch. Anthropic processes them asynchronously within a 24-hour SLA, typically much faster. You poll for completion and retrieve results. Pricing discount vs. real-time (reported ~50%).

**What it doesn't support.** The Message Batches API, as I last saw it, takes *independent* message requests — one-shot, not multi-turn. Each request is an isolated `messages.create`–equivalent call. **Tool use is supported per-request** (you can include tools in a batch request and get tool_use blocks back), but **the batch endpoint doesn't run your tools for you** — so multi-turn tool-calling loops are not served by batches. You'd have to materialize the whole tool loop client-side: submit turn N, receive, run tools, submit turn N+1 as a new batch request. That negates the point.

**Verdict.** Not a fit for Vellum's durable agent loop. Useful for one-shot fan-out workloads, not for stateful multi-turn work.

### 2.3 Anthropic background jobs / "operator"-style patterns (2026)

**I am not sure.** As of my last good look, Anthropic had not shipped a general "run this agent in the background, wake me when it's done" managed service in the way OpenAI shipped Operator or the Assistants API. There have been hints and previews, but I cannot confirm a GA product in April 2026 without checking current docs, and I will not invent one.

**What to check before committing:**
- Anthropic docs for anything named "background," "async run," "scheduled runs," "computer use runs."
- The Claude Agent SDK's current scheduling/durability story. (My knowledge: the SDK is oriented at Claude Code's interactive shape; I don't believe it offers persistent server-side runs, but confirm.)
- Anthropic's API keys page for spend caps (see §6).

If Anthropic has shipped something since, it's plausibly the cleanest answer for Vellum and would deserve re-ranking.

---

## 3. Job queue / worker patterns

If you're not ready for a full durable-execution framework, the pragmatic alternative is "each agent turn is a discrete job on a queue."

- **Celery.** Battle-tested, Redis/RabbitMQ broker. Heavy for single-user localhost; async-native story still rough in 2026 (reported).
- **Dramatiq.** Lighter than Celery, cleaner API; still needs a broker.
- **RQ.** Redis-only, dead simple. Scheduled jobs via `rq-scheduler`.
- **arq.** Async-native on `asyncio` + Redis. `defer_by` / `defer_until` for delayed jobs. Light; still needs Redis.

All four need Redis or RabbitMQ — new infra for a localhost product. Embedded alternatives (`fakeredis`, `redislite`) exist; I wouldn't ship them.

**"Poor man's queue": a scheduler thread polling SQLite.** Viable for Vellum. Pattern: a `jobs` table `(id, dossier_id, kind, run_after, status, attempts, payload)`; a background asyncio task that every N seconds runs `SELECT ... WHERE status='ready' AND run_after <= now() LIMIT 1` with `UPDATE ... SET status='running'` in the same `BEGIN IMMEDIATE` transaction; `asyncio.create_task(run_job(job))` on claim; `UPDATE status='done'` on completion; a startup sweep resets stuck `running` rows back to `ready`.

**Limits.** SQLite contention is a non-issue at Vellum's ~1 job/min rate with WAL. No clean multi-process FastAPI (races on jobs table) — fine for localhost, need Postgres row locks or a real queue on Railway. You write retry/backoff yourself.

**Verdict:** genuinely good enough for day 1, honest about what it can't do. ~100–200 LOC.

---

## 4. Scheduling primitives

| Need | Implementation options |
|---|---|
| Scheduled wake-up ("3am tomorrow") | Temporal `workflow.sleep_until` / Temporal schedules; Inngest `step.sleepUntil`; LangGraph + external scheduler; APScheduler (in-process, SQLite job store); cron + a tiny CLI entrypoint; `run_after` column in a SQLite jobs table |
| Reactive wake-up (user answered) | Temporal signal; Inngest `step.waitForEvent`; LangGraph `Command(resume=...)` into a graph interrupted with `interrupt()`; write a row to SQLite and have the poller pick it up |
| Quiescent self-scheduling (agent says "wake me in 6h") | Let the agent call a `sleep_until(timestamp)` tool that writes to your jobs table / sends a Temporal signal / fires an Inngest event; scheduler handles the rest |
| Cron-style recurring | Temporal schedules, K8s CronJob, systemd timer, cron, APScheduler, celery-beat, Inngest crons |
| Anthropic-side schedules | I am not sure there is a managed schedule primitive in the Anthropic API as of April 2026. Do not rely on one without checking. |

**APScheduler deserves special mention for Vellum.** In-process scheduler with a `SQLAlchemyJobStore` against the existing SQLite file. `scheduler.add_job(run_turn, 'date', run_date=..., args=[dossier_id])` survives FastAPI restarts by reading jobs back on boot. For "laptop closed 8 hours then reopened," the job fires when the process starts again and notices the scheduled time has passed (misfire handling is configurable). That's actually the right semantics for Vellum: when the laptop wakes, pending wake-ups fire and work resumes.

---

## 5. Human-in-the-loop patterns

Vellum has three HITL surfaces already modeled: `needs_input`, `decision_point`, `plan_approval`. The question is how to implement "the agent is paused waiting for human input, possibly for days" durably.

**Patterns surveyed:**

1. **LangGraph `interrupt()` + `Command(resume=...)`.** Inside a node, `value = interrupt({"question": "..."})`. The graph halts, state is checkpointed, control returns to caller. Resume with `graph.invoke(Command(resume=answer), config={"thread_id": ...})`. The node re-runs from the top but `interrupt` short-circuits the second time, returning the resume value. Clean; you must understand that the node re-executes on resume (side-effect implications).

2. **Temporal signal pattern.** `await workflow.wait_condition(lambda: self.answer is not None)`; external code calls `handle.signal(provide_answer, value)`. Days-long pauses are fine — the workflow is persisted and consumes ~no resources while waiting.

3. **Async-iterator pattern.** The agent is an async generator that yields questions and receives answers via `.asend(answer)`. Elegant in-process; useless across process death unless paired with a checkpointer.

4. **OpenAI Assistants `requires_action` polling.** Viable only if durability = "OpenAI servers hold state." Not applicable for Anthropic-based Vellum.

5. **DIY: write a `pending_question` row, return to UI, resume on POST.** This is roughly what Vellum already has (`flag_needs_input`), except today the agent task dies at laptop close. Add durability by checkpointing the full message history + pending `tool_use_id` before parking, and rehydrating on resume. Simple, explicit, no framework — and aligns with Vellum's "dossier is the state" thesis.

**Best practice for "paused for days":** persist everything needed to resume (messages, pending tool_use id, system prompt build inputs) outside process memory; make resume idempotent; surface the pause cleanly in the UI. Whether this is done via LangGraph checkpoints, Temporal workflows, or DIY rows in SQLite is a weight-vs-power tradeoff — all three can be correct.

---

## 6. Budget / cost safety

Unattended agents burn money. This is the section people skip and regret.

- **Anthropic API-key spend caps.** The console has per-workspace spend limits (monthly cap, alert thresholds); the API errors out when the cap is hit. I am not sure whether per-key per-day caps exist in 2026; check the console. Hard backstop, not a scalpel.
- **Temporal / Inngest max-cost-per-workflow.** Nothing built-in. DIY pattern: an activity reads `usage.input_tokens + usage.output_tokens`, accumulates in workflow state, bails (`raise ApplicationError(non_retryable=True)`) on threshold.
- **LangGraph budget hooks.** No first-class primitive; same DIY pattern — track in shared state, gate nodes with a conditional edge.
- **Claude Agent SDK.** Token-tracking hooks exist (reported); I don't recall a spend-cap knob. Verify.

**Standard approach — three layers:**
  1. **Process-level cap.** Workspace spend cap at Anthropic. Stops the bleeding if logic fails.
  2. **Session-level cap.** Vellum already has total tokens per work session in the DB. Turn that into a hard stop, not just a stuck signal.
  3. **Per-turn timeout.** If `messages.create` exceeds N seconds, cancel and surface a decision point. Prevents one pathological turn from eating your budget.

Vellum already has pieces 2 and 3 in spirit (via stuck detection). The gap is hard *termination* on catastrophic budget overrun, separate from the "surface a decision" path. For sleep mode specifically: a "max $X per unattended stretch" gate is mandatory. Without it, a stuck-loop bug costs real money overnight.

---

## 7. Crash recovery semantics

**The core problem.** Durable execution frameworks replay workflow code from the event log. If your workflow called `tool = upsert_section(...)` and crashed *after* the DB write but *before* the event was recorded, a replay will call `upsert_section` again. Your section gets double-written.

**How each framework handles it:**

- **Temporal.** Activities are at-least-once; you make them idempotent with a unique key. `workflow.side_effect` is for non-deterministic reads; side-effecting writes go in activities keyed by idempotency id.
- **Restate.** `ctx.run("step-name", fn)` memoizes the result into the journal; re-executing returns the recorded result. The `step-name` is the idempotency boundary. Correct by construction if you name steps consistently.
- **Inngest.** `step.run("unique-id", async () => {...})` memoizes by step id. Same model. Crash between side effect and step commit: at-least-once inside the step, so you still need a DB-level idempotency key.
- **LangGraph.** Nodes run to completion or not. Crash mid-node, whole node replays on resume. A node that writes SQLite and then calls the model is *not* safe to replay without an idempotency mechanism.
- **DIY on SQLite.** You own it completely. No hidden magic, and no hidden help.

**What Vellum needs to add to tool handlers.** Today, Vellum's `HANDLERS["upsert_section"]` writes to SQLite and returns. For sleep-mode safety, each tool invocation needs:

1. **An idempotency key** — `tool_use_id` from the model's response is already unique per invocation. Store it.
2. **A `tool_invocations` table** — `(tool_use_id PRIMARY KEY, dossier_id, tool_name, input_json, result_json, created_at)`. Before dispatching, check if `tool_use_id` is already there; if yes, return the recorded result.
3. **Write the invocation row and the mutation in one transaction.** SQLite makes this easy. This collapses the "ran the side effect but didn't record it" window to zero.

That's a ~50-line change to `tools/handlers.py` plus a migration, and it unlocks safe crash recovery regardless of which durability framework Vellum eventually picks (Temporal, LangGraph, or DIY). **Do this first.** It's the cheapest safety win in this entire doc.

---

## If Vellum wants sleep-mode, what are the 3 credible paths?

### Path A — Lightest: "poor man's durable execution" on SQLite + APScheduler + idempotent tools

**The architecture.** Vellum's existing asyncio orchestrator, plus three additions:
1. A `jobs` table (dossier_id, kind, run_after, status, attempts, last_error, payload).
2. APScheduler with a SQLAlchemyJobStore pointed at Vellum's SQLite — runs in-process; rehydrates on FastAPI boot.
3. A `tool_invocations` table keyed by Anthropic `tool_use_id` for idempotent replay.

**What Vellum gains.** "Close the laptop, reopen, the agent resumes." On boot, FastAPI checks `jobs` for anything `ready` whose `run_after` has passed, and kicks off the orchestrator. The agent-self-scheduling ("wake me in 6h") becomes a tool call that inserts a `jobs` row. `needs_input` becomes a `jobs` row in `waiting_for_input` status; the UI's POST answer flips it to `ready`.

**What it costs.** No new services, no new vendor, no new language. About one week of focused work — tables, APScheduler wiring, idempotency shim on tool handlers, a boot-time "recover orphaned work sessions" sweep. Zero marginal runtime cost.

**Migration from current code.** Additive. The existing `AgentOrchestrator` stays; it becomes one of several places that can `start()` a dossier (the other being the scheduler-fired `run_job`). `DossierAgent.run()` needs only two changes: (a) check for pending `needs_input` rows before taking a turn and refuse to run if one is open; (b) route tool dispatch through the new idempotent `tool_invocations` table.

**Who this is for.** Ian, the next 60 days, and anyone self-hosting Vellum on one box. It's the right fit for the product as currently scoped: single-user, localhost, a dossier-first mental model, tight week-by-week delivery. It does *not* scale to multi-host hosted Vellum without work — but it doesn't need to, yet, and nothing about it forecloses moving to Path C later.

**Where it will hurt.** Crash during a tool call before the transaction commits: the tool runs again on recovery — which is why idempotency on `tool_use_id` is non-optional. Model calls in flight during a crash: lost, turn re-runs from the top (acceptable). Multi-process FastAPI will race on the jobs table; fine, you aren't doing that yet.

### Path B — Middle: LangGraph-based execution with SqliteSaver and external scheduling

**The architecture.** Rewrite `DossierAgent.run()` as a LangGraph graph: nodes for `call_model`, `dispatch_tools`, `check_stuck`, with conditional edges. Use `SqliteSaver` against Vellum's SQLite. `needs_input` becomes an `interrupt()` call in a node; UI resumes with `Command(resume=...)`. Scheduling is external — APScheduler or cron invokes the graph with the right `thread_id`.

**What Vellum gains.** Checkpointing is a real library primitive, not a DIY table. Interrupt/resume is clean. You get LangSmith-style tracing for free if you add the LangSmith env vars. The path to LangGraph Cloud (if Vellum ever wants managed hosting) is `swap SqliteSaver for the Cloud checkpointer`.

**What it costs.** Dependency weight (LangGraph + LangChain core). Learning curve. LangGraph's abstractions churn between versions — you will pin and you will update carefully. You'll hit ergonomic friction: Vellum's agent-loop today is 200 lines of explicit Python; expressing it as a graph is not obviously clearer at this size. Checkpointing does not solve at-least-once tool calls on its own; idempotent tool handlers (from Path A) are still mandatory.

**Migration from current code.** Moderate. The `DossierAgent.run()` while-loop becomes a graph definition; tool dispatch stays in your `handlers` module but is called from a graph node; the system prompt builder and state snapshot logic don't change. Probably 3–5 days of work for someone who hasn't used LangGraph before.

**Who this is for.** Vellum if Ian decides he wants the *observability and HITL primitives* of LangGraph more than the minimalism of Path A, *or* if he sees a near-term path to hosting on LangGraph Cloud for a small beta. The second reason is the stronger one — LangGraph as a local framework is fine but not obviously better than Path A; LangGraph as "a library that's also a one-click hosted runtime later" is a legitimate hedge.

**Vendor-lock-in note.** LangGraph is OSS (MIT). LangGraph Cloud is the lock-in part; the library itself you can fork.

### Path C — Heavy: Temporal (or Restate) durable execution

**The architecture.** Run a Temporal server (dev mode locally; Temporal Cloud or self-hosted cluster in production). Write `DossierWorkflow` as a workflow class with `run_turn`, `dispatch_tool_call`, and `call_model` as activities. Signals handle `needs_input` resumes. `workflow.sleep_until` handles scheduled wake-ups. Temporal schedules handle recurring "check the dossier every morning."

**What Vellum gains.** Real durable execution: crash mid-activity, another worker picks up, no lost work (assuming activity idempotency, which you still owe). First-class signals, timers, schedules. Observable out of the box (Temporal UI). Scales cleanly to multi-tenant hosted Vellum.

**What it costs.** A Temporal server in every deployment — localhost is `temporal server start-dev` (single binary, fine), production is Temporal Cloud (~$200+/mo floor, reported) or a self-hosted cluster (Cassandra/Postgres + worker fleet). Determinism discipline on workflow code; people underestimate the "why did my replay fail?" debugging tax in month one. The agent loop inverts: workflow runs continuously and calls activities; FastAPI becomes a thin API over `client.signal()` / `client.start_workflow()`.

**Migration from current code.** Large. The current asyncio orchestrator is essentially replaced. Each tool handler becomes an activity (a 1-line wrapper plus idempotency). The `DossierAgent` class becomes a `DossierWorkflow`. Probably 1.5–2 weeks end-to-end, longer if you haven't used Temporal before.

**Who this is for.** Vellum if it pivots from single-user-localhost to multi-tenant-hosted within the next 6 months, *and* durability/observability are non-negotiable selling points. Also the right choice if Vellum grows to multiple concurrent durable workflows per dossier (background research, scheduled digests, recurring check-ins) rather than one.

**Restate as a lighter variant of this path.** If you want the durable-execution model without the Temporal operational weight, Restate is the most credible swap. Single binary, embedded persistence, virtual-object model that maps naturally to "one durable actor per dossier." I'd pilot Restate before committing to Temporal for a product of Vellum's size. Smaller community is the real risk.

---

## Recommendation

**Do Path A now. Do the tool-idempotency work now *regardless* of path. Revisit Path B or Path C at the "hosted beta" decision point, not before.**

Vellum today is a single-user localhost product whose entire value proposition is "a dossier you return to." The durability question is "does the dossier survive the laptop being closed?" — *not* "does Vellum survive a Kubernetes node failure." Path A answers the real question with one week of focused work, no new services, no new language, and no architectural decisions that foreclose Path C later. Idempotent tool handlers are the one thing you must do no matter what, because every heavier path still assumes them. Make the minimal correct thing first; let real multi-user demand justify Temporal or LangGraph Cloud when and if it arrives.

**The one thing Ian is most likely to underestimate.** Not Temporal complexity — Ian will spot that. The thing to watch: **replay semantics for tool calls that already mutated the dossier.** Every durable path above treats a replayed step as cheap; Vellum's tool calls are not cheap — they change the document the user is about to read. One accidental double-`upsert_section` on a crash-recover and the plan-diff sidebar lies to the user. Idempotency on `tool_use_id` is cheap to build and load-bearing to trust; it is the one invisible failure mode that will embarrass the product if skipped.

---

## References

URLs are where to *look*, not a claim I verified the current page in this session.

- Temporal Python SDK — https://docs.temporal.io/dev-guide/python
- Temporal determinism — https://docs.temporal.io/workflows#deterministic-constraints
- Restate — https://docs.restate.dev/
- Inngest Python SDK — https://www.inngest.com/docs/reference/python
- Inngest `waitForEvent` — https://www.inngest.com/docs/features/inngest-functions/steps-workflows/wait-for-event
- DBOS Transact — https://docs.dbos.dev/
- LangGraph persistence — https://langchain-ai.github.io/langgraph/concepts/persistence/
- LangGraph HITL — https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
- LangGraph Platform — https://langchain-ai.github.io/langgraph/concepts/langgraph_platform/
- OpenAI Assistants — https://platform.openai.com/docs/assistants/overview
- Anthropic Batches — https://docs.anthropic.com/en/docs/build-with-claude/batch-processing
- Anthropic web search tool — https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool
- Claude Agent SDK — https://docs.anthropic.com/en/docs/agent-sdk/
- Anthropic spend caps — https://console.anthropic.com/
- APScheduler — https://apscheduler.readthedocs.io/
- arq — https://arq-docs.helpmanual.io/
- Celery — https://docs.celeryq.dev/
- Dramatiq — https://dramatiq.io/

Sources flagged "reported" were last seen before April 2026. Read the current docs page before committing architecture.
