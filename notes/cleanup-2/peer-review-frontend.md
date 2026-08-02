# Peer review — cleanup-2 frontend + test work

**Scope:** `aad2193` (SectionCard collapse + Button wiring + 14 new vitest tests), `30172da` (H-21 coercion logging), `cdf7049` (H-20 last_signal_kind), `77d962d` (storage 7→3 merge + 3 contract tests), `e830acb` (day-N rename), `6257643` (_STUCK_EXEMPT_TOOLS + 2 contract tests).

**Verdict:** Ship-blocking on one high-severity issue; six other items worth a follow-up commit. The refactor direction is right; the work is mostly good; the verification was sloppy.

**Quick verification before reading:** `cd frontend && npm test` → 26 passed (5 files). `cd frontend && npm run build` → **FAILS** (2 TS errors, see Issue 1). `cd backend && pytest -q` → 385 passed, 2 skipped.

---

## Issue 1 — **HIGH** — Build is broken on the cleanup-2 commit

**File:** `frontend/src/utils/time.test.ts:8, 11`

**Description:** The new test file uses `beforeEach` and `afterEach` without importing them. The `tsconfig.json` has no `types: ["vitest/globals"]` entry, so TypeScript doesn't see the vitest globals. `npm test` passes (vitest loads them at runtime), but `npm run build` runs `tsc && vite build` and `tsc` fails with:

```
src/utils/time.test.ts(8,3): error TS2304: Cannot find name 'beforeEach'.
src/utils/time.test.ts(11,3): error TS2304: Cannot find name 'afterEach'.
```

The commit message for `aad2193` says "All 26 vitest tests + npm run build green." That claim is false — the build was never green after this commit landed. CI would fail; a fresh `git clone && npm install && npm run build` would fail.

The other 4 test files (`cx.test.ts`, `AgentActivityIndicator.test.tsx`, `ChangeEntry.test.ts`, `format.test.ts`) all happen to only use `describe`/`it`/`expect`, which they explicitly import, so they don't trip the same trap. `time.test.ts` is the only one that uses lifecycle hooks.

**Suggested fix (smallest delta):** Add `beforeEach, afterEach` to the existing `vitest` import on line 1:

```ts
import { describe, it, expect, beforeEach, afterEach } from "vitest";
```

A more durable fix is to add `"types": ["vitest/globals"]` to `frontend/tsconfig.json` so the project can stop importing `describe`/`it`/`expect` from every file, but that's a wider change.

---

## Issue 2 — **MEDIUM** — test_storage_imports.py is stale; H-20 functions are not pinned

**File:** `backend/tests/test_storage_imports.py:23-87` vs `backend/vellum/storage/__init__.py:145-146`

**Description:** The H-20 commit (`cdf7049`) added two new functions to the storage public surface:

- `set_dossier_last_signal_kind` (line 145 of `__init__.py`)
- `get_dossier_last_signal_kind` (line 146 of `__init__.py`)

The `test_all_documented_storage_names_importable` test's `expected` set was not updated to include them. I confirmed this with `grep`: neither string appears anywhere in `test_storage_imports.py`. The test still passes — but only because the assertion runs the wrong direction: `missing = expected - set(dir(storage))`. It catches names that *disappear* from storage, not names that *get added*. A future cleanup could silently drop the H-20 functions and the test wouldn't notice.

This is the same blind spot the test design admits in its own docstring (lines 14-15: "the assertion that follows catches missing entries, not extra ones"). For a contract test that's supposed to pin the public surface, the H-20 addition is exactly the case where the test should have grown.

**Suggested fix:** Add the two new names to the `expected` set, ideally in a "Wake" block that already exists in the test:

```python
# Wake (now in dossier_lifecycle.py)
"set_dossier_wake_at", ..., "get_dossier_error_state",
# H-20: last stuck signal kind
"set_dossier_last_signal_kind",
"get_dossier_last_signal_kind",
```

