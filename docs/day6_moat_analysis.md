# Day 6 moat analysis

Author: Day-6 MOAT review agent
Date: 2026-04-22
Scope: honest take on whether Vellum has a defensible moat, graded against what
the code and the live `dos_83702bf49194` run actually show.

---

## 1. What is Vellum actually doing for the user?

Reduced to one concrete thing: Vellum takes a poorly-framed consequential
question, refuses to answer it on its own terms, spawns a small set of scoped
sub-investigations against public sources, and produces a structured case file
— six sections, two usable artifacts (a cease-and-desist letter and a 30-day
checklist), an explicit list of paths considered and killed, a debrief, and a
plan-diff of what changed since the user was last here. The dossier persists
across sessions and is editable by the agent between user visits.

On the live credit-card-debt dossier, the 10-turn run literally opened the
first section with "The question is almost certainly the wrong question" and
concluded that the friend owes $0, not some negotiated percentage. The output
is a ~3000-word document plus a letter the user can put in an envelope and
mail for $15. A ChatGPT conversation with a well-written prompt could reach a
similar conclusion; what it could not reach easily is the structured artifact,
the sub-investigation audit trail, the considered-and-rejected log, the state
transitions (`provisional` vs `confident` on each claim), and the "come back
tomorrow and see what changed" surface. The delta is partly the output shape
and partly the state model under it.

That is the honest user-visible value. It is real but narrower than the pitch
suggests.

---

## 2. The plausible MOATs — ranked

### a. Durable investigation unit (the dossier as state model) — **PARTIAL**

**Claim.** The dossier is a typed, append-only, sub-investigation-aware,
plan-diff-aware structured object that outlives any single agent turn or
user session. Sections carry `confident | provisional | blocked`; the
investigation_log has 20 entries on the demo dossier; `mark_considered_and_rejected`
is a first-class surface; `change_log` resets per user visit. A chat session
list is not this.

**Attack.** The state model is ~500 Pydantic lines (`models.py`) and a schema
a competent engineer could re-derive in a week after seeing the UI. There is
nothing algorithmically hard in "sections have states and a change log." The
discipline — that the agent writes *only* through typed tool calls and prose
evaporates — is enforced by a prompt and the shape of the tool surface, both
of which are copyable. The moat is not the data model itself; it is the
commitment to keep the product around the data model under pressure to add a
chat surface, which every user will eventually ask for. That commitment is
cultural, not technical.

The sub-investigation pattern is more novel — a depth-1 spawn with its own
tool surface (`sub_prompt.py` explicitly strips `update_investigation_plan`,
`update_debrief`, and recursive spawning) — but "fan out a scoped specialist
and absorb its return" is something every agent framework is converging on
by Q2 2026. Two years from now this will be table stakes.

Grade: **PARTIAL**. The state *model* is not defensible. The *stance* of
refusing a chat surface is defensible-ish but non-technical.

### b. Premise pushback as product default — **PARTIAL**

**Claim.** The agent's first move is to audit the frame, enumerate competing
framings (`frame_differential`), and refuse to answer while a load-bearing
premise is unvalidated. Observed: section 10.0 of the live dossier is titled
"The question is almost certainly the wrong question," and the debrief opens
with "Pushed back on the premise and investigated whether the friend owes
this debt at all before answering 'what opening percentage.'" This is the
thesis of the product, concretely realized.

**Attack.** `prompt.py` is 235 lines of instruction. Anyone with a Claude
API key can copy-paste the frame-audit section into their own system prompt
tonight. What the prompt *alone* cannot copy is the surrounding architecture
that rewards pushback: `flag_needs_input` as a first-class block, `mark_ruled_out`
as a first-class block, the gating rule "no recommendation while a load-bearing
prerequisite is unvalidated," the plan-approval decision point, the section-
state downgrade mechanism. These together make pushback *structurally
cheaper for the agent than just answering*. Copying the prompt without
copying the tool shape gets you a chat that sometimes pushes back; copying
both gets you Vellum.

But "both" is still maybe two weeks of engineering for a competent team. The
prompt is copyable in an afternoon; the tool surface is copyable in a week or
two. The only thing that is *not* copyable is the willingness to ship a
product whose main behavior is to disappoint the user by refusing their
question. Most product teams will not choose that.

Grade: **PARTIAL — the stance is harder to copy than the code**. This is
the closest thing to a real moat, and even it is thin.

### c. Structured-tool-only writes — **NOT REALLY**

**Claim.** The agent mutates state exclusively through typed tool calls;
there is no raw prose surface to the user. This produces a rigorously
structured case file instead of a chat transcript.

**Attack.** Every agent framework with function calling does this. The
Pydantic schemas in `tools/handlers.py` (857 lines) are specific to Vellum's
shapes but "define Pydantic types for your tool args" is a weekend project.
Structured tool outputs are a commodity. The fact that Vellum *exclusively*
uses them and bans prose is the stance from (b), not a separable moat.

