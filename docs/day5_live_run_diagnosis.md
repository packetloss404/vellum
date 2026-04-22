# Day 5 live-run diagnosis — credit-card-debt demo

Run date: 2026-04-22
Dossier id: `dos_33fe88548558`
Title: "Credit card debt negotiation - deceased parent, no estate"
Branch: `main` (worktree `agent-a11a9654`)

## Section A — Run summary

| Field | Value |
|---|---|
| Command | `scripts/day2_smoke.py --max-turns 40 --problem "<brief-specified text>"` |
| Turns used | 1 |
| Final status | **error** (caught by runtime, surfaced as `reason="error"`) |
| Duration | 00:01 (one second — errored before any real work) |
| Cost estimate | **$0.00** — the error happens before any API request is billed |
| Sub-investigations | 0 (threshold: ≥3) — **FAIL** |
| Sources consulted | 0 (threshold: ≥20) — **FAIL** |
| Artifacts | 0 (threshold: ≥1) — **FAIL** |
| Considered-and-rejected | 0 |
| Sections | 0 |
| Investigation-log entries | 0 |
| Debrief populated? | No |

### The actual exception

The smoke script swallowed the error text (only the `reason` string propagates
into the digest), so the real error was recovered by replaying the runtime's
first API call against the live key with the same shape (dossier, system
prompt, tools, `max_tokens=32000`):

```
ValueError: Streaming is required for operations that may take longer than
10 minutes. See https://github.com/anthropics/anthropic-sdk-python#long-requests
for more details
```

This is a client-side guard in `anthropic==0.96.0`. Any non-streaming
`messages.create(...)` call with `max_tokens >= ~20k` is rejected before it
hits the wire. The agent never made a single successful API call; the run
terminated inside `DossierAgent.run()` at `runtime.py:117` on turn 1 with
`reason="error"`.

> Cost note: because the error is raised client-side, the $2–$5 budget
> allocated to this run was not spent. A follow-up run (after the fix below)
> will be needed to actually exercise the agent against the API.

## Section B — Behaviors observed vs. expected

Because the run died on turn 1, we cannot observe any of the intended
behaviors. Each expectation is "UNKNOWN — not exercised":

| Expected behavior | Observed |
|---|---|
| Push back on the premise ("you may owe nothing") | UNKNOWN — never spoke |
| Draft an investigation plan before substantive work | UNKNOWN — never spoke |
| Spawn 3–6 sub-investigations | 0 |
| Produce usable artifacts | 0 |
| Record considered-and-rejected paths | 0 |
| Populated, substantive debrief | No debrief written |

The prompt (`agent/prompt.py`) and the plan-approval-gate snapshot block
(`build_state_snapshot`) are both well-constructed on paper and the
expectations above are clearly written into the system prompt. Nothing about
the prompt contributed to this failure; the failure is purely a runtime /
SDK-compatibility bug.

## Section C — Concrete failure modes found

### 1. `messages.create(max_tokens=32000)` hard-fails client-side

**Severity: blocks-demo.**

`backend/vellum/agent/runtime.py:117-123` calls
`self._client.messages.create(model=..., max_tokens=32000, system=..., tools=..., messages=...)`
— a **non-streaming** call. Anthropic SDK 0.96.0 enforces a 10-minute
upper bound for non-streaming calls, and at `max_tokens=32000` the SDK
refuses to issue the request at all:

> `ValueError: Streaming is required for operations that may take longer
> than 10 minutes.`

Every turn of every run hits this before any API contact. Status is the
blanket `reason="error"` with no surfacing of the SDK-level message.

**Suspected cause:** we authored this before the SDK began enforcing the
streaming requirement for large `max_tokens`. The sub-runtime
(`agent/sub_runtime.py`) is likely affected the same way; check and
migrate both to streaming.

### 2. RunResult.error is not surfaced to the operator

**Severity: blocks-demo (as a diagnosis multiplier).**

`runtime.py:245-251` converts any exception into
`RunResult(reason="error", error=f"{type}: {exc}")`. But:

- The smoke script (`scripts/day2_smoke.py:429-435`) reads only
  `reason / turns / session_id / error` into a dict and never prints
  `error` anywhere.
- The orchestrator's done-callback only logs when the task itself raised
  (`orchestrator.py:108-115`); because the runtime catches and converts,
  nothing lands in the logger either.
- `storage.end_work_session` does not persist a `result_error` field on
  the work session.

Net effect: when a run fails, the operator sees
`Status: error  Turns: 1  Duration: 00:01` and zero detail. Debugging
requires instrumenting a replay, which we had to do here.

### 3. Digest does not print the error

**Severity: quality.**

`format_digest()` has no branch for `status == "error"` — it renders the
same substance-bar FAIL lines as a real run. The operator can't tell a
hard-fail from a run that completed but produced nothing.

### 4. `request_user_paste` tool exists but isn't documented in the prompt

**Severity: polish.**

Registered in `tools/handlers.py` and exposed to the model, but the main
prompt never mentions it. The agent won't know when to use it.

### 5. Plan-approval gate depends on the agent voluntarily emitting a
`flag_decision_point(kind="plan_approval", ...)` after calling
`update_investigation_plan`.

