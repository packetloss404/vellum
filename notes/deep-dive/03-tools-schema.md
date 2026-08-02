# Vellum deep-dive: typed tool surface, intake agent, and data schema

Scope: how a closed set of typed Pydantic-backed tools drives every user-visible
mutation of a Vellum dossier, the separate intake agent that opens dossiers, and
the SQLite schema underneath it all. All file paths are relative to
`backend/vellum/` unless otherwise noted.

A note on counts up front: the brief described "27 typed tools" and "17
tables." The actual surface is **30 typed dossier tools + 7 intake tools** and
**22 SQLite tables**. I reconcile this in §1 and §6.

---

## 1. Catalog of typed tools

### 1.1 Dossier agent surface (30 tools, `tools/handlers.py:681-715`)

Grouped by what they mutate. Storage columns in parens.

| Tool | Input shape | What it does | Storage touch |
|---|---|---|---|
| **Sections (write)** | | | |
| `upsert_section` | `SectionUpsert` (models.py:479) | Create or revise a section. Required `change_note` shows in the plan-diff. | `sections`, `change_log` |
| `update_section_state` | `{section_id, new_state, reason}` (handlers.py:1098) | Flip `confident / provisional / blocked`. | `sections`, `change_log` |
| `delete_section` | `{section_id, reason}` (handlers.py:1110) | Remove a section. | `sections`, `change_log` |
| `reorder_sections` | `{section_ids: [...]}` (handlers.py:1122) | Full-list re-order. | `sections`, `change_log` |
| **Sections (read-only / JIT)** | | | |
| `get_section` | `{section_id}` (handlers.py:1290) | Load full body of one section. | `sections` |
| `list_sections` | `{state_filter?, kind_filter?}` (handlers.py:1299) | Preview index (title + 80-char preview). | `sections` |
| **Decisions / blockers** | | | |
| `flag_decision_point` | `DecisionPointCreate` (models.py:509) | Surface a structured choice to the user. `kind='plan_approval'` gates plan sign-off. | `decision_points`, `change_log` |
| `flag_needs_input` | `NeedsInputCreate` (models.py:500) | One factual question. | `needs_input`, `change_log` |
| `request_user_paste` | `{what_needed}` (handlers.py:1147) | Softer needs_input for document paste. | `needs_input` |
| **Stuck** | | | |
| `check_stuck` (v1) | `{summary_of_attempts, options_for_user}` (handlers.py:1132) | Reasoning-trail note + DP. | `reasoning_trail`, `decision_points` |
| `declare_stuck` (v2) | `{summary, options, recommendation}` (handlers.py:1271) | `stuck_declared` log entry + DP. | `investigation_log`, `decision_points` |
| **Reasoning & audit** | | | |
| `append_reasoning` | `ReasoningAppend` (models.py:521) | Private cross-session note. | `reasoning_trail` |
| `mark_ruled_out` | `RuledOutCreate` (models.py:526) | Lighter-weight rejection. | `ruled_out`, `change_log` |
| `mark_considered_and_rejected` | `ConsideredAndRejectedCreate` (models.py:755) | Richer rejection with `cost_of_error`. | `considered_and_rejected`, `investigation_log`, `change_log` |
| `log_source_consulted` | `{citation, why_consulted, what_learned, supports_section_ids?}` (handlers.py:1255) | One row per source read. Drives the "47 sources" counter. | `investigation_log` |
| **Investigation plan** | | | |
| `update_investigation_plan` | `InvestigationPlanUpdate` (models.py:543) | Full plan; first-write replaces, partial-merge for revisions. | `dossiers.investigation_plan`, `plan_items`, `change_log` |
| **Debrief & theory** | | | |
| `update_debrief` | `DebriefUpdate` (models.py:536) | Top-of-dossier 2-minute read. | `dossiers.debrief` |
| `update_working_theory` | `WorkingTheoryUpdate` (models.py:159) | Current belief + confidence. | `dossiers.working_theory`, `change_log` |
| `record_premise_challenge` | `PremiseChallengeUpdate` (models.py:187) | Audit hidden assumptions in the user's question. | `dossiers.premise_challenge`, `change_log` |
| **Artifacts** | | | |
| `add_artifact` | `ArtifactCreate` (models.py:612) | Draft a letter / script / table. | `artifacts`, `change_log` |
| `update_artifact` | `ArtifactUpdate` + `artifact_id` (handlers.py:1160) | Revise. | `artifacts`, `change_log` |
| **Sub-investigations** | | | |
| `spawn_sub_investigation` | `SubInvestigationSpawn` (models.py:671) | Open a scoped sub. SYNCHRONOUS in day-1 (handlers.py:250 docstring); sub_runtime overrides via `HANDLER_OVERRIDES`. | `sub_investigations` |
| `complete_sub_investigation` | `SubInvestigationComplete` + `sub_investigation_id` (handlers.py:1193) | Sub-agent's only exit call. | `sub_investigations`, `change_log` |
| `update_sub_investigation` | `SubInvestigationUpdate` + `sub_investigation_id` (handlers.py:1223) | Partial merge of `current_finding` / `confidence` / `known_facts` / etc. | `sub_investigations` |
| **Actions for the user** | | | |
| `set_next_action` | `NextActionCreate` (models.py:573) | Concrete next action. | `next_actions`, `change_log` |
| **Sleep / wake** | | | |
| `schedule_wake` | `ScheduleWakeArgs` (models.py:337) | Self-schedule a future wake. Honors `sleep_mode_enabled` + `schedule_wake_max_hours` settings. | `dossiers.wake_at`, `reasoning_trail` |
| **Lifecycle** | | | |
| `mark_investigation_delivered` | `MarkDeliveredArgs` (models.py:764) | TERMINATES the loop. Pre-flight guards reject if any sub still running, needs_input unanswered, or plan_approval DP open. | `dossiers.status`, `plan_items`, `reasoning_trail` |
| `summarize_session` | `SummarizeSessionArgs` (models.py:790) | Phase-3 "while you were away" row. | `session_summaries` |
| **Read-only JIT (re-listed for clarity)** | | | |
| `get_artifact` | `{artifact_id}` (handlers.py:1310) | Full content of one artifact. | `artifacts` |
| `get_reasoning_window` | `{limit?, tag_filter?, since_iso?}` (handlers.py:1319) | Time/filter slice of reasoning trail. | `reasoning_trail` |

All 30 entries are registered in `HANDLERS` at `tools/handlers.py:681-715`
and their Anthropic-format JSON schemas are emitted by `tool_schemas()` at
`tools/handlers.py:1063`.

### 1.2 Intake agent surface (7 tools, `intake/tools.py:311-319`)