Grade: **NOT REALLY**. Good engineering; not a moat.

### d. Plan approval gate — **NOT REALLY**

**Claim.** User approves or redirects a plan before the agent burns cycles.
Structured decision point, not a chat turn.

**Attack.** A decision-point surface with a resolution endpoint. Claude
Projects, ChatGPT Custom GPTs, and any "review my plan before I run" agent
can do this. The novelty here is that it is typed and reified in the data
model rather than being a conversational check-in, which is marginal. The
live dossier has three decision points (one plan-approval, two stuck-
detection) and they worked; the mechanism is a sidebar plus a POST endpoint.

Grade: **NOT REALLY**. Sensible design; nothing proprietary.

### e. Evidence-of-work display — **NOT REALLY**

**Claim.** The dossier logs 20 investigation_log entries, ~15-20 sources
consulted, three sub-investigations, two artifacts, five next-actions, two
ruled-out paths — all rendered legibly in the UI. Work is visible.

**Attack.** Logging + a sidebar. `InvestigationLogSidebar.tsx` is a React
component. The value is in the UX polish (warm serif, quiet, document-
forward rendering), not in the underlying data. Anyone who watched a demo
could ship the same surface in a sprint. It matters for user trust; it does
not keep a competitor out.

Grade: **NOT REALLY**. UX investment; not durable.

### f. The taste — **REAL but narrow and non-technical**

**Claim.** The warm serif, paper-like, printed-case-file aesthetic and the
deliberate quiet of the product feels different from every other agent
product on the market. The stance — "a destination you walk to, not a
stream you subscribe to" — conflicts with default product instincts.

**Attack.** Taste is copyable in the narrow sense (steal the palette, the
font stack, the margins) but uncopyable in the systemic sense: a company
whose incentive structure rewards engagement, retention pings, and "look
what the agent is doing" progress indicators cannot convincingly ship a
product whose core UX choice is to *not notify the user*. Most VC-backed
agent products will default to engagement surfaces because their metrics
demand it. Vellum's aesthetic is the crystallization of a product-strategy
choice that is structurally hard for well-funded competitors to make.

But: taste moats are narrow. They hold in a specific demographic (builders,
operators, lawyers, researchers — people who read) and evaporate for anyone
who wants a dashboard.

Grade: **REAL but narrow**. Holds against most competitors precisely
because they cannot afford to ship something this quiet. Does not hold
against a deliberately-boutique competitor who studied the product.

### g. The investigation method / library of patterns — **NOT YET**

**Claim.** If Vellum accumulates investigation templates for domains (debt
renegotiation, medical decisions, real estate, immigration, contract
review), each new dossier gets faster and better than the last. Network
effect on the investigation side.

**Attack.** The code has zero pattern reuse right now. Every dossier
starts blank. There is no template library, no cross-dossier memory, no
"this is a debt-negotiation case, here's the scaffold" pathway. The
product is one-dossier-at-a-time with no learning loop. This is a
*potential* moat, not a current one. See section 4.

Grade: **NOT YET**. Option value exists; current value is zero.

### h. Long-horizon agent orchestration (runtime, stuck detection, resume) — **PARTIAL for six months**

**Claim.** `runtime.py` (359), `sub_runtime.py` (600), `orchestrator.py`
(400), `stuck.py` (676) — that is a ~2000-line agent runtime with sub-
spawning, streaming, stuck detection (token budgets + repeated-tool-call
detection), work-session resume, lifecycle reconciliation of orphaned
sessions. The day-5 diagnosis and the subsequent fixes are evidence that
the runtime has had real problems wrung out of it.

**Attack.** Every serious agent product will have this by end of 2026.
Anthropic will ship higher-level primitives; LangGraph and the various
other frameworks will converge on similar patterns. The stuck-detection is
clever (it surfaces a decision_point rather than hard-capping), but
"surface a decision when the agent loops" is a pattern anyone can steal
after reading about it. A six-month head-start is real. A durable moat is
not.

Grade: **PARTIAL**. Engineering capital, time-limited.

### i. (added) The specific failure modes already diagnosed — **REAL but tiny**

Vellum's day-5 diagnosis and day-5-post-streaming notes catalogue specific
things that break when a runtime like this is run for real: silent no-ops
on resume, orphan work-sessions, done-callback log loss, sub-investigations
stuck in `running` (still visible in the live dossier — all three subs
show `state=running, return_summary=null`). Each bug you have fixed is
one a competitor will rediscover on their own. That is a weeks-to-months
lead, not a moat, but it is worth naming: the product that has already
been wrung out against real failures is meaningfully ahead of one that
has not.

