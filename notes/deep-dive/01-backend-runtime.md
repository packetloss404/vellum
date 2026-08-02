# Vellum — Backend Agent Runtime Deep-Dive

Scope: the manual agentic loop in `agent/runtime.py` and `agent/sub_runtime.py`, the
compactor, telemetry, and prompt assembly. All references are to files under
`D:\projects\Vellum\backend\vellum\`.

---

## 1. Turn loop walkthrough — `DossierAgent.run`

`DossierAgent.run` is a 200-line `while` loop, but the real structure is much
tighter. Annotated against `agent/runtime.py`:

**Setup (lines 129–162).** Resolve or open a work session via
`_resolve_session()` (lines 524–547) — the function honors an
`expected_session_id` attribute that the orchestrator may have set, falls
back to the dossier's active session, and otherwise opens a new one with
trigger=`resume`. The session is registered with the stuck-detection
subsystem via `stuck_mod.init_session(session_id, dossier_id)` (line 137) so
escalation counters survive sleep/wake. The system prompt is built once from
`prompt.build_system_prompt(dossier)` (line 150), then wrapped via
`_cached_system_prompt` so Anthropic caches the static system text across
turns (line 153). The tool list (built in `_build_tool_definitions`,
lines 123–127) is the 10 dossier tools from `handlers.tool_schemas()` plus
the built-in server-side `web_search` tool. `_tools_with_cache_breakpoint`
(lab line 55–61) adds a `cache_control: ephemeral` marker to the *last* tool
entry so the definitions also get cached.

The first user message is a synthetic dossier-state snapshot — not a
human-written prompt — built by `_snapshot_content` (line 158–160,
`_snapshot_content` at 549–555), which calls `prompt.build_state_snapshot`
on a freshly-loaded `DossierFull` and collects the IDs of any unseen
`user_notes` so they can be marked seen if the run ends healthy.

**Streaming the model (lines 169–192).** Each turn opens an
`async with self._client.messages.stream(...)` context. `max_tokens=32000`
is fixed (line 171). The block comment above (lines 165–168) explains the
choice: the SDK requires streaming for operations that may exceed 10
minutes, and 32k output + `web_search` makes that the safe path.
`context_management` is sent via `extra_body` (lines 176–190) when
`CONTEXT_MANAGEMENT_THRESHOLD > 0` — a 180k-input-token trigger
(line 66) that asks Anthropic to clear `tool_use` blocks server-side
(`clear_tool_uses_20250919`) while *excluding* the
`_DOSSIER_WRITE_TOOLS` (line 70) so the model keeps its place across a
big prune. `get_final_message()` aggregates the stream.

**After the API call (lines 194–239).** Token counts are pulled off
`response.usage` (lines 194–198) and cost is computed via
`cost_usd_for_turn` from `config.py` (line 201). `record_turn_usage`
updates the per-session counters and the `budget_accounting` daily row in
a *single* transaction (see `storage/session_store.py:141–197`). Per-turn
input tokens are also reported to the stuck module via
`record_input_tokens` (line 217), and a soft budget check fires (line 223).

Then the assistant's `content` blocks are explicitly serialized to plain
dicts before being appended to `state.messages` (lines 229–235). The
comment "H-01: serialize Anthropic SDK objects to plain dicts before
storing" is load-bearing — the compactor's `isinstance(block, dict)`
guards (e.g. `compactor.py:38–40`) would silently misclassify SDK
`TextBlock` / `ToolUseBlock` objects as something else, corrupting both
the token estimate and the compaction text.

`state.turns` is bumped *before* the `pause_turn` check (line 239) so the
counter includes continuation turns from server-side web search.

**`pause_turn` (line 243–244).** If `response.stop_reason == "pause_turn"`,
the loop `continue`s without appending a snapshot, without checking
stuck, without surfacing budget signals. The model resumes; Anthropic
inlines the search results in the next response's content blocks.

**Compaction (lines 251–276).** Threshold is read *dynamically* each turn
via `os.getenv("VELLUM_COMPACT_INPUT_TOKEN_THRESHOLD", "80000")` (line
252) so tests can monkeypatch the env var. The `_estimate_tokens`
heuristic is 4-chars-per-token (`compactor.py:24–43`). If
`should_compact` returns True, `compact_messages` is awaited; the
`storage.append_reasoning` call leaves an audit trail; the entire block
is wrapped in `try/except Exception: pass` (line 274–276) with the
comment "Compaction failure must never terminate the agent." This is
both comforting and slightly alarming — see §7.

**Tool dispatch (lines 278–388).** Tool-uses are filtered from
`response.content`; if none, the loop ends with
`WorkSessionEndReason.ended_turn` (line 282–290). The comment is sharp:

> Model ended the turn. Any prose is discarded — the agent speaks only
> through tool calls into the dossier. (`runtime.py:283–284`)

For each tool call: skip `web_search` (server-side, line 309–310),
enforce a per-turn one-`flag_needs_input` rule with a soft-reject
`tool_result` (lines 312–336), and dispatch via
`_dispatch_client_tool` (line 338–341, full method at 557–632). The
section-id cache (`self._last_section_id`) is updated *only* from the
DB-assigned `section_id` returned by the upsert handler (line 354–357,
with the long comment at 343–353 explaining the previous phantom-id bug
this prevented).

`mark_investigation_delivered` is the terminal tool: it sets a `delivered`
flag only when the handler reports `ok` (line 369–371, helper at
882–907). Per-tool-call stuck tracking fires (line 375–378), and after the
dispatch loop the entire turn's tool results are appended as a single
user message (line 380–381). End-of-turn progress-forcing recording
(line 386–387) feeds the no-progress counter in `stuck.record_turn_end`.

**Post-dispatch (lines 397–424).** Stuck signal check, surface if any
(line 399–416). The runtime does *not* terminate on a stuck signal — the
comment is explicit:

> Surface the signal as a decision_point, but do NOT terminate the
> loop — per stuck.py and the product memory, we detect and report, we
> never cut the agent off mid-thought. … `max_turns` remains the
> backstop. (`runtime.py:404–414`)

Then a *fresh* state snapshot is appended (line 422–424) — this is the
"state snapshot as index" pattern: the model always starts a turn with
a current view of the dossier, and earlier messages are left untouched
so the prompt cache stays warm.

**Termination paths (lines 426–438).** `turn_limit` on max-200,
`delivered` after the `mark_investigation_delivered` call, `error` from
the catch-all `except Exception`. `_end_reason` is set in every path so
the `finally` block (lines 439–522) can call
`end_work_session_with_reason` (line 497), and the `self_heal` module
gets called on success or error (line 503–517).

**Finally (lines 439–522).** A minimal `save_session_summary` row is
written if `summarize_session` never fired (line 446–456) — UPSERT
preserves real content on conflict, so this fallback doesn't clobber
real summaries. `mark_investigation_delivered`'s "I didn't deliver"
path triggers a server-side `set_dossier_wake_at` for daily/weekly
cadences (line 466–495, "H-23"). Self-heal escalates errors, resets on
success, and `stuck_mod.reset_session(session_id)` (line 520) clears
the in-memory counters.

---

## 2. Tool dispatch & idempotency

Dispatch is centralized in `_dispatch_client_tool` (`runtime.py:557–632`).
The flow is:

1. **Unknown tool check** (line 560–569): if not in `handlers.HANDLERS`
   or `HANDLER_OVERRIDES`, return `is_error=True` with a clean string.
2. **Idempotency lookup** (line 577–586):

```python
prior = await asyncio.to_thread(
    storage.get_tool_invocation, tool_use_id
)
if prior is not None:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": prior["result_json"],
        "is_error": prior["is_error"],
    }
