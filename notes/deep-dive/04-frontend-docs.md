# Vellum — Frontend & Docs deep-dive

Scope: React/TypeScript app under `D:\projects\Vellum\frontend\src\`, plus the static docs site at `D:\projects\Vellum\docs\index.html`. This report is read-only — it documents what the code actually does, with line references and quoted snippets. No claims from the README are repeated; everything below is grounded in the source.

---

## 1. App shell & routing

### The router is a thin, lazy-loaded surface

`App.tsx:14-23` lazy-loads every page (including the four `/stress*` routes) and wraps them in a single `Suspense + ErrorBoundary`:

```tsx
const DossierListPage = React.lazy(() => import("./pages/DossierListPage"));
const IntakePage = React.lazy(() => import("./pages/IntakePage"));
const DossierPage = React.lazy(() => import("./pages/DossierPage"));
const DemoPage = React.lazy(() => import("./pages/DemoPage"));
const StressPage = React.lazy(() => import("./pages/StressPage"));
...
const LoadingFallback = () => (
  <div className="p-12 text-ink-faint">Loading…</div>
);
```

Route table (`App.tsx:35-47`):

| Path | Page | Purpose |
|---|---|---|
| `/` | `DossierListPage` | Shelf of dossier cards. |
| `/intake`, `/intake/:id` | `IntakePage` | Two modes, branched in component (`IntakePage.tsx:31`). |
| `/dossiers/:id` | `DossierPage` | The case file. |
| `/demo` | `DemoPage` | Hero dossier rendered from `mocks/dossier.ts`. |
| `/stress*` (4 routes) | `Stress{1,2,3,4}Page` | Each is ~10 LOC — pure wrappers over `FixtureHost` with different mock files. |
| `/settings` | `SettingsPage` | DB-backed settings editor. |
| `*` | `NotFoundPage` | `"That page isn't in the dossier."` |

The QueryClient is constructed once at module scope with a 10s `staleTime` default (`App.tsx:6-12`); per-query overrides do the rest of the work.

### Real vs. demo vs. fixture split

This is the cleanest piece of the architecture. **One render path, three different data sources:**

- **Real** — `DossierPage.tsx` issues network calls via `useDossier`, `useChangeLog`, `useAgentStatus`, etc.
- **Demo** — `DemoPage.tsx` imports `MOCK_DOSSIER_FULL` and `MOCK_CHANGE_LOG` from `mocks/dossier.ts` and feeds them through the same presentational components (`SectionsList`, `RuledOutList`, `ReasoningTrail`, `DecisionPointBlock`, `PlanDiffSidebarView`).
- **Stress fixtures** — `pages/FixtureHost.tsx:39-86` mounts a fresh `QueryClient` and pre-seeds the cache with the chosen case file, then renders `DossierPage` with `readOnlyFixture` set. The header comment (`FixtureHost.tsx:7-32`) explains why this is a separate client rather than wiring the fixture into the app-level one: "we want the fixture routes to feel exactly like `/dossiers/<id>` at render time but without any risk of polluting the real app cache."

```tsx
// FixtureHost.tsx:60-77
qc.setQueryData(qk.dossier(dossierId), dossier);
qc.setQueryData(qk.changeLog(dossierId), changeLog);
qc.setQueryData([...qk.investigationLog(dossierId, undefined), 500], dossier.investigation_log ?? []);
qc.setQueryData(qk.investigationLogCounts(dossierId), investigationLogCounts);
qc.setQueryData(qk.resumeState(dossierId), { active_work_session_id: null, wake_pending: false });
qc.setQueryData(qk.agentStatus(dossierId), { running: false, started_at: null });
```

The `DossierPage` mount signature takes `readOnlyFixture` + `fixtureId` (`DossierPage.tsx:79-87`) and uses both to (a) skip the `POST /visit` mutation (`DossierPage.tsx:110`) and (b) bypass `useParams` so the same component renders with a synthetic id.

### The aesthetic — how "serif-forward, warm, document-like" gets built

It's a tight system, not a vibe:

1. **A small, named palette in Tailwind tokens.** `tailwind.config.js:6-49` defines a hand-curated set — `paper: #FBF8F3`, `paper-dark: #F5EFE4`, `ink: #1F2937`, `accent: #8B4513` (a burnished sienna), plus `state-confident/provisional/blocked` in green/amber/rusty. There's a comment at `tailwind.config.js:6` explicitly justifying the warm off-white: "never pure white."
2. **The type stack is loaded in `index.html:12-15`** — Lora (serif), Inter (sans), JetBrains Mono (mono). `body` gets `font-serif bg-paper text-ink` in `globals.css:43-48`. All code/identifiers across the app are JetBrains Mono (`.font-mono`); all body copy is Lora (`.font-serif`).
3. **Width measures are real.** `tailwind.config.js:59-63` defines `prose: 70ch`, `page: 1120px`, `wide: 1000px`, `narrow: 720px`. The dossier page composes these literally: `mx-auto max-w-page px-6`, `max-w-prose min-w-0` for the left column.
4. **Print is a first-class state.** `globals.css:73-107` has a full `@media print` block that strips aside/form/button/nav, gives the page full width, thins borders to `0.5pt`, and breaks sections/articless into pages. The dossier is meant to be printed.
5. **Tailwind config in plain JS, no plugins.** `tailwind.config.js:69` has `plugins: []`. There is no Tailwind UI, no shadcn — every component hand-rolls its classes.