Grade: **REAL but tiny in duration** — three to six months of runtime
maturity, no more.

---

## 3. The honest answer to "did we find the MOAT?"

**No. Not the way "moat" is usually meant.**

What Vellum has is a *stance* — a set of coherent product choices that
most competitors will not make, because those choices lose to engagement-
optimized products in A/B tests and lose to chat-first products in
onboarding metrics. The stance is: refuse premises, write only through
typed tool calls, stay quiet, make the dossier the product rather than
the chat, present ruled-out paths alongside conclusions, surface a
decision-point rather than burn cycles. That stance, expressed through
the code, is genuinely unusual. But "unusual" and "defensible" are not
the same word, and the builder should not confuse them.

If a well-funded competitor — say, Anthropic's Claude Projects team, or
a team inside a law-firm tech vendor, or a deep-pocketed agent startup —
studied `dos_83702bf49194` for an afternoon, they could ship a credible
clone in six to eight weeks. The Pydantic schema is a week. The prompt
is an afternoon. The sub-investigation pattern is maybe two weeks. The
UI polish is a sprint. The runtime fixes you have already shipped would
bite them once and then they would be caught up.

The *only* thing that would slow them down is the willingness to ship a
product whose headline behavior is refusing to answer the user's stated
question. Most product teams inside bigger companies will not sign up to
disappoint users on purpose. That is a real but fragile protection.

So the honest grade: **Vellum has a differentiated stance, a coherent
design, and about six months of engineering capital baked in. It does
not have a moat. The question is whether a moat can be *built* on top
of what it already is.**

---

## 4. If the moat is thin or missing — what would create one?

Pick from the list. The three most credible, in order:

### Best: Investigation templates library + cross-dossier memory

A curated, slowly-grown library of investigation patterns — "debt-
renegotiation after a death," "offer-letter negotiation," "pediatric
second-opinion sherpa," "immigration-timeline delta," "contract
termination under clause X." Each template encodes the frame-audit
questions, the sub-investigation scaffold, the canonical ruled-out
paths, the artifact shapes. New dossiers in a domain start from the
template and get better with each dossier that runs against it —
the template learns from its ruled-out paths, its needs_input
patterns, its common user-frame-errors.

This is the one place where Vellum can plausibly develop a compounding
advantage. Once you have fifty debt-renegotiation dossiers, your
debt-renegotiation template is better than any competitor can bootstrap
from scratch. And the investigation patterns are *specific* — they
live at the intersection of law, product, and the real-world "what
do users actually ask about this" — so they are hard to synthesize
without running real dossiers.

Investment: 3 months to get the template data model and the first
3-5 templates; then a steady curation pipeline. The compounding
starts when you have ~10 templates and ~200 dossiers per template.
Real moat: 12-18 months of real usage, not a build sprint.

### Second: A brand that signals seriousness for high-stakes decisions

The Planned Parenthood of agent products — the one you go to when
something actually matters. This is a marketing + positioning moat,
not a technical one, and it compounds slowly, but it compounds. A
product that refuses to answer bad questions acquires a specific
reputation: "you go there when you cannot afford to be wrong." That
reputation is worth something, specifically against the generic-agent
competitors who will always have more features and cheaper pricing.

Investment: 12-24 months of careful use-case curation, case studies,
and (most importantly) *not* compromising the product to chase
broader-market users. The hardest part is resisting every VC who
tells you to make it friendlier.

### Third: Domain-tuned sub-agents with proprietary source priors

The sub-investigation agent in `sub_prompt.py` is generic today. A
version trained against (or at least prompt-conditioned on) a specific
domain's source hierarchy — "here are the 40 sources that matter for
consumer-debt questions and here is their relative authority" —
produces meaningfully better sub-investigations than the same agent
doing a cold web_search. This is not training data in the ML sense;
it is curated source priors + evaluation criteria per domain, baked
into the sub-agent prompt and possibly into the retrieval layer.