```

The storage table (`storage/idempotency_store.py:11–34`) is a thin
SELECT-by-`tool_use_id` against `tool_invocations`. The comment at
`runtime.py:571–576` is candid:

> Under Path A this should be rare (new sessions don't replay message
> history), but the shim is migration-proof for Path B/C and closes the
> "double upsert_section lies to the plan-diff" failure mode if runtime
> dispatch ever re-iterates a response.

3. **Dispatch off-thread** (line 592–594): handlers are sync, so
   `asyncio.to_thread(handlers.dispatch, dossier_id, tool_name, tool_input)`
   keeps the event loop unblocked. `handlers.dispatch`
   (`tools/handlers.py:1351–1369`) checks `HANDLER_OVERRIDES` first
   (`spawn_sub_investigation` lives there, see §3), then falls back to
   the default handler, then runs every `TOOL_HOOKS` callback.

4. **Record on success** (line 596–604):

```python
await asyncio.to_thread(
    storage.record_tool_invocation,
    tool_use_id,
    self.dossier_id,
    tool_name,
    _hash_tool_input(tool_input),
    result_json,
    False,
)
```

5. **Record on error** (line 610–626): same call, but `is_error=True`
   with the formatted exception string. The comment "cheap insurance
   against thrashing the DB on the same failure" is honest.

The schema is a `INSERT OR IGNORE INTO tool_invocations` keyed on
`tool_use_id` (`idempotency_store.py:47–64`), so a duplicate dispatch
within the same session short-circuits cleanly. `_hash_tool_input` at
`runtime.py:868–879` is informational, not the dedup key.

**Crash-safety profile.** A handler that raises is *captured*, the tool
gets an `is_error=True` result, the agent sees the error and can react
on the next turn, and the same `tool_use_id` will short-circuit on
replay. A handler that hangs in `asyncio.to_thread` will block one
thread-pool worker (default Python `ThreadPoolExecutor` has
`min(32, os.cpu_count()+4)` workers) but the event loop keeps serving
other agents — bounded blast radius.

What it does *not* do: handle a *crash before* `record_tool_invocation`.
If the process dies between handler completion and the idempotency
write, replay will re-execute the handler. For pure side-effect-free
reads that's fine; for `upsert_section` it could double-insert, and the
old phantom-id bug (`runtime.py:343–353`) was a *consequence* of this
class of retry.

---

## 3. Sub-investigation recursion

The flow is `spawn_sub_investigation` tool call → `spawn_handler`
override → `run_sub_investigation` async loop → result folded back as
the parent's tool result.

**Allowlist.** `SUB_TOOL_ALLOWLIST` (`sub_runtime.py:81–87`) is exactly
five tools:

```python
SUB_TOOL_ALLOWLIST = frozenset({
    "upsert_section",
    "add_artifact",
    "log_source_consulted",
    "mark_considered_and_rejected",
    "complete_sub_investigation",
})
```

The depth cap is enforced by omission — no `spawn_sub_investigation` in
the list, and the sub-prompt explicitly says "You cannot spawn further
sub-investigations. Depth cap is 1" (`sub_prompt.py:53–56`). The
sub-tools list is derived from `handlers.tool_schemas()` filtered by
name, not hand-written (`sub_runtime.py:115–125`):

> Derived (not hand-written) so if a schema shape changes in
> handlers.py the sub-agent picks it up automatically.

`flag_needs_input` is excluded for a real reason: comment at
`sub_runtime.py:78–80` explains that subs surfacing NeedsInput rows
without a `sub_investigation_id` FK caused
`mark_investigation_delivered` to refuse delivery.

**Identity propagation.** `CURRENT_SUB_INVESTIGATION_ID` is a
`contextvars.ContextVar[Optional[str]]` (`sub_runtime.py:104–106`),
set just before the per-turn loop and reset in the `finally`
(line 707). `_inject_sub_id` (line 154–171) is the *only* place the
contextvar is read; it stamps `sub_investigation_id` onto the args of
`log_source_consulted` and `mark_considered_and_rejected` so the
resulting DB rows are correctly attributed.

`complete_sub_investigation` is a special case: the model is *not*
told its own `sub_id`, so `_dispatch_sub_tool` always injects it
server-side (line 242–244).

**`log_source_consulted` scope-fence.** Because
`handlers.log_source_consulted` does not propagate
`sub_investigation_id` into the `InvestigationLogAppend` row, the
sub-runtime re-implements that one handler locally
(`_log_source_consulted_with_sub`, line 174–206) and calls
`storage.append_investigation_log` directly. The comment is candid:

> Rather than edit handlers.py (forbidden by scope), we call storage
> directly from the sub-runtime with the sub_id explicitly set. Same
> observable behavior, plus the attribution the product expects.
> (`sub_runtime.py:181–185`)

This is a real architectural smell — a single tool is implemented
*twice* — but the comment correctly identifies the scope fence as the
cause.

**Force-completion / prods.** The per-turn loop ends either when the
model calls `complete_sub_investigation` (line 600–609, clean exit) or
after `_MAX_PRODS = 2` empty-turn nudges (line 540–561). The nudge is a
synthetic user message:

> You have not yet called complete_sub_investigation. If you have a
> substantive answer, call it now with a brief explanation in
> return_summary. (`sub_runtime.py:551–555`)

If the model still doesn't comply, `force_completed = True` and a
fallback completion is dispatched with
`return_summary="[incomplete — max_turns reached]"` (line 616–647).
The error path is similarly defensive: try
`storage.complete_sub_investigation`, fall back to
`abandon_sub_investigation`, both inside a `try/except` that logs and
continues (line 662–704). The comment at 700–703 admits the limit:
"sub row may remain in `running`" if both fail.

**Session reuse.** The sub reuses the parent's active work session
when present (`sub_runtime.py:412–422`), with a fallback to
opening-and-owning a temporary one. Token accounting rolls into the
parent's `work_sessions` row, so a sub's cost is visible in the
parent's session header. `spawn_handler` mirrors the same pattern
for the *parent* session (line 731–741).

**Spawn glue.** `spawn_handler` is registered at import time
(`sub_runtime.py:866–869`):

```python
if not hasattr(handlers, "HANDLER_OVERRIDES"):
    handlers.HANDLER_OVERRIDES = {}
