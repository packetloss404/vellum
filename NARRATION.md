# Vellum demo — 3-minute narration script

**Total target: 2:50–3:00. Speaking rate ~150 wpm = ~430 words.**

Record in one take if you can; the cuts are natural scroll moments so a single continuous screen recording works. If you prefer safety takes, each segment stands alone and can be re-recorded without needing to re-start the whole thing.

---

## 0:00 – 0:20 | `/stress` fixture opens on the dossier page

> Vellum is for decisions that deserve more than a chat window.
>
> This is a case file an agent has been working on over hours. Structured, typed, paused and resumed across real time. I close the laptop, come back, and the dossier has evolved — new sections, revised conclusions, questions it needs me to answer.

*(Start at `http://localhost:5173/stress`. No backend or API key is needed for this fixture.)*

---

## 0:20 – 0:45 | Hero + premise challenge block visible

> The agent doesn't start by answering the question. It starts by auditing what the question is smuggling in.
>
> This block at the top is the premise challenge. It's a typed field the agent produces on its first turn, before any substantive work happens.

*(Click "show reasoning" or expand the premise block if collapsed.)*

---

## 0:45 – 1:15 | Premise challenge expanded — hidden assumptions, safer reframe

> Here's the original question, verbatim. Here are the hidden assumptions it carries. Here's a safer reframe — how the question *should* be posed. And the evidence the investigation has to turn up before a recommendation is responsible.
>
> This is the product's thesis. Pushback on the premise is not a feature. It's the whole point.

*(Scroll down to the working theory block.)*

---

## 1:15 – 1:45 | Working theory + debrief + plan card

> Once the frame is agreed and the plan is approved, the agent commits to a current working theory — a one-sentence belief, a confidence level, why this is what it thinks, and what would change it.
>
> Below that, the plan. Every item here is a linked investigation question with a status. No item stays "planned" forever — they transition to in-progress, completed, or abandoned as the agent's subs actually do the work.

*(Scroll to linked investigation questions / sub-investigations.)*

---

## 1:45 – 2:20 | Sub-investigation cards + sections

> Each sub-investigation runs in its own scoped agent loop with a narrower tool surface. When one completes, it returns a summary and concrete findings that land back here as sections.
>
> Sections carry state — confident, provisional, blocked — so the user can see not just what the agent found, but how sure it is.

*(Scroll back to the top and click onto the right-rail sidebar.)*

---

## 2:20 – 2:45 | Plan-diff sidebar, "Sessions" block expanded

> This right rail is what the user returns to on every visit. "Since your last visit" — plan changes, new findings, questions that got answered.
>
> And per session: what was confirmed, what was ruled out, what's blocked, and how much the session cost. Because every turn is real money.

*(Open /settings briefly.)*

---

## 2:45 – 3:00 | Delivered-state close

> The backend also has soft-signal budgets, sleep-mode, and stuck escalation, but the important product idea is here on the page: the agent didn't just answer. It maintained a durable case file, challenged the premise, separated confirmed from provisional, and delivered a conclusion I can inspect later.
>
> That's Vellum: not another chat box, but a place for long-running, structured investigation.

*(End on the dossier top rail or right rail. Stay on `/stress` for the whole take.)*

---

## Rehearsal notes

- Pause ~1 second at each cut. The transitions read better with breath.
- Don't explain the stack in the video. Summary doc and README cover that.
- If you hit 3:15 on a take, drop the "trust-mode" sentence in the settings beat.
- If you hit 2:30, add one sentence on the "while you were away" model: "the user didn't see this happen — they came back to it."
- Mic check: the word "premise" at 0:25 is the most important word in the whole script. Make sure it lands.

## What the video does NOT need

- A live agent run. The `/stress` route is a no-network fixture.
- API credits. This is screen-recording existing state.
- Voiceover editing. Single take, flat read, no music.
