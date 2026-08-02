# Bug-check — frontend, post-cleanup-2

**Scope:** `frontend/src/**` after the cleanup-2 + peer-review-fixes pass. 26 vitest pass, `npm run build` clean. Read deeply on the polling surface, the plan-diff sidebar, the intake flow, the plan-approval block, and the list page.

**Baseline:** `npm test -- --run` → 26 passed (5 files). `npm run build` → clean.

**Headline:** **0 HIGH, 2 MED, 3 LOW.** The polling, cache-invalidation, and visit-timing code paths I was most worried about are all sound — the visit-before-diff ordering is implemented correctly, the tab-hidden behavior is fine (React Query v5 default), and the mutations invalidate the right keys. The real issues are concentrated in the intake retry path and a couple of stale-UI surfaces. Nothing crashes; one bug is a data-integrity footgun (duplicate messages on retry) and one is a UX landmine (typing overwritten on late send-failure).

---

## Bugs

### B1 — MED — Intake Retry button re-sends a message the server already received

**File:** `frontend/src/pages/IntakePage.tsx:212-239` (the `doSend` and `handleSendRetry` pair), with the matching affordance in `IntakeInput.tsx:71-83`.

**What happens.** The backend contract for `POST /api/intake/{id}/message` is "HTTP 200 even when the intake agent errored mid-turn, with `result.error` set" (see IntakePage.tsx:217-223 and the comment at lines 217-218). The frontend reflects this in two distinct branches:

```ts
// IntakePage.tsx
const result = await sendMessage.mutateAsync({ intakeId: id, content: text });
if (result.error) {
  setSendError(SERVER_ERROR);
  // BUG: lastUserMessageRef.current is NOT cleared.
} else {
  lastUserMessageRef.current = null;
}
```

The agent-error path leaves `lastUserMessageRef.current` populated on purpose — that's what the Retry button reads from. Then the user sees the error + Retry button (IntakePage.tsx:261-269) and clicks Retry. `handleSendRetry` calls `doSend(last)`, which calls `sendMessage.mutateAsync({ intakeId: id, content: last })` again — **the same content the server already accepted and stored in the conversation**.

**Why it's a real bug, not a style issue.**
- The IntakeInput has already optimistically cleared its textarea on the first send (IntakeInput.tsx:77), so the user has no visible "I already sent this" anchor — the only signal is the message appearing in the thread.
- The error copy says "I couldn't reach the server" (IntakePage.tsx:27). If the agent errored (HTTP 200, `result.error` set), the server was reached just fine; the message text is misleading and the Retry affordance is misleading together with it. The user has no way to know their original message is already in the conversation.
- The server is not guaranteed to dedupe by content. If it doesn't, the user has silently sent the same message twice and the agent runs two extra turns on a duplicate.

**Reproduction.**
1. Open `/intake/{id}` (an intake in `gathering` state).
2. Send a message that the agent can't handle (e.g., empty the conversation by spamming a "stuck" pattern, or temporarily point the server at a model that 500s on a turn).
3. Server returns 200 with `result.error` set. UI shows error + Retry. `lastUserMessageRef.current` is still the original text.
4. Click Retry. The same `text` is sent again via `mutateAsync`.

**Suggested fix (smallest delta).** In the agent-error branch, clear `lastUserMessageRef.current` and don't show Retry. The message was delivered; the agent just couldn't process it cleanly. The user can type a new message:

```ts
if (result.error) {
  setSendError(SERVER_ERROR);
  // Don't offer Retry — the message already reached the server.
  lastUserMessageRef.current = null;
}
```

And tighten the error copy to "The agent hit an error on that turn" instead of "I couldn't reach the server", which is technically false when `result.error` is the trigger.

---

### B2 — MED — IntakeInput restores the old text on send failure, clobbering whatever the user has typed since

**File:** `frontend/src/components/intake/IntakeInput.tsx:71-83`.

**What happens.** The submit handler optimistically clears the textarea and re-fills it from the original `text` if the parent throws:

```ts
async function handleSubmit(e?: React.FormEvent) {
  if (e) e.preventDefault();
  if (!canSend) return;
  const text = trimmed;
  setValue("");          // optimistic clear
  try {
    await onSend(text);
  } catch {
    setValue(text);      // restore on failure
  }
}
```

The IntakeInput is agnostic to the parent's send policy. The parent (`IntakePage.doSend`) re-throws when the network call itself failed (`catch` at IntakePage.tsx:226-228). It does NOT re-throw when the agent errored — in that case IntakeInput never sees a throw and just keeps the empty value, which is fine.