handlers.HANDLER_OVERRIDES["spawn_sub_investigation"] = spawn_handler
```

The `asyncio.run` inside `spawn_handler` (line 756–763) is a *real*
sharp edge — see §7.

**What changes vs. `runtime.py`.** The sub-loop drops:
compaction, `CONTEXT_MANAGEMENT`, `pause_turn` continuation, the
state-snapshot-after-each-turn pattern, `mark_investigation_delivered`
terminal handling, budget soft-signal check (replaced with a simpler
`_check_sub_budget_signals` at line 325–378), and the full
`_surface_stuck` tier handling. It adds: prod-then-force-complete,
section-id tracking for stuck attribution, and a parent dossier
snapshot rendered into the first user turn
(`_build_initial_user_content` at line 301–322) so the sub sees *why*
it was spawned.

---

## 4. Context compaction

`agent/compactor.py` is ~210 lines. The shape is:

- **`_estimate_tokens` (line 24–43):** 4-chars-per-token heuristic, with
  block-level `model_dump()` for SDK objects (H-01 again).
- **`should_compact` (line 46–65):** fires when estimated tokens
  exceed threshold *and* `len(messages) >= 12` (i.e. ≥ 1 first-user
  + 5 keep-recent + something to compact).
- **`_split_turns` (line 68–98):** turn boundaries are assistant
  messages; first user message is always preserved as the anchor.
  Default `keep_recent_turns = 5`.
- **`compact_messages` (line 101–212):** the worker.

The worker flattens the old messages into a single readable text,
calls `client.messages.create(model=SUMMARY_MODEL, max_tokens=2000,
…)` (line 163–170) with a structured-handoff prompt, then *merges*
the first user message's content with the breadcrumb into a *single*
user message at the head of the compacted list (line 188–211). The
comment at 182–187 explains why:

> Critical: do NOT prepend first_msg as a separate message then add a
> second user-role breadcrumb — that produces two consecutive user
> messages which the Anthropic API rejects with a 400. Instead, merge
> the first message's content with the breadcrumb into a single user
> message that opens the compacted list. This preserves the first-turn
> anchor while keeping the alternating-role invariant intact.

This is the kind of bug you'd only learn by hitting the API. The
`SUMMARY_MODEL` is `claude-haiku-4-5` by default
(`config.py:40`), with a comment at `compactor.py:158–161` explaining
that H-11 explicitly switched away from a previous `os.getenv` default
that would have fallen back to the main Opus model and made
compaction prohibitively expensive.

On API failure, the catch-all (line 175–179) writes
`"[Compaction fallback: N messages compressed. Key details may be
lost.]"` and continues — same "never kill the agent" philosophy as the
runtime's try/except, but see §7.

