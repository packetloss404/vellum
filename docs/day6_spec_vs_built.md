# Day 6 — Spec vs. Built (honest audit)

_Author: spec-vs-built review agent. Scope: read the brief, read the code,
read the live-run diagnosis, grade what actually shipped. This is a peer
review, not a promo._

---

## 1. What the brief actually asked for

Vellum is supposed to be a **durable-thinking tool** for consequential
problems. The unit of work is a **dossier** (structured, typed,
document-like) — not a chat session. An agent does a real investigation
against that dossier over hours or days, and the user returns on their
own schedule to a **packet** they can act on. The dossier is the
destination; the agent is quiet; the user sees progress as
plan-diff "since your last visit" on re-entry.

The product stance is opinionated. Six non-negotiables from the brief /
memory / v1→v2 notes:

1. **Premise pushback** — the agent challenges the framing before answering.
   "Pushback on premises is the thesis, not a feature."
2. **Structured writes only** — the agent mutates the dossier only through
   tool calls (`upsert_section`, `flag_needs_input`, `add_artifact`, …); free
   prose evaporates.
3. **Sub-investigations are first-class** — v2 promoted the agent from
   memo-writer to investigator with typed `sub_investigations`, `artifacts`,
   `investigation_plan`, typed `investigation_log`, `considered_and_rejected`.
4. **Plan-diff between visits** — change_log resets per user visit; a
   sidebar surfaces "what changed since you were last here".
5. **Quiet by default** — no pings, no streams; the agent surfaces only via
   `needs_input`, `decision_point`, `declare_stuck`.
6. **Stuck detection** — soft budgets + repeated-call heuristics surface a
   decision_point; the agent is never cut off mid-thought.
7. **Packet not page** — the deliverable is usable objects (letters,
   checklists, scripts), not prose. Substance bar: ≥3 subs, ≥20 sources,
   ≥1 artifact.

Hero demo: credit-card-debt negotiation for a friend's deceased mother. The
agent refuses to pick an opening % until it has confirmed the debt is owed
at all.

---

## 2. Scorecard against the non-negotiables

| # | Brief requires | Code does | Live run shows | Grade |
|---|---|---|---|---|
| 1 | Premise pushback — refuse to answer mis-framed question. | `agent/prompt.py:33-54` has explicit "Push back on the premise" section with the debt example spelled out; intake prompt has "Premise pushback (light)" at `intake/prompt.py:60-65`. | Post-streaming-fix run on `dos_83702bf49194`: first section title literally **"The question is almost certainly the wrong question"**, debrief opens with "Pushed back on the premise…". Unambiguous. | **A** |
| 2 | Structured writes only — prose without a tool call is discarded. | `runtime.py:156-163` discards any turn that ends with no tool_use blocks. System prompt reinforces it (`prompt.py:115-121`). | Confirmed: no prose leaks on the demo run; every user-visible artifact is a typed row. | **A** |
| 3 | Sub-investigations first-class — spawned with narrowed scope, own tool subset. | `agent/sub_runtime.py` (600 LOC) implements a real sub-loop: narrow tool allowlist (`SUB_TOOL_ALLOWLIST` at `sub_runtime.py:61-68`), dedicated work_session for token accounting (line 315), ContextVar sub-id injection (line 85), depth cap 1, force-completion after 2 prods (line 93, 429-460), separate `sub_prompt.py`. | Demo spawned 3 subs on the right questions (jurisdictional exposure, FDCPA/Reg F, non-probate clawback). **But**: all 3 subs stayed in `state=running` with `return_summary=null` — the sub-completion persistence path failed. Sub-output did inform main (sources attributed to subs), but the subs visibly "never finished". | **C+** |
| 4 | Plan-diff sidebar — change_log since last visit. | `storage.py` maintains `change_log` keyed by `work_session_id`; `routes.py:57-59` exposes `/change-log`. Frontend: `PlanDiffSidebar.tsx`, `PlanDiffSidebarView.tsx`, `ChangeEntry.tsx` (359 LOC). `DossierPage.tsx:48-97` documents and implements the "visit-before-diff" fetch ordering. | Not explicitly measured in the two live runs. Visually present in the stress fixture. Plumbing is solid; unverified under real load because the agent never completed a full arc across visits. | **B** |
| 5 | Quiet by default — no pings, no "working on it". | Prompt forbids narration (`prompt.py:128-138`). Runtime has no push channel. `flag_needs_input`, `flag_decision_point`, `declare_stuck` are the only surfaces. | Run 1 marked `delivered` prematurely. Run 2 self-declared `delivered` **while 3 subs were still in `running` state** — violates the prompt's own "not done while blocked/incomplete" rule. The agent is quiet in the no-pings sense, but its sense of "done" is eager. | **C** |
| 6 | Stuck detection — soft, never cuts off. | `agent/stuck.py` (676 LOC): exact-args loop counter, section-budget, session-budget (`_SESSION_BUDGET_MULTIPLIER=15`), revision stall (`_REVISION_STALL_THRESHOLD=5`), same-tool-no-progress heuristic, exempt sets for iterative tools (`_EXEMPT_FROM_LOOP = {update_debrief, update_investigation_plan}`). Runtime surfaces as `decision_point` via `check_stuck`; never raises, never terminates (`runtime.py:224-236`). Dedupe per signal. | Not exercised in either live run (subs and main both under threshold). System is built but demo never stressed it. | **B** (well-engineered but unvalidated) |
| 7 | Packet not page — artifact bar, ≥1 per investigation. | `add_artifact` tool + `ArtifactKind` enum (letter/script/checklist/...) in `models.py:352-399`. `update_debrief` mandatory before `mark_investigation_delivered` (per prompt at `prompt.py:123-126`). | Run 2 produced 2 artifacts (letter + checklist); both visible on the dossier. Substance bar: subs PASS (3 ≥ 3), **sources FAIL (15 < 20)**, artifacts PASS. 2 of 3 bars met autonomously. | **B** |
| 8 | Substance bar met **autonomously** (implicit, from scripts/day2_smoke.py thresholds). | Thresholds encoded in smoke digest; prompt states them. | Only met after `--auto-resolve` simulated the user for the plan-approval DP and a richly-worded `needs_input`. Without user simulation, the demo stalls after plan drafting. | **C** |