If the project owner also wants stronger contract enforcement (catch names that *shouldn't* be in `__all__`), invert one of the three tests to assert `__all__ == expected`. That's a design choice, not a bug.

---

## Issue 3 — **MEDIUM** — test_stuck.py docstring references a test that doesn't exist

**File:** `backend/tests/test_stuck.py:549`

**Description:** The H-20 test `test_last_signal_kind_visible_after_assign_tier_and_emit` has a docstring that says:

> The earlier `test_last_signal_kind_persisted_on_loop_signal` test exercises the loop path; this one covers section_budget so we know all signal kinds trigger the write.

`grep` confirms no test named `test_last_signal_kind_persisted_on_loop_signal` exists in the file. The H-20 commit only added three tests:

1. `test_last_signal_kind_visible_after_assign_tier_and_emit` (section_budget path)
2. `test_last_signal_kind_null_for_clean_dossier` (null state)
3. `test_last_signal_kind_visible_in_dossier_pydantic` (Pydantic surface)

So the **loop** and **session_budget** paths through `_assign_tier_and_emit` are not actually exercised at the test layer. The docstring claims a test exists that doesn't, and the H-20 commit message claims "end-to-end through _assign_tier_and_emit" but only one path (section_budget) is covered.

This is a coverage gap masked by a stale docstring. If `_assign_tier_and_emit` regresses on the loop or session_budget paths (e.g., a refactor that only updates `_emit_investigation_log` but not the last-signal-kind write), no test fails.

**Suggested fix:** Either (a) add `test_last_signal_kind_persisted_on_loop_signal` and `test_last_signal_kind_persisted_on_session_budget_signal` to back the docstring's claim, or (b) rewrite the docstring at line 549 to say "this test covers section_budget; the loop and session_budget paths share the same write code in `_assign_tier_and_emit` and are not separately exercised."

Option (a) is better — three extra tests, ~30 LOC total, and they would actually pin the contract.

---

## Issue 4 — **LOW** — time.test.ts monkey-patches Date.now instead of using a `now` parameter

**File:** `frontend/src/utils/time.test.ts:8-13`

**Description:** The test installs `beforeEach`/`afterEach` hooks that overwrite `Date.now` and restore the original. This works at runtime, but it's the only test file in the repo that does this, and it's strictly more fragile than the cleaner pattern already used by `AgentActivityIndicator.test.tsx`. That test passes `NOW` as a parameter to the pure `derive()` function (line 15: `derive(true, PAST, FUTURE, true, "scheduled", NOW)`).

`relativeTime` in `utils/time.ts:24-44` is also a pure function — it just calls `Date.now()` internally. A 3-line refactor makes it testable without the global mutation:

```ts
export function relativeTime(iso: string, now: number = Date.now()): string {
  // ... uses `now` instead of Date.now()
}
```

The 7 tests stay the same; the `beforeEach`/`afterEach` and the `origNow` capture go away; the build is fixed as a side effect (see Issue 1).

**Suggested fix:** Optional. If the project owner wants to keep the test close to runtime semantics, the `beforeEach` fix from Issue 1 is enough. If they want a cleaner test seam, refactor `relativeTime` to take a `now` parameter.

---

## Issue 5 — **LOW** — format.test.ts test description slightly misleading

**File:** `frontend/src/utils/format.test.ts:22-25`

**Description:** The case `expect(truncate("hello world", 6)).toBe("hello…")` is described as "truncates mid-word and appends ellipsis." But `"hello world"` cut at position 6 yields `hello…` — the cut is at a *word boundary*, not mid-word. A reader who comes to this test trying to understand the contract will form a wrong mental model.

The actual mid-word cut (slice(0, n-1) with no trim) is best shown with a single long word, e.g. `expect(truncate("supercalifragilistic", 8)).toBe("supercal…")`.

The test still passes and pins the right behavior, but the description is wrong.

**Suggested fix:** Either rename the test to "truncates at or near a word boundary" or change the input to a single word. Trivial one-line change.

---

## Issue 6 — **LOW** — Button `inline-flex` change may shift text alignment subtly inside flex containers

**File:** `frontend/src/components/common/Button.tsx:31` (base class)

**Description:** Before the swap, every hand-rolled primary button was a plain `<button>` with `bg-accent text-paper font-sans text-sm rounded px-4 py-2 hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed`. The new `<Button>` adds `inline-flex items-center justify-center` to the base, plus `transition-colors`. 

For the **6 sites** with matching styling (DemoPage, IntakeInput, NeedsInputItem, IntakePage Start intake, IntakePage Retry, ErrorBoundary), the visible diff is `inline-flex items-center justify-center transition-colors`. The `transition-colors` is a pure improvement. The `inline-flex items-center justify-center` makes the button a flex container — vertical centering of single-line button text is unchanged visually (text is short enough that `py-2` still wins), but if the button text ever wraps to two lines (e.g. a future "Yes, approve and continue" CTA) the new flex layout will be the only thing keeping the text centered.

The 2 **PlanApprovalBlock** sites (lines 275-282, 313-319) preserve the `px-5` override. ✓

The 1 **DossierListPage:29** Link is correctly left alone (it's a `<Link>`, not a `<button>`). ✓

Disabled-state, focus rings, and aria semantics are all inherited from the native `<button>` via the spread on `...rest`. The `Button` type defaults to `type="button"` (line 56) which prevents accidental form submission; all 7 sites explicitly pass `type="submit"` or `type="button"`, so this default never kicks in but it's a nice safety net. No regression here.

I do not see a behavioral regression in the current 7 sites. The note is for the next person who adds a button with long text inside a flex container — they'll need to verify the alignment still looks right.

**Suggested fix:** None required for this PR. Optional: add a 1-line note to the Button JSDoc (after line 18) warning that the button is `inline-flex` and to be careful when nesting inside flex containers with `align-items` other than `stretch`.

---

## Issue 7 — **LOW** — SectionCard consolidation visual change is by design but worth confirming

**File:** `frontend/src/pages/DemoPage.tsx:4, 150`

**Description:** The `DemoPage` now imports `SectionList` from `../components/dossier/SectionList` instead of `../components/sections/SectionsList`. The dossier version of `SectionCard` (`components/dossier/SectionCard.tsx`) is materially different from the deleted sections version: type-treatments (e.g., `border-l-2 border-accent` for `recommendation`), scoped `.prose` with h1/h2 downranked, collapse-to-preview at >600 chars, dependency links, italic overline change-notes.

For the three sections in `MOCK_DOSSIER_FULL` (all `type: "finding"`, content 800-1100 chars):

- They will hit the `> 600` branch → collapsed preview by default, with a "Show full" button. The old sections version rendered full always.
- They get the `pl-5 border-l border-rule` wrapper from the `finding` treatment, plus a state pip + a mono type label in the overline.
- One section has a `web` source, so `SourceList` renders below the body.
- One has a `change_note`, so the italic overline text appears.

The research notes (`03-research-frontend.md:50-56`) explicitly call this the intended outcome: "The dossier version is clearly the canonical, Day-4 renderer." The visual change is the goal of this PR. I verified by reading both renderers end-to-end; no load-bearing behavior is lost.

I do not see a regression. The `readOnlyFixture` prop pattern in `DossierPage` is untouched — `FixtureHost.tsx:84` still mounts `<DossierPage readOnlyFixture fixtureId={dossierId} />`, and `DossierPage.tsx:14` already imports `SectionList` from `../components/dossier/SectionList` (it was the canonical importer all along; the import path didn't change for that file). The only change is the `DemoPage` import, which doesn't go through `FixtureHost` at all — `DemoPage` reads `MOCK_DOSSIER_FULL` directly.

**Suggested fix:** None. The change is by design and well-blessed by the research.

---

## Issue 8 — **LOW** — test_no_old_storage_submodule_attribute is the only real safety net for the storage merge

**File:** `backend/tests/test_storage_imports.py:107-122`

**Description:** The storage 7→3 merge (commit `77d962d`) deleted `wake_store.py`, `user_note_store.py`, `next_action_store.py`, `turn_store.py`, `budget_store.py`, `settings_store.py`, `idempotency_store.py`. The contract is: a future refactor that re-introduces one of these names as a submodule of `vellum.storage` should fail this test.

The test asserts via `hasattr(storage, name)`. I verified: as of HEAD, all 7 forbidden names return `False`. ✓

One small note: this test doesn't catch the case where someone adds the old module name to `__all__` *and* re-imports it (the file would have to exist for the `from . import wake_store` to succeed; if it doesn't exist, the import fails at module load, which is itself a build break, so the contract holds). The test is sufficient.

**Suggested fix:** None. The test is well-scoped.

---

## Issue 9 — **LOW** — day-N rename didn't touch one of the four day-prefixed files

**File:** `backend/tests/test_day2_smoke_auto_resolve.py` (left alone)

**Description:** The research notes (`03-research-frontend.md:147-153`) flag four day-prefixed files; the commit renamed three of them. `test_day2_smoke_auto_resolve.py` is left alone because it targets the `--auto-resolve` script feature, not the day-N lifecycle story.

The commit message and the research agree this is intentional. No regression.

**Suggested fix:** None for this commit. If the project owner wants symmetry, the file can be renamed to `test_smoke_auto_resolve.py` in a follow-up; the `git mv` preserves blame. The deep-dive audit and the research notes both already document the exception.

---

## Cross-cutting observations

**The 26 vitest tests genuinely pin load-bearing behavior.** `cx`, `time.relativeTime`, `format.truncate`, `format.titleCase`, `AgentActivityIndicator.derive`, and `ChangeEntry.PLAN_DIFF_CATEGORY_ORDER` are all pure functions where test-as-contract makes sense. The two stuck-whitelist tests (`test_progress_whitelist_covers_all_handlers` and `test_progress_mutation_tools_are_a_strict_subset_of_progress_tools`) are real lint tests that will catch maintenance traps. I verified the 30 HANDLERS keys are all covered by the union of the 6 sets (no uncovered tools). The 3 storage import tests are well-scoped.

**The two storage import tests have a contract soft-spot** (Issue 2) but are otherwise solid. The test for `set_dossier_last_signal_kind` and `get_dossier_last_signal_kind` is implicit — the tests exist, but the contract is *not* pinned via the imports test.

**The backend is solid.** 385 passed, 2 skipped, no warnings beyond an existing `RuntimeWarning: coroutine 'run_sub_investigation' was never awaited` in `test_telemetry.py::test_stats_route_returns_200` (pre-existing, not in cleanup-2 scope).

**The frontend refactor direction is right.** Collapsing the two SectionCard paths, moving SourceList to common/, and wiring 7 buttons to the Button primitive is exactly what the research and design plan called for. The implementation is faithful to the plan. The only material issue is the broken build (Issue 1).

---

## Headline findings

1. **`npm run build` is broken on cleanup-2** — `time.test.ts:8,11` uses `beforeEach`/`afterEach` without importing them. The commit's "build green" claim is false. Fix: add the imports.
2. **`test_storage_imports.py` is stale after H-20** — `set_dossier_last_signal_kind` and `get_dossier_last_signal_kind` are in the storage public surface but not in the test's `expected` set. The test catches deletions, not additions.
3. **`test_stuck.py:549` docstring references a test that doesn't exist** — the H-20 commit claimed "end-to-end through `_assign_tier_and_emit`" but only one of the three signal kinds (section_budget) is actually exercised at the test layer.
4. **`time.test.ts` monkey-patches `Date.now`** — works at runtime but the cleaner pattern (used by `AgentActivityIndicator.test.tsx`) is to inject `now` as a parameter to the pure function.
5. **Everything else checks out** — SectionCard consolidation is the intended visual change, Button wiring is correct, day-N rename is by-design, readOnlyFixture is unaffected, the 26 vitest tests and 25 backend tests in scope all pass at runtime.

---

**Recommended action:** fix Issue 1 in a 1-line patch before pushing `aad2193`. Issues 2-3 are worth folding into the next cleanup pass (Issue 2 takes 4 lines, Issue 3 is either 30 LOC of new tests or a docstring fix). Issues 4-9 are optional polish.