The trigger from the runtime is dynamic: `os.getenv(...)` is read each
turn (`runtime.py:251–253`) so tests can monkeypatch. The audit trail
is a single `append_reasoning` with `tags=["compaction"]`
(`runtime.py:261–272`).

---

## 5. System prompt design

**Main prompt** (`agent/prompt.py:56–162`, `MAIN_AGENT_SYSTEM_PROMPT`):

Ten sections, ~110 lines, each a single load-bearing instruction:

1. **State snapshot as index** (lines 61–66): confident sections show
   80-char previews; artifacts are index-only; reasoning trail shows
   last 5. This is enforced by `build_state_snapshot` (line 358–551)
   and is what makes the system survive multi-hour sessions without
   burning context on full state.
2. **Push back on the premise** (lines 69–79): the example
   "if asked for a debt-negotiation opening %, first establish who
   owns the debt, proof of ownership, delinquency date, jurisdiction,
   statute of limitations, credit-reporting status" is unusually
   concrete for a system prompt — it pre-empts the most common failure
   mode by *showing* it.
3. **Premise challenge and plan gate** (lines 81–93): two
   gates — `record_premise_challenge` and an approved
   `investigation_plan`. "Do not start sources, subs, sections, or
   artifacts until a `plan_approval` decision is resolved."
