# v1 → v2 migration notes (Day 1 planning)

Vellum v1 shipped a "memo that evolves" agent: sections plus a flat
reasoning_trail and a ruled_out ledger. v2 promotes the agent to
"investigator" — it plans, spawns sub-investigations, drafts artifacts, logs
a typed investigation_log, and wrestles in considered_and_rejected. Day 1
lands v2 objects **additively**; nothing v1 gets retired before Day 5. This
doc is the watchlist and migration plan.

## 1. v2 objects added (recap)

- **artifacts** — standalone drafts (memos, scripts, checklists) first-class.
- **sub_investigations** — child work units spawned with narrowed scope + tool set.
- **debrief** — structured end-of-investigation summary.
- **investigation_plan** — explicit plan the agent commits to before working.
- **next_actions** — concrete queue-head the agent draws from each turn.
- **typed investigation_log** — typed replacement for `reasoning_trail`; `entry_type` enum + `source_count` header.
- **considered_and_rejected** — replaces `ruled_out`; adds `why_compelling` and `cost_of_error`.

## 2. v1 ↔ v2 decision matrix

| v1 object | v2 counterpart | Treatment | Reason | Day to act |
|---|---|---|---|---|
| `reasoning_trail` (`models.py:131`, `schema.sql:59`) | typed `investigation_log` | Keep live; v2 agent writes only to investigation_log. v1 data stays readable. | Trust: don't lose prior notes. | Day 2 (stop v2 writes), Day 5 (retire) |
| `ruled_out` (`models.py:140`, `schema.sql:70`) | `considered_and_rejected` | Keep live; v2 writes only new table. Backfill cosmetic: `subject → path`, `reason → why_rejected`, `why_compelling`/`cost_of_error` blank for v1 rows. | No data loss, no UI break. | Day 4 (UI), Day 5 (retire) |
| `DossierStatus` (`models.py:28`) — `active`/`paused`/`delivered` | `mark_investigation_delivered` sets `delivered` | Keep enum. Watch legacy `paused` rows — v2 never emits them. | UI filters on status. | Day 4 (UI audit) |
| `SectionType.ruled_out` (`models.py:41`) | items move to considered_and_rejected | Keep member; v2 stops using it. | Some v1 dossiers have sections of this type. | Day 5 |
| `ReasoningAppend`/`RuledOutCreate` (`models.py:257,262`) | v2-native create models TBD | Keep for v1 route + handler + lifecycle. | Still referenced. | Day 5 |

## 3. v1 call sites touching soon-retiring surfaces

Pointers are exhaustive; exact line numbers from Grep.

**`append_reasoning`** callers:
- `backend/vellum/storage.py:419,634,651` — the mirror inside `update_section_state`, the storage fn, the INSERT. **Keep (v1-only paths)**; the `update_section_state` mirror at line 419 will need a v2 branch on Day 2 so state changes also hit investigation_log.
- `backend/vellum/api/routes.py:166,171` — `POST /reasoning`. **Keep (v1-only).**
- `backend/vellum/tools/handlers.py:73,75,90,128,164,187` — handler, registry, description, input-model map; line 90 is `check_stuck`'s reasoning write. **Retire-candidate** (Day 5).
- `backend/vellum/agent/prompt.py:44,95,131,144` — system-prompt guidance. **Retire** on v2 prompt swap.
- `backend/vellum/lifecycle.py:61` — crash-recovery note. **Keep**; add parallel investigation_log entry (Section 6).
- `backend/e2e_day3.py:123`, `backend/smoke_test.py:56`, `frontend/src/components/sections/ReasoningTrail.tsx:7`. **Keep.**

**`mark_ruled_out`** callers:
- `backend/vellum/tools/handlers.py:79,129,168,188`. **Retire-candidate** (Day 5).
- `backend/vellum/agent/prompt.py:84,129,213`. **Retire** on prompt swap.
- `backend/smoke_test.py:118`. **Keep.**

**`ReasoningAppend` / `RuledOutCreate`** construction:
- `backend/vellum/models.py:257,262` (defs), `storage.py:636,680`, `api/routes.py:168,180`, `lifecycle.py:63`, `handlers.py:75,81,92,187,188`, `e2e_day3.py:125`, `frontend/src/api/types.ts:227,232`. All **keep — v1-only paths** until Day 5.

**`reasoning_trail` table/field** refs: `schema.sql:59,68`; `storage.py:282,419,422,651,666,669`; `models.py:196`; `agent/prompt.py:381,382,553`; `lifecycle.py:46,80,96,212,217`; `frontend/src/api/types.ts:175`, `pages/DossierPage.tsx:125,194`, `pages/DemoPage.tsx:98,154`, `mocks/dossier.ts:157`. **Keep.**

**`ruled_out` table/field** refs: `schema.sql:70,79`; `storage.py:109,283,678,695,707,712,715,718`; `models.py:41,175,197`; `agent/prompt.py:370-374,504,554`; `frontend/src/api/types.ts:24,54,176`, `pages/DossierPage.tsx:124,191`, `pages/DemoPage.tsx:97,152`, `mocks/dossier.ts:184,251`, `components/plan-diff/ChangeEntry.tsx:59`. **Keep.**

## 4. Intake layer

`backend/vellum/intake/prompt.py` produces v1 dossiers via five fields. For
v2, intake should seed a **starter investigation_plan** before handoff — or
flag that the first agent turn must produce the plan. `out_of_scope` and
`check_in_policy` stay. **Day 3 work; no Day 1 changes needed.**

## 5. Agent runtime