| Tool | Args | What it does | Storage touch |
|---|---|---|---|
| `set_title` | `{title}` | Set `IntakeState.title` | `intake_sessions.state` (JSON) |
| `set_problem_statement` | `{problem_statement}` | Set `state.problem_statement` | `intake_sessions.state` |
| `set_dossier_type` | `{dossier_type}` (enum-coerced) | Set `state.dossier_type` | `intake_sessions.state` |
| `set_out_of_scope` | `{items: [...]}` | Replace-scope semantics | `intake_sessions.state` |
| `set_check_in_policy` | `{cadence, notes?}` | Set cadence | `intake_sessions.state` |
| `commit_intake` | `{plan_items?, plan_rationale?}` | Build `DossierCreate` → `create_dossier`, transition to `committed`. Optionally seeds a `plan_approval` decision_point inline. | `dossiers`, `decision_points`, `plan_items`, `intake_sessions.status` |
| `abandon_intake` | `{reason}` | Mark `abandoned`. Idempotent. | `intake_sessions.status` |

The intake tool surface is genuinely **different** from the dossier surface:
no sections, no artifacts, no sub-investigations, no reasoning. The intake
agent cannot write to the dossier directly — it can only mutate its own
`IntakeState` JSON blob and call `commit_intake` once. The 30-vs-7 split is
deliberate and is the heart of the closed-loop claim: the dossier agent has
many tools because it has many things to *do*, the intake agent has seven
because it only has five fields to *collect* (plus two terminals).

### 1.3 Count reconciliation

The brief said ~27 typed tools. Actual count is **30** dossier tools
(`HANDLERS` dict at `tools/handlers.py:681-715`) plus **7** intake tools
(`HANDLERS` at `intake/tools.py:311-319`), for **37 total** in the system.
The brief was off by ~3 on the dossier side — those are the four JIT
read-only tools (`get_section`, `list_sections`, `get_artifact`,
`get_reasoning_window`) which were likely not counted in the day-1 "27 tools"
description plus possibly one or two v2 tools that landed later.

---

## 2. Tool handler patterns

Every handler in `tools/handlers.py` follows the same shape — a 5-line
core with optional pre-flight and post-write logic. The skeleton is:

```python
# tools/handlers.py:48-51
def upsert_section(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    section = storage.upsert_section(dossier_id, m.SectionUpsert(**args), session_id)
    return {"section_id": section.id, "state": section.state.value, "order": section.order}
```

### 2.1 The five-axis pattern

1. **Validation** — every handler takes `args: dict[str, Any]` and immediately
   calls `m.SomeCreate(**args)`. Pydantic does the rest. The strictness is
   the model's default: required fields raise, types coerce, enums reject
   bad values. There is no manual validation in any handler I read.

2. **Persistence** — a single store call. `storage.<thing>(dossier_id, ...,
   session_id)`. Storage functions wrap a `with connect() as conn:` block
   and execute one or two SQL statements inside it. The handler never sees
   a connection.

3. **Side effects** — every handler runs `_ensure_session(dossier_id)` first
   (handlers.py:33-40), which gets-or-creates the active `work_session`.
   Some handlers also call `_touch_dossier(conn, dossier_id)` to bump
   `updated_at` (helpers.py, used inside storage).

4. **Idempotency hooks** — NOT in the handler. Idempotency is one layer up,
   in `runtime.py:571-586`, which checks `storage.get_tool_invocation(
   tool_use_id)` BEFORE invoking the handler. The handler is reached only
   on first dispatch.

5. **Return shape** — a compact dict, **IDs and enum states, never prose**.
   The agent does not see "Section saved successfully"; it sees
   `{"section_id": "sec_abc123", "state": "confident", "order": 30.0}`.
   The README's "no prose surfaces to the user" claim is matched by
   "no prose in the agent's view of success either" — both halves matter.

### 2.2 Two representative walks

#### `mark_investigation_delivered` — the most complex

This is the only handler with pre-flight guards. It refuses to flip
`dossier.status` to `delivered` unless three invariants hold:

```python
# tools/handlers.py:482-570
def mark_investigation_delivered(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    parsed = m.MarkDeliveredArgs(**args)
    why_enough = parsed.why_enough

    # --- Pre-flight guards ------------------------------------------------
    running_subs = storage.list_sub_investigations(
        dossier_id, state=m.SubInvestigationState.running
    )
    if running_subs:
        return {
            "ok": False, "reason": "still_running_subs",
            "subs": [{"id": s.id, "scope": s.scope} for s in running_subs],
            "message": (
                f"{len(running_subs)} sub-investigation(s) still running; "
                "wait for them or abandon explicitly before marking delivered"
            ),
        }
    open_needs = storage.list_needs_input(dossier_id, open_only=True)
    if open_needs:
        return {"ok": False, "reason": "open_needs_input", ...}
    open_dps = storage.list_decision_points(dossier_id, open_only=True)
    open_plan_approvals = [dp for dp in open_dps if dp.kind == "plan_approval"]
    if open_plan_approvals:
        return {"ok": False, "reason": "open_plan_approval", ...}

    # --- All clear: proceed ----------------------------------------------
    session_id = _ensure_session(dossier_id)
    storage.update_dossier(
        dossier_id, m.DossierUpdate(status=m.DossierStatus.delivered)
    )
    plan_sweep = storage.finalize_plan_on_delivery(dossier_id, session_id)
    storage.append_reasoning(
        dossier_id,
        m.ReasoningAppend(note=f"[delivered] {why_enough}", tags=["delivered"]),
        session_id,
    )
    return {
        "ok": True, "dossier_id": dossier_id,
        "status": m.DossierStatus.delivered.value,
        "plan_items_swept": plan_sweep,
    }
```

Notable shape:
- **Soft refusal as a structured response.** `{"ok": False, "reason": "..."}`
  is the agreed dialect (used in 8+ handlers). The agent reads `reason` and
  decides what to do; the loop does not crash.
- **Plan-sweep side effect.** `finalize_plan_on_delivery` flips any
  remaining `planned`/`in_progress` items to `completed` (handlers.py:556
  comment explains why: pre-fix dossiers whose sub-investigations lack
  `plan_item_id` linkage would otherwise ship with visibly-still-planned
  items).
- **No telemetry call from the handler itself.** Telemetry is wired via
  `TOOL_HOOKS` in `dispatch()` (handlers.py:1361-1368), keeping handlers
  pure.

#### `set_next_action` — the simplest interesting case

```python
# tools/handlers.py:336-342
def set_next_action(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    item = storage.add_next_action(
        dossier_id, m.NextActionCreate(**args), session_id
    )
    return {"next_action_id": item.id}
```

Pure: no pre-flight, no post-write logic. Returns just the new id. Storage
inserts the row and writes a `change_log` entry with `kind="next_action_added"`.
The agent reads the id back and either reorders via the API or sets another.

#### `declare_stuck` — the "compound" pattern

Like `check_stuck` but stronger:

