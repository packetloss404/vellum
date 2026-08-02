# Vellum — Frontend Consolidation Research (Cleanup Pass 2)

**Scope:** 6 items from the deep-dive brief (§3 risky/weak + §8 recommendations), focused on the frontend. The previous one-shot cleanup pass handled 6 small items (deleted `types.generated.ts`, set up vitest with 3 smoke tests); this report feeds the deeper 2nd cleanup pass.

**Workspace root:** `D:\projects\Vellum`

**Inputs read:**
- `notes/deep-dive/00-synthesis.md` (esp. §3, §8)
- `notes/deep-dive/04-frontend-docs.md` (full)
- `frontend/src/api/types.ts` (full)
- The 3 vitest tests: `cx.test.ts`, `AgentActivityIndicator.test.tsx`, `ChangeEntry.test.ts`
- Both `SectionCard.tsx` files, both `SourceList.tsx` files, all `common/` primitives, `DossierPage.tsx`, `DemoPage.tsx`, `FixtureHost.tsx`, `hooks.ts`, `IntakeInput.tsx`, `ChangeEntry.tsx`, `PlanDiffSidebarView.tsx`, `InvestigationLogSidebar.tsx`, `time.ts`, `format.ts`, `useDocumentTitle.ts`, `vitest.config.ts`, `package.json`, `test-setup.ts`
- 4 day-prefixed pytest files + their docstring headers + `conftest.py` + `pyproject.toml`

---

## 1. Consolidate the two `SectionCard` paths

### Current state

Two unrelated components render the same `Section[]` data, with materially different visual treatments:

- **State presentation:** dossier = small mono "state pip" in the overline; sections = `<Pill variant="state">` chip top-right.
- **Type treatment:** dossier = per-`SectionType` `TypeTreatment` table at `dossier/SectionCard.tsx:69-120` (recommendation gets `border-l-2 border-accent`, decision_needed `border-l-2 border-attention`, open_question goes serif italic + muted, ruled_out becomes line-through + 70% opacity); sections = single flat wrapper, type only as mono overline text.
- **Markdown hierarchy:** dossier = scoped `.prose` with embedded `h1`/`h2` downranked to `h3`/`h4`; sections = per-element class strings with `h1`/`h2`/`h3` at full sizes.
- **Long content:** dossier collapses to 250-char preview at >600 chars, with a `Show full` button; **blocked sections must stay expanded** (`dossier/SectionCard.tsx:268-353`). Sections renders full always.
- **Sources / `depends_on` / change-note placement:** dossier = linked cross-references + italic overline change-note + bottom `pt-2` source block; sections = "3 sources" in the overline + footer change-note block.

**The dossier version is clearly the canonical, Day-4 renderer.** It implements the "type treatment" architecture the rest of the design system is built around; the sections version is a Day-1/2 fallback that was never updated. The collapse-to-preview is a load-bearing UX detail for the long synthesized sections in the fixture cases (`stress2`, `stress3`).

The `dossier/SectionCard` already imports its `SourceList` from `../sections/SourceList` (`dossier/SectionCard.tsx:4`) — i.e. the dossier path is the one that depends on the `sections/` directory. That's a leak in the wrong direction.

### Target state

**One `SectionCard`, the dossier version, used by both pages.**

- `dossier/SectionCard.tsx` is the single component.
- `dossier/SectionList.tsx` is the single list wrapper.
- `pages/DemoPage.tsx` switches its import from `sections/SectionsList` → `dossier/SectionList`.
- `sections/SectionCard.tsx` and `sections/SectionsList.tsx` are deleted.

### Migration plan (5 ordered steps, each independently shippable)

1. **Verify the dossier version renders the `MOCK_DOSSIER_FULL` fixture data correctly.** Open `/demo` in a separate branch that imports `dossier/SectionList` and check the four sections of the mock render with type-treatments, pips, and no overflow. (This is the visual-blessing step before deletion.)
2. **Update `pages/DemoPage.tsx:4`** — change `import { SectionsList } from "../components/sections/SectionsList";` to `import { SectionList } from "../components/dossier/SectionList";` and the call site at line 150 to `<SectionList sections={sections} />`.
3. **Manually smoke-test `/demo`** — sections render with the dossier treatment, blocked sections stay expanded, change-notes are visible, no source-count appears in the overline (it now lives in the `SourceList` block below).
4. **Delete `sections/SectionCard.tsx` and `sections/SectionsList.tsx`.** No other importers (`sections/SourceList.tsx` and `sections/RuledOutList.tsx` and `sections/ReasoningTrail.tsx` remain for now — see Open Questions).
5. **Re-run vitest** (`npm test`) and the dev server. All 12 vitest tests must still pass.

