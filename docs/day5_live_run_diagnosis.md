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

---

## Post-approval run (auto-resolved)

Run date: 2026-04-22 (second live run of the day)
Dossier id: `dos_83702bf49194` (mid-investigation, from the previous day-5 run)
Branch: `main` (worktree `agent-a57254af`)

### Context

Per the previous (mid-investigation) live run, the dossier was left in
state: plan drafted (6 items) + `plan_approval` decision point open +
one `needs_input` open; no sections, sub-investigations, or artifacts.
Work session `ws_b3230746c268` used 74 328 tokens creating that state
and then ended cleanly. Dossier status was `active` (not `delivered`
— that note in the run brief appears to be stale).

### Pre-resume operations (HTTP)

All four operations succeeded against the running backend at
`127.0.0.1:8731`:

1. `PATCH /api/dossiers/dos_83702bf49194` `{"status":"active"}` — OK (already active).
2. `POST /api/dossiers/.../decision-points/dp_ef204c7686ad/resolve` `{"chosen":"Approve"}` — OK. `resolved_at=2026-04-22T20:37:43Z`. Storage auto-approve hook set `investigation_plan.approved_at=2026-04-22T20:37:43Z`.
3. `POST /api/dossiers/.../needs-input/ni_3ae38b1188e2/resolve` with the jurisdictional / account-relationship / estate / contact-history / goal facts — OK. `answered_at=2026-04-22T20:37:53Z`.
4. Final verification `GET /api/dossiers/dos_83702bf49194`:
   - `status=active`
   - `investigation_plan.approved_at=2026-04-22T20:37:43Z`
   - `dp_ef204c7686ad` resolved
   - `ni_3ae38b1188e2` answered
   - all consistent with expected pre-resume state.

### Resume and monitor

`POST /api/dossiers/dos_83702bf49194/resume` returned
`{"status":"started","work_session_id":"ws_cd2977dbb373"}` at
`2026-04-22T20:38:03Z`.

Monitor polled every 30 s. Snapshots (compact):

| elapsed | doss.status | run_status | log entries | subs | artifacts | sections | sources | ws tokens | ws ended |
|---|---|---|---|---|---|---|---|---|---|
| 0 s | active | idle | 0 | 0 | 0 | 0 | 0 | 0 | null |
| 30 s | active | idle | 0 | 0 | 0 | 0 | 0 | 0 | null |
| 60 s | active | idle | 0 | 0 | 0 | 0 | 0 | 0 | null |
| 90 s | active | idle | 0 | 0 | 0 | 0 | 0 | 0 | null |
| 120 s | active | idle | 0 | 0 | 0 | 0 | 0 | 0 | null |
| 150 s | active | idle | 0 | 0 | 0 | 0 | 0 | 0 | null |

At t≈130 s, `GET /api/agents/running` returned `[]` and
`GET /api/dossiers/.../agent/status` returned `running: false`. The
orchestrator's done-callback had pruned the task; yet the work session
`ws_cd2977dbb373` still had `ended_at=null` and
`token_budget_used=0`. Monitor was terminated manually (the run was
already dead), the orphan session was closed via
`POST /api/work-sessions/ws_cd2977dbb373/end` to keep the storage
layer clean. Final `token_budget_used` for the session: **0**.

### Final substance bar

| Threshold | Target | Actual | Pass/Fail |
|---|---|---|---|
| sub-investigations | ≥ 3 | **0** | **FAIL** |
| sources consulted | ≥ 20 | **0** | **FAIL** |
| artifacts | ≥ 1 | **0** | **FAIL** |

Zero progress from the post-approval run.

### Behaviors observed

- **Did the agent use the answered facts?** No — the agent never produced a turn. The facts remain in the dossier but never reached the model on this run.
- **Did it spawn sub-investigations?** No.
- **Did it produce artifacts?** No.
- **Did it record considered-and-rejected paths?** No.
- **Is the final debrief substantive?** No change from before the resume — the `what_i_did` / `what_i_found` from the first run still reads as preliminary (hedged, no citations, no state-specific reasoning), `do_next` and `left_open` are still `None`.

### New failure modes found