```python
# tools/handlers.py:345-380 (paraphrased)
def declare_stuck(dossier_id, args):
    session_id = _ensure_session(dossier_id)
    summary = args["summary_of_attempts"]
    options = args["options_for_user"]
    recommendation = args.get("recommendation") or summary

    storage.append_investigation_log(  # 1. log a typed entry
        dossier_id, m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.stuck_declared,
            payload={"summary_of_attempts": summary, ...},
            summary=f"stuck: {summary[:160]}",
        ), session_id,
    )
    dp = storage.add_decision_point(   # 2. raise a DP
        dossier_id, m.DecisionPointCreate(
            title="Stuck — need your direction",
            options=[m.DecisionOption(**o) for o in options],
            recommendation=recommendation,
        ), session_id,
    )
    return {"decision_point_id": dp.id}
```

The compound pattern: one tool call produces both an investigation_log
entry (visible in the audit surface) AND a decision_point (the
user-blocking surface). The agent doesn't have to remember to call two
tools.

---

## 3. Closed-loop enforcement — is it real?

**Yes, it is enforced, not a convention.** Two enforcement points:

### 3.1 The main loop drops pure-prose turns

```python
# agent/runtime.py:278-290
tool_uses = [
    b for b in response.content if getattr(b, "type", None) == "tool_use"
]

if not tool_uses:
    # Model ended the turn. Any prose is discarded — the agent
    # speaks only through tool calls into the dossier.
    _end_reason = m.WorkSessionEndReason.ended_turn
    return RunResult(
        reason="ended_turn", turns=state.turns, session_id=session_id,
    )
```

If the model produces only text and ends the turn, the prose is **never
copied to a user-visible channel**. The handler `RunResult` is returned
to the API caller; the prose stays serialized inside the Anthropic SDK
message history (`state.messages` at runtime.py:233) but is not surfaced
to the user. The next user request will inject a fresh dossier state
snapshot, and the user's last view of the dossier is whatever the prior
tool calls wrote.

The docstring at `runtime.py:18-20` confirms:

```python
"""The agent never emits prose to the user. All user-visible content flows
through dossier tool calls into ``storage``; if a turn ends with prose
and no tool calls, the prose is discarded."""
```

### 3.2 Text blocks in mixed-content turns are still silent

When the model produces text + tool_uses in the same response, the text
is **not** collected for the user — only the tool_use blocks are
dispatched. The text blocks are model-dumped into the message history
(runtime.py:229-235) so the next Anthropic call sees them, but they
are never bubbled up to the user. The user only ever sees content
that landed in `storage`.

### 3.3 One sanitizer for the safety net

There's an additional layer in `storage/_helpers.py:27-57`: even when the
agent *does* write prose via a tool, the row-converter strips
tool-markup-style tags from debriefs, working theory, and premise challenge
fields:

```python
# storage/_helpers.py:27-35
_TOOL_MARKUP_RE = re.compile(
    r"""
    <\/?\s*(?:parameter|invoke|function_calls|tool_use|answer|thinking|result)
      (?:\s[^>]*)?>
    |
    <\/[a-z_][a-z0-9_]*>
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)
```

This catches the failure mode where the model "thinks out loud" by
embedding tool calls inside a string field. The regex strips the markup
on read, so the user never sees a half-formed `<parameter>...</parameter>`
in their dossier.

### 3.4 The single soft spot

If the model calls a tool with a string field containing only prose (e.g.
`update_debrief({"what_i_did": "..."})`), that prose IS the user-visible
content. The closed loop is "the agent must use a tool to surface
prose" — not "the agent must keep its opinions out of the dossier."
This is the right boundary; the dossier *is* prose, but it must be
written through the right tool with the right shape.

---

## 4. Intake agent

### 4.1 Architectural separation

The intake runtime is a **separate module** at `intake/runtime.py` with
its own storage (`intake/storage.py`, 6 intake tables — see §6.1), its
own models (`intake/models.py`, no `Dossier` references), its own prompt
(`intake/prompt.py`, 124 lines of system prompt), and its own tool
surface (`intake/tools.py`, 7 tools).

The key architectural decisions in the docstring at `runtime.py:1-20`:

> CRITICAL difference from the dossier agent:
>   * Intake DOES speak to the user in prose. The final text content of
>     each turn IS the user-facing reply, returned in
>     ``IntakeTurnResult.assistant_message`` and persisted as an
>     ``assistant`` message in the intake transcript.
>   * No per-turn dossier state snapshot — messages are short and the
>     gathered-so-far block is surfaced via the system prompt.
>   * No stuck detection — intake conversations are bounded to ~10 turns
>     of internal tool-use iteration per user turn.
>   * No work_sessions — the intake_session itself is the unit.

This is the only place in the system where the agent emits prose to the
user. The intake runtime is essentially a structured-form interview with
a soft conversational overlay.

### 4.2 Model: `claude-sonnet-4-6` (verified)

Confirmed in `config.py:39`:

```python
INTAKE_MODEL = os.getenv("VELLUM_INTAKE_MODEL", "claude-sonnet-4-6")
```

The justification comment at `config.py:33-35`:

> Per-workload model routing. INTAKE_MODEL: intake is a constrained
> conversational flow, not deep investigation — Sonnet 4.6 delivers the
> same quality at ~40% of Opus cost.

The intake runtime also accepts a per-instance override
(`intake/runtime.py:56-61`) for debug/quality-comparison use, but
defaults to `INTAKE_MODEL`. The dossier agent uses `MODEL` (default
`claude-opus-4-7` at `config.py:30`).

The intake runtime **also records its spend** in the daily budget rollup
(via `main_storage.record_budget_usage` at `runtime.py:153-159`), so a
prolific intake conversation is visible on the same cost dashboard as
dossier work.

### 4.3 Tool surface comparison

| Capability | Dossier agent (30 tools) | Intake agent (7 tools) |
|---|---|---|
| Write to dossier | yes (sections, artifacts, plan, theory, ...) | no |
| Set state fields | via 30 specialized tools | 5 `set_*` tools mutate a JSON blob |
| Commit to a real entity | via terminal tool `mark_investigation_delivered` | via `commit_intake` |
| Abandon | `request_user_paste` is a soft exit | `abandon_intake` is a hard terminal |
| Read state | 4 JIT read-only tools (`get_section`, etc.) | none — state is rebuilt in system prompt |
| Speak to user in prose | NO (enforced) | YES |

The intake surface is **deliberately a closed 7-tool vocab** — the
prompt says so at `prompt.py:45-51`:

> Seven tools: set_title, set_problem_statement, set_dossier_type,
> set_out_of_scope, set_check_in_policy, commit_intake, abandon_intake.
> Call them as info accrues — talking about a field without the tool
> call does nothing.

### 4.4 Transition from prose interview to constructed dossier

The handoff happens inside `commit_intake` at `intake/tools.py:122-295`:

1. **Required-field gate** (lines 173-194). Returns `{"error": "...",
   "missing": [...]}` if any of `title`, `problem_statement`,
   `dossier_type`, `check_in_policy` is missing. The model recovers
   by calling the right `set_*` tool and retrying.

