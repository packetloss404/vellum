# Vellum — Cleanup 2 Research: Runtime & Stuck-Detection Refactor

**Scope:** six refactor candidates feeding the second cleanup pass. Read against
`D:\projects\Vellum\backend\vellum\` on 2026-08-02. All citations are
`file_path:line_number`. The five "sharp edge" items from
`notes/deep-dive/00-synthesis.md` §3 are the priority; item 6 (the
`asyncio.run()` dance) and item 4 (`_PLACEHOLDER_V2_SCHEMAS`) are lower
risk but worth a decision now.

A note up front: **the one-shot cleanup pass that produced this folder
already resolved synthesis item #3 in part.** The dead
`mark_needs_input_resolved` function cited at
`notes/deep-dive/02-durability.md:553-562` no longer exists in the tree
(`grep` for `mark_needs_input_resolved` returns only the deep-dive
notes). The aspirational `mark_progress` reference in `stuck.py:36-41`
is still there (and the surrounding docstring is now self-inconsistent
with the code); that's a one-line docstring fix, not a refactor. I
record this here so the project owner doesn't redo the work.

---

## 1. Add `test_scheduler.py` (synthesis #1, highest value)

### Current state

`backend/vellum/agent/scheduler.py:88-105` is the 30s polling loop the
README calls "reactive wake within one tick." The code path is:

- `Scheduler._run` (lines 88-105): outer `while not _stopping` → tick
  → `wait_for(_stopping.wait, timeout=poll_seconds)`.
- `Scheduler._tick` (lines 107-126): read `sleep_mode_enabled` →
  `list_dossiers_ready_to_wake` → for each, `_wake_one`.
- `Scheduler._wake_one` (lines 128-265): the load-bearing path. It
  closes any stale active session, pre-creates a `trigger=scheduled`
  work_session, calls `ORCHESTRATOR.start(dossier_id,
  expected_session_id=pre_created_session_id)`, and on
  `AgentAlreadyRunning` / `AgentCapacityExceeded` *closes the
  pre-created session and keeps `wake_pending` set* (the comment at
  `scheduler.py:202-216` is the canonical late-answer correctness
  contract — per the deep-dive, "one of the most important lines in the
  repo").

No test file exercises this path. `test_resume.py` patches
`ORCHESTRATOR.start` to a no-op, so the HTTP-level `/resume` path is
covered, but the actual poll loop and the contention-with-precreated-
session path are unobserved. `test_self_heal.py` and `test_day3_lifecycle.py`
hit `lifecycle.reconcile_at_startup` and DB recovery, not the
scheduler's behavior.

### Target state

A single `test_scheduler.py` (estimate ~10–14 tests, < 5s total) that
pins the load-bearing behaviors via `asyncio.run` + `monkeypatch` on
`ORCHESTRATOR.start`, matching the pattern in `test_orchestrator.py:72-76`
(where `monkeypatch.setattr(orch_mod, "_runtime_cls", _SleepRuntime)`
swaps in a no-op runtime).

The minimum test plan:

1. **`test_tick_picks_up_wake_pending_dossier`** — seed one dossier
   with `wake_pending=1` via `storage.mark_wake_pending`, run a single
   `_tick` via `asyncio.run(sched._tick())`, assert
   `ORCHESTRATOR.start` was called with the right `dossier_id` AND
   `expected_session_id` matching the pre-created session. Assert
   `wake_pending=0` after the call (cleared via
   `clear_dossier_wake`).
2. **`test_tick_picks_up_due_wake_at_dossier`** — same as above but
   with `wake_at` set to a past ISO timestamp. Assert the wake fires.
3. **`test_tick_skips_future_wake_at_even_with_wake_pending`** —
   pre-set BOTH `wake_at = future` AND `wake_pending=1`; assert
   `ORCHESTRATOR.start` is NOT called (the H-28 path at
   `scheduler.py:139-159`).
4. **`test_tick_skips_quarantined_dossiers`** — set `quarantined_at`
   on a dossier with `wake_pending=1`; assert the scheduler leaves it
   alone.
5. **`test_tick_respects_sleep_mode_disabled`** — set the
   `sleep_mode_enabled` setting to `False`; assert no start calls.
6. **`test_tick_continues_after_tick_exception`** — patch
   `storage.list_dossiers_ready_to_wake` to raise on the first call
   and return `[]` on the second; assert the scheduler does not
   propagate the exception (matches the `try/except` at
   `scheduler.py:96-99`).
7. **`test_wake_one_closes_stale_active_session`** — pre-create an
   active `work_session` for a dossier with `wake_pending=1`; assert
   it gets `end_reason='crashed'` and a new `trigger=scheduled`
   session is created (the `storage.get_active_work_session` path at
   `scheduler.py:165-181`).
8. **`test_wake_one_keeps_wake_pending_on_AgentAlreadyRunning`** —
   the canonical late-answer test. Patch `ORCHESTRATOR.start` to raise
   `AgentAlreadyRunning`. Assert: (a) the pre-created session is
   `end_work_session`'d (no orphan), (b) `wake_pending=1` is
   preserved, (c) the dossier's `wake_at`/`wake_pending` is
   unchanged.
9. **`test_wake_one_keeps_wake_pending_on_AgentCapacityExceeded`** —
   same as #8 but with `AgentCapacityExceeded`.
10. **`test_wake_one_keeps_wake_pending_on_unexpected_exception`** —
    same as #8 but `ORCHESTRATOR.start` raises a generic
    `RuntimeError`. The generic-exception branch at
    `scheduler.py:235-250` must also retain the wake fields.
11. **`test_run_loop_terminates_on_stop`** — start the scheduler,
    call `stop()`, assert `_task is None` and the loop exited
    cleanly.
12. **`test_run_loop_polls_at_poll_seconds_interval`** — set
    `poll_seconds=1` on a fresh `Scheduler`, start it, count the
    number of `_tick` invocations over ~1.05s. Assert ≥ 1 and ≤ 3
    (the loose upper bound absorbs scheduler jitter per the
    orchestrator test's pattern at `test_orchestrator.py:86-122`).

### Migration plan

Each test is independently shippable. The recommended order:

1. Tests #1–#4 (the simple "scheduler picks up the right dossier"
   path). All four use the same fixture: `fresh_db` +
   `_mk_dossier` + `monkeypatch.setattr(ORCHESTRATOR, "start",
   recording_no_op)` following the `_patch_orchestrator_start`
   pattern at `test_resume.py:43-70`.
2. Tests #7 (stale-session recovery). This is the only test that
   actually needs `storage.start_work_session` — the rest stay at the
   orchestrator-mock layer.
3. Tests #8–#10 (the contention / late-answer correctness path).
   These are the load-bearing tests; do them after the basic path
   is solid.
4. Tests #5, #6, #11, #12 (mode switches, exception containment,
   lifecycle). These are regression guards.

### Risk assessment

- **Blast radius:** the new test file touches only test code, no
  production code. The `monkeypatch.setattr(ORCHESTRATOR, "start", ...)`
  pattern is already used in `test_resume.py:69`, so the seam is
  proven.
- **Determinism:** tests #1–#10 use `asyncio.run(sched._tick())`
  directly; no real sleep, no real poll. Test #12 is the only one
  that uses real wall time (~1.05s); the loose upper bound keeps
  flakiness low. Total suite time is well under 5s.
- **Compliance with the 358-tests-stay-green constraint:** zero
  production code changes; only additions.
- **One thing NOT to test:** the `_run` while-loop's exact cadence
  under load. That's an asyncio-implementation detail; testing it
  would be flaky. The "polled at least once" assertion in #12 is the
  right level.

### Effort estimate

**Small.** ~150–200 LOC. The pattern is established by
`test_orchestrator.py` and `test_resume.py`; the new file is mostly
scaffolding four new fixtures (dossier factories, the start-recording
fake, a `Scheduler(poll_seconds=1)` factory) and wiring them together.

### Open questions

- Do we want the new tests to actually call the orchestrator's
  `start()` (with a mocked runtime) to exercise the session
  attribution, or stop at the orchestrator's signature? The former
  is closer to integration; the latter is faster and more focused.
  My read: stop at the orchestrator signature. `test_orchestrator.py`
  already covers the integration.
- Is the new file `test_scheduler.py` or `test_sleep_mode.py`? The
  scheduler is one of two sleep-mode mechanisms (the other is
  `lifecycle.reconcile_at_startup`). I'd go with `test_scheduler.py`
  to match the module name exactly — readers can find it by grep.

---

## 2. Add `last_signal_kind` column on `dossiers` (synthesis #2)

### Current state

`db.py:52` already adds `stuck_escalation_count` via the
`_REQUIRED_COLUMNS` ratchet. The schema row is:

```python
("dossiers", "stuck_escalation_count", "INTEGER NOT NULL DEFAULT 0"),
```

The escalation *count* survives sleep/wake, but the *kind* does not.
`stuck.py:345-396` (`_assign_tier_and_emit`) knows the signal kind
when it bumps the count, but it only persists the count. After a
sleep/wake, a new session loads `stuck_escalation_count=3` and
starts with a fresh `_SessionState`; the system prompt
(`agent/prompt.py:358-551` `build_state_snapshot`) has no way to
mention "the last three times you got stuck, it was the same
heuristic firing."

The user-facing consequence: a flaky agent that always trips
`same_tool_no_progress` re-trips it from scratch after every wake,
with no shared memory of the prior failure mode. A user who
resolves one wake then walks away will see a different stuck signal
on the next wake, which is misleading.

### Target state

Add a new column and wire it through:

1. **`_REQUIRED_COLUMNS` entry** at `db.py:17-58`:
   ```python
   ("dossiers", "last_signal_kind", "TEXT"),
   ```
   NULL-tolerant on existing rows (the ratchet's `ALTER TABLE` handles
   this automatically — see the comment at `db.py:12-16`).

2. **Write side** — add a thin helper in `storage/wake_store.py`
   (which already owns the H-19 persistence pattern at
   `stuck.py:212-247` and the dossier state at
   `wake_store.py:144-156`):
   ```python
   def set_dossier_last_signal_kind(dossier_id, kind: str) -> None: ...
   ```
   Best-effort: a write failure must not break signal emission
   (mirror the `try/except` in `_persist_escalation_count` at
   `stuck.py:237-248`).

3. **Write call** — in `stuck.py:_assign_tier_and_emit` (line 379-383,
   where the daemon thread is spawned for escalation-count
   persistence), add a parallel best-effort write of `kind`. The
   existing daemon thread pattern is the right seam: it already
   means "this happens async after the signal returns, never block
   the runtime."

4. **Read side** — in `agent/prompt.py:build_state_snapshot` (lines
   358-551), add a small "Last stuck signal: {kind}" block to the
   snapshot when the dossier's `last_signal_kind` is non-NULL. The
   block should be small and conditional, surfaced in a place the
   model is likely to read it (e.g. right after the
   `stuck_escalation_count` context that the prompt already
   surfaces, or near the unseen-user-notes block at
   `prompt.py:493-506`).

5. **Test side** — add 2-3 tests in `test_stuck.py` (matching its
   17-test discipline):
   - `test_last_signal_kind_persisted_on_signal` — drive
     `record_tool_call` past `LOOP_DETECTION_THRESHOLD`; assert
     `storage.get_dossier(...).last_signal_kind == "loop"`.
   - `test_last_signal_kind_loads_into_state_snapshot` — call
     `stuck.init_session` then `record_tool_call`; assert
     `prompt.build_state_snapshot` contains a reference to the kind.
   - `test_last_signal_kind_null_for_clean_dossier` — assert
     fresh dossiers have `last_signal_kind IS NULL`.

### Migration plan

1. Add the `_REQUIRED_COLUMNS` row to `db.py` (one-line). This
   applies on next `init_db` and is non-breaking.
2. Add the `set_dossier_last_signal_kind` helper to `wake_store.py`
   (eight lines).
3. Wire the write into `stuck.py:_assign_tier_and_emit` (three lines,
   inside the existing daemon-thread spawn). Re-run all 358 tests.
4. Add the prompt surface in `build_state_snapshot` (5-10 lines).
5. Add tests.

Each step is independently shippable. Steps 1-3 can be a single
commit; step 4 should land after step 3 is stable for at least one
session.

### Risk assessment

- **Blast radius:** the new column is NULL-tolerant, the new helper
  is best-effort, and the prompt surface is conditional. None of
  these changes alter existing behavior for dossiers that have never
  had a stuck signal.
- **Existing behavior:** `stuck_escalation_count` is unchanged. The
  new column is purely additive.
- **Hot path:** the new write goes through the same daemon-thread
  pattern as the existing escalation-count write — no event-loop
  blocking.
- **Backward compat:** the `_REQUIRED_COLUMNS` ratchet at
  `db.py:66-70` does an `ALTER TABLE` for missing columns, so
  existing DBs pick up the new column on next startup.

### Effort estimate

**Small.** 1 + 8 + 3 + 10 + ~30 LOC of tests = ~50 LOC total. The
hardest part is the prompt-surface wording, and even that is a copy
of the existing "unseen user notes" block pattern at
`prompt.py:493-506`.

### Open questions

- Should the column also include the *tier*? (e.g. `"loop@tier_2"`)
  My read: no. The tier is already implied by
  `stuck_escalation_count`. The kind is the new information; adding
  tier to the same column would conflate two orthogonal signals and
  make grep harder.
- Should we also persist the *signal summary*? (The
  `summary_of_attempts` field, not just the kind.) It would be
  useful for the prompt, but it's also long (multi-sentence) and
  could go stale. I recommend: start with kind only, add summary
  later if a real session shows the kind alone is insufficient.
- Should we also clear `last_signal_kind` on `mark_progress`? Per
  item 3 below, `mark_progress` is a docstring-only reference; the
  clear would be a separate decision. My read: don't clear it. The
  column's job is "tell the next session what tripped last time,"
  and clearing it after a recovery loses the memory the column
  exists to provide. The escalation count is the "current health"
  signal; the kind is the "history" signal.

---

## 3. Document and harden the `_PROGRESS_*` whitelists (synthesis #16)

### Current state

`stuck.py:184-201` (`_PROGRESS_TOOL_NAMES`) and `stuck.py:157`
(`_PROGRESS_MUTATION_TOOL_NAMES`) are two hand-maintained sets of
tool names. They drive two different behaviors:

- `_PROGRESS_TOOL_NAMES` (16 names) — consumed in
  `record_turn_end` (`stuck.py:778-797`) to reset
  `turns_since_progress` when a turn includes any of these tools.
  Wrong membership here: add a non-progress tool → agent "makes
  progress" on a turn that didn't move; remove a real progress tool
  → the no-progress counter fires after a productive turn.

- `_PROGRESS_MUTATION_TOOL_NAMES` (2 names: `add_artifact`,
  `spawn_sub_investigation`) — consumed in `record_tool_call`
  (`stuck.py:444-448`) to `.clear()` the per-section revision-stall
  counters. Wrong membership: add a non-mutation tool → section
  counters cleared without justification; remove a real mutation
  tool → counters accumulate forever.

`tools/handlers.py:718+` (`TOOL_DESCRIPTIONS`) and
`tools/handlers.py:955+` (`_INPUT_MODELS`) are the canonical
registry. Today the two `_PROGRESS_*` whitelists are independent of
those — a new tool added to `HANDLERS` (or to `_INPUT_MODELS`) is
not automatically reflected in either list.

### Target state

A guardrail that catches the "added a tool, forgot the whitelist"
case. Three options I considered, ranked by what I'd actually
ship:

**(a) Lint-style test that asserts whitelist ⇄ HANDLERS consistency.**
Add a test in `test_stuck.py` (or a new `test_stuck_lists.py`)
that:

1. Imports every key in `HANDLERS` from
   `vellum.tools.handlers.HANDLERS` (or — more conservatively —
   every key in `TOOL_DESCRIPTIONS`).
2. Asserts each key is in **either** `_PROGRESS_TOOL_NAMES` or
   `_PROGRESS_MUTATION_TOOL_NAMES` **or** in a documented
   `_EXPLICIT_NON_PROGRESS` set (e.g. `upsert_section`,
   `update_section_state`, `append_reasoning`,
   `log_source_consulted`, `update_debrief`,
   `update_investigation_plan`, `update_artifact`,
   `reorder_sections`).
3. Fails loud with a "tool X is not classified" message that names
   the tool and points at the two whitelists.

This makes "added a tool, forgot the list" a CI failure rather
than a silent stuck-detection drift.

**(b) Move the lists to a typed enum on the `tools` module.**
Replace the two sets with a `class ProgressClass(str, Enum)` in
`tools/handlers.py` and have `stuck.py` import the enum. Same
runtime behavior, but the classification becomes a single
declaration per tool, next to the handler registration.

**(c) Docstring + code comment at the handler site.**
Add a comment at each `_PROGRESS_*` list explaining the contract,
plus a `stuck.py:36-41` docstring update that describes the
current actual reset path. Lowest cost, lowest impact.

**My recommendation:** (a) + (c). The test makes the contract
load-bearing without a refactor; the docstring makes the next
contributor understand the contract. (b) is a bigger change with no
test-cycle benefit beyond what (a) already provides.

The test should explicitly *not* require the list to be exhaustive
— that's brittle. The right contract is "every tool is classified,
either as progress, as a mutation, or as a non-progress
explanation." The third category (explicit non-progress) is what
makes the test stable as the tool surface grows.

### Migration plan

1. Update `stuck.py:36-41` docstring to match the actual code path
   (replace the aspirational `mark_progress` reference with a
   description of the inline `_PROGRESS_MUTATION_TOOL_NAMES` clear).
2. Add `_EXPLICIT_NON_PROGRESS` set near
   `_PROGRESS_MUTATION_TOOL_NAMES` listing the seven tools that are
   intentionally in neither list.
3. Add `test_stuck_lists.py::test_every_tool_is_classified` — single
   test, ~30 LOC.
4. (Optional) Add `test_stuck_lists.py::test_no_orphan_progress_tool`
   — assert no tool in `_PROGRESS_TOOL_NAMES` is also in
   `_EXEMPT_FROM_LOOP` or `_EXEMPT_FROM_NO_PROGRESS` (that would be
   a contradiction).

### Risk assessment

- **Blast radius:** the new test is the only change. The
  `_EXPLICIT_NON_PROGRESS` set is documentation, not a logic
  change.
- **Determinism:** the test enumerates `HANDLERS.keys()` and
  compares to a static set. Zero timing dependency.
- **Failure mode:** when the test fails, the message must name the
  tool and the two whitelists so the next contributor can fix it
  in 30 seconds.

### Effort estimate

**Small.** ~30 LOC of test + 1-line docstring fix.

### Open questions

- What about `flag_needs_input`, `flag_decision_point`, etc. — are
  they "progress" or "explanatory"? My read: progress (they're in
  `_PROGRESS_TOOL_NAMES` today, and the rationale is that raising a
  need for input is itself a movement of the investigation forward).
  Confirm with the project owner; the test should encode the
  decision once made.
- Should the `_EXEMPT_FROM_LOOP` and `_EXEMPT_FROM_NO_PROGRESS` sets
  also get the same treatment? They're smaller (2 entries each) and
  the failure mode is less load-bearing (an over-classified
  exemption is a false-negative, not a false-positive), but for
  consistency I'd lump them in.

---

## 4. Address the `asyncio.run()`-inside-event-loop dance (synthesis #5)

### Current state

`sub_runtime.py:756-783` runs the sub-agent's async loop inside
`spawn_handler` via `asyncio.run(run_sub_investigation(...))`. The
defensive fallback at `sub_runtime.py:764-783` catches
`RuntimeError("asyncio.run() cannot be called from a running event
loop")` and switches to a manually-created event loop.

**This is actually correct as written.** I read this carefully and
want to push back on the deep-dive's framing. The two production
call sites are:

1. `runtime._dispatch_client_tool` (`runtime.py:592-594`) wraps
   handler dispatch in `asyncio.to_thread(...)`. So when the
   runtime calls `spawn_sub_investigation`, the handler runs on a
   thread-pool worker that has *no* event loop, and `asyncio.run()`
   works normally.
2. Direct unit tests call `spawn_handler` from synchronous test
   code (`test_sub_runtime.py:233` does
   `result = sub_runtime.spawn_handler(...)`). Same shape: no event
   loop, `asyncio.run()` works.

The fallback is reachable only if a future contributor adds a
second `await` upstream — e.g. if `spawn_sub_investigation`
becomes callable from inside another async function, or if the
runtime's tool-dispatch stops using `asyncio.to_thread`. The
fallback is *correct* for that case (it spins up a fresh loop and
runs the coroutine), so it's not a bug — it's a safety net for a
contract violation that doesn't exist today.

The deep-dive called it "a real sharp edge" because the seam
between "the parent runtime is async" and "the sub runs
synchronously from the parent's POV" is subtle. The subtlety is
real, but the code is doing the right thing. There's no actual
bug to fix.

### Target state

I recommend **documenting the contract** rather than refactoring
the code. Concretely:

1. Add a comment at `sub_runtime.py:748-751` (above the
   `asyncio.run` call) explaining *why* this is correct: handlers
   are dispatched via `asyncio.to_thread`, so the calling thread
   has no event loop.
2. Add a comment at `sub_runtime.py:763-783` (above the
   `RuntimeError` fallback) saying: "this fallback only fires if
   the contract at runtime.py:592-594 is broken (i.e. someone
   dispatches a handler inside a running loop). If you find
   yourself here, the upstream contract is broken; fix the
   upstream, don't rely on the fallback."
3. Add a test that pins the contract:
   `test_spawn_handler_called_from_running_loop_uses_fallback` —
   run `spawn_handler` inside `asyncio.run(...)` and assert the
   fallback path was taken (or, better, assert it raises a
   "contract violation" exception, removing the fallback entirely).

**Optional refactor:** the most honest fix is to remove the
fallback entirely and let `asyncio.run` raise its
`RuntimeError`. The runtime's dispatch is the only caller; if
that ever changes, the failure mode should be loud, not silently
swallowed by a manually-created loop. A manually-created loop
inside a running loop is *itself* a footgun (it bypasses the loop
the caller expects to be the source of truth).

### Migration plan

1. Add the two clarifying comments (10 lines).
2. Add the pinning test (15-25 LOC).
3. **Defer** the "remove the fallback" decision. The current
   fallback is harmless; the test pins the contract; the day
   someone needs to make a different decision, they'll have the
   evidence in front of them.

### Risk assessment

- **Blast radius:** comments and a test only. No production change.
- **Determinism:** the test uses `asyncio.run` to drive the
  parent-loop case; deterministic.
- **Compliance:** 358 tests stay green.

### Effort estimate

**Small (option 1) / medium (option 2).** 10-25 LOC plus a test.

### Open questions

- Does the project owner want the fallback removed? I recommend
  keep-with-test for now, but if the project owner prefers "loud
  failure over silent fallback," removing it is a 10-line change.
- Are there any plans to make `spawn_handler` truly async (i.e.
  `async def` and `await` the sub)? If yes, then this whole
  section is moot — but the deep-dive #3 confirms the architecture
  intentionally inlines the sub inside the parent's coroutine, so
  making the seam async would change the entire sub-investigation
  story, not just this one function. I recommend: don't.

---

## 5. Resolve the `_PLACEHOLDER_V2_SCHEMAS` dict (synthesis finding from deep-dive #3)

### Current state

`tools/handlers.py:989-1051` defines a dict of 6 placeholder
schemas. The pattern is:

- `tool_schemas()` (lines 1063-1320) emits the agent's tool
  surface.
- For each tool with a Pydantic input model in
  `_INPUT_MODELS[tool_name]`, the schema is derived from the
  model (lines 1073-1081).
- For tools NOT in `_INPUT_MODELS`, the loop at lines 1085-1092
  falls through to `_PLACEHOLDER_V2_SCHEMAS`.

The six tools in the placeholder dict are:
`update_investigation_plan`, `update_debrief`, `add_artifact`,
`spawn_sub_investigation`, `mark_considered_and_rejected`,
`set_next_action`.

**I checked `_INPUT_MODELS` (lines 955-982).** Each of those six
tools has a matching `_maybe_add(...)` call:

- `update_investigation_plan` → `InvestigationPlanUpdate` (line 975)
- `update_debrief` → `DebriefUpdate` (line 976)
- `add_artifact` → `ArtifactCreate` (line 979)
- `spawn_sub_investigation` → `SubInvestigationSpawn` (line 980)
- `mark_considered_and_rejected` → `ConsideredAndRejectedCreate` (line 981)
- `set_next_action` → `NextActionCreate` (line 982)

So in the current merged tree, the placeholder path is **dead
code**: `tool_schemas()` will always find a Pydantic model for
each of these six tools and never reach the fallback.

The dead-code rationale is in the comment at lines 985-988:
"Permissive placeholder schemas used when a v2 Pydantic model
hasn't merged yet. Keeps `tool_schemas()` stable at 14+ entries
on any branch. Real schemas take precedence automatically once
the model shows up in `_INPUT_MODELS` via `_maybe_add`."

This was useful during the day-by-day multi-worktree dev (the
"v2" model hadn't landed yet on some branches). In the single-tree
post-hackathon state, it's pure overhead.

### Target state

**Delete the dict and the fallback loop.** That's 67 lines of
code (`tools/handlers.py:985-1092`) that no test exercises, no
handler uses, and the comment explicitly says is a transient
multi-worktree scaffolding artifact.

If the project owner ever branches again and needs the
placeholder behavior, the dict can be revived from git history.
The git archeology cost is one `git show` — much cheaper than
maintaining dead code in main.

### Migration plan

1. `git grep _PLACEHOLDER_V2_SCHEMAS` to confirm zero remaining
   references (I checked: only the definition, the fallback loop,
   and the comment reference it).
2. Delete the dict (lines 989-1051) and the fallback loop
   (lines 1083-1092).
3. Update the comment at `handlers.py:1073-1081` to remove the
   reference to the placeholder fallback.
4. Re-run the 358 tests. Expect zero changes.

### Risk assessment

- **Blast radius:** zero. The dead code is unreachable.
- **Determinism:** no timing impact.
- **Compliance:** trivially safe.

### Effort estimate

**Trivial.** ~70 LOC of deletion, plus a comment cleanup.

### Open questions

- None. This is a pure deletion.

---

## 6. Address the silent Pydantic `field_validator` backward compat (synthesis #3 in deep-dive #3)

### Current state

`models.py:548-570` defines `InvestigationPlanUpdate._coerce_legacy_items`,
a `field_validator` that converts `InvestigationPlanItem` instances
to `PlanItem` instances before validation. The deep-dive noted
that this is "the only model-level backward-compat hack in the
codebase, and it's silent" — the caller can't tell if the input
was old-shape or new-shape.

I checked whether the legacy path is actually reachable. The
`grep` results:

- `models.py:86` defines `InvestigationPlanItem` (the legacy
  model).
- `models.py:103-117` defines `PlanItem` (the new model).
- `models.py:105` is a docstring on `PlanItem` saying it
  "Replaces the embedded InvestigationPlanItem inside the
  dossiers.investigation_plan JSON blob."
- `intake/tools.py:229` constructs `InvestigationPlanItem` instances
  during intake commit.
- `storage/dossier_store.py:622` reads legacy
  `InvestigationPlanItem` objects from the JSON column and converts
  them.
- 4 test files use `InvestigationPlanItem`:
  - `test_agent_status.py:86-87`
  - `test_day2_smoke_auto_resolve.py:130-131`
  - `test_dossier_extensions.py:128, 143, 264`
  - `test_plan_approval.py:58-59`
  - `test_tool_surface.py:288-292` (a structural test that
    specifically tests the compat shim)

**So the legacy path is NOT dead.** The intake agent still
constructs `InvestigationPlanItem` instances; the storage layer
still reads them; four test files still exercise the compat path.
The `_coerce_legacy_items` validator is the bridge that lets
`InvestigationPlanUpdate.items` accept either the old or the new
shape.

The deep-dive's framing was off on the dead-code angle but
correct on the "silent" angle. The validator is silent: a caller
passing `InvestigationPlanItem` instances gets them converted
without any log line, warning, or version marker. That's a real
maintenance trap: a future contributor who refactors
`intake/tools.py` to use `PlanItem` directly will see all the
tests pass, but the validator still does work for any older
caller (e.g. an out-of-tree integration, a stale dataset, a
crash-recovered mid-write plan blob).

### Target state

I recommend **make the compat path explicit**, not delete it. The
path is load-bearing for the intake agent's current shape; deleting
it is a breaking change for at least three call sites
(`intake/tools.py:229`, `storage/dossier_store.py:622`, the four
test files).

Concretely:

1. **At `models.py:561-583` (`_coerce_legacy_items`):** add a
   `logger.debug("plan_update: coerced N legacy InvestigationPlanItem
   -> PlanItem", n)` call so the conversion is no longer silent.
   Use `logger.debug` (not `warning`) to avoid log spam; the goal
   is "this is traceable, not annoying."
2. **At `intake/tools.py:229`:** change the construction to use
   `PlanItem` directly. `PlanItem` is a strict superset of
   `InvestigationPlanItem`'s fields (id, question, rationale,
   expected_sources, as_sub_investigation, status — all present
   on `PlanItem`). The only missing field on `PlanItem` is
   `dossier_id` (defaulting to None), which is filled in by
   storage on insert.
3. **At `storage/dossier_store.py:622`:** keep the legacy
   conversion for the JSON-blob read path, but add a comment
   that the live path now uses `PlanItem` and the
   `InvestigationPlanItem` shim is only for backward-compat reads
   of pre-v2 dossiers.
4. **Update the 4 test files** to construct `PlanItem` directly.
   This is mechanical (same field names, just a different class).
5. **In a follow-up commit (separately),** once zero callers
   construct `InvestigationPlanItem`, delete the model and the
   `_coerce_legacy_items` validator. That's a 2-line deletion.

### Migration plan

1. Add the debug log to `_coerce_legacy_items` (1 line).
2. Migrate `intake/tools.py:229` from `InvestigationPlanItem` to
   `PlanItem` (1 line + assertion that the test still passes).
3. Update `storage/dossier_store.py:622` comment (3 lines).
4. Migrate the 4 test files (4 small changes).
5. Re-run all 358 tests. Re-run the live smoke test
   (`scripts/day2_smoke.py`) on a non-critical dossier.
6. **Defer** the actual deletion of `InvestigationPlanItem` and
   the validator. Do it after a week of no regression, when we're
   sure no caller was missed.

### Risk assessment

- **Blast radius:** the migrations are pure renames; the runtime
  doesn't observe them.
- **Test coverage:** the existing 4 test files will surface any
  field-name regression immediately.
- **Smoke test:** the day-2 smoke exercises the full intake →
  plan → resume → deliver flow. Running it once is the strongest
  pre-deletion check.
- **Compliance:** 358 tests must stay green through every step.

### Effort estimate

**Small-to-medium.** ~40 LOC of changes (mostly in tests) plus
the one-line debug log. The deferred deletion is one more 5-line
commit.

### Open questions

- Is the project owner comfortable with the two-step "migrate
  callers, then delete" structure, or would they prefer a single
  "delete the model and update all callers" commit? The
  two-step is safer for a solo dev (revert one step without
  losing the other); the single-step is faster. My read: the
  two-step is the right call here because the validator is
  load-bearing for the storage JSON-blob read path, and a
  half-migrated system would silently drop plans.

---

## Cross-cutting notes

### Compliance with the 358-tests-stay-green constraint

None of the six items modify production behavior in a way that
would break existing tests. Items 1, 3, 4, and 5 are pure
additions/deletions. Item 2 adds a column with NULL default and a
best-effort write — backward compat. Item 6 changes the *kind* of
object passed across the validation boundary but the
*information content* is identical.

### Compliance with "the agent never speaks to the user"

None of the items touch the closed-loop enforcement. The prompt
changes in item 2 are *additive* (a new informational block in
`build_state_snapshot`); the agent's response path through
`runtime.py:282-290` (the prose-discard branch) is untouched.

### Compliance with the closed-loop enforcement

Item 2 adds a system-prompt surface. The risk is "agent now
paraphrases `last_signal_kind` in prose instead of calling a
tool." Mitigation: place the surface in the
`build_state_snapshot` block that already gets prepended each
turn; the model's existing behavior is to *react* to snapshot
context via tools, not narrate it. If a regression appears, the
fix is one line in `prompt.py` to make the surface a
tool-call-shaped directive instead of a fact.

### Ordering recommendation

If the project owner wants to ship all six in one cleanup pass,
the order I'd ship is:

1. **Item 5** (delete `_PLACEHOLDER_V2_SCHEMAS`) — trivial, zero
   risk, 70 LOC of dead code off the books.
2. **Item 1** (add `test_scheduler.py`) — the highest-value
   test per the deep-dive; nothing else depends on it.
3. **Item 3** (harden `_PROGRESS_*` whitelists) — small test
   that catches a real future bug.
4. **Item 4** (`asyncio.run()` comments + test) — small, no
   behavior change.
5. **Item 2** (add `last_signal_kind` column) — small, additive,
   test-friendly.
6. **Item 6** (migrate `InvestigationPlanItem` callers) — the
   meatiest change, save it for last so the cleanup pass lands on
   a stable base.

If only 2-3 items are picked, the top three by ROI are
**1, 2, 5**. Item 3 is cheap insurance. Items 4 and 6 are
good-but-optional.

---

## Headline summary

- **`test_scheduler.py` is the single highest-value test in the
  repo** — 12 tests in ~150 LOC, all deterministic, < 5s, that
  pin the 30s polling loop, the pre-session creation, the
  `AgentAlreadyRunning`/`AgentCapacityExceeded` retry path, and
  the late-answer correctness contract (the `scheduler.py:202-216`
  block).
- **`last_signal_kind` is a small, additive, NULL-tolerant
  column** (~50 LOC) that lets the next agent turn re-surface
  "the last time you got stuck, it was `loop` not `budget`" — the
  one piece of stuck history that doesn't currently survive
  sleep/wake.
- **Five of the six items are independent, small, and ship
  risk-free.** The sixth (the `InvestigationPlanItem` migration)
  is the only one that touches multiple call sites and deserves a
  two-step "migrate then delete" structure.