The aesthetic discipline is high. The `<dl>` definitions, the `<time>` elements, the `font-mono uppercase tracking-wide` for metadata strips, the deliberate border-l-2/4 treatments on status cards — they're all chosen to evoke a printed case file rather than a chat app.

---

## 2. Dossier rendering surface (`DossierPage.tsx`)

`DossierPage` is a layout file. The whole page is a 320-character ASCII sketch in the comment block at `DossierPage.tsx:34-67` (yes, it includes a box-drawing diagram) that defines the band layout. The actual render is:

1. **`Header`** with the dossier's title and status pill (`DossierPage.tsx:198-205`).
2. **Top band — hero + Resume CTA** (`DossierPage.tsx:210-256`). The Resume button is `absolute right-0 top-0 z-10` so it floats over the hero; the hero has `pr-24` reserved space so a long title never collides with it.
3. **`QuarantineBanner`** if the dossier has been auto-paused after repeated failures (`DossierPage.tsx:232-236`).
4. **`OpenApprovalsStrip`** — a quiet horizontal bar that counts open needs_input, decision points, and pending plan approval. Renders nothing when nothing is pending (`OpenApprovalsStrip.tsx:47`).
5. **`PremiseChallengeBlock` + `WorkingTheoryBlock` + `DebriefBlock`** stacked full-width.
6. **Two-column band.** Main column (`max-w-prose min-w-0`) holds Plan/PlanApproval → NeedsInput → DecisionPoints → Sections → SubInvestigations → Artifacts → ConsideredAndRejected → NextActions. Right rail (`340px`, `sticky top-6 self-start max-h-[calc(100vh-3rem)] overflow-y-auto`) holds the UserNoteComposer, the PlanDiffSidebar, and the InvestigationLogSidebar.

### How the dossier state is loaded

`DossierPage.tsx:88-99` wires four hooks in parallel:

```tsx
const resumeState = useResumeState(dossierId);   // 3s poll
const agentStatus = useAgentStatus(dossierId);   // 3s poll
const liveDossierPolling =
  agentStatus.data?.running || resumeState.data?.wake_pending ? 3000 : false;
const { data, isLoading, error } = useDossier(dossierId, {
  refetchInterval: liveDossierPolling,
});
const changeLog = useChangeLog(dossierId);
```

The conditional 3s dossier poll is the load-bearing choice. When the agent is doing nothing the dossier is read once and cached; when it's running or about to wake, the dossier itself polls. The hooks are independent — each fires its own 3s tick for the activity indicators even when the dossier is idle — so the UI stays responsive without a global heartbeat.

### The right rail — `InvestigationLogSidebar`

The single biggest file in the codebase at 19 KB (`InvestigationLogSidebar.tsx:1-548`). Three bands, top-to-bottom:

1. **Counts hero** (sticky inside the rail) — four big mono numbers: sources, sub-investigations, artifacts, considered & rejected. The numbers blend two sources: `useInvestigationLogCounts` for sources, and the live dossier snapshot for the other three (`InvestigationLogSidebar.tsx:94-112`). The comment at `:71-78` explains why: "the backend only logs some event types, so the log-counts endpoint under-reports sub-investigations and artifacts" — the snapshot is authoritative when both disagree.
2. **Filter chips** — 12 entry types each get a glyph + count, plus an "all" reset. Each is an `aria-pressed` toggle button (`:242, :262`).
3. **Timeline** — reverse-chronological, grouped by day ("Today", "Yesterday", "Mar 4"). `LOG_LIMIT = 500` (`:28`), but only `VISIBLE_INITIAL = 100` rows render at a time, with a "Show 100 more" button that pages in `VISIBLE_PAGE = 100`-sized chunks (`:32-33, :530-536`).

Each row can be clicked to expand a `PayloadDetails` block; if the entry references a section/sub-investigation, `scrollToEntryTarget` (`InvestigationLogSidebar.tsx:146-173`) scrolls the main body to the matching `id={…}` anchor. The scroll target resolution is deliberately hand-rolled — it inspects `payload.section_id`, `payload.supports_section_ids[0]`, and `payload.artifact_id`, and gracefully bails if the anchor doesn't exist.

### `OpenApprovalsStrip` — the only always-on affordance

Tiny but worth pulling out (`OpenApprovalsStrip.tsx:18-74`). Renders nothing if nothing's pending. When items are pending, the entire strip is the user's "what needs me right now" answer:

```tsx
{pieces.map((p, i) => (
  <span key={p.key} className="flex items-center gap-2">
    <a href={p.href} className="font-serif text-sm text-ink hover:text-accent transition-colors">
      {p.label}
    </a>
    {i < pieces.length - 1 ? <span aria-hidden="true" className="text-ink-faint">·</span> : null}
  </span>
))}
```

The links are fragment-only (`#plan`, `#decisions`, `#needs-input`) — they scroll, not navigate. The strip is hidden via `null`, not `display:none`, so it doesn't take vertical space when nothing's open.

### The "since your last visit" plan-diff window

This is the most architecturally interesting feature in the frontend. The data-flow subtlety is described in a long comment at `DossierPage.tsx:54-67`:

> VISIT-BEFORE-DIFF TIMING. The "since your last visit" sidebar must render entries captured BEFORE we POST /visit (which resets last_visited_at server-side). We achieve this by:
> 1. Firing both GET /dossier and GET /change-log immediately...
> 2. Holding off on POST /visit until useChangeLog has completed...
> 3. POST /visit invalidates the change-log query; the refetch after visit returns the empty post-visit window, but the user has already seen the diff for this session.