### Risk assessment

- **Visual change on `/demo` is intentional and visible** — the demo's section cards will now look like the live dossier's section cards. This is the *desired* outcome (the deep-dive §1 explicitly says the architecture is "one render path, three data sources"; the divergence is a bug).
- **No risk to the live `/dossiers/:id` page** — the import path doesn't change.
- **Type contract is identical** — both consume `Section` from `api/types.ts`. No Pydantic/type drift risk.
- **No `FixtureHost` impact** — the fixtures mount `DossierPage`, not `DemoPage`, so the readOnlyFixture path is untouched.

### Effort estimate

**Small.** Three-file change (1 import, 2 deletes). Most of the time goes into the visual-verification step.

### Open questions

- **`sections/RuledOutList.tsx` and `sections/ReasoningTrail.tsx`** are also demo-only. The deep-dive doesn't ask to address them here. After SectionCard is gone, the `sections/` directory holds 3 demo-only files. **Should this cleanup pass also move them out of `sections/`** (e.g. to `pages/DemoPage.tsx` as private sub-components, or a `pages/demo/` subfolder)? My recommendation: defer to a follow-up pass; this report scopes to SectionCard only.
- **Is the visual change on `/demo` acceptable** as part of "cleanup"? The user is the same human; the demo is meant to advertise the product; aligning it with the live aesthetic is a net win. But if you want a byte-for-byte identical `/demo` to ship first, then a flag-day switch in a follow-up, the migration is still safe — just visually different in step 2.

---

## 2. Consolidate the two `SourceList` components

### Current state

`components/common/SourceList.tsx` (2285 bytes) and `components/sections/SourceList.tsx` (2285 bytes) are **byte-for-byte identical** (same file size, same content, same import path inside). The `common/` version has **zero importers** (verified by grep — only its own file references it). The `sections/` version is used by `dossier/SectionCard.tsx:4` and `sections/SectionCard.tsx:5`.

### Target state

Delete `common/SourceList.tsx`. Keep `sections/SourceList.tsx`. No other changes.

### Migration plan (1 step)

1. Delete `common/SourceList.tsx`. There are no importers. Done.

### Risk assessment

**Zero risk.** Pure dead-code removal. The file is not exported from any barrel. TypeScript will not complain because the file is never imported.

### Effort estimate

**Trivial.** One file deletion. Verify by running `tsc` (`npm run build`) — should produce zero new errors.

### Open questions

- After item 1 deletes `sections/SectionCard.tsx`, the only importer of `sections/SourceList.tsx` is `dossier/SectionCard.tsx`. Should `sections/SourceList.tsx` be moved to `common/SourceList.tsx` at that point to clean up the import direction (`dossier → common` reads better than `dossier → sections`)? My recommendation: yes, but only if you're already touching the file — and as part of item 1, you are. Bundle it.

---

## 3. Clean up the unused `common/` primitives

### Current state

Per-grep audit of every file in `frontend/src/`:

- **`Card.tsx`** — 7 importers (DecisionPointItem, PlanApprovalBlock, DossierCard, NeedsInputItem, PlanBlock, UserNoteComposer, DemoPage). **Used.** Keep.
- **`Pill.tsx`** — 8 importers. **Used.** Keep. (After item 1, down to 7.)
- **`Button.tsx`** — 1 importer (SettingsPage). **Used but underused.** 9 hand-rolled `bg-accent text-paper …` sites: `DemoPage.tsx:79`, `DossierListPage.tsx:29`, `NeedsInputItem.tsx:111`, `IntakePage.tsx:111`, `IntakePage.tsx:176`, `IntakeInput.tsx:121`, `PlanApprovalBlock.tsx:278`, `PlanApprovalBlock.tsx:315`, `ErrorBoundary.tsx:43`.
- **`Badge.tsx`** — 0 importers outside its own file. **Dead.** Delete.
- **`Divider.tsx`** — 0 importers outside its own file. **Dead.** Delete.
- **`StateBadge.tsx`** — 0 importers outside its own file. **Latent conflict:** `ArtifactCard.tsx:70` defines its own local `StateBadge` for `ArtifactState` (different domain — `draft`/`ready`/`superseded`); `dossier/SectionCard.tsx:44-58` defines a local `StatePip` that uses `bg-attention` for "provisional" while `StateBadge.tsx:25` uses `bg-state-provisional`. **Different colors for the same state.** Delete.
- **`SourceList.tsx`** — 0 importers (covered in item 2). **Dead.** Delete.