Investment: ~2 months per domain for a serious version, done with a
domain expert. Real moat: requires the templates library (best #1)
to amortize.

The other candidates from the brief — proprietary data partnerships,
integrations, automated evidence capture — are useful but not moat-
level. Partnerships can be copied by a better-funded competitor;
integrations add value but also surface area; evidence capture is a
feature, not a moat.

---

## 5. What to do next given this honest assessment

The moat is thin today, and the options are:

1. **Double down on one high-value vertical** — pick debt renegotiation
   (the one demo that already exists) or pick medical-decision sherpa
   (higher-stakes, higher-willingness-to-pay, lower regulatory drag
   than legal), and go deep on templates, source priors, and artifacts
   for that vertical. The moat grows from depth, not breadth.

2. **Keep Vellum as a narrow personal tool** — Ian + a small beta of
   friends who have real consequential questions. Let the moat emerge
   from use: after 100 real dossiers, the patterns start to show up,
   and those patterns are what get extracted into the templates library.
   This is the slow path but it is the path most consistent with what
   Vellum already *is*.

3. **Extract the core primitives into a different product** — the
   frame-audit pattern, the sub-investigation spawning, the structured-
   write-only agent, the considered-and-rejected surface. Sell those as
   a framework or a feature-kit to other agent teams. This is the
   "fail gracefully" option and should be held in reserve.

4. **Sell it as a feature to an adjacent platform** — a law firm's
   knowledge platform, a financial-advisor client-prep tool, a
   healthcare-navigation service. Vellum-as-a-feature inside someone
   else's workflow is a plausible outcome.

**Recommendation: option 1, aimed at option 2 in the near term.**

Pick debt renegotiation specifically. It is the demo, the code already
has the first template implicitly encoded (the live dossier is
essentially "how to investigate a collector-harassment-of-survivor
case"), and the user population — people with unexpected debt after a
death, people negotiating settlements, people dealing with garnishment
threats — is large, high-emotion, and poorly served by either a
chatbot or a $400/hour consumer-debt attorney. Go deep: three
templates in six months, 50 dossiers, a curated source-priors list,
a small beta of 20 real users. Do *not* pivot to "Vellum for
everything" yet. The horizontal positioning in the pitch is fine for
the eventual V2; the V1 needs one vertical to produce a real moat
signal.

Keep the narrow-personal-tool posture for the first six months
(this is option 2 as an input, not an exit). A moat cannot be built
by pitching; it can only be built by running real dossiers and
curating the patterns. The pitch catches up later.

---

## 6. Signal vs noise in the 6-day build

### Signal — durable, hard to replicate, worth keeping

- **The prompt.** `prompt.py` is the product's actual thesis expressed
  as instructions. The frame-audit contract, the voice rules ("never
  use 'let me...'"), the canonical example about credit-card debt,
  the tag vocabulary for `append_reasoning` — this is load-bearing
  and reflects real thinking. A competitor who does not write an
  equivalent prompt does not have Vellum.
- **The tool surface shape.** Not the code — the *shape*. The
  choice to make `mark_ruled_out`, `flag_needs_input`, and
  `flag_decision_point` first-class tools rather than prose
  conventions. This forces the agent into structured behavior at
  the API boundary, not just at the prompt boundary. Copyable but
  not obvious.
- **The sub-investigation pattern with a stripped tool surface.**
  Main has plan + debrief + spawn; sub has only scope + sources +
  section + artifact + one-way exit. The asymmetry is the insight,
  not the spawning.
- **Stuck detection that surfaces a decision rather than capping.**
  The repeated-tool-call detection plus the "ask the user what to
  do" surface is a specific design choice most agent frameworks
  will not make by default.
- **The aesthetic commitment.** Not the palette — the commitment.
  Quiet, document-like, no notifications, no streaming progress
  indicator. This is the hardest thing to defend as the product
  scales and will be the first thing everyone tells you to change.

### Noise — polish anyone would eventually add

- The specific Pydantic schema shapes (copyable in a week).
- The React component tree (`SectionsList`, `DecisionPointItem`,
  `ConsideredRejectedList` — these are straightforward).
- The `PlanDiffSidebar`. Nice; anyone building a long-horizon agent
  product will ship one.
- The intake conversational chat (commodity).
- The specific runtime fixes (streaming migration, orphan session
  cleanup, done-callback logging). All of these are things a
  competitor will rediscover in their first month of real use.
- The substance bar (≥3 subs, ≥20 sources, ≥1 artifact) as a
  forcing function. Useful internally, not a moat.
- The warm serif palette. The stance behind it is signal; the
  palette itself is copyable in an afternoon.

The 80-commit build has produced maybe 20% signal and 80% polish/
plumbing, which is a normal ratio for a six-day sprint. The signal
is concentrated in the prompt, the tool-surface shape, and the
aesthetic commitment. Those three things are what should be
protected under pressure. Everything else is table stakes that
every competitor will eventually reach.

---

## Summary

- **Moat grade: thin.** What Vellum has is a differentiated stance,
  a coherent design, and about six months of engineering capital.
  Not a moat in the "competitor-proof" sense.
- **Closest-to-real moat today:** the premise-pushback stance,
  because it is the product choice most competitors will not make —
  not because the code is hard to copy.
- **Best path to an actual moat:** investigation templates library
  for a specific vertical (recommendation: debt renegotiation),
  built out of real dossiers over 12-18 months.
- **Biggest self-deception risk:** confusing "novel design" with
  "defensible product." The code is novel. Defensibility requires
  either depth in a vertical (templates + source priors + domain
  expertise) or a cultivated reputation for high-stakes seriousness
  that a VC-funded competitor cannot credibly replicate. Neither
  exists yet.