The implementation has two pieces. First, a snapshot hook at `hooks.ts:77-128` (`useChangeLogSinceVisit`) — it captures the first non-undefined response into local state and never updates it again:

```tsx
// hooks.ts:107-111
useEffect(() => {
  if (entriesSnapshot !== null) return;
  if (changeLog.data === undefined) return;
  setEntriesSnapshot(changeLog.data);
}, [changeLog.data, entriesSnapshot]);
```

`DossierPage.tsx:106-116` enforces the order: the `/visit` POST fires only after `changeLogSettled` is true, and is gated by `visitedRef` so it runs exactly once per mount. The result: when a user lands on a dossier, they see the diff for "what changed while you were away" rendered with the pre-visit entries, then a `useVisitDossier` mutation fires, the change-log query is invalidated, and the next refetch returns the (now empty) post-visit window. The user has already seen the relevant data, so the empty result is the correct one for "now that you've caught up."

The diff itself is `PlanDiffSidebarView` (`plan-diff/PlanDiffSidebarView.tsx:50-162`), grouped by `PLAN_DIFF_CATEGORY_ORDER` from `ChangeEntry.tsx:29-37`: Plan & debrief → Sections → Sub-investigations → Artifacts → Flagged for you → Considered & rejected → Housekeeping. Each row's `KindPresentation` table (`ChangeEntry.tsx:101-209`) defines a glyph (single Unicode), a label, and an accent color (amber/neutral/rusty/green) per `ChangeKind`. The `state_changed` rows go through `parseStateTransition` (`:241-260`) which understands `"from → to"` and `"label: from → to"` and colorizes the `from`/`to` words based on `stateToneClass` (`:262-270`).

`SessionsSummary` (`plan-diff/SessionsSummary.tsx:88-238`) sits above the categories and surfaces the per-session "what did each work session do" view. It's keyed off `workSessions` filtered by `lastVisitedAt` threshold — a first-visit (no `lastVisitedAt`) shows every session. The compact line shows trigger, duration, change count, end_reason, and cost; if a matching `SessionSummary` row exists, it expands with confirmed/ruled_out/blocked_on bullets and an optional `recommended_next_action`. A nice touch: the total dollar cost is summed and shown next to the heading (`:135-139`).

---

## 3. Polling & live state

The polling pattern is hand-rolled, but uses `@tanstack/react-query`'s `refetchInterval` rather than a custom `setInterval`. Three polling endpoints are active in steady state:

| Hook | Endpoint | Interval | Where |
|---|---|---|---|
| `useAgentStatus` | `GET /api/dossiers/:id/agent/status` | **3000ms** | `hooks.ts:137-147` |
| `useResumeState` | `GET /api/dossiers/:id/resume-state` | **3000ms** | `hooks.ts:351-362` |
| `useRunningAgents` | `GET /api/agents/running` | **3000ms** | `hooks.ts:155-165` |
| `useDossier` (conditional) | `GET /api/dossiers/:id` | 3000ms when running or `wake_pending`, else off | `DossierPage.tsx:90-94` |
| `useChangeLog` | `GET /api/dossiers/:id/change-log` | on-demand | `hooks.ts:54-59` |
| `useBudgetToday` | `GET /api/budget/today` | staleTime 15s | `hooks.ts:470-476` |