2. **Dossier creation** (lines 196-207). Constructs `DossierCreate` from
   the gathered `IntakeState` and calls `dossier_storage.create_dossier`.
   The `intake_sessions` row transitions to `committed` with
   `dossier_id` set.

3. **Optional plan seeding** (lines 219-253). If the agent passed
   `plan_items` + `plan_rationale`, `commit_intake` calls
   `update_investigation_plan` with `approve=False`. The seed is
   best-effort: a validation failure returns `plan_error` to the
   model but **does not roll back the committed dossier** (lines
   210-213). This is a deliberate resilience choice — opening a
   dossier is more important than seeding a perfect plan.

4. **Inline plan_approval DP** (lines 254-294). If the plan seeded
   successfully, a `plan_approval` decision_point is created on the
   new dossier immediately, with two structured options
   ("Approve" / "Redirect"). This means the user can see and act on
   the plan the moment they open the dossier — no need to click
   Resume to let the agent produce the DP. Resolving this DP sets
   `wake_pending` (via `resolve_decision_point` per the comment at
   line 257-260), so approval wakes the dossier agent through the
   same reactive path as any other decision.

5. **Idempotency** (lines 165-170). If the intake was already committed,
   the call returns the existing `dossier_id` with `plan_seeded=False`
   — the first commit wins, replays don't overwrite.

The handoff is one-shot: once committed, the intake session is over.
The dossier agent is then driven by the user's first visit (which
fires `mark_dossier_visited`, the first appearance of the
plan_approval DP), the scheduler (if the dossier is set to wake), or
an explicit resume.

### 4.5 Intake runtime loop

The intake loop is intentionally simpler than the dossier loop:

```python
# intake/runtime.py:34-39
INTERNAL_MAX_ITERATIONS = 10
```

10 internal model<->tool iterations per user turn, then short-circuit
to a safe fallback message (runtime.py:202-221). No stuck detection, no
compaction, no per-turn state snapshot. The only failure-recovery is
the per-handler `except Exception` at `runtime.py:288-301` which
returns `is_error=True` to the model so it can retry with a corrected
arg.

---

## 5. Pydantic as single source of truth

`models.py` is **the** schema file. Everything else derives from it.

### 5.1 (a) The Anthropic tool schema

Tool schemas are emitted by `model.model_json_schema()` inside
`tools/handlers.py:1074-1080` for Pydantic-derived schemas, and via
`m.DecisionOption.model_json_schema()` at handlers.py:1060 for the
shared decision-option sub-schema:

```python
# tools/handlers.py:1074-1082
for name, model in _INPUT_MODELS.items():
    if model is None:
        continue
    schemas.append({
        "name": name,
        "description": TOOL_DESCRIPTIONS[name],
        "input_schema": model.model_json_schema(),
    })
```

The intake agent does the same in `intake/tools.py:368-502` — for
tools that don't map cleanly to a single model, the schema is
hand-written but the `enum` values are pulled from
`[t.value for t in m.DossierType]` (line 365) and
`[c.value for c in m.CheckInCadence]` (line 366), keeping the source
of truth in `models.py`.

### 5.2 (b) The SQLite row

The `Dossier`, `Section`, `NeedsInput`, etc. models are turned into
rows by `_row_to_dossier`, `_row_to_section`, etc. in
`storage/_helpers.py` (around lines 82-120+). JSON blob columns
(`out_of_scope`, `check_in_policy`, `debrief`, `investigation_plan`,
`working_theory`, `premise_challenge`) are parsed back via
`m.SomeModel.model_validate_json(text)`. So adding a new required
field to e.g. `WorkingTheory` will fail row parsing on existing rows
— a real, strict coupling.

List types use a `TypeAdapter` at `storage/_helpers.py:21-22`:

```python
_SourceList = TypeAdapter(list[m.Source])
_OptionList = TypeAdapter(list[m.DecisionOption])
```

So `Source` and `DecisionOption` round-trip the same way the Pydantic
model classes do, with the same validation.

### 5.3 (c) The FastAPI response

The models double as Pydantic request/response shapes. The intake
has dedicated `IntakeStart` / `IntakeUserTurn` request models
(`intake/models.py:56-61`), and the dossier uses `DossierCreate`,
`DossierUpdate`, `SectionUpsert`, etc. (models.py:463-577). API
routes (e.g. `api/routes.py`, `api/intake_routes.py`) consume these
directly. The intake return type is a dataclass
`IntakeTurnResult` at `intake/models.py:67-73` rather than a Pydantic
model — it is constructed in the runtime and serialized to JSON for
the API.

### 5.4 How strict is the validation?

Strict on shapes, lax on content.

- **Required fields**: enforced. `MarkDeliveredArgs` has only
  `why_enough: str`; missing it raises at handler entry.
  `InvestigationPlanUpdate` items must be a list; the
  `field_validator` at `models.py:548-570` even coerces legacy
  `InvestigationPlanItem` to `PlanItem` for backward compat.
- **Enum values**: enforced. `DossierType`, `SectionState`,
  `SubInvestigationState`, `WorkingTheoryConfidence`,
  `InvestigationConfidence` all coerce from string and reject
  unknowns.
- **String lengths**: minimal. `UserNoteCreate` is the only one with
  `min_length=1, max_length=10000` (models.py:497). Section `content`,
  `note`, `path`, `subject`, etc. are unbounded `str`. See §8 for
  why this is a hazard.
