# Vellum — Consolidated Deep-Dive Brief

**Source:** 5 subagent reports (`01-backend-runtime.md` through `05-tests-submission.md`), ~210 KB of analysis across every backend, frontend, test, and submission-asset file. Read against `D:\projects\Vellum` on 2026-08-02. All line refs are `file_path:line_number`.

**Project:** Solo-built, 5-day submission to Anthropic's "Built with Opus 4.7" hackathon. "A durable, multi-agent investigation engine where the dossier is the primary surface, not chat."

---

## TL;DR

1. **The thesis is real, not a sales pitch.** The "no chat to the user" invariant is enforced in three layers (prompt, runtime, sub-prompt), the 30-tool typed surface genuinely drives every user-visible mutation, and the dossier-state snapshot is the actual prompt prefix. Most projects at this scale rely on convention; Vellum relies on a Pydantic-bounded `if not tool_uses: discard prose` branch at `agent/runtime.py:282-290`.
2. **The README undersells and oversells in different places.** It understates counts (30 dossier tools + 7 intake tools = 37, not 27; 22 tables, not 17; 323 test symbols across 36 files, not 230+ across 31) and hides a real coverage gap (the sleep-mode scheduler has no dedicated test file). It also makes a few phrasings more load-bearing than the code supports ("synchronous" sub-investigation return, "reactive wake within one tick").
3. **There are about a dozen honest engineering wins that a 5-day solo project has no business having.** Per-dossier `asyncio.Task` with a schema-level partial unique index backing it, idempotency by `tool_use_id`, tier-persisted stuck detection, server-side cadence enforcement that prevents the "agent forgot to wake up" failure mode, a separate intake agent with its own tool surface and prose speech, a Remotion video pipeline (30+ compositions) that mirrors the live design tokens. The base is real.
4. **There are also a dozen honest sharp edges.** Dead `mark_needs_input_resolved` and missing `mark_progress` in `stuck.py`. 200-turn `AGENT_MAX_TURNS` as the hard backstop. In-memory stuck state lost on every wake (only the tier survives). `asyncio.run()` inside an event loop in `sub_runtime.py:756-783`. 17 thin per-entity store files. A redundant `dossiers.investigation_plan` JSON column shadowing `plan_items`. A `next_actions.priority` type mismatch (REAL in SQL, `int` in API). 146 KB of `types.generated.ts` no one imports. No frontend tests. None of these are bugs; all are real things a maintainer would clean up.

---

## 1. What Vellum actually is

A manual agentic loop over the Anthropic Messages API (`agent/runtime.py:129-499`, ~370 LOC) that turns a Pydantic schema into the user's persistent surface. The user opens an intake conversation; the intake agent (`claude-sonnet-4-6`) gathers 5 fields and commits; the dossier agent (`claude-opus-4-7`) takes over and writes through 30 typed tools; the user returns to find a structured case file with confident/provisional/blocked sections, open decision points, and a right-rail audit log of every tool call.

Five layered subsystems make it durable:

| Subsystem | File(s) | Job |
|---|---|---|
| **Runtime** | `agent/runtime.py`, `agent/sub_runtime.py` | Manual turn loop over `client.messages.stream()`. Tool dispatch is off-thread via `asyncio.to_thread`. Tool idempotency by `tool_use_id` in the `tool_invocations` table. `pause_turn` continuation without re-snapshotting. Haiku-driven compaction at ~80k input tokens. |
| **Orchestrator** | `agent/orchestrator.py` | One `asyncio.Task` per dossier. `AgentAlreadyRunning` and `AgentCapacityExceeded` guards. 30s graceful shutdown. |
| **Scheduler** | `agent/scheduler.py` | 30s polling loop over `dossiers.wake_pending` / `wake_at`. Pre-creates a work session, then calls orchestrator. On `AgentAlreadyRunning`/`AgentCapacityExceeded` it closes the pre-created session and **keeps the wake flags set** — the comment at `scheduler.py:202-216` is one of the most important lines in the repo. |
| **Stuck detection** | `agent/stuck.py` (~890 LOC) | Loop hashing with exact args, same-tool-no-progress heuristic, per-section revision counters, per-section/per-session token budgets, three-tier escalation. `stuck_escalation_count` is the one field that survives sleep/wake. |
| **Lifecycle** | `lifecycle.py` | Boot-time reconciliation of orphaned `work_sessions`; stale-intake cleanup; closed-loop on the partial unique indexes. |