- **System prompt swap.** `agent/prompt.py:21-235` is v1-authored. Day 1 parallel stream replaces it.
- **Tool set expansion.** `DossierAgent._build_tool_definitions` at `runtime.py:80-84` splices web_search onto `handlers.tool_schemas()`. Day 1 adds v2 handlers: `spawn_sub_investigation`, `log_investigation_entry`, `write_artifact`, `set_investigation_plan`, `consider_and_reject`, `mark_investigation_delivered`, `write_debrief`.
- **Sub-investigation spawning (Day 2 — NOT YET IMPLEMENTED).** Design sketch:
  - Main runtime receives `spawn_sub_investigation` tool_use; it blocks the parent loop and runs a sub-agent inline with a narrower system prompt and restricted tool subset (no `mark_investigation_delivered`, depth cap).
  - Sub-agent runs its own `run()` to completion with a lower `max_turns`. Its summary payload becomes the `tool_result` for the parent's original `tool_use_id` — parent sees one opaque call.
  - **work_session:** sub-agent gets its own session so change_log attribution and `increment_session_tokens` (`storage.py:775`) stay honest. Parent session does not absorb child tokens.
  - **stuck.py:** sub-agent gets its own `_SESSION_STATE` bucket automatically (per-session keying at `stuck.py:61`).
  - **Orchestrator:** `AgentOrchestrator._tasks` is keyed by dossier_id (`orchestrator.py:78`). Sub-agents run in-process under the parent's task — do not register as siblings or `AgentAlreadyRunning` fires.
- **Stuck detection (`stuck.py`).** v2's wider tool surface means more distinct `(tool_name, args_hash)` keys, so the `LOOP_DETECTION_THRESHOLD` check at `stuck.py:125` should get a per-tool budget (web_search is cheap; investigation_log entries shouldn't count as "loops"). **Day 2 tweak.**

## 6. Lifecycle (crash recovery)

`backend/vellum/lifecycle.py:61-73` writes a `[lifecycle]`-tagged entry to
`reasoning_trail` on orphan-session recovery. For v2 consistency it must
also write an investigation_log entry. Recommended shape:

```
entry_type: "crash_recovered"    # new enum member
summary:    "Previous working session was interrupted — nothing lost."
source_count: 0
work_session_id: None
```

**Day 2: double-write.** Day 5 retires the reasoning_trail branch.

## 7. Frontend (Day 4 checklist)

Pages:
- `DossierListPage.tsx` — minor (new Dossier fields, status-filter audit).
- `DossierPage.tsx` — major: sub-investigation tree, artifacts tab, investigation_log sidebar, considered_and_rejected list, plan viewer/editor, debrief renderer.
- `DemoPage.tsx` — fixture updates.
- `IntakePage.tsx` — no-op unless starter plan added.

Minor edits: `components/layout/Header.tsx` (status pill), `common/DossierHero.tsx`.

New views (replace v1 siblings):
- `sections/ReasoningTrail.tsx` → `InvestigationLog.tsx` (typed entries + source-count header).
- `sections/RuledOutList.tsx` → `ConsideredAndRejectedList.tsx`.
- `plan-diff/ChangeEntry.tsx` — new ChangeKinds.

Net-new: `InvestigationPlan` (viewer/editor), `SubInvestigationTree`, `ArtifactsTab`, `DebriefRenderer`, `NextActionsQueue`.

TS drift: `frontend/src/api/types.ts:15` (DossierStatus), `:45-55` (ChangeKind), `:170-178` (DossierFull).

## 8. Risks and flags

- **`DossierType.script` (`models.py:25`).** v2 dossier_type is metadata-only — keep for now; revisit Day 5.
- **JSON-in-TEXT columns.** `out_of_scope`, `check_in_policy`, section `sources`/`depends_on`, decision_point `options`; v2 adds investigation_plan + debrief. Keep keys stable and shallow so a Postgres/JSONB port stays cheap.
- **`work_session` accounting.** `increment_session_tokens` (`storage.py:775`) is called from `runtime.py:128`. v2 must not collide — sub-agents need their own session.
- **`ChangeKind` Literal (`models.py:166-177`).** Grows fast (artifact_created, sub_investigation_spawned, plan_updated, debrief_written). Watch TS drift at `types.ts:45-55`.
- **Mixed v1/v2 data in one dossier.** Additive schema — nothing breaks — but UI must handle `debrief=null`, `sub_investigations=[]`, `investigation_plan=null`, `considered_and_rejected=[]`.
- **`check_stuck` (`handlers.py:86-104`)** writes to reasoning_trail via `append_reasoning`. Port to investigation_log on Day 2 or v2 loses stuck signals.
- **`update_section_state` mirror (`storage.py:419-433`).** Same porting need on Day 2.
- **Intake commit path.** `intake/tools.py:commit_intake` creates a Dossier directly; if Day 3 slips, v2 dossiers open with no plan and the first agent turn has to generate it on its own.

## 9. Day 1 → Day 2 handoff checklist

1. v2 objects additively defined in `models.py` and `schema.sql`; migrations run on dev DB.
2. v2 tool handlers stubbed in `tools/handlers.py` HANDLERS; `tool_schemas()` emits them. v1 handlers untouched.
3. v1 system prompt (`agent/prompt.py`) not yet swapped — parallel stream, Day 2 switches runtime.
4. `DossierFull` grows optional v2 collections; `storage.get_dossier_full` (`storage.py:273`) populates them.
5. `frontend/src/api/types.ts` mirrors new types as optional — unblocks Day 4.
6. Lifecycle double-write plan agreed (reasoning_trail + investigation_log).
7. Sub-investigation spawning design (Section 5) reviewed and green-lit.
8. `stuck.py` per-tool budget sketch agreed.
9. No v1 surface removed — `DossierFull.reasoning_trail` and `DossierFull.ruled_out` still present and populated.
10. Retirement decisions deferred to Day 5.