**Overall weighted grade: B−.** Strong on framing and structured writes,
weak on "know when you're done" and sub-completion plumbing. See §6.

---

## 3. What exceeds spec

(These weren't in the brief but shipped anyway. Assessment of each.)

- **Telemetry / session stats endpoint** (`agent/telemetry.py:163-259`,
  `GET /api/work-sessions/{id}/stats`). Aggregates per-session tool
  counts, source count, sub count, artifact count, tokens, duration.
  **Genuine improvement** — it's the primitive that makes the substance
  bar checkable without bespoke scripts. Cheap to build, high leverage.

- **Per-tool-call JSON log via `TOOL_HOOKS`** (`telemetry.py:_register_hook`,
  `VELLUM_TOOL_LOG_PATH` env var). **Genuine improvement** — essential
  for debugging live runs on day 5; was load-bearing for the diagnosis.

- **Resume-state endpoint** (`GET /dossiers/{id}/resume-state`,
  `agent_routes.py:173-180`). Returns the compact info the UI needs to
  decide whether to offer a "Resume" CTA. **Genuine** — frontend needs
  it to avoid offering Resume when a session is already open.

- **Computed dossier-status endpoint** (`GET /dossiers/{id}/status`,
  `agent_routes.py:186-198`). Precedence rules in `storage.get_dossier_status`
  collapse `delivered / running / waiting_plan_approval / waiting_input /
  stuck / idle` into one authoritative field. **Genuine** — the header
  pill needs a single truth source; alternative was scattered logic in
  the UI.

- **Fleet view** (`GET /api/agents/running`, `orchestrator.list_running`,
  `list_active`). **Marginal** — justifiable as day-2 multi-dossier
  concurrency groundwork. Unused by the hero UI; will matter once more
  than one dossier ever runs in parallel.

- **Stress fixture + `/stress` dev route** (`pages/StressPage.tsx`,
  `mocks/stressCaseFile.ts`). A separate pre-populated QueryClient
  mounting `DossierPage` against a "worst-case" fixture. **Useful during
  build, scope creep for shipped product** — it's a dev tool in
  `App.tsx` with a public route. Should be gated behind `import.meta.env.DEV`
  or removed for a real build.

- **Plan-approval `kind` field + auto-approve hook** (`models.py:165`,
  `storage.py:750-752`). When a `decision_point` with `kind="plan_approval"`
  resolves with an approving choice, `approve_investigation_plan` fires
  automatically. **Genuine** — the brief had plan approval as a concept;
  shipping it as one typed flow through the normal decision-point surface
  is clean design.

- **Stuck-detection calibration knobs** (`stuck.py:17-46` rationale block,
  `_EXEMPT_FROM_LOOP`, `_EXEMPT_FROM_NO_PROGRESS`,
  `_REVISION_STALL_THRESHOLD`, `_SESSION_BUDGET_MULTIPLIER`, all config-
  driven). **Mild scope creep** — the calibration is thoughtful and
  earned from a 40-turn run's observed behavior, but 676 LOC of stuck
  detection for a system whose demo never tripped a signal is heavy.
  Say B+ on build quality, D on necessity-for-v1.

- **`--auto-resolve` harness for the smoke script** (`scripts/day2_smoke.py:477-663`).
  Keyword-matched canned answers for the demo's `needs_input`/`decision_point`
  surfaces. **Workaround, not improvement** — exists because the agent
  stalls on blocking surfaces with no user present. It's a concession
  that the autonomous 60-second demo didn't quite land.

- **Lifecycle reconcile at startup** (`lifecycle.py`, 295 LOC). Orphan
  work_session detection + reconcile on process restart. **Genuine** —
  the day-5 diagnosis found real orphan-session failure modes; this is
  the defensive layer.

---

## 4. What falls short

- **Autonomous live runs don't hit the substance bar without human (or
  simulated human) intervention.** Run 1 errored on turn 1 (non-streaming
  SDK guard, 32k max_tokens — `runtime.py:117` pre-streaming). Run 2
  drafted a plan then stalled waiting on approval + `needs_input`. Only
  the "post-streaming-fix + manual-auto-resolve" run produced substance,
  and that's not an autonomous loop — the script simulates a user. The
  brief's "close the laptop, come back, find work done" premise is
  partially built; the "work done without user babysitting" half isn't
  robustly demonstrable.