**Severity: quality (untested — not exercised this run).**

The system prompt describes the gate; the snapshot block restates it every
turn. That's good layering, but there's no runtime enforcement — nothing
in `runtime.py` blocks `upsert_section` / `log_source_consulted` /
`spawn_sub_investigation` while `plan.approved_at is None`. If the agent
skips the gate, the dossier silently fills with pre-approval work. Can't
tell from this run whether the prose-only gate is sufficient, but it's
worth planning enforcement.

### 6. `VELLUM_MODEL=claude-opus-4-7` works at the API level

**Severity: none (not a bug — noting the false lead).**

A diagnostic ping confirmed `claude-opus-4-7` is accepted by the API and
returns a valid response. The failure is not model-name related.

## Section D — Recommended fixes

### `backend/vellum/agent/runtime.py` (blocker)

Replace the non-streaming call at lines 117–123:

```python
response = await self._client.messages.create(
    model=self.model, max_tokens=32000,
    system=system_prompt, tools=self._tools, messages=state.messages,
)
```

with a streaming call that accumulates into the same shape as
`response`. Two viable patterns in the SDK:

1. **Context-manager stream, then `.get_final_message()`** — keeps the
   rest of the runtime (which reads `response.content`, `response.usage`,
   `response.stop_reason`) unchanged:

    ```python
    async with self._client.messages.stream(
        model=self.model, max_tokens=32000,
        system=system_prompt, tools=self._tools, messages=state.messages,
    ) as stream:
        response = await stream.get_final_message()
    ```

2. **`.with_streaming_response`** if we want to consume events live
   (for progress, tool-use interception). Adds complexity; (1) is the
   minimum-diff fix.

Also reduce `max_tokens=32000` — Opus 4.7's 32k output ceiling is only
needed for the longest section drafts. 8000 is plenty for turn-level
control loops and may let non-streaming work on future SDK rev, but the
proper fix is streaming.

Mirror the change in `backend/vellum/agent/sub_runtime.py` (same SDK
call shape will be used there).

### `backend/vellum/agent/runtime.py` — surface the error

In the exception branch, additionally:

- `logger.exception("runtime failed on turn %d", state.turns)` so
  the orchestrator's configured logging captures the traceback;
- Persist the error onto the work session: add
  `storage.end_work_session(session_id, result_error=str(exc))` and
  teach `WorkSession` to carry the field.

### `backend/vellum/agent/orchestrator.py`

At line 117 (the success branch of `_on_done`), inspect the `RunResult`
and `logger.warning(...)` when `reason == "error"` — right now only
unhandled exceptions log, which means the runtime's caught-and-bagged
errors are invisible.

### `scripts/day2_smoke.py`

`_run_agent` should return `error` verbatim into the digest; `format_digest`
should print:

```
Status: error  |  reason: <reason>  error: <err_msg>
```

so an operator sees the cause, not just the status.

### `backend/vellum/agent/prompt.py`

No blocker, but two polish adds:

- Mention `request_user_paste` in "Your tools" so the agent knows when to
  use it (e.g. "the user's mother had three card statements — ask them
  to paste the account numbers and balances via `request_user_paste`").
- Strengthen the push-back section with an explicit recipe for this
  specific problem shape: "If the user mentions a deceased person and
  debt liability, your first tool call should be `flag_decision_point`
  with a plan-approval asking them to confirm (a) jurisdiction, (b) any
  community-property status, (c) whether they actually received
  collection contact, BEFORE spawning sub-investigations." This gives
  the eval a harder-to-miss signal.

### `backend/vellum/agent/sub_prompt.py`

No change needed — sub prompt was never exercised.

### `backend/vellum/tools/handlers.py`

No blocker. One possible enhancement: richer `mark_investigation_delivered`
description — currently says "substance bar is met" but doesn't cite the
numbers (≥3 subs, ≥20 sources, ≥1 artifact) the way the main prompt does.
Move those numbers into the tool description so the agent can't forget
them even if it partially ignores the system prompt.

### Runtime / orchestration

- Add a runtime-level plan-approval enforcement: reject
  `upsert_section` / `log_source_consulted` / `spawn_sub_investigation`
  with an `is_error` tool-result while `plan.approved_at is None`. The
  prompt describes the gate; the runtime should enforce it so an agent
  that ignores the prompt still can't produce silent pre-approval work.

### Schema / storage

- `WorkSession`: add `result_reason: Optional[str]` and
  `result_error: Optional[str]` columns (and Pydantic fields). Populate
  from `runtime.py` in the `finally` block so every ended session records
  its outcome, not just "ended_at set".

## What to do next

1. Apply Section D.1 (streaming migration + sub-runtime mirror) — this
   is the single blocker.
2. Apply D.2, D.3, D.4 so the next smoke run can be diagnosed without
   another instrumented replay.
3. Re-run `scripts/day2_smoke.py --max-turns 40 --problem "<brief text>"`
   exactly once to exercise the prompt layer and produce the real
   Section-B observations this run could not collect.
4. Only then consider D.5 (prompt polish) and the enforcement / schema
   items — those depend on observations from a run that actually spoke
   to the API.