The two **partial unique indexes** (`db.py:144-147`) are the most interesting design choice in the schema. They make "at most one open session per dossier" and "at most one open plan_approval per dossier" DB-level invariants — no code bug can quietly violate them.

---

## 2. What's genuinely strong

These are not "good for a hackathon" — they would be good in a production system.

1. **Closed-loop enforcement is real, layered, and tested.** Prompt says "tool calls only." Runtime drops the prose if the model ends the turn with text only (`runtime.py:282-290`). Sub-prompt repeats the rule. `_helpers.py:27-57` strips tool markup regex from string fields as a safety net. `test_runtime_v2.py:643-661` pins the state-snapshot contract; `test_runtime_v2.py:407-421` pins the `pause_turn` handling. The invariant is load-bearing in the right places.
2. **Tool idempotency by `tool_use_id`.** The runtime checks `storage.get_tool_invocation(tool_use_id)` before dispatch (`runtime.py:571-586`). The handler is reached only on first call. Replays are a no-op. This is the single mechanism that makes the whole system crash- and retry-safe.
3. **The two partial unique indexes.** `idx_work_sessions_one_active_per_dossier` and `idx_decision_points_one_open_plan_approval_per_dossier`. The code-level guards are belt-and-braces; the schema is the hard guarantee.
4. **Stuck-tier persistence across sleep/wake.** `dossiers.stuck_escalation_count` is a single `INTEGER` column. A flaky agent that always trips the same heuristic reaches tier 3 across wake cycles without the user re-babysitting. The in-memory loop/section/session counters reset, but the *escalation level* survives (`stuck.py:125-131`).
5. **Server-side cadence enforcement (H-23).** `runtime.py:466-495` — if the agent ends a session without delivering AND without calling `schedule_wake`, the runtime stamps `wake_at` based on the dossier's `check_in_policy.cadence`. This removes a whole class of "agent died and the dossier never woke up" bugs.
6. **Trust-mode auto-pilot writes to the reasoning trail.** The auto-decision is *visible* to the user later via `[trust_mode:auto]` reasoning notes. Not silent. The alternative — quietly picking the recommended option — would erode trust.
7. **Pydantic as the schema source.** `models.py` is the API shape, the SQLite row, and the Anthropic tool schema. Adding a required field to `WorkingTheory` will fail row parsing on existing rows. The coupling is real and the right kind of strict.
8. **Intake as a separate, prose-speaking agent.** The intake runtime is a deliberately smaller module (`intake/runtime.py`, ~14 KB) with its own 7-tool closed surface, 10-iteration cap per turn, and prose speech. The dossier agent cannot write to the dossier until intake commits. The split is the heart of the closed-loop claim.
9. **The visit-before-diff timing pattern.** `DossierPage.tsx:54-67` is a 9-line JSDoc explaining how the "since your last visit" sidebar snapshots the change log *before* the `POST /visit` invalidates it. `useChangeLogSinceVisit` (`hooks.ts:77-128`) is a hand-rolled wrapper over `useChangeLog` that captures the first non-undefined response and never updates. Genuinely clever and genuinely necessary.
10. **The Remotion second deliverable.** `submission-assets/remotion/` is a real Node/Remotion project with 30+ named render targets, design tokens lifted from `frontend/tailwind.config.js` so cuts between live `/stress` and Remotion don't break, and per-case variants for stress2/stress3. The decision to build a *pipeline* (not a single video) means the narrations are editably re-renderable.

---

## 3. What's risky / weak

Ranked by impact, not by ease of fix.