- **Source count undershoots.** Real run logged 15; debrief claimed
  "~20"; substance bar is ≥20. The model under-logs. Prompt has the
  "every read gets a log" rule (`prompt.py:171`) and tool description
  reinforces it (`handlers.py:471-479`) — still missed. Day-6 fix
  candidate flagged in diagnosis (`day5_live_run_diagnosis.md:501`).

- **Sub-investigation completion persistence is broken.** Demo spawned
  3 subs, all stayed `running`, all had `return_summary=null`.
  `sub_runtime.py:429-460` has a force-complete fallback, but even that
  didn't land — suggests the sub-agent loop errored before the
  force-complete branch, and the `except Exception` best-effort clause
  at `sub_runtime.py:475-498` also failed to persist. The subs' work DID
  reach the dossier (sources attributed), but the sub rows themselves
  read as stuck.

- **`mark_investigation_delivered` fires too eagerly.** The prompt
  explicitly says "Do NOT call mark_investigation_delivered just because
  you are waiting on user input or plan approval" (`prompt.py:154-159`)
  — added at day 5 (`ff3e032 day5: prompt — don't mark_delivered while
  blocked on user`). Still didn't hold: run 2 marked delivered with 3
  subs `running`. The prompt isn't strong enough; there's no runtime
  enforcement. Recommended fix (diagnosis §D): backend-side refusal of
  `status=delivered` transition while any sub is `running`.

- **No runtime enforcement of the plan-approval gate.** Prompt says
  "do not begin substantive work (sources, subs, sections, artifacts)
  until approved" (`prompt.py:69-71`); state snapshot repeats it each
  turn (`prompt.py:304-308`). But `runtime.py` / `handlers.py` don't
  reject `upsert_section` / `spawn_sub_investigation` /
  `log_source_consulted` while `plan.approved_at is None`. An agent
  that ignores the prompt could silently do pre-approval work.
  Flagged in `day5_live_run_diagnosis.md:127-138` as quality risk,
  unpatched.