The bug is the network-error path. If the user types message A, hits Send, the network call hangs, the user types message B in the meantime, and then the request finally fails (timeout / 500 / network drop), `setValue(text)` overwrites B with A. The user's message B is silently lost.

**Why it's a real bug, not a style issue.**
- The user has no warning that their in-progress text is at risk. The optimistic clear is invisible (the textarea is empty) so they start typing in a place that the next failure can wipe.
- The flow is "primary path": intake is a primary surface, the textarea is the only input channel, and the failure path is reachable on a normal localhost dev session (slow backend during a model call, server restart, network blip).
- "Lost user input" qualifies as data loss in the UI even though the user can retype.

**Reproduction.**
1. Open `/intake/{id}`.
2. Type a long message A.
3. Hit Send. The textarea clears optimistically.
4. Before the response lands, type a fresh message B in the now-empty textarea.
5. Have the backend time out / 500.
6. The textarea reverts to message A. B is gone.

**Suggested fix.** Either don't clear the textarea on submit (let the parent show a "sending…" state, and only clear on confirmed success), or restore the value under a "stashed draft" key that the user's current value is compared against — if they typed something, don't restore.

Smallest patch is to keep the value in place and rely on the parent's pending state for the "Send" button disabled:

```ts
async function handleSubmit(e?: React.FormEvent) {
  if (e) e.preventDefault();
  if (!canSend) return;
  try {
    await onSend(trimmed);
    setValue("");        // clear only on confirmed success
  } catch {
    // leave value in place; the parent's error state is the signal
  }
}
```