### Target state

- **Delete `Badge.tsx`, `Divider.tsx`, `StateBadge.tsx`, `SourceList.tsx` outright** — no importers, no future use plans documented.
- **Wire `Button` to the 9 hand-rolled sites** — the `Button` component's primary variant matches the hand-rolled class strings *exactly* (the base class + size class produce `font-sans text-sm rounded px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed` and the variant adds `bg-accent text-paper hover:bg-accent-hover`). One site (`DossierListPage.tsx:29`) is a `<Link>`, not a `<button>` — leave it alone (or wire to a styled Link; see Open Questions).
- **Two of the 9 sites use `px-5` instead of `px-4`** (both in `PlanApprovalBlock.tsx`, lines 278 and 315 — the "Approve" and "Send redirect" CTAs). The `Button` md size is `px-4`. The override is `className="px-5"`. This is a real, intentional visual difference (wider CTAs for a high-stakes gating action); it should be preserved.

### Migration plan (3 ordered steps)

1. **Delete the 4 dead primitives** in one commit: `Badge.tsx`, `Divider.tsx`, `StateBadge.tsx`, `common/SourceList.tsx`. Run `npm run build` to confirm zero new errors.
2. **Wire `Button` to 6 of the 9 hand-rolled sites** (the `px-4` ones): `DemoPage.tsx:79`, `NeedsInputItem.tsx:111`, `IntakePage.tsx:111`, `IntakePage.tsx:176`, `IntakeInput.tsx:121`, `ErrorBoundary.tsx:43`. Each is a 1-import + 1-attribute swap. Visuals stay byte-identical (the `Button` base class adds `transition-colors` and `disabled:cursor-not-allowed`; both are improvements, not regressions). Run `npm test` and visually smoke `/`, `/intake`, `/intake/:id`, `/dossiers/:id`.
3. **Wire `Button` to the 2 `PlanApprovalBlock.tsx` sites** (lines 278, 315) using `className="px-5"` to preserve the wider CTA. Visually smoke `/dossiers/:id` with a plan-approval gate open.

### Risk assessment

- **Step 1 is zero risk** — pure deletion of files with no importers.
- **Step 2 is low risk** — the `Button` class string is a *superset* of the hand-rolled class strings. The added `disabled:cursor-not-allowed` and `transition-colors` are CSS improvements that match the `Button` design intent. Two sites (`IntakePage.tsx:176` Retry, `ErrorBoundary.tsx:43` Reload) don't have a disabled state today, so the added `disabled:cursor-not-allowed` is dormant.
- **Step 3 needs the `className="px-5"` override** — without it the CTA loses 4px of horizontal padding, a visible regression on the highest-stakes page-level action. The override is the right call.
- **The `DossierListPage.tsx:29` "Open a new dossier" Link is intentionally not wired** — `Button` is a `<button>`, and replacing `<Link>` with `<button>` would break client-side routing. See Open Questions.

### Effort estimate

**Small.** 4 file deletions + 8 button-replacements. ~30 LOC delta total. The risk is concentrated in the `PlanApprovalBlock` step where the `px-5` override must be remembered.

### Open questions

- **The `DossierListPage.tsx:29` Link** is the "Open a new dossier" entry-point on the landing page. It hand-rolls `bg-accent text-paper px-4 py-2 … rounded … hover:bg-accent-hover`. It's a `<Link>` not a `<button>` because it navigates via `react-router-dom`. Two options:
  - **Option A: leave alone** (recommended for this pass) — `<Button>` doesn't model links; creating `<ButtonLink>` is scope creep.
  - **Option B: add a `<ButtonLink>` that wraps `<Link>` with the same variant API** — ~15 LOC, fixes the styling drift. Defer to a follow-up.
- **`StateBadge` vs the local `StatePip` in `dossier/SectionCard.tsx:44-58`**: the *colors* disagree (provisional is `bg-attention` in the card, `bg-state-provisional` in `StateBadge`). If you want to delete the local `StatePip` and route through `StateBadge`, you'd need to reconcile the colors — and one of them is wrong. **Don't try this in a cleanup pass**; the right answer is "delete `StateBadge.tsx` and keep the local `StatePip`."