4. **Sub-investigations** (lines 95–103): "A serious dossier often has
   3-6 subs. Do not absorb sub-scope work into the main thread."
5. **Substance bar** (lines 105–112): the 30–80 sources / real
   artifacts / rejected paths bar, with `cost_of_error` called out as
   the load-bearing field on `mark_considered_and_rejected`.
6. **Structured writes only** (lines 114–127): every user-visible
   change must be a tool call; prose without tool calls "evaporates."
7. **User interruptions** (lines 129–134): batched one ask per turn.
8. **Sleep, summaries, stuck** (lines 136–146): real-world time only
   for `schedule_wake`; "Lead with a verb" for `summarize_session`.
9. **Delivery** (lines 148–153): a multi-part pre-condition list.
10. **Tool rhythm** (lines 155–162): a single-sentence summary of the
    full lifecycle, written as a checklist.

**`build_state_snapshot`** (`prompt.py:358–551`) is its own art. It
renders: budget pressure (only when over warn-fraction, line 282–355),
working theory, plan status, last plan review (the chosen option +
its implications), dossier header, sections (with confident-sections
showing only 80-char previews, non-confident showing full content —
line 458–463), artifacts (index-only), open needs_input, *unseen
user notes* (with the explicit "Weigh them before anything else this
turn" instruction, line 493–506), open decision_points, ruled out,
and the last 5 reasoning_trail entries. The unseen-notes block is
deliberately *above* the decision_points block — "a note can
invalidate the question a pending decision is asking"
(line 491–492).

**Sub-agent prompt** (`sub_prompt.py:19–103`,
`SUB_INVESTIGATION_SYSTEM_PROMPT`): ~85 lines, four sections plus a
return contract.

- **No narration** (lines 27–32): re-states the discard-prose rule
  for the sub.
- **Your tools** (lines 34–56): enumerated list of the 6 tools the
  sub can actually call, with the depth cap spelled out and the
  missing main-agent tools called out by name.
- **Scope discipline** (lines 58–71): "Before each `web_search`, ask:
  does this query fall within the scope the main investigator handed
  me? If no, stop."
- **Return calibrated** (lines 73–92): the 3–8-sentence
  `return_summary` contract — "Lead with the answer; do not restate
  your scope, the parent already knows it. Every summary MUST state a
  confidence level (high / medium / low) and what evidence would
  move it." `findings_section_ids` must include at least one id
  unless the sole deliverable was an artifact.
- **When to exit** (lines 94–103): "If you have a confident answer
  after eight to twelve sources, return." Plus the anti-pattern
  warning: "A three-source return saying 'needs more work' is a
  failure, not a deliverable."

**Prompt-injection defense.** `_sanitize_user_field`
(`prompt.py:24–53`) wraps every user-controlled string in
`<user_content>…</user_content>`, strips leading `#` Markdown headings,
and escapes `& < >` so a user-supplied string cannot close the tag.
This is *not* airtight (a determined attacker can use other XML
boundaries) but it raises the bar materially and is applied
consistently to problem statement, out-of-scope list, check-in
policy notes, and the sub-agent's scope/questions.

---

## 6. Cost / token telemetry

**Pricing table** (`config.py:116–138`):

```python
MODEL_PRICING_USD_PER_MTOK = {
    "claude-opus-4-7":     {"input": 5.0, "output": 25.0,
                            "cache_creation_input": 5.0 * 1.25,
                            "cache_read_input":       5.0 * 0.1},
    "claude-sonnet-4-6":  {"input": 3.0, "output": 15.0,  …},
    "claude-haiku-4-5":   {"input": 1.0, "output":  5.0,  …},
}
```

Verified from `platform.claude.com` 2026-04-23 (comment at line 117).
Unknown models fall back to `0.0` with a logger warning
(`config.py:153–159`).

**Per-turn path.** `record_turn_usage` (`session_store.py:141–197`)
runs both the `work_sessions` UPDATE and the `budget_accounting`
INSERT/UPSERT in a single transaction (line 153–197). The
`budget_accounting` table has columns for both
`cache_creation_input_tokens` and `cache_read_input_tokens`, so cache
hit-rate is queryable.

**Per-turn runtime hookup** (`runtime.py:194–223`):
`cost_usd_for_turn` is computed, `record_turn_usage` writes both
counters, `stuck_mod.record_input_tokens` updates section attribution,
and `_check_budget_signals` is called immediately.

**Daily / per-session cap surface.** `DEFAULT_SETTINGS`
(`config.py:173–198`) seeds `budget_daily_soft_cap_usd = 10.0`,
`budget_per_session_soft_cap_usd = 3.0`,
`budget_daily_warn_fraction = 0.8`,
`progress_forcing_turns = 5`, `trust_mode_enabled = False`. The
runtime's `_check_budget_signals` (`runtime.py:634–678`) reads both
caps, queries `get_budget_today` for the daily rollup, and the
work-session for session cost; dedup is per-instance via
`self._budget_daily_reported` / `self._budget_session_reported`
flags (line 117–118). The comment at the top is the philosophy:

> Soft-signal budget check — runs after each turn's usage capture.
> Emits a `declare_stuck`-shaped decision_point via storage when the
> daily global cap or the per-session cap is crossed. Never
> terminates the loop — the agent and user decide whether to
> continue. (`runtime.py:634–641`)

`_surface_budget_signal` (line 680–740) routes through
`check_stuck` (the agent-side handler) — *not* the runtime's stuck
machinery — and honors `trust_mode_enabled` to skip the decision_point
and just write a reasoning note. Three options are presented: keep
going, pause for direction, or mark delivered.

**`telemetry.py`.** Two surfaces:

1. **`log_tool_call`** (line 120–149): a JSON-line hook into
   `handlers.TOOL_HOOKS`. Truncates strings to 200 chars; verbose
   keys (`content`, `body`, `text`) to 120. `duration_ms = None` by
   design — the hook fires post-dispatch, so there's no start time.
2. **`session_stats`** (line 165–261): aggregates per-session
   `tool_counts` (from `change_log.kind` + `investigation_log.entry_type`),
   `source_count` (from `investigation_log` where
   `entry_type = 'source_consulted'`), `sub_investigation_count`
   (counted via the `started_at` window into `[session.started_at,
   session.ended_at]` — the comment at line 225–237 explicitly notes
   "day-2 schema doesn't add [a work_session_id] column"), and
   `artifact_count` (from `change_log` where
   `kind = 'artifact_added'`). The `_safe_fetchall` helper
   (line 155–162) catches `sqlite3.OperationalError` so this works
   before and after schema merges land.

The soft-cap decision point and the telemetry hooks both feed
`storage/budget_store.py` reads; the actual
soft-cap-vs-trust-mode branching is in the runtime, not in storage.

---

## 7. Honest assessment

**Genuinely well-engineered:**

- **State-snapshot-as-index** is the right pattern for a long-running
  agent loop and the implementation (cap sections at 80-char
  previews, redirect to `get_section` for full body) is unusually
  tight. See `prompt.py:443–466`.
- **Idempotency by `tool_use_id`** with `INSERT OR IGNORE` keyed on
  the Anthropic-generated id is the right primitive for replays. The
  shape is small and the *audit* column (input hash) is layered on
  without changing the dedup semantics.
- **Premise-challenge + plan-approval as a hard gate** is rare in
  agent systems. The product memory that "we never deliver just
  because you are waiting on a user answer" is encoded in the prompt
  *and* in the runtime's refusal path
  (`runtime.py:369–371`/`882–907`).
- **Tier-based stuck escalation with DB-persisted counter**
  (`stuck.py:357–394`, `stuck_escalation_count` in
  `dossiers.stuck_escalation_count`) survives sleep/wake — most
  custom agent systems lose this kind of state on every restart.
- **The `pause_turn` handling and `CONTEXT_MANAGEMENT` exclusion
  list** (`_DOSSIER_WRITE_TOOLS`, `runtime.py:70–78`) is a level of
  care that's not visible until you read the API docs.
- **Force-completion with prod-then-abandon fallback** in the
  sub-runtime (`sub_runtime.py:611–704`) is exactly the right
  defensive shape.
- **Test surface**: the structural smoke test at the bottom of
  `runtime.py:910–939` (the one that asserts the
  `needs_input_in_turn` tracker sits *after* the `while` in source
  order) is the kind of regression guard you only write when you've
  been burned.

**Rushed / hacky / fragile:**

- **`_log_source_consulted_with_sub` is a fork of
  `handlers.log_source_consulted`** (`sub_runtime.py:174–206`).
  Two implementations of the same tool, diverging in attribution. The
  scope-fence comment is honest about the cause but the code is the
  smell. Either the main handler needs to accept the sub-id or the
  sub-id injection needs a real hook on the handler signature.
- **Compaction silently swallows all exceptions**
  (`runtime.py:274–276`). If the Haiku call fails three runs in a
  row and the session is in the 80k+ range, you get the
  "[Compaction fallback: N messages compressed. Key details may be
  lost.]" breadcrumb with no log line and no signal. The fallback in
  `compact_messages` itself does log (`compactor.py:175–179`),
  which is good, but the outer swallow means the session continues
  with degraded context and nobody knows.