- **Partial merges**: Pydantic-friendly. `WorkingTheoryUpdate`,
  `DebriefUpdate`, `PremiseChallengeUpdate`, `ArtifactUpdate`,
  `SubInvestigationUpdate` are all `Optional` and rely on storage to
  enforce "first write must include all required fields" (e.g.
  `models.py:159-164` says "If any field is supplied on a dossier
  with no existing WorkingTheory, all REQUIRED fields must be
  present — storage enforces this").
- **Tool input coercion**: minimal. The handlers pass `**args` into
  Pydantic directly, so `{"is_error": "1"}` would fail, but
  `{"tags": "stuck"}` would also fail (must be list). The Pydantic
  default strictness is `lax` on Pydantic v2 — integer-vs-string
  coercion works.

---

## 6. 17-table schema design

### 6.1 Actual count: 22 tables

The brief said 17. The actual `CREATE TABLE` count in
`D:\projects\Vellum\backend\vellum\schema.sql` is **22** (lines 3, 28,
45, 60, 70, 85, 96, 107, 123, 135, 148, 158, 168, 184, 204, 220, 240,
257, 269, 279, 298, 318). All 22 are in the file; the schema is flat
(no `CREATE SCHEMA` namespaces).

| # | Table | Purpose group | FK to `dossiers` | Notes |
|---|---|---|---|---|
| 1 | `dossiers` | core | (PK) | All `out_of_scope`, `debrief`, `working_theory`, `premise_challenge` stored as JSON. |
| 2 | `sections` | core | yes, CASCADE | `order` is REAL (float). |
| 3 | `needs_input` | core | yes, CASCADE | |
| 4 | `user_notes` | core | yes, CASCADE | `seen_at` semantics: agent self-heal re-surfaces unseen notes. |
| 5 | `decision_points` | core | yes, CASCADE | `kind` enum: `generic | plan_approval | stuck_resolution`. |
| 6 | `reasoning_trail` | core | yes, CASCADE | Private agent notes. |
| 7 | `ruled_out` | core | yes, CASCADE | |
| 8 | `work_sessions` | session | yes, CASCADE | `cost_usd`, token usage, end_reason. |
| 9 | `change_log` | session | yes, CASCADE | Plan-diff surface. |
| 10 | `next_actions` | core | yes, CASCADE | `priority` is REAL, but the API model `NextAction.priority: int` (models.py:131). Type mismatch. |
| 11 | `intake_sessions` | intake | no FK to dossiers | `dossier_id` set on commit, but no FK. |
| 12 | `intake_messages` | intake | (intake_sessions.id) | |
| 13 | `artifacts` | core | yes, CASCADE | `supersedes` has no FK. |
| 14 | `sub_investigations` | sub | yes, CASCADE | `parent_section_id` has no FK. |
| 15 | `investigation_log` | audit | yes, CASCADE | Append-only. `payload` is JSON. |
| 16 | `considered_and_rejected` | core | yes, CASCADE | |
| 17 | `tool_invocations` | idempotency | yes, CASCADE | PK is `tool_use_id` itself. |
| 18 | `budget_accounting` | cost | n/a (no FK) | PK is UTC day string. |
| 19 | `settings` | config | n/a (no FK) | `key` is PK, `value_json` is JSON. |
| 20 | `session_summaries` | session | yes, CASCADE | `confirmed`/`ruled_out`/`blocked_on`/`questions_advanced` are JSON lists. |
| 21 | `plan_items` | core | yes, CASCADE | First-class plan rows; `UNIQUE(dossier_id, plan_item_id)`. |
| 22 | `agent_turns` | telemetry | yes, CASCADE | One row per Anthropic API call. |

### 6.2 Grouping

- **Dossier core (10 tables)**: `dossiers`, `sections`, `needs_input`,
  `user_notes`, `decision_points`, `reasoning_trail`, `ruled_out`,
  `next_actions`, `artifacts`, `plan_items`, `considered_and_rejected`.
  Plus the derived `change_log` (also dossier-rooted). These are the
  "what the user sees" tables.
- **Sessions/turns (3)**: `work_sessions`, `change_log`,
  `session_summaries`. The "what the agent did" tables.
- **Sub-investigations (1)**: `sub_investigations` (with
  `investigation_log` and `considered_and_rejected` serving as its
  audit trail).
- **Intake (2)**: `intake_sessions`, `intake_messages`. Stand-alone —
  see §6.4.
- **Idempotency (1)**: `tool_invocations`. Cross-cutting.
- **Cost / budget (1)**: `budget_accounting`. Stand-alone — keyed by
  UTC day.
- **Telemetry (1)**: `agent_turns`. One row per Anthropic call, used
  for cost dashboards.
- **Settings (1)**: `settings`. DB-backed runtime knobs.

### 6.3 Most interesting indexes

```sql
-- schema.sql:43, 55, 68, 83, 94, 105, 121, 133, 146
CREATE INDEX IF NOT EXISTS idx_sections_dossier      ON sections(dossier_id, "order");
CREATE INDEX IF NOT EXISTS idx_needs_input_dossier   ON needs_input(dossier_id, answered_at);
CREATE INDEX IF NOT EXISTS idx_user_notes_dossier    ON user_notes(dossier_id, created_at);
CREATE INDEX IF NOT EXISTS idx_decision_points_dossier ON decision_points(dossier_id, resolved_at);
CREATE INDEX IF NOT EXISTS idx_reasoning_dossier     ON reasoning_trail(dossier_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ruled_out_dossier     ON ruled_out(dossier_id, created_at);
CREATE INDEX IF NOT EXISTS idx_work_sessions_dossier ON work_sessions(dossier_id, started_at);
CREATE INDEX IF NOT EXISTS idx_change_log_dossier    ON change_log(dossier_id, work_session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_next_actions_dossier  ON next_actions(dossier_id, priority);
```

The pattern is **composite `(dossier_id, <time-or-order>)`** on every
child table — these are the access paths the UI uses to render a
dossier's timeline. The wake-scheduler adds two functional indexes:

```sql
-- db.py:142-152
CREATE INDEX IF NOT EXISTS idx_dossiers_wake
  ON dossiers(wake_pending, wake_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_work_sessions_one_active_per_dossier
  ON work_sessions(dossier_id)
  WHERE ended_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_decision_points_one_open_plan_approval_per_dossier
  ON decision_points(dossier_id)
  WHERE kind = 'plan_approval' AND resolved_at IS NULL;
```

The two **partial unique indexes** are the most interesting design
choice in the schema. They are SQL-level enforcement of two
invariants the README claims and the storage code tries to honor:

1. "At most one open work_session per dossier" — the partial unique
   index makes a duplicate `_ensure_session` call into a constraint
   violation, not a soft fail.
2. "At most one open `plan_approval` decision point per dossier" —
   same idea, prevents the agent from flooding the user with parallel
   plan sign-off asks.

These are exactly the kind of "the agent could go wrong here, so the
DB stops it" guarantees that are easy to get wrong in a soft
codebase. They are real.

### 6.4 Surrogate vs natural keys

Every primary key is a **surrogate string id** with a type prefix
(`new_id(prefix)` at `models.py:11-12`):

```python
def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
```

Prefixes I can see from the model field doc-comments: `dos` (dossiers),
`sec` (sections), `pli` (plan_items), `act` (next_actions), `art`
(artifacts), `sub` (sub_investigations), `rtr` (reasoning_trail),
`ro` (ruled_out), `intk` (intake_sessions), `im` (intake_messages),
`ilg` (investigation_log), `crj` (considered_and_rejected),
`agt` (agent_turns). The prefix is human-readable for log-grepping
but the id is otherwise opaque.

The two natural keys in the schema:

- `tool_invocations.tool_use_id` is the Anthropic SDK's tool_use id.
  This is the **only** table where the PK is a non-Vellum-generated
  value. Necessary for idempotency.
- `budget_accounting.day` is the UTC date string. Natural because
  there's exactly one row per day, and UPSERTs are easy.
- `settings.key` is a string. Natural because the keys are
  application-defined and the table is a key-value store.

The intake-link `intake_sessions.dossier_id` is a natural key (set
on commit) but is **not** a foreign key. Same for
`sub_investigations.parent_section_id`, `artifacts.supersedes`,
`sub_investigations.plan_item_id`, `change_log.section_id` — they are
all stored as `TEXT` without FK constraints. This is a deliberate
tradeoff (see §8).

### 6.5 WAL setup

WAL is enabled at `db.py:231-232`:

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

The comment at `db.py:228-231` explains:

> WAL allows concurrent readers + single writer — needed because the
> runtime dispatches handlers in asyncio.to_thread across parallel
> dossiers, and default rollback journal serializes harshly.

`synchronous=NORMAL` is the standard WAL companion (it does not fsync
on every commit, relying on WAL's crash-recovery); `synchronous=FULL`
would be safer but slower. The connection is `sqlite3.connect(path,
timeout=10.0)` (`db.py:248`) — 10s busy-timeout on writer contention.

`PRAGMA foreign_keys = ON` is set at the top of `schema.sql:1` AND
re-asserted in `connect()` at `db.py:250`. SQLite's FK enforcement is
per-connection; the re-assertion ensures every fresh `connect()`
honors it. This matters because `PRAGMA foreign_keys` does not persist
in the file.

### 6.6 The 22-vs-17 discrepancy

The brief's 17 likely counts only the "dossier core" tables
(dossiers, sections, needs_input, user_notes, decision_points,
reasoning_trail, ruled_out, work_sessions, change_log, next_actions,
artifacts, sub_investigations, investigation_log,
considered_and_rejected, plan_items, agent_turns, tool_invocations) =
17. The remaining 5 are the cross-cutting tables (intake ×2, budget,
settings, session_summaries) and the v2 audit (`investigation_log`).
Reasonable to call the dossier-domain subset 17; total is 22.

---

## 7. Migration runner

The migration system lives in `db.py` and is **forward-only**. There
is no rollback path.

### 7.1 The boot sequence

`init_db()` at `db.py:222-242` runs these steps in order:

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.executescript(SCHEMA_PATH.read_text())        # 1. CREATE TABLE IF NOT EXISTS for all 22
_ensure_columns(conn)                              # 2. ALTER TABLE ADD COLUMN for ratcheted columns
_backfill_decision_point_kinds(conn)               # 3. one-time data backfill
_close_duplicate_unresolved_plan_approvals(conn)  # 4. one-time data normalization
_close_duplicate_active_work_sessions(conn)       # 5. one-time data normalization
_ensure_indices(conn)                              # 6. CREATE INDEX (after columns exist)
_migrate_plan_items(conn)                          # 7. one-time data migration (sentinel-guarded)
conn.commit()
```

### 7.2 Runtime column migrations

`_REQUIRED_COLUMNS` at `db.py:17-58` is a list of
`(table, column, type_and_default_sql)` tuples. The comment at
`db.py:12-16` is explicit:

> SQLite's CREATE TABLE IF NOT EXISTS does not add new columns to a
> table that already exists from an earlier schema. _REQUIRED_COLUMNS
> lists every column added after the initial schema; init_db applies
> ALTER TABLE for each missing one. Each entry is
> (table, column, type_and_default_sql). Keep additive: this is a
> one-way ratchet — we never drop or rename here.

This is a pragmatic hack to add columns without a real migration
framework. Pros: simple, idempotent, no migration-version table
needed. Cons:

- **No version tracking** — the system has no record of which
  migrations a given DB has applied. The `_migrate_plan_items` step
  uses a sentinel in `settings` (`plan_items_migrated`) to
  idempotently guard its data copy (db.py:172-219). This is a one-off
  pattern, not a general solution.
- **Order matters but is not enforced** — `_ensure_columns` must run
  before `_ensure_indices` because the indexes reference columns added
  in step 2. The ordering is implicit in the `init_db` function body,
  not declared anywhere.
- **No rename, no type change, no drop** — by design. A future
  schema cleanup would require a side-channel script.

The most recent additions to `_REQUIRED_COLUMNS` reveal the velocity
of schema change (db.py:30-57):

```python
# Day-4 (phase 1): sub-investigation identity.
("sub_investigations", "title", "TEXT"),
("sub_investigations", "blocked_reason", "TEXT"),
# Phase 4 SA2: linked-question richness on sub-investigations.
("sub_investigations", "why_it_matters", "TEXT"),
("sub_investigations", "known_facts", "TEXT NOT NULL DEFAULT '[]'"),
("sub_investigations", "missing_facts", "TEXT NOT NULL DEFAULT '[]'"),
("sub_investigations", "current_finding", "TEXT"),
("sub_investigations", "recommended_next_step", "TEXT"),
("sub_investigations", "confidence", "TEXT NOT NULL DEFAULT 'unknown'"),
# Day-4 (phase 2): working theory — JSON-encoded WorkingTheory model.
("dossiers", "working_theory", "TEXT"),
("dossiers", "premise_challenge", "TEXT"),
# ...
("dossiers", "stuck_escalation_count", "INTEGER NOT NULL DEFAULT 0"),
# Self-heal: consecutive error/crash counter + quarantine gate.
("dossiers", "consecutive_error_count", "INTEGER NOT NULL DEFAULT 0"),
("dossiers", "quarantined_at", "TEXT"),
("dossiers", "quarantine_reason", "TEXT"),
```

This is **two years of feature work in one file**. It works because
SQLite ALTER TABLE ADD COLUMN is fast and the column default
(`NOT NULL DEFAULT 0` or `DEFAULT '[]'`) is correct for existing rows.

### 7.3 The index-after-columns rule

The comment at `db.py:138-140` is important:

> Indices that reference columns added via ensure_columns must be
> created AFTER the ALTER TABLE pass — otherwise executescript sees
> the CREATE INDEX against a column that does not yet exist on a
> pre-sleep-mode DB and bails.

`_REQUIRED_INDICES` (db.py:141-153) creates the wake index and the
two partial unique indexes I noted in §6.3. This is why
`idx_dossiers_wake` is NOT in `schema.sql` even though it would
logically belong there.

### 7.4 Data migrations

Three one-time data normalizations run on every boot (they are
idempotent because they're `UPDATE ... WHERE ...`):

- `_backfill_decision_point_kinds` (db.py:73-91) sets
  `kind='plan_approval'` on legacy decision points whose titles look
  like approval asks (e.g. matches `%plan_approval%`).
- `_close_duplicate_unresolved_plan_approvals` (db.py:116-135) closes
  all but the most recent open plan_approval DP per dossier.
- `_close_duplicate_active_work_sessions` (db.py:94-113) closes all
  but the most recent active work_session per dossier with
  `end_reason='crashed'`.

These last two are interesting: they exist because the partial unique
indexes would otherwise make startup FAIL on legacy data. The
`init_db` order is "clean up the data, then create the constraint
that would have rejected the bad data." The two functions are written
in a way that will become no-ops once legacy data is fixed.

### 7.5 The plan_items migration

`_migrate_plan_items` (db.py:161-219) is the **only** sentinel-guarded
data copy. It reads `dossiers.investigation_plan` JSON blobs, parses
out the `items` array, and inserts each into `plan_items` with
`INSERT OR IGNORE`. The sentinel `plan_items_migrated=true` in the
`settings` table prevents re-execution. Comment at db.py:166-169:

> Guarded by the 'plan_items_migrated' settings sentinel so the bulk
> of the work is skipped on subsequent init_db calls. INSERT OR
> IGNORE makes every individual row insertion idempotent, so the
> migration is safe to re-run even if the sentinel is absent (e.g.
> in tests that manually clear it).

The rest of the v2 rollout (working_theory, premise_challenge,
sub-investigation fields) was also a column-add, but with no data
backfill needed because those columns are nullable / start empty.

---

## 8. Honest assessment

### 8.1 What is genuinely well-designed

- **Closed-loop enforcement in the runtime.** The
  `if not tool_uses: return RunResult` at `runtime.py:282-290` is
  real. It's one if-statement; it works.
- **Two partial unique indexes** for "one active session per dossier"
  and "one open plan_approval per dossier" — these are the
  right shape of invariant, in the right layer.
- **Tool descriptions are written for the model, not the developer.**
  The descriptions in `TOOL_DESCRIPTIONS` (handlers.py:718-944) are
  dense, opinionated, and embed negative examples ("Do NOT use
  flag_needs_input for choices — that is flag_decision_point"). The
  model is more likely to behave well with these than with terse
  one-liners.
- **The compound handlers** (`declare_stuck`, `commit_intake`,
  `mark_investigation_delivered`) push multi-step invariants into
  one tool call. The agent doesn't have to remember "log AND raise
  DP" — one call does both atomically.
- **Soft-refusal as structured response.** `{"ok": False, "reason":
  "..."}` is a coherent dialect across ~8 handlers. The agent can
  pattern-match on `reason` and the loop survives.
- **Storage adapter pattern.** Storage functions take Pydantic models
  in, return Pydantic models out. Handlers never see sqlite3.
  `from .. import models as m; storage.fn(dossier_id, m.Create(**args))`
  is the only storage-call shape I found.

### 8.2 What feels over-engineered

- **17 separate per-entity store files.** `dossier_store.py` is 34 KB
  and the others are 2-13 KB. Many store functions are 3-5 lines
  that could live in a single `storage.py`. The split has payoff
  for the larger files (dossier, plan_items, sub_investigation) but
  `wake_store.py` (5 KB) and `user_note_store.py` (3 KB) are thin
  enough that the indirection is more friction than value. I would
  consider consolidating the small ones and keeping the heavy ones.
- **The intake/dossier split is mostly justified**, but the
  intake-runtime docstring claims it is "different from the dossier
  agent" in 4 ways; 3 of those (no state snapshot, no stuck
  detection, no work_sessions) are *because intake is short-horizon
  and small*, not because the underlying primitives are different.
  The shared `models.py` already defines `DossierCreate`. A
  thinner intake storage layer (just `intake_sessions` and
  `intake_messages`) would be a clean factor; instead both sides
  re-import the other's storage where needed.
- **Placeholder schemas for v2 tools** (handlers.py:989-1051). The
  `_PLACEHOLDER_V2_SCHEMAS` dict exists so day-1 wiring doesn't
  break if a v2 Pydantic model hasn't merged yet. This is a
  feature-flag pattern masquerading as a schema layer. Useful in
  multi-worktree dev; suspicious in a single-tree deployment.
- **Pydantic `field_validator` for `InvestigationPlanUpdate`**
  (models.py:548-570) coerces legacy `InvestigationPlanItem` to
  `PlanItem`. This is the only model-level backward-compat hack in
  the codebase, and it's silent — the validator succeeds, so a
  caller can't tell if the input was old-shape or new-shape.

### 8.3 What feels under-engineered

- **No retention policy on `tool_invocations`.** Every Anthropic
  tool call leaves a row. With 30 tools × 200 max turns = 6000 rows
  per session × multiple sessions per dossier × N dossiers, this
  grows unbounded. No VACUUM, no TTL, no archival in the code I
  read.
- **No retention on `agent_turns`, `investigation_log`,
  `reasoning_trail`, `change_log`.** Same story — append-only,
  unbounded. A long-running dossier will accumulate millions of
  rows.
- **No retention on `intake_messages`.** Same.

### 8.4 Schema hazards

- **Unbounded JSON columns** in `dossiers`:
  - `out_of_scope` (list of strings, no size cap)
  - `debrief` (4 string fields, no size cap on the JSON)
  - `investigation_plan` (now redundant with `plan_items` — see
    below)
  - `working_theory` (5 fields, no cap)
  - `premise_challenge` (5 fields, no cap)
  A single agent can write a 1 MB string to `working_theory.why` in
  one tool call. There's no app-level cap and no DB-level cap.

- **Redundant storage**: `dossiers.investigation_plan` is still
  populated even though `plan_items` is the first-class table now.
  `dossier_store.get_dossier` (lines 82-86) merges the two: it reads
  `investigation_plan` from the JSON blob and overwrites its `items`
  with rows from `plan_items`. The JSON column is dead weight
  except as a forward-compat cache for the migration. Keeping it
  invites drift.

- **Type mismatch in `next_actions`**: the schema column is
  `priority REAL NOT NULL` but the API model is
  `priority: int = 0` (models.py:131). The handlers accept
  whatever the agent sends, the column accepts floats, and the
  API will return an int. Pydantic won't catch this because
  `int` is a subtype of `float`. Subtle.

- **Missing FK constraints** that are still relied on for
  correctness:
  - `intake_sessions.dossier_id` — no FK, but the commit path
    sets it (intake/tools.py:205-207). If a dossier is deleted
    out-of-band, the intake row points to a non-existent
    dossier.
  - `sub_investigations.parent_section_id` — no FK. Same story.
  - `sub_investigations.plan_item_id` — no FK. Spawning a sub for
    a deleted plan item leaves a dangling reference.
  - `artifacts.supersedes` — no FK. An artifact claiming to
    supersede a deleted artifact silently fails.
  - `change_log.section_id` — no FK. The plan-diff can show
    entries for deleted sections.
  - `agent_turns.sub_investigation_id` — no FK.

  Each of these is a plausible "the system would just keep working
  with a NULL or a stale string" failure mode. The FK-less design
  may be intentional (cascade-deletes are heavy, especially across
  `sub_investigations` ↔ `sections` cycles) but it deserves a
  comment somewhere.

- **No CHECK constraints anywhere.** Enums are stored as TEXT. A
  bad string in `decision_points.kind` would parse but never
  match `kind='plan_approval'` filters. SQLite supports CHECK;
  the schema has none.

- **`intake_sessions` FK is by convention, not constraint.** Same
  for the dossier→intake link after commit.

- **The `id` column on every table is `TEXT PRIMARY KEY`** but
  there is no length cap. A model field could conceivably pass
  a 10 MB string as `id`; the DB would accept it. Defensive
  validation lives only in `new_id(prefix)`, not at the schema
  boundary.

### 8.5 Where store-level duplication should be consolidated

- `wake_store.py`, `user_note_store.py`, `settings_store.py`,
  `budget_store.py`, `idempotency_store.py` are all < 6 KB.
  Together with `_helpers.py` (14 KB) they cover a third of the
  storage surface area. A single `storage/misc_store.py` would
  remove 4 import statements from `__init__.py` and make the
  dependency graph smaller.
- `log_store.py` mixes four concerns: `reasoning_trail`,
  `ruled_out`, `investigation_log`, `considered_and_rejected`,
  `change_log`. Five tables, one file, ~280 lines. The first two
  could move to their own files; the latter three are
  genuinely a "log" family.
- `dossier_store.py` is 34 KB and imports from
  `decision_point_store`, `section_store`, `needs_input_store`,
  `log_store`, `plan_items_store`. It's a God module. The
  `update_debrief`, `update_working_theory`,
  `update_premise_challenge`, `update_investigation_plan`
  functions arguably belong in their own files (they each
  touch `dossiers.<json_col>` plus a child table).

---

## 9. Notable design choices — and why each matters

### 9.1 Per-entity store files

One file per storage domain (`section_store.py`, `plan_items_store.py`,
etc.) instead of a single monolithic `storage.py`. The benefit: large
domains (`dossier_store.py` 34 KB, `plan_items_store.py` 13 KB,
`sub_investigation_store.py` 12 KB) get their own namespace and don't
drown out small ones. The cost: a thin wrapper like
`wake_store.py` (5 KB) is mostly an import-trip. Net: justified for
the big ones, could be consolidated for the small ones.

### 9.2 `tool_invocations` table for idempotency

Every tool dispatch writes a row keyed by `tool_use_id`
(`storage/idempotency_store.py:37-65`). On replay, the runtime
short-circuits to the recorded result (`runtime.py:571-586`). This
matters because:

- The Anthropic SDK can retry on transient errors, regenerating the
  same `tool_use_id` *only* if the original call hadn't returned
  yet. The table protects against that race.
- A future move to a message-history-replay runtime (Path B/C, per
  the comment at `runtime.py:574-576`) would replay tool calls
  verbatim; the table is the only thing keeping that from
  double-inserting `upsert_section` rows.
- The `input_hash` column (handlers.py:868-873) is informational
  only — the idempotency key is `tool_use_id`. Storing the hash
  lets future audits detect "a replay arrived with a mutated
  payload" (it shouldn't, but the data is cheap).

The cost: one INSERT per tool call. 200 max turns × 30 tools = up
to 6000 INSERTs per session. Not free.

### 9.3 Runtime column migrations (`_REQUIRED_COLUMNS`)

A flat list of `(table, column, type_and_default_sql)` triples,
applied as `ALTER TABLE ADD COLUMN` on every boot if missing
(`db.py:17-58`, `_ensure_columns` at lines 66-70). The pros:
zero infra (no migration-version table), idempotent, fast.
The cons: no rename, no type change, no drop, no record of what
ran. For a solo project shipping fast and never needing to
downgrade, this is the right tradeoff. For a team project, it
would not survive a second developer.

### 9.4 Pydantic as schema language

`models.py` is the only place the type vocabulary lives. The
Anthropic tool schemas derive from it
(`model.model_json_schema()` at handlers.py:1080 and
intake/tools.py:368-502). The SQLite round-trips derive from it
(`TypeAdapter(list[m.Source])` at `_helpers.py:21-22`,
`m.Dossier.model_validate_json(...)` at `_helpers.py:88-118`). The
FastAPI request/response shapes are the same models. The result:
**adding a field to `Section` is a one-file change** that flows
automatically to all four layers. The cost: any breaking change
to a model is breaking across four layers simultaneously.

### 9.5 Storage adapters that take Pydantic in, return Pydantic out

Every store function signature is `(dossier_id, m.SomeCreate, session_id) -> m.SomeModel`. The handler never imports `sqlite3`, never builds a SQL string, never types a column. This is the single biggest reason the handlers stay 5 lines each.

### 9.6 Partial unique indexes for "one open per dossier"

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_sessions_one_active_per_dossier
ON work_sessions(dossier_id) WHERE ended_at IS NULL;
```

SQLite enforces the invariant that the soft-delete convention
("ended_at IS NULL means active") is actually true. The agent can
screw up the `_ensure_session` call, the runtime can race on
re-activation, the DB will still hold the line. This is the only
real schema-level correctness enforcement I found beyond NOT NULL
and FKs.

### 9.7 Storage-marker sentinel for data migrations

The `plan_items_migrated` row in `settings`
(`db.py:172-174`) is a one-off pattern: a row in the
key-value settings table doubles as a "have I run this migration"
flag. Clever for a one-shot. Doesn't scale to N migrations (a
proper framework would use a `schema_migrations` table), but for
a single sentinel it works and reuses the existing
`settings` table.

### 9.8 The intake agent's prose surface

Intake is the ONLY place in the system where the model emits prose
to the user (`intake/runtime.py:11-14`). The dossier agent is
strictly tool-mediated. The intake agent's prose is stored as
`intake_messages.content` (rows in the intake_messages table) so
the conversation is auditable. The user sees intake prose; the
dossier body they later read is purely tool-mediated. The
split is principled: intake is a structured form, the dossier is
a structured artifact.

### 9.9 Soft refusal as a structured response dialect

`{"ok": False, "reason": "<short_code>"}` is used in at least 8
handlers (mark_investigation_delivered at line 504,
update_working_theory at line 180, schedule_wake at line 404,
update_sub_investigation at line 286, etc.). It is not raised as
an exception — it is a return value. The agent reads the reason,
makes a decision, retries. This is the right shape for "the agent
should be able to recover from this," which is the dominant
failure mode for an LLM-driven system.

### 9.10 Per-entity id prefixes

`new_id("dos")` → `dos_a1b2c3d4e5f6` (12 hex chars). The prefix
is human-readable in logs and SQLite shells. The 12-hex suffix
is 48 bits, ~280 trillion ids per prefix — collision-safe for
any single-project scale. The cost: ids leak into URLs and
wire-protocols; the prefix is decorative metadata anyone can
see.

---

## Summary

Vellum's tool surface and schema reflect a single-author project
that has aggressively traded conventional framework overhead for
pragmatic simplicity. The closed-loop tool contract is real (one
if-statement, runtime.py:282-290), the Pydantic-as-source-of-truth
pattern is the right shape and pays for itself in every handler
reading 5 lines, and the partial unique indexes are a good
example of pushing invariants to the right layer.

The cost of that simplicity is concentrated in three places:
(1) the runtime column-migration ratchet is forward-only and
invisible — adding a column is one tuple in a list, but a
breaking change would be a side-channel script; (2) several
unbounded JSON columns in `dossiers` are the natural target of
LLM verbosity and have no defense; (3) the FK-light design
relies on storage code being correct, not the DB. None of these
are showstoppers for a solo dev shipping a hackathon project,
but each is a place where the next two years of feature work
will pile on debt.

The 22-table schema, the 30-tool dossier surface, and the
7-tool intake surface are all honest counts of what the code
actually exposes — the brief's "17 / 27" numbers are
under-counts.