1. **The sleep-mode scheduler has no dedicated test file.** I read the conftest, the orchestrator tests, the resume tests, the self-heal tests, and the day-3 lifecycle test. None of them drive the actual `_run` poll loop in `agent/scheduler.py:88-105`. The 30s "reactive wake within one tick" claim in the README is plausible from the code but not pinned by a test. **For a 5-day solo project this is the single highest-value test you could add.**
2. **The 200-turn `AGENT_MAX_TURNS` cap is a number someone picked.** `config.py:73-75`. A reviewer would ask whether 200 turns is a real safety net or a guess. With prompt caching and 32k output tokens, a 200-turn run can plausibly burn through $30+ on Opus 4.7. The soft budget signals are good; the hard backstop deserves a comment about why 200.
3. **In-memory stuck state is lost on every wake.** Only the `stuck_escalation_count` survives. A "last_signal_kind" column on `dossiers` would let the agent re-surface a stuck-different-reason decision on the next wake, instead of appearing to start fresh.
4. **Dead code in `stuck.py`.** `mark_needs_input_resolved` (`stuck.py:776-784`) is defined, called from the self-test, and never reached by production. The docstring at `stuck.py:36-39` references a `mark_progress` function that does not exist in the repo. The actual reset path is the broad `.clear()` in `record_tool_call` for `add_artifact` and `spawn_sub_investigation`. **Either wire it up or delete the function and the comment.**
5. **The `asyncio.run()`-inside-event-loop dance.** `sub_runtime.py:756-783`. The README describes sub-investigations as "synchronous return to parent" but the implementation inlines them inside the parent's coroutine AND has a fallback that re-enters the loop. The seam is subtle; a future contributor who adds a second `await` upstream will break it.
6. **The 17 thin per-entity store files.** `wake_store.py` (5 KB), `user_note_store.py` (3 KB), `budget_store.py` (3 KB) are thin enough that the per-file indirection is more friction than value. `dossier_store.py` (34 KB), `plan_items_store.py` (13 KB), and `sub_investigation_store.py` (12 KB) earn their split. A consolidation pass would clean the seam.
7. **Redundant storage.** `dossiers.investigation_plan` is a JSON column shadowed by the first-class `plan_items` table. `dossier_store.get_dossier` (`dossier_store.py:82-86`) merges them. Keeping the column invites drift.
8. **Type mismatch in `next_actions.priority`.** Schema is `REAL NOT NULL`; API model is `priority: int = 0` (`models.py:131`). Pydantic's `int` is a subtype of `float`, so the round-trip works. Subtle. Should be a CHECK constraint or a one-line schema fix.
9. **Missing FK constraints where they would matter.** `intake_sessions.dossier_id`, `sub_investigations.parent_section_id`, `artifacts.supersedes`, `change_log.section_id`, `agent_turns.sub_investigation_id` are all stored as `TEXT` without FK. Each is a plausible "the system would just keep working with a stale string" failure mode. May be intentional (avoiding cascade-delete cycles), but deserves a comment.
10. **Unbounded JSON columns.** `dossiers.debrief`, `working_theory`, `premise_challenge`, `investigation_plan`, `out_of_scope` — all unbounded `str`/`list`. A single tool call can write a 1 MB string to `working_theory.why`. No app-level cap, no DB-level cap.
11. **No retention policy on append-only tables.** `tool_invocations`, `agent_turns`, `investigation_log`, `reasoning_trail`, `change_log`, `intake_messages` all grow unbounded. 30 tools × 200 max turns × multiple sessions = a real DB weight over time. No TTL, no archival.
12. **The frontend has no tests.** The README's "230+ test functions across 31 files" is all backend. A refactor to `InvestigationLogSidebar` (548 LOC, the biggest frontend file) could break the day-bucket grouping and no test would catch it.
13. **The 146 KB `types.generated.ts` is dead weight.** Per the frontend deep-dive, *zero* files import from it. The `npm run types:gen` script documented in `README.md:150-156` doesn't exist in `package.json:6-10`. The hand-maintained `types.ts` is the actual source of truth. The README describes a workflow that isn't wired up.
14. **Two `SectionCard` and two `SourceList` components.** The "dossier" path and the "sections" path render the same `DossierFull` data through two different visual treatments. `DemoPage` uses one, `DossierPage` uses the other. A future contributor will copy the wrong one and ship a visual regression.
15. **`common/` directory has unused primitives.** `Divider.tsx` (15 LOC, zero importers), `SourceList.tsx` (duplicated), `StateBadge.tsx` and `Badge.tsx` (zero importers in places where they're needed — pages hand-roll `bg-accent text-paper ... rounded px-4 py-2`).
16. **The `_PROGRESS_TOOL_NAMES` whitelist in `stuck.py:182-199` is a maintenance trap.** A new "actually-moves-the-investigation" tool that someone forgets to add will silently inflate the no-progress counter.

---

## 4. README claims vs. code reality

A scorecard for the README's load-bearing assertions. Each row cites where to verify.

| README claim | Reality | Source |
|---|---|---|
| "27 typed tools" | **37** (30 dossier + 7 intake) | `tools/handlers.py:681-715`; `intake/tools.py:311-319` |
| "17-table relational schema" | **22** (17 if you count dossier-domain only) | `schema.sql` line enumeration |
| "230+ test functions across 31 files" | **323 `def test_` symbols across 36 files** | `grep` across `tests/`, `conftest.py`, `__init__.py` |
| "It streams `client.messages.stream(max_tokens=32000)`" | Verified | `agent/runtime.py:129-499` |
| "Handles Anthropic's `pause_turn` for server-side `web_search`" | Verified, tested | `runtime.py:407-421` (`test_pause_turn_does_not_count_as_ended`) |
| "Idempotent, replay-safe tool dispatch" | Verified, tested | `runtime.py:571-586`; `test_runtime_v2.py:281-335` |
| "Multi-dossier orchestrator with bounded concurrency" | Verified, tested | `agent/orchestrator.py`; `test_orchestrator.py` |
| "Sleep-mode scheduler... 30s polling" | Verified in code; **no dedicated test** | `agent/scheduler.py:88-105` |
| "Recursive sub-investigations... returns a `return_summary`" | Verified; sub-investigations are inlined in the parent's coroutine, with a documented hole (`:700-703`) | `agent/sub_runtime.py` |
| "Tiered stuck detection (~870 LOC)" | Verified; `stuck.py:1-50` docstring; three-tier ladder at `stuck.py:343-394` | |
| "Crash recovery at startup" | Verified, tested | `lifecycle.py:121-206`; `test_day3_lifecycle.py:250-499`; `test_self_heal.py` |
| "Separate intake agent" | Verified | `intake/runtime.py` (14 KB), separate prompt/tools/storage/models |
| "Soft-budget economics with per-model pricing" | Verified | `config.py` pricing table; `telemetry.py`; `budget_accounting` |
| "Trust-mode auto-pilot" | Verified, audited in reasoning_trail | `runtime.py:680-708, 800-813` |
| "The agent refuses to propose a number until..." | Verified at runtime (`runtime.py:282-290`); system prompt is opinionated | `agent/prompt.py` |
| "All output flows through ~27 typed tools" | Slight slip — actually ~30, plus 4 JIT read-only tools (`get_section`, `list_sections`, `get_artifact`, `get_reasoning_window`) | |
| "Sub-investigations return findings synchronously" | True *by implementation* (inlined in parent coroutine) but not pinned by a test | `sub_runtime.py:81-87` |
| "Crash-resume picks up orphaned sessions on boot" | Verified | `lifecycle.reconcile_at_startup()` |
| "No notifications, no status updates" | True in design; the 3s polling at the activity indicator is the one "is the agent alive" affordance | `AgentActivityIndicator.tsx:31-37` |
| "Built solo in 5 days" | At the limit of believability given the surface area. Either a remarkable 5 days or longer than the README admits. | — |

The notable **deltas from the README** are: tool/table/test counts are all understated; the scheduler polling loop is unexercised by tests; the synchronous sub-investigation return is an implementation detail, not a tested contract.

---

## 5. Test & quality posture

The 323-test suite is **real but unevenly distributed**.

**Thick coverage:**
- `test_stuck.py` (17 tests) — every signal kind has a dedicated test. Exempt-tool carve-outs are pinned.
- `test_sub_runtime.py` (9), `test_sub_investigations.py` (10), `test_sub_completion_reliability.py` (8) — sub-investigation storage, runtime, and a named-bug regression suite (`test_sub_completion_reliability.py:1-23` documents the live dossier id `dos_83702bf49194` and the failure mode).
- `test_plan_items.py` (19), `test_plan_approval.py` (11) — plan lifecycle.
- `test_tool_surface.py` (25) — every tool description must be 80–700 chars; critical tools must contain `"example"` or `"good:"`. Behavior-by-prompt contract.
- `test_runtime_v2.py` (16) — dispatch loop, state snapshot contract, `pause_turn`, idempotency.

**Thin coverage:**
- **No scheduler test** — `agent/scheduler.py:88-265` is the sleep-mode wake loop. `test_resume.py` covers post-crash reconciliation, but the `_run` poll and contention handling are not visibly exercised.
- **No frontend tests** — `package.json:18-27` has no `vitest`/`jest`.
- **Auth** — `test_api_auth.py` (3 tests) for the optional `VELLUM_API_TOKEN` bearer-token path.
- **Telemetry** — `test_telemetry.py` (9), `test_config_cost.py` (10) — adequate, not thick.

**Patterns worth calling out:**
- The `_isolate_tool_hooks` autouse fixture (`conftest.py:19-40`) is sophisticated. The docstring confesses an actual bug — `from vellum.main import create_app` appends a telemetry hook to `TOOL_HOOKS` as a side effect, and without the snapshot the sentinel at `test_runtime_hooks.py:138-144` would fail non-deterministically.
- `test_day*_*.py` naming is a development log. `test_day1_roundtrip.py` and `test_day3_lifecycle.py` are 21 KB and 23 KB *single-test* files. They work for the author as a milestone record; they hurt a reader who doesn't know the day mapping.
- `fresh_db` is redefined four times with subtly different shapes (`conftest.py:43-66` vs `test_day1_roundtrip.py:22-86` vs `test_plan_items.py:25-48` vs `test_resume.py:73-110`).
- The `_SCRIPT_QUEUE` + `_ScriptedClient` pattern in `test_day3_lifecycle.py:106-116` is a **textbook LLM mock** — the test author knew `client.messages.stream()` + `get_final_message()` is the production shape, not `.create()`.
- Flakiness discipline is high: no `time.sleep`/`asyncio.sleep` in critical-path tests. The only timing-dependent test uses a 3s bound on a synthetic LLM.

**Operational scripts (the hidden strength):**
- `scripts/abandon_zombie_subs.py` — production-grade cleanup with dry-run and `--force` guards. The docstring narrates the live bug it fixes.
- `scripts/day2_smoke.py` — the deliverable smoke test, 28 KB, with `DigestStats` exit codes, canned-fact matchers, and a live progress ticker. `test_day2_autonomous.py:72-189` has structural tests for its public surface so it can't silently regress.
- `scripts/verify_phase4_run.py` — 9 acceptance-criteria checks against a live backend.
- `scripts/tail_tool_log.py` — color-highlighted `tail -f`.

None of these are wired into `lifecycle.py` or `orchestrator.py`. They're dev/operator tools, not production hooks — but their presence is the strongest evidence this is a real product, not a demo.

---

## 6. Submission / demo story

**What's strong:**
- `HACKATHON_SUBMISSION.md:24-40` — the demo path uses `/stress`, a static fixture, no API key required. Reproducible for judges.
- `HACKATHON_SUBMISSION.md:60-68` — "What is not in scope" lists 6 things it doesn't do. The most credible thing a hackathon submission can say.
- The narrations are production-paced (2:50–3:00) with realistic live-capture allocations (~60–90s of live `/stress`).
- The Remotion project is a real second deliverable, with design tokens synced to `frontend/tailwind.config.js` so the cuts between live and rendered footage don't visually break.
- The on-disk artifacts are organized by case study (14 stress2 screenshots, 18 stress3, 12 stress2 video clips, 12 stress3, 6 PNG logo variants, final 269 MB `Sequence 01.mp4`).
- The 3 fixture cases (debt, fertility, mortgage) cover different domains and demonstrate the thesis generalizes.

**What's risky (rhetorically true, literally false):**
- `NARRATION.md:0:30` says "Here is that as the real product surface" and points to `/stress`. The reality: `/stress` is `frontend/src/mocks/stressCaseFile.ts` — a hand-written fixture, not a live dossier. The framing is **rhetorically true** (it IS the dossier page rendering a dossier) and **literally false** (it is not produced by the agent). A judge who pauses to check the URL will see this; a judge who watches the video once through will not.
- The `stress2` and `stress3` cases (fertility, mortgage) are described in the demo as if they were real agent output. They are not. Both are static TypeScript fixtures in `frontend/src/mocks/`.
- `ONEPAGE.md:13` describes the scheduler as a "30-second polling asyncio coroutine" with "reactive wake within one tick." The polling is verified; "reactive within one tick" is testable but not pinned by a test.

**What the docs site does well:**
- `docs/index.html` is a single 76 KB self-contained file with inline CSS/JS and one inline SVG architecture diagram. Designed reading experience with five named sections (Thesis, How it's different, The dossier, Under the hood, Run it locally).
- The dossier section is a 267-line hand-recreation of the `/stress` route, not a screenshot. Includes premise challenge, working theory, plan, sub-investigations, needs-input, decision points, and a "since your last visit" sidebar. The closing line: "Every block above is a rendered output of a typed tool call. The agent cannot write anything else — no chat reply, no loose prose, no 'thoughts'. The dossier is the transcript."

**What the docs site omits:**
- The `problem_statements.png` in `submission-assets/` is **not referenced anywhere** in the docs. Zero matches.
- No live screenshots of the running app.
- No interactive demo (zero client-side JS).
- No problem-statement gallery.
- The site reads as a long design doc, not a marketing tour. The footer line "# no backend or API key needed for the /stress fixture" is a quiet admission that the docs are *showing* the product, not *selling* it.

---

## 7. Cross-cutting observations

These came up in two or more of the per-area reports.

- **Pydantic v2 is doing real work.** Type coercion (`int → float` round-tripping `next_actions.priority`), the partial unique index dependency, the row-parser-on-read pattern in `storage/_helpers.py`, the tool-schema generation in `tools/handlers.py:1074-1082`. The codebase commits to it; the seam is clean.
- **The dossier state is the prompt.** `runtime.py:233` keeps `state.messages` as the conversation history, and the dossier snapshot is prepended on every turn. `test_runtime_v2.py:643-661` is a load-bearing test — it pins this contract. If a future refactor accidentally stops prepending, that test fails loudly.
- **The 3s polling choice is deliberate and defensible.** For a single-user localhost app, polling is simpler than SSE, degrades gracefully (the `retry: false` on `useRunningAgents` and `useResumeState` makes that explicit), and the 1s `setInterval` in `AgentActivityIndicator` smooths the textual counters. A real product would batch or stream.
- **The aesthetic is consistent and intentional.** The hand-curated palette in `tailwind.config.js:6-49`, the `font-serif` for body, the `font-mono uppercase tracking-wide` for metadata, the `border-l-2/4` separators, the print stylesheet. Every component applies the same conventions. There is no design-system dependency (no shadcn, no daisyUI) — it's enforced by hand consistently.
- **The intake UI is best-in-class keyboard handling.** `IntakeInput.tsx:84-93`: Enter submits, Shift+Enter newlines, Cmd/Ctrl+Enter submits, IME composition detection, auto-grow measured by `useLayoutEffect`, optimistic clear with retry-restore, refocus on enable. 130 lines that handle more keyboard cases than most production textareas.
- **Trust-mode auto-decisions are auditable, not hidden.** `[trust_mode:auto]` reasoning notes surface the chosen path and the original signal summary. The user can disable trust mode and the next signal surfaces normally.

---

## 8. Concrete recommendations (priority order)

1. **Add a `test_scheduler.py` with a real poll loop.** Drive `_run` with a fake clock and a `wake_store` pre-populated with three dossiers (one `wake_pending=1`, one `wake_at <= now`, one future `wake_at`). Assert all three behaviors: pre-session creation, contention retries, and the `AgentAlreadyRunning` close-the-precreated-session path. This is the single highest-value test you can add.
2. **Add a "last_signal_kind" column on `dossiers`.** Persist *what* tripped the last stuck signal, not just the count. Lets the next wake re-surface a "stuck-different-reason" decision instead of starting fresh.
3. **Wire or delete `mark_needs_input_resolved` and `mark_progress`.** Aspirational docstrings that don't match the code are a maintenance trap.
4. **Add a CHECK constraint to `next_actions.priority`** to make the REAL/int mismatch a hard error, not a silent one. Or change the SQL to `INTEGER` and the API to `int` and the Pydantic to strict.
5. **Add app-level size caps to unbounded JSON columns** in `dossiers` (debrief, working_theory, premise_challenge). 100 KB per field is a reasonable cap.
6. **Consolidate the thin store files** (`wake_store`, `user_note_store`, `budget_store`, `next_action_store`, `settings_store`, `idempotency_store`) into one or two `storage/light.py` modules. Keep the heavy files (`dossier_store`, `plan_items_store`, `sub_investigation_store`) split.
7. **Drop `dossiers.investigation_plan` after `plan_items` is fully trustworthy.** It's redundant storage that invites drift. The migration sentinel `plan_items_migrated=true` (`db.py:172-219`) is the only place the JSON column is read.
8. **Delete the unused `types.generated.ts` and the README's `Regenerating frontend types` section.** Or wire `client.ts` to read from it and delete `types.ts`. The current state (146 KB of generated code in the bundle, zero importers, no regen script) is the worst of both.
9. **Consolidate the two `SectionCard` paths** (`components/dossier/SectionCard` vs `components/sections/SectionCard`) and the two `SourceList` paths. Pick one render path for the `DossierFull` data; use the live dossier in `DemoPage` with a `readOnlyFixture` prop.
10. **Replace the `day-N` test file names** with behavior-named ones. `test_runtime.py`, `test_lifecycle.py`, `test_intake.py`, `test_autonomous.py`. Keep the day docstring at the top of each file as a development-log reference.
11. **Add `vitest` + 5-10 critical frontend tests.** `InvestigationLogSidebar` day-bucket grouping, `useChangeLogSinceVisit` snapshot, `IntakeInput` IME composition, `AgentActivityIndicator` derive, `PlanDiffSidebarView` category ordering. The infrastructure cost is small; the regression surface is real.
12. **Add a one-line comment to `AGENT_MAX_TURNS=200`** explaining the choice. Even a "this is a backstop; budget signals should fire first" gives a reviewer something to anchor on.

---

## 9. Closing take

For a 5-day solo project, Vellum is *unusually* well-built. The closed-loop enforcement is real, the durability subsystems are layered correctly (orchestrator + scheduler + stuck + lifecycle + idempotency table), the schema has DB-level invariants where they matter, and the frontend maintains a tight aesthetic without a design-system dependency. The Remotion pipeline as a second deliverable is the kind of decision a one-person team only makes when they understand the difference between a video and a video pipeline.

The 16 sharp edges listed in §3 are all honest maintenance items, not design failures. Most of them would have been caught by a week of code review. A handful — the missing scheduler test, the dead `mark_needs_input_resolved` / `mark_progress`, the redundant `investigation_plan` column, the unused `types.generated.ts` — are the ones worth doing first because they would compound if left for a year.

The thesis holds up. "A durable investigation system where the dossier is the primary surface, not chat" is not marketing copy — it's the load-bearing claim of the runtime, the schema, the closed tool surface, the visit-before-diff timing pattern, and the 30-second polling cadence. The right next move is a focused 2-week cleanup pass to convert the README's "at the limit of believability" surface into one a maintainer could read with full confidence.

---

**Source reports (read alongside this brief):**
- `D:\projects\Vellum\notes\deep-dive\01-backend-runtime.md` (~36 KB) — turn loop, sub-investigations, compaction, telemetry, system prompt
- `D:\projects\Vellum\notes\deep-dive\02-durability.md` (~32 KB) — orchestrator, scheduler, stuck detection, lifecycle, trust mode
- `D:\projects\Vellum\notes\deep-dive\03-tools-schema.md` (~55 KB) — 30+7 typed tools, Pydantic as schema, 22-table SQLite, partial unique indexes
- `D:\projects\Vellum\notes\deep-dive\04-frontend-docs.md` (~43 KB) — dossier page, polling, intake UI, mock fixtures, the 146 KB dead `types.generated.ts`
- `D:\projects\Vellum\notes\deep-dive\05-tests-submission.md` (~44 KB) — 323 tests, scheduler coverage gap, the four operational scripts, the Remotion pipeline, the narrations