- **Token estimation is `len(content) // 4`**. For English prose this
  is roughly right; for JSON tool inputs and section bodies, it's
  off by 30–50%. The compaction trigger threshold (80k) is tuned to
  this estimate, so the actual API-side token count when compaction
  fires is a moving target.
- **`spawn_handler` uses `asyncio.run()`** inside what is normally
  already a running event loop (`sub_runtime.py:756–783`). The
  fallback path creates a fresh event loop with
  `asyncio.new_event_loop()` and tears it down manually. This works
  in tests but is exactly the kind of thing that breaks under
  ASGI/uvicorn and arbitrary nesting.
- **The `setattr(agent, "expected_session_id", ...)` dance**
  (`orchestrator.py:168–169`, read in `runtime.py:524–528`) is an
  out-of-band channel into the runtime. The runtime's `__init__`
  doesn't accept it. A second caller (e.g. a test that wants to
  resume a specific session) would have to know to set this
  attribute.
- **`HANDLER_OVERRIDES` is set on the `handlers` module at import
  time** in `sub_runtime.py:866–869`. Test isolation, dev-server
  reload, and any branch that imports `sub_runtime` before the
  `HANDLERS` dict is fully populated can race.
- **The runtime never emits a "stuck at max_turns" log** that would
  help debug a session that ran out of budget. There's a `turn_limit`
  reason in the result, but no investigation_log entry and no
  reasoning note.