- **Intake is conversational-structured rather than form-structured.**
  The brief's non-negotiable is "structured data, not prose" — that's
  about the dossier. The brief's stack-decisions say intake is
  "structured conversational chat, not a form". The intake does commit
  typed fields (`intake/tools.py:commit_intake`), and now seeds a
  starter `investigation_plan` (`intake/prompt.py:78-105`). So it
  conforms to the "structured conversational" stance. **But** the
  elicitation is still a linear back-and-forth; there's no structured
  form fallback for a user who knows what they want and hates chatting
  to an intake bot. Meets spec, but feels heavier than necessary for
  repeat users.

- **Artifacts render as markdown prose with a title — grab-and-use-ness
  is uneven.** `ArtifactCard.tsx` (356 LOC) and `ArtifactList.tsx` (213
  LOC) render kind/title/intended_use/content well with a copy button.
  The live-run letter and checklist are usable. Nothing structured
  beyond that — no inline form fields, no "send via email" action, no
  recipient-address placeholder validation. Which is fine; v1 is
  markdown + copy. "Grab-and-use" passes the copy-the-letter test but
  not the fill-in-the-blanks test.

- **Reliable ≥1 artifact unprompted: YES.** Run 2 produced 2 artifacts
  without user prompt. Credit where due; this is a real prompt-behavior
  win.

- **"Quiet" is quiet but "know when you're done" is wobbly.** No pings,
  no narration — quiet passes. Delivered-state self-declaration fires
  too eagerly, twice in two runs. Prompt tightening (commit `ff3e032`)
  helped but didn't fix.

---

## 5. Scope creep

- **Three parallel sidebar/log surfaces**: the in-page `NextActionsList`
  and `ConsideredRejectedList` blocks, the right-rail `PlanDiffSidebar`
  (359 LOC in `ChangeEntry.tsx` alone), and the right-rail
  `InvestigationLogSidebar` (507 LOC). The brief called for one
  plan-diff sidebar. "Investigation log" as a separate first-class
  sidebar overlaps with plan-diff and with the investigation_log typed
  feed surfaced elsewhere. **Overbuilt for v1.** A single merged
  sidebar (diff + log unified) would have done the job.

- **`/stress` dev route lives in production routes**
  (`App.tsx:18,37`). It's useful for FE development against the worst-
  case fixture, but shouldn't be exposed in a shipped build. Should be
  `import.meta.env.DEV ? <Route path="/stress" … /> : null`. Dev-only
  bloat shipping as-is.

- **`/demo` page carries legacy v1 fixture code**
  (`pages/DemoPage.tsx`, `mocks/dossier.ts`). Renders v1 `SectionsList`,
  `RuledOutList`, `ReasoningTrail` — not the v2 surface the real
  dossier page uses (`DebriefBlock`, `PlanBlock`, `SubInvestigationList`,
  `ArtifactList`, `ConsideredRejectedList`). The demo page at `/demo`
  shows a different product than `/dossiers/:id`. Either retire /demo
  or port it to the v2 fixture.

- **676 LOC of stuck detection** (`stuck.py`) for a demo that never
  tripped a signal. The heuristics are well-designed (exempt sets,
  config-driven thresholds, day-5 calibration rationale), but v1 would
  have been fine with the three-identical-tool-call loop detector and
  a session-token cap. Everything beyond is pre-optimizing for stress
  we haven't met.

- **Dual work_session accounting for sub-agents** is correct (brief
  asked for it in v1→v2 notes §5) but the implementation added a
  ContextVar, a handler wrapper, and attribution logic
  (`sub_runtime.py:75-87`, `_inject_sub_id`) — three abstractions where
  "pass sub_id explicitly through the dispatch path" would have been
  one. Works; not elegant.

- **NextAction reordering, completion, and removal REST endpoints**
  (`routes.py:254-292`) — the brief didn't ask for next-action
  reordering UX in v1; the agent sets them in priority order. Building
  4 endpoints for user-side next-action management is scope creep
  unless there's a UI affordance, which there isn't (the
  `NextActionsList` is display-only, 59 LOC).

---

## 6. The honest characterization

**What is Vellum, really?** It is a **structured agent loop with a
notebook-style UI, plus a credible first attempt at an investigator
stance**. The frame-pushback behavior is load-bearing and visible on the
live demo; the typed structure (sub-investigations, artifacts, considered-
and-rejected with `cost_of_error`, investigation_plan, typed investigation_log)
is all real and all plumbed end-to-end through Pydantic → storage →
FastAPI → React. The 14-tool v2 surface exists, the sub-agent actually
runs with a narrower toolset and its own work_session, and the frontend
is serif-forward / warm / document-like rather than chat-y.