(Trade-off: the user could double-send if they don't read the disabled state. Mitigate by also disabling the textarea or making the pending state more obvious — but the lost-input case is the worse failure mode.)

---

### B3 — LOW — OpenApprovalsStrip doesn't apply the plan_approval title-fallback heuristic, drifting from PlanApprovalBlock / DecisionPointBlock

**File:** `frontend/src/components/dossier/OpenApprovalsStrip.tsx:21-22` (and the matching filters in `DossierPage.tsx:174-186` and `PlanApprovalBlock.tsx:54-62` / `DecisionPointBlock.tsx:18-25`).

**What happens.** PlanApprovalBlock and DecisionPointBlock both define a "is this a plan_approval?" matcher that falls back to a title heuristic for dossiers whose decision_points predate the `kind` field:

```ts
// PlanApprovalBlock.tsx:54 / DecisionPointBlock.tsx:18
function matchesPlanApproval(p: DecisionPoint): boolean {
  if (p.kind === "plan_approval") return true;
  if (p.kind === undefined) {
    const t = p.title.toLowerCase();
    return t.includes("approve") || t.includes("plan");
  }
  return false;
}
```

OpenApprovalsStrip doesn't have this:

```ts
// OpenApprovalsStrip.tsx:21-22
const planApproval = openDps.find((dp) => dp.kind === "plan_approval");
const otherDps = openDps.filter((dp) => dp.kind !== "plan_approval");
```

So for a pre-`kind`-field dossier (the docstring at `PlanApprovalBlock.tsx:34-36` explicitly calls out that this is a temporary state during the parallel backend rollout), a plan_approval decision point is correctly rendered by `PlanApprovalBlock` (deliberation) but **missed by the strip at the top of the page**. The strip shows "1 decision to resolve" in the `otherDps` bucket, and the plan_approval also appears (incorrectly) in that bucket — meaning the strip and the block disagree about which decision is which kind of decision.

**Why it's LOW not MED.** The strip is a navigation aid, not a primary surface. The deliberation is still rendered. The user can find the plan approval by scrolling. But the strip lies about what's pending (it counts the plan_approval as a generic decision), so the user can't trust the strip's breakdown.

**Suggested fix.** Promote the `matchesPlanApproval` helper to a shared util and have all three sites import it. Or duplicate the heuristic in OpenApprovalsStrip for the duration of the rollout. One line in each of the two `find/filter` calls.

---

### B4 — LOW — Intake thread "pending" indicator disappears before the new assistant message lands (brief flicker)

**File:** `frontend/src/pages/IntakePage.tsx:243-254` with `frontend/src/components/intake/IntakeThread.tsx:55`.

**What happens.** `awaitingAssistant = sendMessage.isPending` is the only signal the thread uses to render the "VELLUM …" thinking indicator. `useSendIntakeMessage.onSuccess` (hooks.ts:275-283) invalidates the intake query — the thread re-renders with the new messages AFTER the refetch lands, not when the mutation resolves. So between "mutation resolves" and "refetch resolves" there's a window where:

- `sendMessage.isPending` is false → pending indicator is hidden.
- `data.messages` is still the pre-mutation snapshot → the assistant reply isn't shown yet.
- `sendError` is null → no error UI either.

For ~10-50 ms on localhost this is imperceptible. On a slow server (or a model call that took the agent to the wire), the window stretches to seconds and the user sees a thread that has their message at the bottom and no other feedback — looks like a freeze.

**Why it's LOW.** On the demo backend (localhost, fast) it's invisible. On a slow network or under load, it's a UX issue, not a data issue. No data is lost or wrong; the user just doesn't know the system is working.

**Suggested fix.** Either set the cache directly from the mutation result (the pattern `useStartIntake` already uses at hooks.ts:264-265), or gate `pending` on both `sendMessage.isPending || query.isFetching`. The `setQueryData` route is the cleanest because it also avoids a wasted GET round-trip.

---

### B5 — LOW — `useResumeState` polls a 404'ing endpoint every 3s during the rollout window

**File:** `frontend/src/api/hooks.ts:351-362`.

**What happens.** The `useResumeState` hook polls at 3s with `retry: false`. The docstring at hooks.ts:347-349 says the endpoint "is being added by another agent; until it lands, the query will 404 and the caller should treat that as 'unknown'". That part works. What doesn't is the cost: while the endpoint doesn't exist, every dossier page on the site is firing a 404 to `/api/dossiers/{id}/resume-state` every 3 seconds. Open three dossiers in three tabs and you've got a 404/second from a stable user session.

**Why it's LOW.** It's pure noise — no functional impact, no cache state to leak, no UI flicker (the hook returns `data === undefined` cleanly). The fallback is graceful. But it's the kind of thing that makes a developer go "why is the network tab red?" during the rollout, and it can mask a real 404 in the same area of the dev tools.

**Suggested fix.** Gate the polling on observed success. The hook could:
- track first-success in a ref,
- only set `refetchInterval` to 3000 once the first non-error response has been seen,
- keep `refetchInterval: false` (or a much longer cadence like 30s) during the 404 window.

Smallest patch: hoist the `refetchInterval` decision into a `useEffect` that watches `resumeState.isError` and toggles a ref, then pass that ref to `useQuery`. Or use `useState` for the interval and a `useEffect` that bumps it to 3000 on first success.

---

## Things I checked and did NOT find

The list below is for the next reviewer — these are the places I looked hardest and either found nothing or found something already covered by the existing logic.

- **Visit-before-diff ordering is correct.** DossierPage.tsx:106-116 fires the visit mutation only after `changeLogSettled` is true. The `useChangeLogSinceVisit` hook (hooks.ts:77-128) snapshots the first non-undefined response and ignores all subsequent refetches, so the post-visit refetch (which is empty) can't overwrite the pre-visit window. The "since your last visit" sidebar shows what the user came back to. The `lastIdRef` reset (hooks.ts:97-105) correctly handles dossier navigation. ✓

- **Polling pause on tab hidden.** `useAgentStatus` (hooks.ts:137-147) and `useResumeState` (hooks.ts:351-362) both set `refetchInterval: 3000` and rely on React Query v5's default `refetchIntervalInBackground: false`. The poller pauses when the tab/window is hidden, restarts on focus. I didn't set `refetchIntervalInBackground: true` anywhere. ✓

- **Polling dedup.** React Query deduplicates in-flight queries with the same key, so the `useDossier` + `useChangeLog` in `DossierPage` and the second `useDossier` + `useChangeLog` inside `useChangeLogSinceVisit` (PlanDiffSidebar) share cache entries — no duplicate fetches. ✓

- **Dynamic `refetchInterval` on `useDossier` in DossierPage** (DossierPage.tsx:90-94). Recomputes on every render as `running || wake_pending ? 3000 : false`. React Query picks up the new value without a remount. No stale-closure issue — `liveDossierPolling` is a number/false, not a function. ✓

- **AgentActivityIndicator timer cleanup** (AgentActivityIndicator.tsx:136-139). `setInterval` is cleared on unmount, no leak. The `tickNow` re-render is once per second, used only for the elapsed/countdown text in `derive`. The `derive` function itself is pure and pinned by 6 vitest cases. ✓

- **Mutation cache invalidations are complete.** Every mutation in `hooks.ts` invalidates the keys it should. `useResolveDecisionPoint` / `useResolveNeedsInput` / `useAddUserNote` all invalidate dossier + changeLog + resumeState + agentStatus + runningAgents (+ dossiers list for the resolve mutations). `useStartAgent` / `useStopAgent` / `useResumeAgent` mirror the same pattern. `useSendIntakeMessage` invalidates intake + (conditionally) dossiers + (conditionally) the new dossier. ✓

- **No successful mutation can leave the cache stale.** I checked each `onSuccess` against the cache key it writes/refreshes. Every invalidation set covers the surface the user is looking at. The only "stale-by-design" surface is the `useChangeLogSinceVisit` snapshot, which is intentional and documented.

- **`visitedRef` in DossierPage** (DossierPage.tsx:106-116) resets on unmount (it's a `useRef`), so navigating between dossiers correctly fires a fresh visit. The `readOnlyFixture` check correctly skips the visit for `/stress*` routes. ✓

- **PlanApprovalBlock branch coverage.** All four branches (no plan, approved, deliberation, waiting) are handled. The hooks (`useState`, `useResolveDecisionPoint`, `useStartAgent`) are called unconditionally above the early returns — no hooks-order violation. The `point!` non-null assertion at PlanApprovalBlock.tsx:174 is safe because the `if (!point) return` at line 124 narrows the type at runtime. ✓

- **DecisionPointItem mutation handling.** `pendingLabel` and the disabled state correctly mute the unselected options while a choice is in flight. After the mutation settles, both reset cleanly. ✓

- **NeedsInputItem mutation handling.** Optimistic clear on submit, no restore on failure (the textarea is just left populated). Consistent with the design. ✓

- **IntakeInput IME handling.** `isComposing` is checked in the keydown handler (IntakeInput.tsx:87). Enter during composition is passed through, not submitted. ✓

- **IntakeInput focus management.** The `useEffect` at IntakeInput.tsx:65-69 focuses the textarea when `disabled` flips false. Standard pattern, no race. The initial mount focuses once — desired behavior for the chat-like composer. ✓

- **Intake auto-redirect race** (IntakePage.tsx:145-153). The 900ms `setTimeout` is cleared on unmount, on `status` change, and on `dossierId` change via the cleanup. No double-navigation. ✓

- **SectionCard collapse / "Show more" toggle.** `isLong` + `mustExpand` logic at SectionCard.tsx:268-273 is correct. The collapse-back "Show less" only appears when the user manually expanded a long section (not when blocked-forced expansion). ✓

- **InvestigationLogSidebar pagination and at-limit message.** `atLimit = totalEntries >= LOG_LIMIT` is the right signal for "the backend truncated the data" — independent of the user-visible filter state. The "Show more" increments by `VISIBLE_PAGE` and re-uses the already-sorted list (no re-sort). ✓

- **SettingsPage draft sync** (SettingsPage.tsx:200-207). The `useEffect` correctly resets the draft when `entry.value` changes, so a save in another tab doesn't leave the user with a stale-but-dirty draft. The `JsonField` `useEffect` (SettingsPage.tsx:152-154) re-formats the textarea when `draft` changes. ✓

- **DossierListPage `useRunningAgents`** has `retry: false` (hooks.ts:164). A failure there is intentionally silent (the docstring at hooks.ts:161-163 says so) and doesn't break the list. ✓

- **DossierListPage `formatSubhead`** has a dead-code ternary at line 103 (`delivered === 1 ? "delivered" : "delivered"`) — both branches return the same string. Style nit, not a bug. Already noted in peer-review-frontend if you want to fold it in.

- **DossierListPage `useDossierList` doesn't poll.** New dossiers created in another process won't appear until the user navigates away and back. By design — the list page is a quiet shelf, not a live monitor.

- **`useDocumentTitle` cleanup under React 18 strict mode.** The "previous title" capture works correctly across strict-mode double-mount because the unmount-remount cycle captures the same `previous` on the second mount. No flicker in production. ✓

- **DossierHero legacy + rich mode** (DossierHero.tsx:199-216). The branch on `props.dossier` is unambiguous. DemoPage uses the legacy mode, DossierPage uses the rich mode. No overlap. ✓

- **`useChangeLogSinceVisit` id-change reset.** The `lastIdRef` + `useEffect` pattern (hooks.ts:97-105) correctly resets the snapshots when the dossier id changes. The two subsequent effects (107-119) only fire on first non-undefined data, so an id change can't cause the wrong dossier's changeLog to be snapshotted. ✓

- **Header dossier-mode type cast.** The `status` string is cast to `DossierStatus` at Header.tsx:32 and the default branch catches unknown values. The `dossier!` non-null assertion (Header.tsx:65) is safe because the `dossierMode` guard at line 47 narrows the type. ✓

---

**Recommended next pass.** B1 is the only one I'd consider ship-relevant — it's a real user-visible failure mode (silent duplicate) on a primary input path. B2 is a papercut but worth fixing in the same commit because the two-line patch is essentially free. B3, B4, B5 can sit — they're real but LOW and none of them cost a user data.