**5. Silent no-op on resume (highest severity)**

> *Observed*: `/resume` returned `status=started` and opened
> `ws_cd2977dbb373`. `GET /api/agents/running` went from non-empty
> back to `[]` within ~2 minutes. Throughout, the work session
> recorded `token_budget_used=0`, `investigation_log` had 0 entries,
> and `ws.ended_at` was `null`. The agent made no API call, no tool
> call, no write of any kind.

Suspected cause: one of two paths in `DossierAgent.run()`:

 a. An exception was raised **before** the `try:` block at
    `runtime.py:113` (i.e. in `_resolve_session`,
    `build_system_prompt`, or `_snapshot_content` →
    `build_state_snapshot`) — in which case the runtime's
    `finally: storage.end_work_session(...)` would not run, which
    matches the observed orphan session exactly.

    I manually exercised `storage.get_dossier_full(...)`,
    `prompt.build_system_prompt(...)`, and
    `prompt.build_state_snapshot(...)` against this dossier; all three
    succeeded. So if this is the path, the triggering condition is
    specific to the asyncio task context (e.g. a thread-sensitive
    storage access or a module-level import happening for the first
    time under the event loop).

 b. An exception was raised inside the orchestrator's `start()` call
    after `asyncio.create_task` but before the runtime's own `try:` —
    the task's done-callback logs the error via
    `logger.error(..., exc_info=exc)`, but dev.sh streams logs to
    stdout with no file capture, so the traceback is invisible once
    the shell scrolls.

Either way, the symptom is identical from the API surface: session
orphan, 0 tokens, task gone.

Severity: **critical**. This is the post-approval path — the whole
product experience after the user answers the plan. A silent no-op
here means the user approves the plan and the agent simply does
nothing, with no observable reason.

**6. Orphan work-session on runtime-boundary failure (high)**

> *Observed*: `ws_cd2977dbb373` had `ended_at=null` after the task
> was already reaped by the orchestrator's done-callback.

Suspected cause: `DossierAgent.run()` performs `_resolve_session()`,
`build_system_prompt()`, and `_snapshot_content()` **before** the
`try:` block that holds the `finally: end_work_session(...)` clause.
Any exception in those steps leaves the session open forever. This
compounds failure mode 5 by making retries impossible — a subsequent
`/resume` 409s on the stale active session.

Severity: **high**. Blocks all retries without manual intervention.

**7. Done-callback log loss (high)**

> *Observed*: `_make_done_callback` in
> `orchestrator.py:99–120` logs exceptions with full tracebacks, but
> the backend is launched via `dev.sh` with stdout going straight to
> the terminal (no file, no rotation). In a live-run context, the
> first evidence of a failure is lost as soon as the shell scrolls —
> which is how we ended up with symptom (5) above and no traceback.

Severity: **high**. Makes the whole runtime effectively un-debuggable
on dev machines.

**8. Resume endpoint does not expose run-outcome (medium)**

> *Observed*: the `/resume` endpoint is fire-and-forget; the caller
> has no way to learn that the run ended with `reason="error"` and
> what the error was. Combined with (7), a run that dies on turn 0
> looks indistinguishable to the UI from "running in the background,
> come back later".

Severity: **medium**. User-visible. A next-run UX would say "we
tried; here's why it failed."

### Cost

- First session (`ws_b3230746c268`, pre-approval): 74 328 tokens.
  Rough Opus-4-7 blended estimate at $15/Mtok input + $75/Mtok output,
  assuming roughly 80/20 split: ≈ **$1.80–$2.20**. This is sunk cost
  from the previous live run, not this one.
- Second session (`ws_cd2977dbb373`, post-approval, **this run**):
  **0 tokens — $0.00**. The agent never reached the API.
- **Total cost of this diagnosis run: $0.00** (within noise of the
  free HTTP calls to the local backend).

The $3–$10 budget the run brief allocated was not spent. As with the
original diagnosis, a follow-up run will be needed to exercise the
post-approval path once failure modes 5–7 are understood.

### Recommended investigation

Do not attempt a retry until the silent-failure instrumentation
lands. Specifically:

1. **Capture agent task exceptions to a file.** Add a
   `logging.FileHandler` in `main.py` (gated by `VELLUM_AGENT_LOG`
   env var, defaulting to `backend/logs/agent.log`) so the
   orchestrator's done-callback tracebacks survive after the terminal
   scrolls. Rotation can wait.

2. **Move the runtime's session-end into a try/finally at the top of
   `run()`.** Shift `_resolve_session()`,
   `build_system_prompt(...)`, and the first `_snapshot_content(...)`
   call **inside** the `try:` block so the existing
   `finally: storage.end_work_session(...)` covers them. This fixes
   failure mode 6.

3. **Add an outcome column to `work_sessions`.** Per Section D of
   the original diagnosis ("Schema / storage"): add
   `result_reason: str` and `result_error: str` and populate them
   from the runtime's `finally`. This fixes failure mode 8 and makes
   future live-run forensics a single SQL query.

4. **Re-run the post-approval scenario** with the instrumentation in
   place, against a fresh resume of this same dossier (the facts
   answered in the `needs_input` are rich and worth preserving).
   Expect this to surface whatever the real exception was in step 2.

---

## Post-streaming-fix live run (manual auto-resolve)

Run date: 2026-04-22 (after streaming migration + prompt tightening)
Dossier id: `dos_83702bf49194` (continued from the first post-approval attempt)
Entry point: direct `DossierAgent.run(max_turns=15)` against the already-approved, fact-answered state.

### Result

- Turns used: 10 (`reason=delivered`)
- **Substance bar**:
  - sub-investigations ≥ 3: **PASS** (3 spawned)
  - sources consulted ≥ 20: close but FAIL (15 — debrief claims "~20")
  - artifacts ≥ 1: **PASS** (2)
- Sections: 6 (first one: "The question is almost certainly the wrong question" — premise pushback in the title itself)
- Considered-and-rejected: 3
- Next actions: 5
- Debrief: populated, decisive

### What worked

1. **Premise pushback is real and visible.** The first section title is "The question is almost certainly the wrong question" and the debrief opens with "Pushed back on the premise and investigated whether the friend owes this debt at all before answering 'what opening percentage.'"
2. **Sub-investigations were spawned on the right questions**: (i) risks of negotiating/paying non-probate debt, (ii) FDCPA/Reg F/CFPB on collector behavior, (iii) state-specific exposure including non-probate asset clawback. These are credible scoped dives.
3. **Usable artifacts produced**: a letter and a checklist. The user can act on these.
4. **Considered-and-rejected logged** (3 paths). Visible wrestling.

### New failure modes

1. **Sub-investigations stay in `running` state.** All 3 spawned subs show `state=running`, `return_summary=null`. The main agent's `spawn_sub_investigation` handler blocks until the sub returns, then should persist `state=delivered` via `storage.complete_sub_investigation`. The subs produced output (15 source_consulted entries exist, attributed via context) but the completion call never landed. Likely: the sub-agent loop errored mid-turn (streaming exception, tool dispatch error, etc.) and the force-complete path ALSO failed — leaving the subs pristine. Severity: **quality/demo** — subs visibly "never finished" even though their work did inform the main. Day-6 fix candidate.
2. **`delivered` status while subs running.** The main agent self-declared `mark_investigation_delivered` with 3 subs still in `running` — violates the updated prompt's "not done while blocked/incomplete" rule. Likely the prompt strengthening is not strong enough on the "subs are part of substance bar" read. Day-6 fix candidate.
3. **Source-log underreporting** (15 actual vs. ~20 claimed in debrief). The model is undercounting its per-source-logging. Likely a prompt/tool-description follow-up — `log_source_consulted` needs to be reinforced as non-optional.

### Day-6 priorities (derived from this run)

- Investigate why sub_runtime's completion path doesn't persist (add more logging; instrument the force-complete). The 3 running subs on the demo dossier are the most visible imperfection.
- Tighten `mark_investigation_delivered` to check sub-investigation states: refuse if any sub is `running`.
- Consider a backend sanity-check on delivered: reject the transition if any sub is running (defence in depth beyond the prompt).
- Otherwise: the dossier at `dos_83702bf49194` is demo-worthy as-is.