**Sharp edges / concurrency hazards:**

- **Sub-agent `try/except` cascade can fail both completion and
  abandon** (`sub_runtime.py:685–703`). The sub row "may remain in
  `running`" is the explicit comment, which is at least honest.
  `mark_investigation_delivered` will then refuse to deliver
  because the unfinished sub is unresolved. Recovery: a manual
  `abandon_sub_investigation` or a follow-up tool call.
- **`asyncio.to_thread` for handlers** uses the default executor.
  Under `VELLUM_AGENT_MAX_CONCURRENT_RUNS = 2` and a slow handler
  that does N DB roundtrips, you can starve other agents waiting
  for `to_thread` slots. The default `ThreadPoolExecutor` size is
  `min(32, cpu_count+4)`, so this is bounded but not zero.
- **SQLite WAL** is mentioned in `orchestrator.py:14` as the
  concurrency story, but `sub_runtime.py:412–422` opens and
  *owns* a work session for the sub when the parent has none. If
  two callers race, the second gets `ActiveWorkSessionExists` and
  reuses the first's session — which is correct, but only because
  storage raises. If that exception path is ever refactored, the
  invariant breaks silently.
- **Compaction threshold read via `os.getenv` each turn**
  (`runtime.py:251–253`): if a test mutates the env mid-run, a
  concurrent prod run picks it up. Real risk in a multi-tenant
  deploy, zero in the current solo-dev shape.
- **`_last_section_id` attribution** was a known phantom-id bug
  (`runtime.py:343–353`). The fix uses the handler-returned
  `section_id`, but if any future handler returns a phantom
  `section_id` (or none), the same class of bug re-emerges.
- **`trust_mode_enabled`** (`config.py:197`) auto-dismisses
  tier-2 stuck and budget-cap decision points. The product memory
  says "Plan approval gates are NEVER skipped by trust mode," but
  this is a single line of text — the runtime doesn't enforce it,
  and an accidentally-enabled `trust_mode` for a new user is a
  footgun.

---

## 8. Notable design choices and why they matter

- **Manual agentic loop over `claude-agent-sdk`.** The docstring at
  `runtime.py:1–21` enumerates the reasons: closed set of Pydantic-
  derived tools, server-side `dossier_id` injection, per-turn state
  snapshot, built-in `web_search` server tool, after-each-tool-call
  stuck hooks. The Agent SDK would add MCP wrapping and make
  per-turn state injection awkward. This is the right call *for
  Vellum's shape*; a different shape (broader tools, less typed
  state) would prefer the SDK.