The 3s tick is justified at `hooks.ts:142-146` as "tight enough to feel responsive on the demo, loose enough not to spam the localhost backend." The fleet `useRunningAgents` is the load-bearing call for the list page: "One request powers the 'Researching' pill on every dossier card in the list view — avoids an N+1 fanout" (`client.ts:166-167`, ref'd from `DossierListPage.tsx:110`). `retry: false` is set on `useRunningAgents` (`:164`) and `useResumeState` (`:356`) so a transient failure shows as "unknown" rather than blocking the UI with retry storms.

### How the UI knows the agent is running — `AgentActivityIndicator`

A 165-line component (`AgentActivityIndicator.tsx`) that derives a 4-state indicator:

```tsx
// AgentActivityIndicator.tsx:31
type IndicatorState = "running" | "waking" | "scheduled" | "idle";
```

Priority order in `derive` (`:75-108`): running > waking (`wake_pending || wake_at <= now`) > scheduled (`wake_at` in the future) > idle. Each state has a Tailwind dot class and label class. The component owns a 1s `setInterval` (`:131-135`) to drive the elapsed/countdown text — the underlying queries fire every 3s, but the textual counters need to update between refetches. The component is hidden when idle unless `showIdle` is passed, so the hero doesn't carry a permanent "idle" pill.

`wakeReasonLabel` (`:60-73`) maps `scheduled | crash_resume | needs_input_resolved | decision_resolved` to human strings ("Waking", "Resuming after crash", "Picking up your answer", "Picking up your decision") — the same wake-reason vocabulary the backend uses.

### React Query vs. hand-rolled

It's React Query end-to-end, with a hand-rolled `setTimeout` for the auto-redirect on commit (`IntakePage.tsx:145-153`) and a 1s `setInterval` for the activity indicator's elapsed text (`AgentActivityIndicator.tsx:131-135`). All network state — query keys, cache, invalidations — goes through React Query. Every mutation in `hooks.ts:170-376` invalidates the relevant query keys on `onSuccess`; no manual cache management anywhere.

The `useChangeLogSinceVisit` hook (`hooks.ts:77-128`) is a hand-rolled *wrapper* over `useChangeLog` — it uses `useState` to snapshot the first response, with a `useRef` to reset the snapshot when the dossier id changes. This is a clean example of the seam between React Query (transport, dedup, error handling) and component-state (a one-shot capture).

### Lazy fetching

`useDossier` accepts `opts.refetchInterval` and sets `staleTime: 0` only when polling is enabled (`:51`). The change-log, intake, and artifact queries are lazy — they fire on first subscriber and don't refetch. There's no stale-while-revalidate window; either you set an explicit `refetchInterval` or you get "fetch on mount, then re-fetch when invalidated."

---

## 4. Generated vs. hand-maintained types

This is the most interesting finding in the codebase.

**`types.generated.ts`** is the standard `openapi-typescript` output (146 KB, 4,762 lines). The structure is what you'd expect — `paths`, `operations`, `components`, `$defs`, `webhooks` interfaces for the entire OpenAPI schema (`types.generated.ts:6`, `:tail`). The file's banner at `:1-4` says it all: "This file was auto-generated by openapi-typescript. Do not make direct changes to the file."

**`types.ts`** is a hand-maintained 16 KB file that mirrors the Pydantic models. It exports a `Dossier`, `Section`, `DecisionPoint`, `IntakeSession`, `WorkSession`, `DossierFull` etc., plus enums as string unions, plus frontend-only types like `BudgetToday`, `SettingEntry`, `InvestigationLogEntryType`. The banner at `:1-3` is explicit: "Types mirrored from backend/vellum/models.py and backend/vellum/intake/models.py."

**`client.ts`** imports from `./types` (hand-maintained), not `./types.generated` (the auto-generated file). And the entire codebase — 46 importers per `grep` — imports from `./types` only:

```
.\components\dossier\UserNoteComposer.tsx
.\components\dossier\QuarantineBanner.tsx
.\api\client.ts
.\api\hooks.ts
... (46 files total)
```

**Zero files import from `types.generated.ts`.**

The README (`:150-156`) documents a `npm run types:gen` workflow, but that script doesn't exist in `package.json:6-10` — the only scripts are `dev`, `build`, `preview`. The 146 KB of generated types is **dead weight in the bundle**: it's compiled into the TypeScript build (since `tsconfig.json:22` `include: ["src"]` globs it in) but never referenced.

**The seam in practice:** when a backend Pydantic model changes, the developer is expected to either (a) hand-edit `types.ts` to match, or (b) regenerate `types.generated.ts` and then *also* hand-edit `types.ts` because the client uses the latter. The README's `Regenerating frontend types` section is therefore aspirational at best — the regeneration is half a workflow with the second half not actually implemented.

### Drift candidates

- `Dossier.consecutive_error_count` and `Dossier.quarantined_at` / `quarantine_reason` (types.ts:127-129) are hand-added fields, presumably to match a v2 backend addition.
- `SubInvestigation.plan_item_id`, `why_it_matters`, `known_facts`, `missing_facts`, `current_finding`, `recommended_next_step`, `confidence` (types.ts:478-497) are all Phase 4 additions marked optional for backward compat.
- `WorkingTheory`, `PremiseChallenge` (types.ts:132-150) are Phase 2/4 additions; the comments mark them clearly.

These hand-maintained additions are the right place for them — `types.generated.ts` would carry them once, but the hand-maintained `types.ts` is the load-bearing contract. The risk is just the opposite: that `types.generated.ts` drifts far from `types.ts` and someone trusts the former.

---

## 5. Intake UI

Three components — `IntakeInput`, `IntakeThread`, `IntakeStateSummary` — composed by `IntakePage.tsx` in two modes (`/intake` and `/intake/:id`).

### `IntakeThread` — explicitly not a chat UI

The comment at `IntakeThread.tsx:6-16` is on the nose:

> This is explicitly NOT a chatbot bubble UI. Both sides are left-aligned; the only differentiation is the small-caps mono author label and a subtle left border on assistant messages.

```tsx
// IntakeThread.tsx:36-50
<div key={m.id}>
  <div className="text-xs font-mono uppercase tracking-wide text-ink-faint mb-1">
    {isAssistant ? "VELLUM" : "YOU"}
  </div>
  <div className={
    isAssistant
      ? "font-serif text-base text-ink leading-relaxed whitespace-pre-wrap border-l-2 border-rule pl-4"
      : "font-serif text-base text-ink leading-relaxed whitespace-pre-wrap"
  }>
    {m.content}
  </div>
</div>
```

The thinking indicator is also hand-rolled — three `<span>` dots with staggered `animation-delay` driven by inline `style` (`IntakeThread.tsx:88-103`). An inline `<style>` block in the component defines the keyframe (`:77-82`). It's not a spinner; it's "someone is writing."

### `IntakeInput` — best keyboard handling in the codebase

`IntakeInput.tsx:84-93` implements:
- **Enter** submits, **Shift+Enter** newlines, **Cmd/Ctrl+Enter** also submits.
- **IME composition** is detected via `onCompositionStart`/`onCompositionEnd` (`:106-107`) so an Enter that *finalizes* a CJK composition does not submit the turn prematurely (`:86`).
- **Auto-grow** between 3 and 12 rows, measured via computed `lineHeight` + `paddingY` + `borderY` from the actual element (`useLayoutEffect` at `:44-60`). It re-measures on every keystroke.
- **Optimistic clear with retry** — `setValue("")` then `await onSend(text)`; on throw, restore the text (`:74-82`).
- **Refocus on enable** — `useEffect` at `:64-68` re-focuses the textarea when the parent flips `disabled` back off, so the user doesn't have to click back in after every assistant turn.

### `IntakeStateSummary` — the right-rail "Gathered so far"

A 117-line panel that reads the `IntakeState` shape and shows each field with a small-caps mono label. `buildRows` (`:21-50`) maps the state into a `FieldRow[]`; `missingKeys` (`:52-54`) returns the keys whose values are null. The bottom of the panel shows one of three states:

```tsx
// IntakeStateSummary.tsx:97-112
{status === "committed" && dossierId ? (
  <Link to={`/dossiers/${dossierId}`} className="inline-block">
    <Pill variant="state" state="confident">Dossier open</Pill>
  </Link>
) : missing.length === 0 ? (
  <div className="text-xs font-mono text-attention">
    All gathered — ready to commit.
  </div>
) : (
  <div className="text-xs font-mono text-attention">
    Missing: {missing.join(", ")}
  </div>
)}
```

### UX assessment

The intake flow is actually a model. Three things stand out:

1. **The "Dossier open" pill is a deliberate hand-off.** On commit, the backend returns `dossier_id` and `IntakeStateSummary` renders a `Link` to it. The page itself auto-redirects with a 900ms delay (`IntakePage.tsx:147-150`) "to let the user register the success state." That's the right call — without the pause the transition would feel abrupt.
2. **Send errors keep the draft.** The conversation intake has the same optimistic-clear-then-restore pattern as `IntakeInput` — on a 500, the user's text is preserved and a Retry button is offered (`IntakePage.tsx:213-230`).
3. **The state is shown as a plan, not a status.** The right rail surfaces the intake agent's structured state — title, problem_statement, type, out_of_scope, check-in policy — with `not set` placeholders. The user can see the dossier being constructed in real time, which is a more honest UX than a spinner.

The "intro" prompt at `/intake` (`IntakePage.tsx:72-79`) is just a `<textarea>` with `autoFocus` and a single line of copy: "A sentence or two is enough — the intake assistant will ask follow-ups." That sets expectations correctly — intake is iterative prose, not form fields.

---

## 6. Mock fixtures & stress pages

### The five mock files

| File | Size | Used by | Purpose |
|---|---|---|---|
| `mocks/dossier.ts` | 12.8 KB | `DemoPage` | Single hero case file for `/demo`. |
| `mocks/stressCaseFile.ts` | 67.8 KB | `StressPage` (`/stress`) | "Credit card debt — Marjorie" deep case. |
| `mocks/stress2CaseFile.ts` | 106.2 KB | `Stress2Page` (`/stress2`) | Fertility-decision-at-35 case. |
| `mocks/stress3CaseFile.ts` | 110.2 KB | `Stress3Page` (`/stress3`) | Third case. |
| `mocks/stress4CaseFile.ts` | 104.5 KB | `Stress4Page` (`/stress4`) | Fourth case. |

`mocks/dossier.ts:1-10` is explicit: "Hero-demo fixture for `/demo`. Hand-written as if the dossier agent had produced it after a first work session on a real scenario... All timestamps are computed relative to 'now' so the fixture stays evergreen; spacing is in the last ~20 hours." The 100KB+ stress case files follow the same pattern but for deeper dossiers — each carries a full `DossierFull` shape plus a `STRESS_CHANGE_LOG` array, all from the same hand-authored narrative.

### The stress pages are 10-line wrappers

`StressPage.tsx:13-21` is the entire file:

```tsx
export default function StressPage() {
  return (
    <FixtureHost
      dossier={stressCaseFile}
      changeLog={STRESS_CHANGE_LOG}
      investigationLogCounts={STRESS_INVESTIGATION_LOG_COUNTS}
    />
  );
}
```

`Stress2Page.tsx` and the others are identical except for the imported symbols. The four `/stress*` routes exist primarily for the screencast/demo — the `submission-assets/` directory contains stress screenshots and pre-rendered video clips (`notes/deep-dive/04-frontend-docs.md` references these as having a heavy media presence).

### What the fixtures are actually for

The stress fixtures exist so that:

- The `/stress*` URLs work with no backend running and no API key — the docs site advertises this explicitly (`docs/index.html:2076-2078`): `$ ./dev.sh` then `$ open http://localhost:5173/stress`, and the comment "# no backend or API key needed for the /stress fixture."
- The `FixtureHost` can mount the same `DossierPage` component against pre-seeded data, proving that the rendering path doesn't depend on a live agent.
- Screencasts and submission screenshots can be re-rendered if the component changes, by just opening `/stress` in a browser.

The fixtures are not used by anything beyond the demo pages — `grep` shows no other importers of the `stress*CaseFile` modules. The investment in 100KB+ hand-written fixture content is real and pays for itself in demo parity: a reviewer can click `/stress` and see the same dossier shape they'd see on a live `/dossiers/:id`.

---

## 7. Component quality

### Over-engineered

- **`AgentActivityIndicator.tsx` (165 LOC)** is the canonical "lots of props/state for one tiny pill" file. Four states, a 1s tick interval, a `derive` function that needs all five inputs as parameters — the abstraction is justified by the four distinct copy lines ("Researching", "Waking", "Resuming after crash", "Picking up your answer") but the state machine could collapse to a discriminated union.
- **`DossierHero.tsx` (216 LOC)** is a *two-mode* component — `RichHero` for the live dossier and `LegacyHero` for `DemoPage`. The legacy mode's props (`title`, `eyebrow`, `subtitle`, `meta`) are kept around "so DemoPage keeps compiling" (`:155-158`). This is a real cost: the `if (props.dossier)` branch at `:200` decides which render path to take, and a future contributor has to understand both shapes.
- **`InvestigationLogSidebar.tsx` (548 LOC)** is a small program — its own state for filtering, pagination, expansion, day grouping, payload parsing, anchor scrolling. The `ENTRY_TYPES` constant (`:38-55`) maps 12 types to (glyph, label) pairs and is then re-indexed twice into `GLYPH_BY_TYPE` and `LABEL_BY_TYPE` (`:57-63`) for `O(1)` lookup, which is the right call but the file is doing a lot.

### Thin / one-liner wrappers

- **`Divider.tsx` (15 LOC)** — just `<hr className="border-0 border-t border-rule my-6" />`. Not referenced anywhere; `grep` finds zero importers. It would be a "one-liner" if anyone used it.
- **`SourceList.tsx`** exists in **two** near-identical copies: `components/common/SourceList.tsx` and `components/sections/SourceList.tsx` (both ~90 LOC, both render the same data). Neither is imported — the dossier's `SectionCard` (in `dossier/`) imports from `../sections/SourceList` and `DossierPage` doesn't import either directly. **Actual duplication in the tree.**
- **`Button.tsx` and `Badge.tsx`** are well-shaped primitives (clean variants/sizes) but neither is imported anywhere outside of where they're defined. The `common/` directory has `Card`, `Pill`, `StateBadge`, `RelativeTime` — these *are* used, and the rest (`Badge`, `Button`, `Divider`, `SourceList`, `StateBadge`) are sitting unused. (The "real" buttons in pages are hand-rolled with `bg-accent text-paper font-sans text-sm rounded px-4 py-2 hover:bg-accent-hover` directly.)

### Duplication

- **Two `SourceList.tsx`** as noted above.
- **Two `SectionCard.tsx`** — `components/dossier/SectionCard.tsx` (370 LOC) and `components/sections/SectionCard.tsx` (160 LOC). The dossier one is the current Day-4 renderer with state pip + type treatment + collapse; the sections one is a Day-1/2 fallback with a simpler `<Pill>`. `DemoPage` uses `sections/SectionsList` → `sections/SectionCard`, while `DossierPage` uses `dossier/SectionList` → `dossier/SectionCard`. The same `DossierFull` data flows through two different render paths in two different routes, with different visual treatments.
- **Three `SectionCardProps` interfaces** — `SectionList.tsx:14-15` defines its own, `dossier/SectionCard.tsx:20` extends it, and `dossier/SectionCard.tsx:257` re-extends it as `SectionCardFullProps`. Minor but symptomatic.
- **Inline `cx` helper** is reimplemented in `common/Button.tsx:45-47`, `common/Card.tsx:29-31`, `common/Pill.tsx:29-31`, `common/Badge.tsx:36-38`, `common/StateBadge.tsx:36-38`, and `common/Divider.tsx:7-9`. A shared `utils/cx.ts` already exists (`utils/cx.ts:13-14`) and is exported; nobody imports it.
- **Three confidence-pip tables** are essentially the same data: `WorkingTheoryBlock.tsx:22-38`, `SubInvestigationList.tsx:85-101`, and `AgentActivityIndicator.tsx` (no table — uses inline classes). Three mappings of `high/medium/low` → `{pipClass, labelClass}`.

---

## 8. The docs site (`docs/index.html`)

A single self-contained file at `D:\projects\Vellum\docs\index.html` (2,088 lines, ~76 KB). All CSS is inlined in six `<style>` blocks (lines 16, 92, 297, 539, 1168, 1385); the only "image" is one inline SVG diagram. The page is structured in five sections matching a sticky nav:

- **Nav** (`:1476-1489`): Thesis · How it's different · The dossier · Under the hood.
- **Masthead** (`:1491-1506`): A 88vh-tall hero with the wordmark in Newsreader at `clamp(72px, 11vw, 160px)`, an italic tagline, and a long prose framing paragraph.
- **Problem** (`:1508-1519`): A two-column block — `WHY CHAT IS WRONG FOR DECISIONS` over the same 19px serif body used everywhere.
- **Three load-bearing behaviors** (`:1521-1598`): Premise Challenge, Structured Writes (with a list of 8 typed tool names in mono), First-Class State. Each behavior is a card with prose on the left and a styled exhibit on the right.
- **The dossier** (`:1600-1884`): A stress mockup — same content as `/stress`, recreated by hand in HTML. Includes: title, problem statement, a "WAITING ON YOU" strip, premise challenge with hidden assumptions + required evidence, working theory with confidence pill, investigation plan with done/in-progress/planned pips, four sub-investigations (delivered / running), eight sections (some confident, one blocked), a needs-input textarea, a decision point with two radio options (one recommended), and a "Since your last visit" sidebar with three change-log rows. The closing line (`:1880`): "Every block above is a rendered output of a typed tool call. The agent cannot write anything else — no chat reply, no loose prose, no 'thoughts'. The dossier is the transcript."
- **Under the hood** (`:1886-2064`): A single inline SVG diagram of the turn loop (`:1898-1967`), the 30s scheduler explanation, sub-investigations paragraph, a table of all 24 typed tools, stuck escalation paragraph, and a stack `<dl>`.

### On `problem_statements.png`

**Not referenced anywhere in the docs.** A grep across the file (`grep -E "problem_statements|png|jpg|webp"`) returns zero matches for image filenames. The only graphics are:
- A single inline SVG architecture diagram (`:1898-1967`).
- The favicon (data-URI, `:10`).
- The CSS `::before` counter on `.stress-premise-col li` (`:712-721`) and similar counters — pure CSS, not images.

The "mockup" in the dossier section is recreated with hand-written HTML (`:1610-1877`) — a 267-line inline case file that mirrors the actual `/stress` route's data. It's a *live HTML recreation, not a screenshot*, as the section caption says (`:1608`).

### Does it function as a real product tour?

Yes. It's a designed reading experience:
- The masthead uses Newsreader (a display serif) for the wordmark and a large italic display line, then drops into Lora (the same body serif the app uses) for the framing paragraph.
- The behavior section pairs a paragraph on the left with a styled exhibit on the right — the same pattern as the app's hero+sidebars, but with the sidebars' role inverted (exhibits, not navigation).
- The stress mockup mirrors the dossier page's actual visual hierarchy, including the "WAITING ON YOU" strip, the state pips, the kind chips.
- The architecture section drops into mono for technical labels (`# STUCK DETECTION`, `claude-opus-4-7`, `wake_at <= now`), matching the app's mono-typography discipline.

What's notably **absent**:
- No interactive demo (no live data, no client-side JS).
- No screenshots of the live app.
- No mention of how to actually use the product beyond the `Run it locally` block in the footer (`:2074-2079`).
- No problem-statement gallery or screenshots.

The site reads more as a long design document than a marketing tour. The "Run it locally" footer line ("# no backend or API key needed for the /stress fixture") is a quiet admission that the docs are *showing the product*, not *selling the product*.

---

## 9. Honest assessment

### What's polished

- **The aesthetic is consistent and intentional.** Every component uses the same color tokens, the same mono-uppercase tracking-wide pattern for metadata, the same `font-serif` for body, the same `border-l-2 border-rule` for separators. There is no design system in Tailwind sense (no preset components), but there is a visual system applied by hand consistently.
- **The dossier loading + visit-timing pattern is genuinely clever.** Snapshotting the change-log first response, deferring `POST /visit` until both queries settle, then invalidating — this is the kind of thing that's hard to retrofit. The 9-page JSDoc at `DossierPage.tsx:54-67` is the right amount of explanation.
- **Keyboard handling in `IntakeInput` is best-in-class.** IME composition detection, Cmd/Ctrl+Enter, auto-grow with measured line-height, optimistic clear with restore on error, refocus on enable. This is a 130-line file that handles more keyboard cases than most production textareas.
- **The 24-tool architecture is well-exemplified in the UI.** Each `ChangeKind` has a glyph and accent (`ChangeEntry.tsx:101-209`), each `SectionType` has a visual treatment (`dossier/SectionCard.tsx:76-120`), each `SubInvestigationState` has a state pip (`dossier/SubInvestigationList.tsx:41-63`). The backend's enum is mirrored faithfully.
- **The print stylesheet (`globals.css:73-107`)** is a thoughtful touch — the dossier is designed to be printed, with hidden chrome and `break-inside: avoid-page` for sections.

### What's rough

- **The auto-generated types are dead weight.** `types.generated.ts` is 146 KB of OpenAPI output that no file imports. The `npm run types:gen` script doesn't exist. The README describes a workflow that isn't wired up.
- **There are two `SectionCard` and two `SourceList` components.** A future contributor will copy the wrong one and ship a visual regression. This is a code-organization problem masquerading as a design choice.
- **`PlanApprovalBlock` has 364 lines of branchy logic.** The four-branch render (no plan / approved / drafted-no-DP / full deliberation) is correct but hard to scan. The `findPlanApprovalPoint` function at `:63-77` falls back to a title-regex when `kind` is undefined (`:56-60`), which is a temporary workaround for a backend that may or may not have shipped. This is the kind of thing that should be a single switch on `plan.state` if the backend added one.
- **Polling at 3s on three endpoints means ~20 req/min while the dossier is open.** With two dossiers open and a wake pending, that's ~120 req/min to a localhost backend. Fine for the demo, but a real product would batch or use SSE/WebSockets.
- **The `dossier.ts` mock file has hand-computed relative timestamps (`iso(NOW - 20 * HOUR)` etc., `dossier.ts:14-15`) that work but are fragile.** When the user opens `/demo` two days after a build, the demo's "Last visited 20h ago" still shows 20h. This is intentional ("the fixture stays evergreen") but it does mean the demo never ages.
- **`ArtifactList` (211 LOC) has filter logic that could be hoisted.** The `presentKinds` memoization (`:74-78`) is fine, but the showKindChips check (`> 3` artifacts) and the "show all / superseded only" state filter coexist awkwardly.
- **`No tests in the frontend.** The README (`:50-51`) claims "230+ test functions across 31 files" but they're all backend tests. There's no `vitest`/`jest` in `package.json:18-27`. A refactor to `InvestigationLogSidebar` could quietly break the day-bucket grouping and no test would catch it.

### Accessibility

- Focus rings are explicit and consistent: `globals.css:62-71` installs `*:focus-visible` outline in accent color, with `border-radius: 2px`.
- `aria-live="polite"` is used on the agent activity indicator (`AgentActivityIndicator.tsx:150`) and the copy button (`ArtifactCard.tsx:251`).
- `aria-expanded` is set on every collapsible (SectionCard, PremiseChallengeBlock, WorkingTheoryBlock, SubCard, ChangeEntry, LogRow, RuledOutList, ReasoningTrail, PlanDiffSidebar's filter chips).
- `aria-label` is used where context is missing (DossierHero masthead link, the thinking indicator, the asks composer textarea).
- **What's missing:** no skip-to-content link. The Header is a thin strip — once the user tabs past the wordmark, the first focusable is "All dossiers" or "Settings", which isn't the actual primary content. Tab order on the dossier page is also not great: the Resume button is `absolute right-0 top-0 z-10` (`DossierPage.tsx:217`) — visually prominent, tabbable, but the hero's h1 doesn't get focused first.

---

## 10. Notable design choices

### Polling vs. WebSockets

The 3s polling choice is deliberate and defensible. For a single-user localhost app, polling at 3s with cache invalidation is simpler than SSE, doesn't require sticky sessions, and degrades gracefully when the backend is offline (the `retry: false` in `useRunningAgents` and `useResumeState` make that explicit). The hidden cost is that the UI is 0–3s stale on the dossier state, but the activity indicator's 1s tick smooths over that. SSE would shave the 3s but add a connection lifecycle to manage.

### React Query

The hooks file is ~480 LOC and does exactly what React Query is good at: query keys, mutations, invalidation, dedup, background refetch. The custom `useChangeLogSinceVisit` hook is the one place the codebase reaches past React Query — and it's a clean custom layer *over* React Query, not a replacement for it.

### Hand-rolled + generated types

This is the weakest part. The README pitches a clean two-file seam, but in practice the generated file is compiled in and unreferenced. The hand-maintained `types.ts` is the actual source of truth. A future cleanup would either (a) wire `client.ts` to read from `types.generated.ts` and delete `types.ts`, or (b) commit to hand-maintenance and delete `types.generated.ts`. Currently it's both.

### Tailwind

Tailwind 3.4 with no plugins, no shadcn, no daisyUI. The custom palette in `tailwind.config.js:6-49` does the heavy lifting. The trade-off: every component's class string is long and bespoke (e.g. `ArtifactCard.tsx:73-78` has a 5-class string per state). The benefit: no theme override to learn, every class is local. The codebase commits to this — there's no `clsx`/`classnames` dependency; the inline `cx` is a 1-line filter.

### Skipping a rich-text editor

Sections and artifacts are rendered as Markdown via `react-markdown` (`SectionCard.tsx:79-145` and `ArtifactCard.tsx:113-215`). The editor is just a textarea + a single primary action — no formatting toolbar, no WYSIWYG. This is consistent with the "structured data first, prose second" thesis in the README (`:9`): the agent writes through typed tool calls with markdown payloads, the user reads them, and on rare edits they get a textarea. The cost is the user can't easily edit a section; the benefit is the renderer has a small, predictable surface (one Markdown library, one set of styled components per renderer).

### The "Doc, not chat" thesis in the UI

The single most distinctive design choice: `IntakeThread` is explicitly not a chat UI (`IntakeThread.tsx:6-16`). Both user and assistant messages are left-aligned with the same serif body. The only differentiation is a small-caps mono author label ("VELLUM" / "YOU") and a left border on assistant messages. This is anti-conventional: every chatbot for the last decade has used right-aligned user bubbles or color-distinct roles. The reasoning is in the README (`:11`): the dossier is a destination, not a stream. The intake conversation is a means to construct the dossier, not the dossier itself. Visual sameness reinforces that.

### Polling-only, no streaming, no SSE

A more ambitious product would stream the agent's `pause_turn`/tool-call events over SSE so the UI updates as the agent works. Vellum deliberately doesn't — the README's "Quiet by default" stance (`:11`) means the agent should work in the background and the user returns to find a dossier. Polling at 3s for the activity indicator is enough to show the dot pulse; the dossier itself is the destination. The 100-row visible log cap (`InvestigationLogSidebar.tsx:32`) and 500-row fetch cap (`:28`) further enforce "the dossier is a reading surface, not a live ticker."

---

## Headline

- **The dossier page is a single composition file (`DossierPage.tsx`, 322 LOC) that renders nine surface components in a hero → 2-column band layout, with a 3s conditional poll and a hand-rolled "snapshot before /visit invalidates" pattern that genuinely earns its complexity.** It's the most architecturally interesting file in the codebase.
- **Two visual stacks (`dossier/SectionCard` vs. `sections/SectionCard`, two `SourceList.tsx`, an unused `utils/cx.ts` and a 146 KB `types.generated.ts` no one imports) are the visible seams of a solo dev shipping at speed — none of them are bugs, but a refactor pass would consolidate them.** The aesthetic consistency is the thing that holds them together visually.
- **The docs site is a single self-contained 76 KB HTML file with one inline SVG and no images — a designed reading experience that mirrors the app's visual system but doesn't include any live product tour, screenshots, or the rumored `problem_statements.png` (which doesn't exist).** The footer sells `./dev.sh` and `/stress` as the way in; the rest of the page is a long design doc.

**Report path:** `D:\projects\Vellum\notes\deep-dive\04-frontend-docs.md`