**How much of the behavior is the Vellum architecture vs. Opus 4.7 +
web_search?** A lot of the demo's quality is Opus 4.7 doing the smart
thing with a well-aimed prompt. The "The question is almost certainly the
wrong question" section title is the model following the push-back prompt
literally — the architecture didn't force it; the prompt invited it. The
architecture's contribution is (a) making that prose survive (because it's
shaped as a typed section), (b) surfacing it in a document layout where
it reads as a case file rather than a chat, (c) giving the sub-agents a
separate loop so they don't smear into the main, and (d) providing a
plan-approval gate so the user can redirect. That's a meaningful
contribution, but an honest reviewer would say: swap Opus 4.7 for a
lesser model and the substance bar collapses. The product is **Opus 4.7
with rails**, not "an agent architecture that makes a weaker model behave
well".

**What would a code+live-run reviewer honestly say?** Engineering is
careful, the tool surface is coherent, the domain model is the source of
truth, and the runtime story (streaming, sub-runtime, orchestrator, stuck
detection, lifecycle) is thoughtful. The live run on day 5 worked in the
large — premise-pushback landed, artifacts landed — and failed in the
small: subs stuck in running, delivered-too-eagerly, source count short.
For a 6-day build ending on `dos_83702bf49194`, that's legitimately
impressive. For a shippable single-user localhost v1, it's an 80%
product with visible seams around sub-completion and done-detection.
Nothing here is conceptually broken — all the visible failures have a
named fix in the diagnosis doc.

---

## 7. Quality of engineering

**Prototype-quality that is unusually disciplined in a few specific
places, and hand-wavy in a few others.** It's not production-quality
(no auth, no rate limiting, no observability beyond stderr, SQLite,
localhost), but it's significantly better-organized than a 6-day prototype
has any right to be.

Three concrete examples:

- **Schema coherence is real.** `models.py` (513 LOC) is a single Pydantic
  source of truth. `tool_schemas()` in `handlers.py:625-693` derives tool
  JSON Schemas from the same Pydantic models that the API routes and the
  storage layer use. `frontend/src/api/types.ts` is hand-mirrored but
  stays in sync because the v1→v2 notes call out the exact TS drift
  points. That's careful.

- **Runtime boundaries are respected.** `runtime.py:250-262` has a try /
  except / finally where the `finally` closes the work_session and resets
  stuck-detection state regardless of outcome. Exceptions are bagged
  into `RunResult(reason="error", error=...)` rather than raised up into
  the orchestrator. The orchestrator (`orchestrator.py`) documents
  six invariants in its module docstring and enforces them. The
  sub_runtime has its own dedicated session, its own ContextVar, and its
  own force-complete fallback. These are not prototype sensibilities.

- **But**: 676 LOC stuck detection, 600 LOC sub-runtime, 507 LOC
  investigation-log sidebar, 359 LOC change-entry component — individual
  modules are long for v1. `storage.py` is 1936 lines. Several features
  (lifecycle reconcile, telemetry, computed status, resume-state, stuck
  calibration) were built against risks that didn't materialize in the
  demo. That's a v1 engineering-over-build signature: the code is
  production-reasoning-quality but the product hasn't yet exercised a
  tenth of its defensive layers.

**Test discipline is high** (208 tests across 24 files, per
`backend/tests/`). `conftest.py` has autouse isolation for
`TOOL_HOOKS`/`HANDLER_OVERRIDES`. Dedicated day-3 lifecycle integration
test (603 LOC) walks the full open → approve → work → close → reopen
→ resume path. Runtime tests use a mock Anthropic client — no live-API
dependency in unit tests. This is tight for a 6-day build.

**Net**: the code is **disciplined prototype**. A reviewer reading it
fresh would be mildly surprised by the schema coherence and the runtime
care, and mildly surprised by how much of the stuck/lifecycle/telemetry
machinery is untested against real failure modes. Both signals point to
the same thing: the build front-loaded structure and under-invested in
live-run debugging. The day-5 diagnosis doc is the first and only
forensic report; the fixes it names haven't all landed.

---

_End of audit._