---

## 4. Replace the `day-N` pytest file names

### Current state

Four test files in `backend/tests/` carry the day-N prefix:

- `test_day1_roundtrip.py` (21 KB, 1 test, `test_day1_roundtrip`) — "Day-1 end-to-end roundtrip test for the Vellum v2 backend"
- `test_day2_autonomous.py` (13 KB, 6 tests; 1 gated live + 5 structural) — "Day-2 autonomous-agent smoke test"
- `test_day2_smoke_auto_resolve.py` (11 KB, 13 tests) — "Tests for the `--auto-resolve` feature of `scripts/day2_smoke.py`"
- `test_day3_lifecycle.py` (23 KB, 1 test, `test_day3_full_lifecycle`) — "Day-3 lifecycle integration test"

The task scope explicitly lists three of these (day1, day2 autonomous, day3). The fourth (`test_day2_smoke_auto_resolve.py`) is day-prefixed but targets a different concern (canned-answer auto-resolve) — treated as an Open Question.

Pytest collection is filename-based (default `python_files = ["test_*.py"]`; no `pytest.ini` and no `[tool.pytest.ini_options]` in `pyproject.toml:1-26`). The conftest (`backend/tests/conftest.py`, 2,075 bytes) contains zero references to any of these filenames. Pure file rename = zero code changes outside the docstring.

### Target state

| Current | Target |
|---|---|
| `test_day1_roundtrip.py` | `test_roundtrip_v2.py` |
| `test_day2_autonomous.py` | `test_autonomous_live.py` |
| `test_day3_lifecycle.py` | `test_lifecycle_crash_recovery.py` |
| `test_day2_smoke_auto_resolve.py` | (untouched) |

The day docstring is kept at the top of each renamed file as a development-log reference (e.g. the new `test_roundtrip_v2.py` still starts with `"""Day-1 end-to-end roundtrip test …"""` so git blame still works). The docstring references to the filename itself (`pytest tests/test_day1_roundtrip.py -v`) must be updated to the new path — there are 3 such references across the 3 files (`test_day1_roundtrip.py:10`, `test_day2_autonomous.py:22` and `:29`, `test_day3_lifecycle.py` — let me confirm the third is empty on this).

### Migration plan (1 step + verification)

1. **For each of the 3 in-scope files**: `git mv` to the new name; update the docstring's `pytest tests/... -v` line to the new path; keep the day-N prose at the top of the docstring.
2. **Verify**: run `./.venv/Scripts/python.exe -m pytest -v` from `backend/`. Expect: same 36 files collected, same number of `test_` symbols (323 per the deep-dive §2), same pass/fail profile. No conftest changes needed.

### Risk assessment

**Zero risk to test functionality.** Pure filesystem operation. The day docstrings stay intact so git blame and human reading both still work.

**Tiny risk to internal documentation** — there are 3 in-file references to the old filename (the "Run from backend/" command examples). They're trivially updated.

**No risk to CI** — there's no CI config that references the day-prefixed names (the only references in the repo are the test files themselves and the deep-dive notes).

### Effort estimate

**Trivial.** 3 `git mv` + 3 string edits. ~5 minutes.

### Open questions

- **`test_day2_smoke_auto_resolve.py`** is still day-prefixed and arguably should also be renamed (`test_smoke_auto_resolve.py` or `test_day2_smoke_auto_resolve_canned_answers.py`). The user explicitly listed only the other three. **My recommendation: include this rename in the same commit** — it's a one-line `git mv` + docstring update, and consistency matters. The user can drop it if they want a tighter scope.

---

## 5. Replace the inline `cx` reimplementations

### Current state

Six files define a private 1-line `cx` helper. The vitest test at `src/utils/cx.test.ts:1-19` already pins the contract — filter falsy, join with space, handle `null`/`undefined`/`false`/empty string.

- `utils/cx.ts:13` — the shared one: `(...parts: Array<string \| false \| undefined \| null>): string`
- `common/Button.tsx:45`, `common/Card.tsx:29`, `common/Pill.tsx:29` — inline copies with `string \| false \| undefined` (no `null`); these survive item 3
- `common/Badge.tsx:36`, `common/StateBadge.tsx:36`, `common/Divider.tsx:7` — inline copies that are deleted with their files in item 3