- **`max_tokens=32000`.** Forced by the SDK's 10-minute non-streaming
  cap and web_search's potential latency (`runtime.py:165–171`).
  Worth it: a single turn can include 32k tokens of tool output
  *plus* a `web_search` pause, and still not hit the wall.

- **Streaming required even for short turns.** Cost: extra
  machinery (`async with stream: await get_final_message()`).
  Benefit: no turn ever fails because it crossed the 10-minute
  non-streaming threshold. Right tradeoff.

- **Discard prose without tool calls.** The one-liner at
  `runtime.py:282–290` and the matching contract in the prompt
  (`prompt.py:114–121`) is the *core product invariant* — the
  agent never speaks to the user. Every design choice flows
  downstream from this: structured writes only, no narration in
  the sub-agent prompt, prose-evaporates rule.

- **State snapshot appended *after* every turn, not at start**
  (`runtime.py:422–424`). Comment: "This keeps the agent's view of
  the dossier current without rewriting earlier messages (which
  would bust the cache)." Inverted from a naive "snapshot at
  start" pattern, and the caching reasoning is the right one.

- **`CONTEXT_MANAGEMENT` server-side edit with
  `_DOSSIER_WRITE_TOOLS` exclusion** (`runtime.py:66–78`,
  `176–190`). A 180k-input-token trigger asks Anthropic to clear
  tool blocks *except* the dossier-mutating ones, so the model
  keeps the schema/identity of "which section am I editing"
  across a big prune. The 80k compaction threshold is well below
  the 180k management threshold, so by the time server-side
  clearing fires, compaction has already trimmed history once.

- **Sub-agent tool allowlist *derived*, not hand-written**
  (`sub_runtime.py:115–125`). If a schema shape changes upstream,
  the sub picks it up automatically. Good invariant.

- **`ContextVar` for sub-identity** rather than threading
  `sub_id` through every handler call. Reads as a tiny choice, but
  it means the handler signatures stay clean and the sub runtime
  can be removed without rewriting any handler.

- **Idempotency on `tool_use_id`, not on tool+args.** The dedup
  key is the Anthropic-issued id, not (tool, args). A retry of the
  same tool_use_id returns the recorded result; a retry with
  mutated args but a new id is a *new* call. This is the right
  primitive because the API is the source of truth for tool
  identity.

- **Per-turn one-`flag_needs_input` enforcement via soft-reject
  tool_result** (`runtime.py:312–336`) rather than prompt
  re-issuing. The agent sees a structured rejection and can batch
  on the next turn. Cost: extra turn of latency. Benefit: the
  rule holds even when the model ignores the prompt.

- **One compaction model, one intake model, one main model.**
  `config.py:30–40` carves out `INTAKE_MODEL = sonnet-4-6` and
  `SUMMARY_MODEL = haiku-4-5` for the cheap paths. A real
  cost-engineering decision, not a config accident.

- **Budget soft-signal: daily + per-session, deduped per
  instance, surfaced as `check_stuck` decision point** (never
  hard-stops). This is the product philosophy of
  "detect and report, never cut the agent off mid-thought"
  (`stuck.py:7–9`), and it shapes every other runtime decision.

---

**Report file:** `D:\projects\Vellum\notes\deep-dive\01-backend-runtime.md`

**Headline summary:**

- **The runtime is a 200-line `while` loop over a single
  `client.messages.stream()` call**, with four genuinely
  load-bearing patterns: state-snapshot-as-index appended *after*
  every turn (not before), `pause_turn` continuation without
  re-snapshotting, server-side `clear_tool_uses_20250919` with a
  dossier-write exclusion list at 180k tokens, and Haiku-driven
  compaction at 80k that *merges* the first user message into the
  breadcrumb to dodge Anthropic's no-two-consecutive-users rule.

- **Sub-investigations are real recursive agent loops with a hard
  depth cap of 1** (enforced both by a 5-tool allowlist and by the
  sub-prompt), identity propagated via a `ContextVar` so handler
  signatures stay clean, force-completion via prod-then-abandon
  fallback that still has a documented hole ("sub row may remain in
  `running`" if both storage calls fail).

- **The product invariant that the agent never speaks to the user
  is enforced in three places** — prompt ("Assistant prose without
  tool calls evaporates"), runtime (line 282–290 discards the
  prose), and the sub-prompt — and every other design choice
  (manual loop, typed tool surface, dossier state as the prompt,
  idempotency by `tool_use_id`, budget soft-signals, tier-based
  stuck escalation) flows from it.