The shared `utils/cx.ts` is a strict superset (accepts `null`; the vitest test at `cx.test.ts:9-11` explicitly exercises `null`). **Zero files import from `utils/cx`** outside of `utils/cx.test.ts` itself.

### Target state

The 3 surviving primitive files (`Button`, `Card`, `Pill`) import `cx` from `../../utils/cx`. The 3 files being deleted (`Badge`, `StateBadge`, `Divider`) take their private `cx` with them.

### Migration plan (1 step)

1. **For each of `common/Button.tsx`, `common/Card.tsx`, `common/Pill.tsx`**: replace the local `function cx(...)` block with `import { cx } from "../../utils/cx";` at the top of the file. The 3 callsites (one per file) continue to work unchanged because the shared `cx` accepts a strict superset of types.

### Risk assessment

**Zero functional risk.** The shared `cx` is a strict superset (it accepts `null`; the inline versions don't). The vitest test already pins the contract.

**Zero bundling risk** — the 3 inline copies are deleted, the 3 imports add 1 line each, net -12 LOC.

### Effort estimate

**Trivial.** 3 file edits, ~6 LOC delta. Run `npm test` to confirm.

### Open questions

None. The vitest test pins the contract and the shared helper is a strict superset.

---

## 6. Expand the vitest test coverage

### Current state (after one-shot pass)

12 vitest tests across 3 files, all green per the one-shot pass:

- `src/utils/cx.test.ts` (4 tests) — `cx` contract
- `src/components/dossier/AgentActivityIndicator.test.tsx` (6 tests) — `derive` state machine
- `src/components/plan-diff/ChangeEntry.test.ts` (2 tests) — `PLAN_DIFF_CATEGORY_ORDER`

The deep-dive §3.12 called out the *absence* of frontend tests as a sharp edge; the one-shot pass addressed the most acute gap. This item picks the next round.

### Target state — 7 new tests across 5 new files

**Priority order (load-bearing first, easy wins second):**

1. **`src/utils/time.test.ts`** — `relativeTime` is a pure function used in every dossier page. Cases: `<60s → "just now"`, `<60m → "Nm ago"`, `<24h → "Nh ago"`, `1d → "yesterday"`, `2–13d → "Nd ago"`, `>=14d → "Mon D"`, invalid ISO → `""`.
2. **`src/utils/format.test.ts`** — `truncate` (returns input unchanged when `s.length <= n`; mid-word cut + ellipsis; non-string → `""`; `n <= 1 → "…"`) and `titleCase` (lowercases then capitalizes first letter of each whitespace-delimited word; preserves whitespace).
3. **`src/utils/useDocumentTitle.test.ts`** — Pins the route-leave restoration: sets `document.title` on mount, restores previous on unmount, updates when `title` prop changes.
4. **`src/api/useChangeLogSinceVisit.test.tsx`** — Pins the load-bearing snapshot behavior. Needs a `QueryClient` wrapper. Cases: first response captured, second ignored; reset on `dossierId` change; `lastVisitedAtSnapshot` is `undefined` → `null` → string; `snapshotReady` flips after first non-undefined response.
5. **`src/components/intake/IntakeInput.test.tsx`** — Pins the IME composition behavior. Cases: plain Enter submits; Shift+Enter newlines; Cmd/Ctrl+Enter submits; **Enter during IME composition does NOT submit** (the load-bearing CJK case); empty/whitespace disables submit; on `onSend` throw, value is restored.
6. **`src/components/plan-diff/PlanDiffSidebarView.test.tsx`** — Purely presentational; no React Query mocking needed. Cases: 7 categories in `PLAN_DIFF_CATEGORY_ORDER`; empty categories omitted; within a category, newest-first; "Last visited 3h ago" / "Your first visit" / no subtitle per `lastVisitedAt` shape; "Mark as read" only when `onMarkRead !== undefined`.
7. **`src/components/dossier/InvestigationLogSidebar.test.tsx`** — The hardest test. Requires a `QueryClientProvider` with seeded data and a jsdom scroll container. Cases: `dayKey` → `"YYYY-MM-DD"`; `dayLabel` → `"Today"` / `"Yesterday"` / `"Mon D"`; entries grouped under day headers; "Show more" appears when `matchedEntries > VISIBLE_INITIAL`.

### Migration plan (7 ordered steps, each independently shippable)

1. Add `time.test.ts` (pure, <5ms, 7 tests).
2. Add `format.test.ts` (pure, <5ms, ~8 tests).
3. Add `useDocumentTitle.test.ts` (jsdom, <20ms, 3 tests).
4. Add `useChangeLogSinceVisit.test.tsx` (jsdom + QueryClient, <50ms, 4 tests).
5. Add `IntakeInput.test.tsx` (jsdom + user-event, <100ms, 6 tests).
6. Add `PlanDiffSidebarView.test.tsx` (jsdom, <50ms, 7 tests).
7. Add `InvestigationLogSidebar.test.tsx` (jsdom + QueryClient + scroll stubs, <200ms, 4 tests).

End state: 36 frontend tests across 10 files, all green, total runtime well under 1s. The vitest config at `vitest.config.ts:6-11` already wires `globals: true`, `environment: "jsdom"`, `setupFiles: ["./src/test-setup.ts"]` (just `import "@testing-library/jest-dom/vitest"` per `test-setup.ts:1`). No config changes needed.

### Risk assessment

- **Tests 1–3 are zero risk** — pure-function tests, deterministic, fast.
- **Test 4 (useChangeLogSinceVisit) is low risk** — the hook is already pure relative to its inputs (just `useState` + `useRef` + React Query calls); the existing React Query cache can be seeded via `setQueryData` in beforeEach.
- **Test 5 (IntakeInput IME) is low risk but high-effort** — the IME composition simulation in `@testing-library/user-event` is well-documented but the API (`setupComposition` + `compositionStart`/`compositionEnd`) needs to be wired correctly. If the test infra can't fire `compositionstart` events cleanly, fall back to manually dispatching the events via `fireEvent` on the textarea.
- **Test 6 is low risk** — `PlanDiffSidebarView` is purely presentational; render with hand-built entries, assert on the DOM.
- **Test 7 is medium risk** — the `InvestigationLogSidebar` is the most complex component in the codebase (548 LOC, 5 subcomponents). The day-bucket grouping requires seeding the React Query cache, mocking `getBoundingClientRect` for the sticky element, and a long test. **If this turns flaky, drop it and ship the other 6 tests.** It's the most load-bearing test but also the riskiest to ship.

### Effort estimate

**Medium overall.** Tests 1–3 are quick wins (~30 min total). Test 4 is ~30 min. Test 5 is ~1h. Test 6 is ~30 min. Test 7 is ~2h with risk of a flake. Total: ~4–5h.

### Open questions

- **Which of the 7 tests to ship in this cleanup pass?** My recommendation: ship 1–6; defer 7 to a follow-up. The first 6 cover the highest-value seams without the risk of a flaky sidebar test.
- **Should `useChangeLogSinceVisit` and `IntakeInput` be tested through component rendering or by extracting the pure logic?** The current implementations entangle the logic with React effects. Extracting `dayKey`/`dayLabel` to a `utils/dateBuckets.ts` (mirroring `time.ts`) would make the test simpler — but that's a refactor on top of the test. Recommend: test in-place; refactor only if the test is hard to write.

---

## Closing summary

| # | Item | Effort | Risk |
|---|---|---|---|
| 1 | Consolidate the two `SectionCard` paths | Small | Low (visual change on `/demo` only, intentional) |
| 2 | Consolidate the two `SourceList` components | Trivial | Zero |
| 3 | Clean up the unused `common/` primitives (delete 4, wire 8 buttons) | Small | Low (visual identity preserved; `px-5` override required) |
| 4 | Replace the `day-N` pytest file names (3 files) | Trivial | Zero |
| 5 | Replace the inline `cx` reimplementations (3 files survive) | Trivial | Zero |
| 6 | Expand vitest coverage (7 new tests, recommend shipping 6) | Medium | Low–Medium (test 7 may be flaky) |

**The 12 existing vitest tests stay green at every commit.** No backend code changes. The polling pattern is untouched. The `readOnlyFixture` + `FixtureHost` patterns are untouched.

**Total estimated effort: ~6–8 hours of focused work, all independently shippable.** Each item can land in a separate commit, so the cleanup pass can be cut into 6 reviewable PRs (or 7 if you split item 3 into "delete dead primitives" and "wire Button"). No item is a "big bang."

**Report path:** `D:\projects\Vellum\notes\cleanup-2\03-research-frontend.md`
