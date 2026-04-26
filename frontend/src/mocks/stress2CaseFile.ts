// Day-5 stress fixture #2 — fertility-decision-at-35 dossier.
// A "what does this look like when the agent actually runs over two days
// on a deeply ambivalent life decision" dossier. Same structural shape
// as stressCaseFile.ts: 8 sections, 6 sub-investigations, 4 artifacts,
// 12 considered-and-rejected entries, 6 next actions, 80-100 investigation
// log entries, 3 work sessions, ~25-30 change-log entries.
//
// Used by /stress2 (see App.tsx routing). Not loaded on any production path.
//
// Tone: this is journaling / decision-support, NOT clinical advice. The
// agent is acting as a thoughtful interlocutor on a question that the
// user herself does not yet have a settled answer to. The "premise
// challenge" is doing real work: the question as asked is probably the
// wrong question.

import type {
  Artifact,
  ChangeLogEntry,
  ConsideredAndRejected,
  DossierFull,
  InvestigationLogEntry,
  InvestigationLogEntryType,
  NextAction,
  ReasoningTrailEntry,
  RuledOut,
  Section,
  SubInvestigation,
  WorkSession,
} from "../api/types";

export const STRESS2_DOSSIER_ID = "stress2-case-child35";

const NOW = Date.now();
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

const iso = (ms: number) => new Date(ms).toISOString();

// ---------- sub-investigation ids ----------

const SUB_AMH_ID = "stress2-sub-amh-trajectory";
const SUB_CAREER_ID = "stress2-sub-career-reentry";
const SUB_AMBIV_ID = "stress2-sub-ambivalence-as-signal";
const SUB_PARTNER_ID = "stress2-sub-partner-preferences";
const SUB_FINANCE_ID = "stress2-sub-financial-modeling";
const SUB_FRIENDS_ID = "stress2-sub-peer-comparison";

// ---------- section ids ----------

const SEC_SUMMARY = "stress2-sec-summary";
const SEC_AMBIV = "stress2-sec-ambivalence";
const SEC_FERTILITY = "stress2-sec-fertility";
const SEC_CAREER = "stress2-sec-career";
const SEC_PARTNER = "stress2-sec-partner";
const SEC_THREE_WAY = "stress2-sec-three-way";
const SEC_RULED_AGE = "stress2-sec-ruled-age-pressure";
const SEC_OPEN_GRIEF = "stress2-sec-open-grief";

// ---------- artifact ids ----------

const ART_PARTNER_SCRIPT = "stress2-art-partner-script";
const ART_CLINIC_CHECKLIST = "stress2-art-clinic-checklist";
const ART_JOURNAL_PROMPTS = "stress2-art-journal-prompts";
const ART_FINANCE_SHEET = "stress2-art-finance-sheet";

// ===========================================================================
// Dossier
// ===========================================================================

const DOSSIER = {
  id: STRESS2_DOSSIER_ID,
  title:
    "Fertility decision at 35 — working through ambivalence about whether to try for a child (partner of 7 years, meaningful career)",
  problem_statement:
    "I'm 35. My partner and I have been together seven years, both financially stable, and the question of children has gone from theoretical to load-bearing this year. I have meaningful work I'd have to pause or restructure, and I genuinely do not know whether I want motherhood or whether I just feel I should want it. I'd like to use this dossier to separate the wanting from the pressure before another year passes by default.",
  out_of_scope: [
    "adoption pathways and foster-to-adopt",
    "egg/embryo freezing as a standalone choice (will be touched on, not centered)",
    "logistics of a specific clinic or insurance navigation",
    "the partner's separate clinical workup (he can pursue independently)",
    "religious framing — the user has explicitly bracketed this",
  ],
  dossier_type: "decision_memo" as const,
  status: "active" as const,
  check_in_policy: {
    cadence: "on_demand" as const,
    notes:
      "User wants a slow burn — pause between sessions, resume when she has reflections to share. Do not push her toward a decision. The pace is part of the answer.",
  },
  last_visited_at: iso(NOW - 18 * HOUR),
  created_at: iso(NOW - 2 * DAY),
  updated_at: iso(NOW - 22 * MIN),
  debrief: {
    what_i_did:
      "Spent two sessions trying to honor the question you actually asked rather than the one your phrasing implied. Audited the hidden assumptions in 'should I try at 35' and reframed it as three separable questions: do you want this, what does the medical baseline actually allow, and what does each path cost in identity terms. Pulled the AMH/age-decline literature, the motherhood-penalty career-reentry research, and the psychology literature on pre-decision ambivalence as data versus avoidance. Drafted four artifacts: a structured pre-commitment conversation script for you and your partner, a first-clinic-visit checklist, a one-week journaling prompt sequence, and a financial scenario sheet. Spawned six sub-investigations — three returned with substantive findings, two are still running, one was abandoned (peer comparison — the wrong reference class).",
    what_i_found:
      "Three load-bearing findings. (1) The ambivalence is probably not what you think it is. The psychology literature distinguishes pre-decision ambivalence (a signal that you have not yet integrated the trade-offs) from chronic avoidance ambivalence (a signal that the answer is actually no but the social cost of saying so feels too high). These look identical from the inside. The journaling prompt sequence is designed to surface which one you're in. (2) AMH at 35 is informative but oversold. Population-level fecundity does decline through your 30s, but the per-month-of-trying decline from 35 to 38 is much shallower than the popular '35 is a cliff' framing suggests. Your individual baseline matters far more than your age. (3) Career-reentry data tells a more nuanced story than 'pause your career, lose ground forever': the median earnings hit is real and durable, but it is highly path-dependent on whether you stay attached to your professional network and what you re-enter into. The decision worth making is not 'pause vs. don't pause' — it's 'what would the off-ramp and on-ramp specifically look like, given who you are.'\n\nAlso surfaced: your partner has been answering the wrong question in conversations. He's been answering 'will I support you whatever you decide' when the question you actually need answered is 'what do you want, independent of what you think I want.' The conversation script in Artifacts is built around forcing that distinction.",
    what_you_should_do_next:
      "Three things, in order. (1) Run the one-week journaling prompt sequence. It is designed to be done alone, not with your partner. (2) Have the structured conversation with your partner using the script — set aside two hours, no phones, not at home. (3) Schedule a fertility clinic visit for AMH/FSH/AFC baseline within the next 4-6 weeks. The medical data is useful regardless of which way you decide; not having it is what makes 35 feel like a cliff. Do not try to do these in parallel. The journaling needs to come before the conversation, and the conversation should ideally precede the clinic visit so that you walk in with shared framing.",
    what_i_couldnt_figure_out:
      "Whether your sense that 'I should want this' originates internally or externally. You have described it both ways at different points in our conversations, and I cannot triangulate from the outside which is more accurate. The journaling sequence is designed to give YOU the data on this; I cannot resolve it for you. Also: I do not know what your partner actually wants. You have inferred it; he has not stated it. Until he does, treating his preference as known is probably wrong.",
    last_updated: iso(NOW - 22 * MIN),
  },
  premise_challenge: {
    original_question:
      "Should I try for a child at 35 given my ambivalence?",
    hidden_assumptions: [
      "that wanting children is a stable preference that introspection can reveal cleanly, rather than a thing partly constructed by the act of choosing",
      "that 35 is a meaningful medical cliff for YOUR specific reproductive picture, rather than a population-level statistical artifact that may or may not apply to you",
      "that the right decision is the one that maximizes future happiness, rather than one you can live with under either outcome",
      "that your partnership is the right lens on this — rather than identity, autonomy, work, or grief",
      "that ambivalence is a problem to be resolved before deciding, rather than information about the decision itself",
      "that the choice is binary (try / don't try) rather than three-way (yes, no, or not yet)",
    ],
    why_answering_now_is_risky:
      "A premature 'yes, go for it' under social pressure produces a child you may not have wanted. A premature 'no' under career-protection logic forecloses a path you may grieve at 42. The window where the question can be held open without 35-anxiety forcing a default is shorter than feels comfortable, but it is not closed. The most expensive answer right now is any answer — what's needed first is the data (medical, partner, internal) that lets the answer emerge rather than be forced.",
    safer_reframe:
      "Don't ask whether to try yet. Ask: what is the smallest, time-boxed set of investigations that would convert this from a pressure question into a wanting question? Three weeks of structured journaling, one structured partner conversation, one fertility-clinic baseline visit. Reconvene at the end of that month and see what the question actually looks like. The ambivalence may resolve on its own once it has data to work with, or it may sharpen into a clear answer in either direction. Either is acceptable; staying in unstructured ambivalence is not.",
    required_evidence_before_answering: [
      "clarity on whether the ambivalence is pre-decision (haven't integrated trade-offs) or chronic-avoidance (the answer is no but the social cost is high)",
      "concrete medical baseline — AMH, FSH, antral follicle count, partner's basic fertility workup",
      "honest partner conversation record on what he wants independent of what he thinks you want",
      "career and income delta scenarios for 1-year, 2-year, and 3-year leave structures versus continuous work",
      "an honest accounting of what you would grieve under each path (yes, no, not-yet)",
    ],
    updated_at: iso(NOW - 2 * DAY + 12 * MIN),
  },
  working_theory: {
    recommendation:
      "Don't decide yet. The ambivalence is signal, not noise. Spend the next 3-6 months collecting real data — medical baseline, an honest partner conversation, structured journaling — before letting 35-anxiety force a premature commitment. If at the end of month six the ambivalence remains in roughly the same shape, that itself is an answer.",
    confidence: "medium" as const,
    why:
      "The literature on pre-decision ambivalence consistently shows it diminishes when load-bearing facts get clarified — but only if those facts get clarified. Holding the question in unstructured limbo doesn't reduce ambivalence, it accumulates it. The structured month is the smallest intervention that produces the data the decision needs. If after that month the wanting hasn't emerged, treating its persistent absence as information (rather than as a failure to introspect harder) is the move.",
    what_would_change_it:
      "If your AMH baseline returns notably below age-norm — say, in the lowest decile for 35 — the time pressure becomes real and the structured-month framing collapses; the conversation shifts to whether to bank embryos as a hedge while continuing to think. If the partner conversation reveals he's been quietly wanting a no, that also changes everything: the question stops being 'do you want this' and becomes 'do you want this given that he doesn't.'",
    unresolved_assumptions: [
      "your AMH/FSH baseline is in normal range for 35 (untested — first-visit gap)",
      "your partner is genuinely undecided rather than quietly preferring one outcome (his stated 'I support whatever you decide' has not been pressure-tested)",
      "you have a 3-6 month decision window before the calculus hardens (true on biology, may be false on emotional bandwidth)",
      "the meaningful work you'd pause is reversibly paused — not, e.g., a tenure-clock or partner-track gate that closes",
    ],
    updated_at: iso(NOW - 1 * HOUR),
  },
  investigation_plan: {
    items: [
      {
        id: "stress2-plan-1",
        question:
          "What does the AMH/FSH/AFC baseline picture actually look like at 35, and how steep is the 35-to-38 decline curve compared to popular framing?",
        rationale:
          "Most of the felt urgency around 35 is anchored on a curve that misrepresents what AMH means and how steeply it declines in the typical case. Pinning the actual literature is prerequisite to any framing of urgency.",
        expected_sources: [
          "Human Reproduction Update",
          "Fertility & Sterility",
          "ASRM committee opinions",
          "Anti-Müllerian Hormone in Reproductive Aging (Broer et al.)",
        ],
        as_sub_investigation: true,
        status: "completed" as const,
      },
      {
        id: "stress2-plan-2",
        question:
          "What does the career-reentry literature actually say about the motherhood penalty, and how path-dependent is the recoverable trajectory?",
        rationale:
          "The 'pause and lose ground forever' framing is too coarse. Need the path-dependence — what predicts return-to-baseline vs. permanent earnings decline — so we can tell what the off-ramp would actually look like for her field.",
        expected_sources: [
          "AEA Papers and Proceedings",
          "Journal of Labor Economics (Bertrand, Goldin, Katz)",
          "Stanford GSB working papers on parental leave career trajectories",
        ],
        as_sub_investigation: true,
        status: "completed" as const,
      },
      {
        id: "stress2-plan-3",
        question:
          "Is the user's ambivalence pre-decision (not yet integrated) or chronic-avoidance (the answer is no but social cost is high)? How would she tell the difference?",
        rationale:
          "Most consequential gate. The answer reframes the entire investigation. Need a structured introspection sequence she can run, plus the criteria that distinguish the two from the inside.",
        expected_sources: [
          "van Harreveld et al. (2009) on ambivalence as decision input",
          "Newby-Clark & Ross on attitudinal ambivalence",
          "Schwartz on the psychology of choice",
          "user-paste of journaling outputs",
        ],
        as_sub_investigation: true,
        status: "completed" as const,
      },
      {
        id: "stress2-plan-4",
        question:
          "How can we structure a partner conversation that surfaces what HE wants independent of what he thinks she wants?",
        rationale:
          "Partner has been answering 'will I support you' rather than 'what do I want.' The decision needs his actual preference, not his accommodation. Structured conversation script is the deliverable.",
        expected_sources: [
          "Gottman Institute on life-stage transitions",
          "Esther Perel — Mating in Captivity / unstated preferences in long partnerships",
          "couples-therapy literature on stated vs. revealed preferences",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
      {
        id: "stress2-plan-5",
        question:
          "What would the user grieve, specifically, under each of the three outcomes — yes, no, not-yet? Can we make the grief concrete enough to use as a tiebreaker?",
        rationale:
          "Asymmetric regret is the right frame for irreversible decisions. We don't yet have the user's grief inventory under each path; without it, the recommendation cannot be properly weighted.",
        expected_sources: [
          "user journaling outputs",
          "decision-theory literature on regret minimization (Loomes & Sugden)",
        ],
        as_sub_investigation: false,
        status: "planned" as const,
      },
    ],
    rationale:
      "Plan is sequential, not parallel. The introspection work (item 3) needs to come before the partner conversation (item 4), because she needs her own clarity before she can hold his honestly. The medical baseline (item 1) is parallel-safe — it's information regardless. The grief work (item 5) is the synthesizer at the end. Items 1-3 returned in the first two sessions; 4 is in flight; 5 waits.",
    drafted_at: iso(NOW - 2 * DAY + 25 * MIN),
    approved_at: iso(NOW - 2 * DAY + 50 * MIN),
    revised_at: iso(NOW - 14 * HOUR),
    revision_count: 2,
  },
};

// ===========================================================================
// Sections
// ===========================================================================

const SECTIONS: Section[] = [
  {
    id: SEC_SUMMARY,
    dossier_id: STRESS2_DOSSIER_ID,
    type: "summary",
    title: "Where this stands",
    content:
      "The question you brought is 'should I try for a child at 35 given my ambivalence.' After two days of work, the recommendation is to not answer that question yet — and that is not avoidance. The ambivalence is itself the data, and forcing a decision in its current shape is the most expensive move on the board. Three things need to happen first, in order: a one-week structured journaling sequence (alone), a structured conversation with your partner using the script in Artifacts, and a fertility-clinic baseline visit. Each has a deliverable that converts a pressure question into an information question. At the end of the month, the question may have answered itself. If it hasn't, the persistent absence of clarity is itself an answer. The biology gives you that month; the social pressure is what would have you skip it.",
    state: "confident",
    order: 1,
    change_note:
      "Rewrote the summary after the ambivalence section hardened — the framing pivots away from 'should you try' and toward 'what is the smallest investigation that converts this from a pressure question to a wanting question.'",
    sources: [],
    depends_on: [],
    last_updated: iso(NOW - 1 * HOUR),
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: SEC_AMBIV,
    dossier_id: STRESS2_DOSSIER_ID,
    type: "finding",
    title: "The ambivalence is probably not what you think it is",
    content:
      "Two kinds of ambivalence are usually conflated, and they look identical from the inside. **Pre-decision ambivalence** is what you feel when you haven't yet integrated the trade-offs — the wanting and the not-wanting are both genuine, both load-bearing, and the resolution comes from working through them rather than around them. **Chronic-avoidance ambivalence** looks the same on the surface but the underlying structure is different: the answer is actually relatively clear (often no, though sometimes yes), but admitting it carries a social cost the chooser has decided is too high to pay, so the ambivalence is preserved as a way to never actually have to say the thing.\n\nThe psychology literature on this is messier than I'd like — van Harreveld and colleagues (2009) frame it as the difference between 'felt' and 'objective' ambivalence and find that the felt version is what predicts decision quality, while objective ambivalence is more correlated with avoidance behavior. Newby-Clark and Ross's earlier work on attitudinal ambivalence found that holding both positive and negative cognitions simultaneously is actually a better decision input than holding only one — the ambivalent decider is, on average, more accurate about how they will feel afterward.\n\nThe practical question is: which one are you in? The journaling prompt sequence (Artifacts) is built to surface this. It works by asking the same underlying question through six different framings over six days. If the answers converge — even toward 'I don't know' — you are probably in pre-decision ambivalence and the work is forward. If the answers diverge wildly depending on the framing (especially: more pro-child when the prompt invokes external observers, more no-child when the prompt isolates you alone with the choice) you are probably in chronic-avoidance and the question is no longer 'should I' but 'why is saying no so costly to me.'\n\nA real possibility worth naming: the ambivalence may not resolve at all in a month, and that is itself information. Persistent ambivalence after structured introspection looks much more like 'this is not for me, and the difficulty is in saying so' than like 'I just need more time.' Most people who really want children, when given space and structure, find that the wanting is recoverable from underneath the noise. If yours doesn't surface, take that seriously.",
    state: "provisional",
    order: 2,
    change_note:
      "Kept provisional because the framing depends on the journaling output, which we don't have yet. The pre-decision vs. chronic-avoidance distinction is well-supported in the literature; the application to your specific case is what needs the data.",
    sources: [
      {
        kind: "web",
        url: "https://www.sciencedirect.com/science/article/abs/pii/S0065260108004036",
        title:
          "van Harreveld, van der Pligt & de Liver (2009) — The agony of ambivalence and ways to resolve it",
        snippet:
          "Distinguishes felt versus objective ambivalence and ties felt ambivalence to better post-decision calibration.",
      },
      {
        kind: "web",
        url: "https://psycnet.apa.org/record/2003-99641-008",
        title: "Newby-Clark & Ross — Conceiving the past and the future (1999/2003)",
        snippet:
          "Holding simultaneous positive and negative cognitions correlates with more accurate affective forecasting.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 4 * HOUR),
    created_at: iso(NOW - 38 * HOUR),
  },
  {
    id: SEC_FERTILITY,
    dossier_id: STRESS2_DOSSIER_ID,
    type: "finding",
    title: "Fertility baseline at 35 — where you actually are",
    content:
      "The popular '35 is the cliff' framing is a flattening of a real but more gradual curve. Anti-Müllerian hormone (AMH), produced by granulosa cells in small follicles, is the most informative single marker of ovarian reserve, and its decline through the 30s is real but highly individual. Broer and colleagues (Human Reproduction Update, 2014) characterized the population trajectory: median AMH at 35 is roughly 1.5-2.5 ng/mL, with the 10th percentile near 0.7 and the 90th percentile near 4.5 — meaning a healthy 35-year-old can plausibly sit anywhere across an order-of-magnitude range. Your individual number is far more informative than your age.\n\nThe per-month-of-trying conception probability does decline through the 30s, but more shallowly than the cliff framing suggests. Dunson and colleagues (Fertility & Sterility, 2004) found roughly a 20% per-cycle conception rate at 27-29, falling to about 12-15% at 35-37 and 8-10% at 38-39. That's a decline, not a collapse. The cumulative-probability-after-12-months number for healthy 35-year-olds in their data was around 78%, versus around 86% for 27-29-year-olds. Real difference, not a precipice.\n\nWhat actually matters more than the population baseline is your specific picture: AMH, day-3 FSH, antral follicle count (AFC) on transvaginal ultrasound, and your partner's basic semen analysis. Without these you are reasoning about a generic 35-year-old, who isn't you. With them, the urgency calibration becomes concrete: a baseline AMH at the 50th percentile for your age means the structured-month makes sense; a baseline AMH below the 10th percentile means the calculus changes and embryo-banking-while-thinking becomes a serious option.\n\nNote what this section is NOT: it is not telling you what to do, and it is not advice that you should treat 35 as urgent. It is telling you that the medical data exists, is fairly cheap to obtain (a single clinic visit for the major markers), and would convert your reproductive picture from generic-statistical to specific. The journaling and the partner conversation are the higher-value moves; the clinic visit is what makes the time pressure question answerable rather than felt.",
    state: "confident",
    order: 3,
    change_note:
      "Upgraded from provisional after Broer et al. (2014) population curve and Dunson et al. (2004) per-cycle data both confirmed the same gentler-than-popular gradient. Added the practical 'go get the baseline' framing.",
    sources: [
      {
        kind: "web",
        url: "https://academic.oup.com/humupd/article/20/5/688/623013",
        title:
          "Broer et al. (2014), Human Reproduction Update — Anti-Müllerian Hormone: ovarian reserve testing and its potential clinical implications",
        snippet:
          "Population AMH trajectories by age, with 10th/50th/90th percentile bands; AMH as the most informative single marker of ovarian reserve.",
      },
      {
        kind: "web",
        url: "https://www.fertstert.org/article/S0015-0282(03)03192-1/fulltext",
        title:
          "Dunson, Baird & Colombo (2004), Fertility & Sterility — Increased infertility with age in men and women",
        snippet:
          "Per-cycle and cumulative conception probabilities by age band; the 35-39 decline is real but gradual.",
      },
      {
        kind: "web",
        url: "https://www.asrm.org/practice-guidance/practice-committee-documents/",
        title: "ASRM Practice Committee — Testing and interpreting measures of ovarian reserve",
        snippet:
          "Clinical guidance on which markers to draw (AMH, FSH, AFC) and how to interpret the combination.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 5 * HOUR),
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: SEC_CAREER,
    dossier_id: STRESS2_DOSSIER_ID,
    type: "finding",
    title:
      "Career: the reversibility is worse than you think, but not the way you feared",
    content:
      "The motherhood-penalty literature is one of the more empirically grounded parts of labor economics, and the picture is more nuanced than either the 'pause your career, lose ground forever' framing or the 'you can do it all' framing.\n\nThe headline finding (Bertrand, Goldin & Katz, AEA Papers and Proceedings, 2010, on MBAs from a top program): women's earnings track men's almost perfectly until the first child, at which point a divergence opens that is durable and specifically tied to hours-worked rather than to skill atrophy. The penalty is roughly 30% lower earnings ten years post-first-child, but it is overwhelmingly composed of fewer hours and more career interruption rather than a per-hour wage penalty. Goldin's later work (American Economic Review, 2014) generalized this: in occupations with convex returns to long hours (law, finance, consulting, surgery, certain academic tracks), the penalty is steepest. In occupations with linear returns to hours (pharmacy, certain engineering tracks, software, science), the penalty is much smaller.\n\nThe practical implication for you: the question is not 'pause vs. don't pause' in the abstract — it is whether YOUR specific work has convex or linear returns to hours, and whether the meaningful-ness of the work is recoverable through a part-time or restructured arrangement. If your field has convex returns and a hard tenure-clock or partner-track gate, the off-ramp is more expensive and the on-ramp is harder; you'd want to be eyes-open on that. If your field has linear returns and an established part-time path, the off-ramp is genuinely cheap and the on-ramp can be close to full.\n\nA second finding worth holding: the durability of the penalty is heavily mediated by network attachment during leave. Stanford GSB work (Bertrand et al. follow-up, 2018) found that women who maintained even modest professional contact during a 1-2 year leave (a quarterly lunch, a part-time advisory role, a continued conference attendance) had earnings recovery curves substantially closer to no-leave peers than women who fully detached. The mechanism appears to be opportunity flow rather than skill maintenance.\n\nWhat this means for the present decision: 'the meaningful work I'd have to pause' is not a single binary — it is a set of choices about HOW to pause, and several of those choices are much cheaper than the worst-case framing in your head. A specific scenario sheet (Artifacts) lays out 1-year, 2-year, and 3-year pause options with rough income deltas under different on-ramp assumptions. Run those numbers; the answer to 'is this affordable' is in the differences, not the headline.",
    state: "confident",
    order: 4,
    change_note:
      "Upgraded from provisional once career-reentry sub returned with the Bertrand-Goldin-Katz citations and the Goldin (2014) convex-vs-linear-hours framing. Reframed from 'pause vs. don't' to 'what does pause look like specifically.'",
    sources: [
      {
        kind: "web",
        url: "https://www.aeaweb.org/articles?id=10.1257/app.2.3.228",
        title:
          "Bertrand, Goldin & Katz (2010), AEA Papers and Proceedings — Dynamics of the Gender Gap for Young Professionals",
        snippet:
          "Earnings tracking that diverges at first child, hours-driven rather than wage-driven.",
      },
      {
        kind: "web",
        url: "https://www.aeaweb.org/articles?id=10.1257/aer.104.4.1091",
        title:
          "Goldin (2014), American Economic Review — A Grand Gender Convergence: Its Last Chapter",
        snippet:
          "Convex vs. linear returns to hours as the predictor of motherhood-penalty severity by occupation.",
      },
      {
        kind: "web",
        url: "https://www.gsb.stanford.edu/faculty-research/working-papers",
        title:
          "Stanford GSB working paper series — career-reentry trajectories after parental leave",
        snippet:
          "Network-attachment-during-leave is the strongest predictor of earnings recovery.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 6 * HOUR),
    created_at: iso(NOW - 34 * HOUR),
  },
  {
    id: SEC_PARTNER,
    dossier_id: STRESS2_DOSSIER_ID,
    type: "finding",
    title: "What your partner is and isn't telling you",
    content:
      "You have described your partner's position to me three times, in three slightly different ways, and the variation is the finding. In session one you said he's 'fine either way.' In session two you said he's 'leaning toward yes but really committed to whatever I want.' This morning you said he hasn't actually said. Those three are different positions and you have been collapsing them.\n\nThis is a known pattern in long partnerships, particularly around life-stage transitions. The Gottman Institute's work on these transitions (their long-form research on couples through major decisions, summarized in The Seven Principles for Making Marriage Work) makes the point that the most consequential conversations in long partnerships are the ones where each partner is performing accommodation of the other's perceived preference rather than stating their own. Both people end up answering 'what does my partner want me to want' rather than 'what do I want,' and the actual question never gets asked.\n\nEsther Perel, working from a different tradition, has the same observation: in seven-year-plus partnerships the partners' preferences become so mutually shaped that distinguishing 'what I want' from 'what we have settled into wanting' takes deliberate effort. She frames this as a feature, not a bug — but a feature that requires periodic recalibration around major decisions, and a child decision is the canonical major decision.\n\nThe practical implication: the partner conversation script (Artifacts) is built around forcing the distinction. It opens with a structured prompt that asks each of you to first answer 'what do you want, in a world where you don't know what the other one wants' — and to actually write it down before showing each other. The mechanic is artificial on purpose; without it, the conversation defaults back to mutual accommodation. The script also includes a question I want you to actually ask him, in those words: 'if I told you tomorrow that I had decided no, what would you grieve?' His answer (or his inability to answer) tells you more than any number of 'what do you think we should do' rounds.\n\nOne more thing. You are not trying to extract a hidden preference from him. You are trying to give him space to formulate one — quite possibly for the first time — and then let it sit alongside yours. The goal is not alignment; it's two clear positions you can hold next to each other.",
    state: "provisional",
    order: 5,
    change_note:
      "Provisional pending the actual conversation. The framing is grounded in the Gottman/Perel literature; the application to your partnership rests on what you actually report back from the script.",
    sources: [
      {
        kind: "web",
        url: "https://www.gottman.com/about/research/",
        title: "The Gottman Institute — research on life-stage transitions in long partnerships",
        snippet:
          "Major-decision conversations frequently default to mutual accommodation rather than stated preference.",
      },
      {
        kind: "web",
        url: "https://www.estherperel.com/books",
        title: "Esther Perel — Mating in Captivity (2006) and follow-on writing",
        snippet:
          "In long partnerships, distinguishing 'what I want' from 'what we have settled into wanting' requires deliberate recalibration around major life decisions.",
      },
    ],
    depends_on: [SEC_AMBIV],
    last_updated: iso(NOW - 8 * HOUR),
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: SEC_THREE_WAY,
    dossier_id: STRESS2_DOSSIER_ID,
    type: "recommendation",
    title:
      "The decision isn't 'yes / no' — it's 'yes, no, or not yet', and not-yet is real",
    content:
      "The framing trap in your original question is binarity. Treating 'try for a child' as a yes/no compresses out the most useful option in the space, which is a structured 'not yet' with a defined re-decision point.\n\nThe three-way frame:\n\n- **Yes (now)**: Begin trying within the next 1-3 months. Schedule clinic baseline this month, begin tracking next, begin trying within 8-12 weeks. Career conversation happens in parallel, not as a precondition. The cost of error: a child you may not have wanted, with the consequent reorientation of your life that is difficult to undo.\n- **No**: A genuine no — not 'not yet that resolved into no by default,' but a chosen no that is held with intention. The cost of error: you may grieve at 42 a path you closed at 36. (Worth noting: regret-minimization research, Loomes & Sugden, suggests that anticipated regret of the path NOT taken is the more accurate predictor of post-decision wellbeing than expected utility of the path taken — meaning the 'will I grieve a no' question is more diagnostic than 'will I enjoy a yes.')\n- **Not yet (with a re-decision date)**: Hold the question open for a defined window — 6 months, 12 months, 18 months — during which the structured introspection, partner conversation, and medical baseline are completed. At the re-decision date you choose between yes and no with the data you didn't have at the start. Cost of error: small if the window is short, larger if the window is long and the medical baseline turns out to be borderline.\n\nThe recommended path, based on what we have so far, is **not yet, with a 6-month window**. Six months is long enough to do the introspection, partner, and medical work without rushing; short enough that if the medical baseline returns mid-window with concerning numbers you can re-cut to yes-now without much loss. It is also short enough that 'not yet' does not function as a soft no; it stays an actual decision point.\n\nWhat would shift the recommendation: a low AMH baseline pushes toward yes-sooner with embryo-banking-as-hedge during the introspection window. A journaling output that converges clearly toward 'no and the social cost is what was making it hard to say' pushes toward no-now. A partner conversation revealing a quiet preference on his side meaningfully reframes the question rather than just shifting the answer.",
    state: "confident",
    order: 6,
    change_note:
      "Reframed from binary to three-way after the ambivalence section landed. The 'not yet' option was the missing third leg; making it explicit changed the recommendation from 'don't decide' (which sounded like avoidance) to 'choose not-yet' (which is an active stance).",
    sources: [
      {
        kind: "web",
        url: "https://www.jstor.org/stable/2232669",
        title:
          "Loomes & Sugden (1982), Economic Journal — Regret theory: an alternative theory of rational choice under uncertainty",
        snippet:
          "Anticipated regret of the path not taken predicts post-decision wellbeing more reliably than expected utility of the path taken.",
      },
    ],
    depends_on: [SEC_AMBIV, SEC_FERTILITY, SEC_CAREER],
    last_updated: iso(NOW - 2 * HOUR),
    created_at: iso(NOW - 24 * HOUR),
  },
  {
    id: SEC_RULED_AGE,
    dossier_id: STRESS2_DOSSIER_ID,
    type: "ruled_out",
    title: "Ruled out: deciding based on age pressure alone",
    content:
      "An early frame of the question was 'I'm running out of time, the answer has to be yes.' That framing does not survive contact with either the AMH literature (which shows the 35-to-38 trajectory is gradual, not cliff-shaped) or with the ambivalence literature (which shows that pressure-driven decisions on irreversible choices have the highest regret rates in the affective-forecasting research).\n\nThe inverse framing — 'I have decades, defer indefinitely' — is also ruled out. Biology is real; the curve is real even if it is not a cliff; emotional bandwidth for the decision is not infinite. Indefinite deferral is a soft no that the chooser refuses to claim, and the regret literature treats it harshly.\n\nWhat is NOT ruled out: deciding based on age plus a constellation of other inputs. Age belongs in the calculus; it does not own the calculus. The recommendation is a 6-month structured window precisely because that is short enough to respect biology and long enough to respect the decision.",
    state: "confident",
    order: 7,
    change_note:
      "Ruled out and kept visible so the path is on the record. Both poles of the age framing — 'must decide now because of age' and 'age doesn't matter, defer' — fail the same way.",
    sources: [],
    depends_on: [],
    last_updated: iso(NOW - 26 * HOUR),
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: SEC_OPEN_GRIEF,
    dossier_id: STRESS2_DOSSIER_ID,
    type: "open_question",
    title:
      "Open: what would you specifically grieve under each path?",
    content:
      "We have three candidate outcomes (yes, no, not-yet) and a working recommendation, but we don't yet have the grief inventory under each one — and grief is the most useful data for an irreversible decision.\n\nWhat I'd like from you, after you've done the journaling sequence: a written, specific list of what you would grieve under each of the three paths. Not 'I'd be sad' — the actual content. Under yes: what specifically would you grieve about the work you'd restructure, the autonomy you'd reorient, the partnership shape that would shift? Under no: what specifically would you grieve about the not-having — the version of you that didn't have this experience, the family configuration you won't see, the conversations with friends and family that would land differently? Under not-yet: what would you grieve about a 6-month window of intentional uncertainty?\n\nThe specificity matters. Vague grief is the same shape under any path; specific grief is what differentiates them. If your no-grief is concrete and your yes-grief is vague, the answer is probably yes. If the inverse, the answer is probably no. If both are equally concrete the recommendation tightens around not-yet, with the grief inventory becoming the decision tool at the re-decision date.\n\nThis is the section that is most genuinely blocked on you. The clinical and career sections close on data I can fetch; this one closes on data only you have access to.",
    state: "blocked",
    order: 8,
    change_note: "Blocked pending journaling sequence completion. Don't try to answer abstractly; do the prompts first.",
    sources: [],
    depends_on: [SEC_AMBIV, SEC_THREE_WAY],
    last_updated: iso(NOW - 4 * HOUR),
    created_at: iso(NOW - 12 * HOUR),
  },
];

// ===========================================================================
// Sub-investigations
// ===========================================================================

const SUB_INVESTIGATIONS: SubInvestigation[] = [
  {
    id: SUB_AMH_ID,
    dossier_id: STRESS2_DOSSIER_ID,
    parent_section_id: SEC_FERTILITY,
    plan_item_id: "stress2-plan-1",
    title: "AMH/FSH meaning at 35 — what's the actual trajectory",
    scope:
      "Pin down the actual age-decline curve for AMH and per-cycle conception probability through the 30s, comparing the population literature against the cliff-framing in popular discourse.",
    questions: [
      "What is the median AMH at 35 and what are the 10th and 90th percentile bands?",
      "How steep is the decline from 35 to 38 in the per-cycle conception data?",
      "What does ASRM recommend as the standard ovarian-reserve panel?",
      "Are there 2022-2024 studies that meaningfully revise the older Broer/Dunson numbers?",
    ],
    state: "delivered",
    return_summary:
      "Median AMH at 35 ~1.5-2.5 ng/mL with order-of-magnitude individual range (Broer 2014). Per-cycle conception ~12-15% at 35-37 vs ~20% at 27-29; cumulative-after-12-months ~78% vs ~86% (Dunson 2004). Standard panel: AMH + day-3 FSH + AFC. No 2022-2024 work meaningfully revises the curves; recent work has refined AMH-as-IVF-response-predictor more than AMH-as-spontaneous-fertility-predictor. Bottom line for the dossier: the 35-cliff framing overstates urgency for a typical baseline; the individual number from a clinic visit is far more informative than the age.",
    findings_section_ids: [SEC_FERTILITY],
    findings_artifact_ids: [ART_CLINIC_CHECKLIST],
    started_at: iso(NOW - 40 * HOUR),
    completed_at: iso(NOW - 30 * HOUR),
    why_it_matters:
      "Most of the felt time pressure is anchored on a curve that doesn't quite represent what AMH means. Calibrating the actual urgency is prerequisite to any 'should I' framing.",
    known_facts: [
      "Broer 2014 population AMH curve has median ~1.5-2.5 at 35",
      "Dunson 2004 per-cycle data shows gradual rather than cliff decline",
      "ASRM standard panel includes AMH + FSH + AFC",
    ],
    missing_facts: [
      "user's individual AMH/FSH/AFC values — needs first clinic visit",
      "user's partner's basic semen analysis — independent workup he can pursue",
    ],
    current_finding:
      "Population baseline is gentler than popular cliff framing; individual clinic baseline is the high-value next step.",
    recommended_next_step:
      "Schedule fertility clinic visit within 4-6 weeks for the standard panel.",
    confidence: "high",
  },
  {
    id: SUB_CAREER_ID,
    dossier_id: STRESS2_DOSSIER_ID,
    parent_section_id: SEC_CAREER,
    plan_item_id: "stress2-plan-2",
    title: "Career return patterns after 1-3 year pauses",
    scope:
      "Characterize the motherhood-penalty literature with attention to its path-dependence — what predicts return-to-baseline versus durable earnings decline.",
    questions: [
      "What is the headline motherhood-penalty magnitude in modern data?",
      "Is the penalty wage-based or hours-based?",
      "Which occupations have convex vs. linear returns to hours, and how does that change the penalty?",
      "What predicts earnings recovery during and after leave?",
    ],
    state: "delivered",
    return_summary:
      "Bertrand, Goldin & Katz 2010: ~30% earnings gap ten years post-first-child for top-MBA cohort, hours-driven not wage-driven. Goldin 2014 generalization: convex-returns-to-hours occupations (law, finance, surgery, certain academic tracks) have steepest penalty; linear-returns occupations (pharmacy, software, certain science) have much smaller penalty. Stanford follow-on: network attachment during leave is the strongest single predictor of recovery — a quarterly lunch matters. Practical: question is 'what does the off-ramp look like' not 'pause vs. don't.'",
    findings_section_ids: [SEC_CAREER],
    findings_artifact_ids: [ART_FINANCE_SHEET],
    started_at: iso(NOW - 36 * HOUR),
    completed_at: iso(NOW - 26 * HOUR),
    why_it_matters:
      "The 'pause your career, lose ground forever' framing is too coarse to be useful. Knowing the actual path-dependence converts an abstract dread into a set of concrete choices.",
    known_facts: [
      "Penalty is real and durable but hours-driven not wage-driven",
      "Convex-vs-linear occupational structure dominates the size of the penalty",
      "Network attachment during leave dominates the recovery curve",
    ],
    missing_facts: [
      "what specific structure the user's field has — convex or linear, hard tenure/partner gates or not",
      "whether her current org has a part-time or restructured-hours track, formally or informally",
    ],
    current_finding:
      "The career cost is heavily mediated by HOW the pause is structured, not whether one is taken.",
    recommended_next_step:
      "Run the financial scenario sheet with conservative and aggressive on-ramp assumptions; surface whether the convex/linear question is answered for her field.",
    confidence: "high",
  },
  {
    id: SUB_AMBIV_ID,
    dossier_id: STRESS2_DOSSIER_ID,
    parent_section_id: SEC_AMBIV,
    plan_item_id: "stress2-plan-3",
    title:
      "Ambivalence as pre-decision signal vs. ambivalence as decision-itself",
    scope:
      "Pull the psychology literature on ambivalence as decision input — pre-decision vs. chronic-avoidance — and design a structured introspection sequence the user can run.",
    questions: [
      "What's the empirical distinction between pre-decision and chronic-avoidance ambivalence?",
      "What introspection structures reliably surface which one a chooser is in?",
      "Is ambivalence a better or worse decision input than confidence in either direction?",
      "What does the literature say about persistent ambivalence after structured introspection?",
    ],
    state: "delivered",
    return_summary:
      "van Harreveld et al. (2009) distinguish felt vs. objective ambivalence; felt ambivalence predicts better post-decision calibration, objective is more correlated with avoidance. Newby-Clark & Ross find that holding both positive and negative cognitions correlates with more accurate affective forecasting. Designed a six-day prompt sequence that asks the same underlying question through different framings; convergence indicates pre-decision, divergence indicates chronic-avoidance. Persistent ambivalence after structured work is itself information and should be treated as such — most often it tracks 'this is not for me' more than 'I need more time.'",
    findings_section_ids: [SEC_AMBIV],
    findings_artifact_ids: [ART_JOURNAL_PROMPTS],
    started_at: iso(NOW - 32 * HOUR),
    completed_at: iso(NOW - 14 * HOUR),
    why_it_matters:
      "Most consequential single finding. If she's in chronic-avoidance, the entire question reframes. The journaling sequence is what tells her which.",
    known_facts: [
      "Felt ambivalence predicts post-decision calibration (van Harreveld 2009)",
      "Simultaneous-cognitions approach correlates with accurate affective forecasting (Newby-Clark)",
      "Persistent ambivalence after structured introspection is itself diagnostic",
    ],
    missing_facts: [
      "the user's actual journaling outputs",
      "whether her ambivalence has a stable shape across framings or shifts with the framing",
    ],
    current_finding:
      "The distinction is empirically real and the journaling sequence is the operationalization.",
    recommended_next_step:
      "Run the one-week journaling prompt sequence (Artifacts), alone, before the partner conversation.",
    confidence: "high",
  },
  {
    id: SUB_PARTNER_ID,
    dossier_id: STRESS2_DOSSIER_ID,
    parent_section_id: SEC_PARTNER,
    plan_item_id: "stress2-plan-4",
    title: "Partner stated vs. revealed preferences in long partnerships",
    scope:
      "Characterize the literature on stated-vs-revealed preference in long partnerships at major life-stage decisions, and design a conversation script that surfaces preferences that mutual accommodation has hidden.",
    questions: [
      "What does Gottman find about life-stage transition conversations?",
      "What does Perel observe about long-partnership preference-shaping?",
      "What conversation structures reliably surface a hidden preference?",
      "How should the user interpret 'I support whatever you decide' as a position?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [SEC_PARTNER],
    findings_artifact_ids: [ART_PARTNER_SCRIPT],
    started_at: iso(NOW - 14 * HOUR),
    completed_at: null,
    why_it_matters:
      "The decision needs his actual preference, not his accommodation. Without the script, the conversation defaults to mutual deferral.",
    known_facts: [
      "Gottman frames major-decision conversations as defaulting to mutual accommodation",
      "Perel: long partnerships shape preferences mutually; recalibration requires deliberate effort",
      "User has reported the partner's position three different ways across three sessions",
    ],
    missing_facts: [
      "what he actually says when given structured space",
      "his own grief inventory under each path",
      "whether his position has the same stable-vs-shifting shape across framings as hers",
    ],
    current_finding:
      "Conversation script drafted; needs actual conversation to validate and revise.",
    recommended_next_step:
      "Run the conversation using the script. Two hours, no phones, not at home. Take notes after, not during.",
    confidence: "medium",
  },
  {
    id: SUB_FINANCE_ID,
    dossier_id: STRESS2_DOSSIER_ID,
    parent_section_id: SEC_CAREER,
    plan_item_id: null,
    title: "Financial modeling: leave-year impact on lifetime earnings",
    scope:
      "Build a scenario sheet that runs 1-year, 2-year, and 3-year pause structures against continuous-work baseline, with conservative and aggressive on-ramp assumptions.",
    questions: [
      "What's the rough lifetime-earnings delta for 1/2/3-year leaves under standard assumptions?",
      "How does the convex-vs-linear-hours occupational structure shift those numbers?",
      "What's the network-attachment premium during leave?",
      "How sensitive are the numbers to the user's specific salary and field?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [],
    findings_artifact_ids: [ART_FINANCE_SHEET],
    started_at: iso(NOW - 8 * HOUR),
    completed_at: null,
    why_it_matters:
      "The career section landed conceptually; the user wants to see the numbers in her own scale to know whether 'affordable' is the right word for any given path.",
    known_facts: [
      "Hours-based penalty structure transfers cleanly to a multiplicative model",
      "Network-attachment premium is roughly 25-40% of the gap on Stanford follow-on data",
    ],
    missing_facts: [
      "user's actual current salary and growth rate",
      "her field's specific convexity",
      "household budget tolerance for various leave structures",
    ],
    current_finding:
      "Generic scenario sheet drafted; user-specific numbers need her input to populate.",
    recommended_next_step:
      "User to populate the salary and growth-rate cells; we re-run the scenarios with her numbers next session.",
    confidence: "low",
  },
  {
    id: SUB_FRIENDS_ID,
    dossier_id: STRESS2_DOSSIER_ID,
    parent_section_id: null,
    plan_item_id: null,
    title: "Comparing to friends' decisions — abandoned, wrong reference class",
    scope:
      "Originally: characterize what the user's friends-cohort has decided and how that constrains the social-pressure component of her ambivalence.",
    questions: [
      "What's the distribution of 'tried at 35' vs. 'didn't' in her cohort?",
      "How is she reading her friends' choices as data?",
      "Are there specific friends whose decisions she is over-weighting?",
    ],
    state: "abandoned",
    return_summary:
      "Abandoned: this is the wrong reference class. Friends' decisions are noisy projections of their own constraints (partner, finances, health, biology) that don't transfer cleanly to hers. The work to disentangle which friend's situation is informative would itself be more emotional labor than information value. The user agreed in session 2 that the comparison was load-bearing in a way she didn't endorse on reflection. Closed the sub and added a considered-and-rejected entry.",
    findings_section_ids: [],
    findings_artifact_ids: [],
    started_at: iso(NOW - 30 * HOUR),
    completed_at: iso(NOW - 20 * HOUR),
    why_it_matters:
      "Was a candidate signal source; turned out to be a candidate noise source instead. Worth recording the reasoning so we don't re-approach this from a different angle by accident.",
    known_facts: [
      "Friend-cohort decisions are heavily individual-circumstance-bound",
      "Her own social-pressure ambivalence does not principally come from friends — it comes from a more diffuse cultural source",
    ],
    missing_facts: [],
    current_finding:
      "Wrong reference class. Closed.",
    recommended_next_step:
      "If social-pressure ambivalence resurfaces in journaling, route it back through the ambivalence sub, not the peer-comparison frame.",
    confidence: "high",
  },
];

// ===========================================================================
// Artifacts
// ===========================================================================

const PARTNER_SCRIPT_CONTENT = `# Partner conversation script — structured pre-commitment talk

## Setup

- Two hours, on a weekend, no phones, not at home. A long walk works; a quiet cafe works; the kitchen table does not.
- Bring this script printed out. Both of you should have read it ahead of time.
- The structure is artificial on purpose. The structure is what makes the conversation different from the dozens of unstructured versions you have already had.

---

## Stage 1 — Independent positions (20 minutes)

Before either of you speaks, each writes down, separately, on paper:

1. What I want, in a world where I don't know what my partner wants. (One paragraph, specific.)
2. What I think my partner wants. (One paragraph.)
3. What I would grieve if we ended up not having a child. (Specific. "I would be sad" is not specific enough.)
4. What I would grieve if we ended up having a child. (Same standard.)

Write before reading the next section. Do not look at each other's paper yet.

---

## Stage 2 — Read aloud, no response (15 minutes)

One of you reads all four answers aloud. The other listens. No interruptions, no clarifying questions, no facial responses.

Switch. The other reads all four answers aloud. The first listens.

After both readings: a five-minute silence. Actually silent. This is harder than it sounds and is part of the work.

---

## Stage 3 — One question each (30 minutes)

Each of you, in turn, asks the other ONE question, and only one. Not the question you most want to ask — the question whose answer would actually change something.

Suggested questions if you don't have one of your own:

- "If I told you tomorrow that I had decided no, what would you grieve?"
- "If I told you tomorrow that I had decided yes, what would you grieve?"
- "What is the part of your answer that surprised you when you wrote it?"
- "What would you want to be true that isn't, that would make this easier?"

The asked partner takes their time answering. Aim for two-to-three minutes of answer, not thirty seconds.

---

## Stage 4 — What's now visible (45 minutes)

This is the open conversation, but with a constraint: every contribution must reference something that was on one of your papers, or in the answer to the one question. New material is held for next time.

If you find yourselves slipping back into mutual accommodation ("whatever you want is fine"), one of you names it and you go back to one of the papers.

End the conversation when the agreed two hours are up, even if you feel unfinished. The point is not to resolve; the point is to have two clearer positions you can hold next to each other.

---

## After

Each of you, separately, in the next 24 hours, writes one paragraph on what changed. Don't share it yet. Bring it to the next conversation in two weeks.

If nothing changed, write that. "Nothing changed" after a structured conversation like this is itself diagnostic.`;

const CLINIC_CHECKLIST_CONTENT = `# First fertility-clinic visit — what to ask for

## Before the visit

- [ ] Bring a list of your last 3-6 cycle dates if available
- [ ] Bring any relevant family history (early menopause in mother/sisters, fertility issues in close relatives)
- [ ] Note: this is NOT a "trying to conceive" appointment. You are gathering baseline data. Be explicit about that with the scheduler.

## The standard ovarian-reserve panel — ask for all four

- [ ] **AMH (anti-Müllerian hormone)** — the single most informative number. Drawable any day of cycle.
- [ ] **Day-3 FSH** — drawn on cycle day 3 specifically. May require a return visit.
- [ ] **Day-3 estradiol** — drawn at the same time as FSH, contextualizes the FSH number.
- [ ] **Antral follicle count (AFC)** — transvaginal ultrasound, ideally early-cycle.

## Partner workup (he can do this independently)

- [ ] Basic semen analysis — count, motility, morphology. One sample, one lab visit.

## Questions worth asking the clinician

- [ ] "Where do my numbers sit on the population curve for my age?"
- [ ] "What would change your assessment from 'baseline range' to 'elevated concern'?"
- [ ] "If I were to want to bank embryos as a hedge while continuing to think, what's the timeline and rough cost?"
- [ ] "If we tried for 6 months without success, at what point would you recommend further workup?"

## What you do NOT need at this visit

- A treatment plan. You are not in treatment. You are baseline-gathering.
- A timeline pressure pitch. If the clinic gives you one, that is information about the clinic, not about your numbers.
- A decision. The visit's only deliverable is data.

## After the visit

Sit with the numbers for at least a week before letting them shift the dossier framing. A baseline at the 50th percentile reads differently after a week than after an hour.`;

const JOURNAL_PROMPTS_CONTENT = `# One-week journaling sequence — six prompts in seven days

## Rules

- Do this alone. Not with your partner. The point is to surface YOUR position, not the joint one.
- Handwrite if you can. The slowness matters.
- Twenty minutes per prompt, minimum. No editing.
- Date each entry. Don't reread until day seven.

---

## Day 1 — The room

Imagine you are in a room with a person who knows you completely and who has no stake in your choice. They ask you, simply: do you want a child?

Write your answer. Not the considered answer. The first answer.

---

## Day 2 — At forty

Imagine yourself at 40. You did not have a child. Describe the day you are having. What is the texture of it? What is the part that surprises you?

Now imagine yourself at 40, with a four-year-old. Describe that day. Same prompt.

Which of the two days felt more like writing fiction, and which felt more like remembering?

---

## Day 3 — The unwanted observer

Imagine your mother is reading what you wrote yesterday. Or your closest friend with kids. Or a stranger on the internet who has strong opinions.

Write what you'd cut from yesterday's entry if you knew they would read it. Then write what you'd add.

The cuts and the additions tell you where the social-pressure component lives.

---

## Day 4 — The thing under the thing

What is the answer you are afraid of having? Not afraid of being WRONG about — afraid of having.

Write toward that, slowly. If nothing comes, write "nothing comes" repeatedly until something does.

---

## Day 5 — Costs and the people who pay them

If you choose yes: who pays a cost you haven't fully accounted for? (You. Your partner. Your work. Your future child. Other.) Name the person and the cost.

If you choose no: same question.

Be specific. Vague costs cancel each other out; specific costs differentiate.

---

## Day 6 — The version of you

There is a version of you who exists if you do this, and a version of you who exists if you don't. Both are real and both will exist in some form depending on your choice.

Describe each one in third person. What does she care about? What does she regret? What is she good at? What is she at peace with?

You are not deciding which version is "better." You are seeing them both as possibilities you might miss.

---

## Day 7 — Read all six entries

Read in order, slowly. Mark passages where you wrote something that surprised you when you read it back.

The marked passages are the data. Bring them to the next session.`;

const FINANCE_SHEET_CONTENT = `# Financial scenario sheet — leave structure scenarios

## How to use

Fill in your numbers in the bracketed cells. The sheet runs three pause durations (1, 2, 3 years) against a continuous-work baseline, under conservative and aggressive on-ramp assumptions. The deliverable is the differences between scenarios, not the absolute numbers.

---

## Inputs (fill these in)

- Current annual salary: $[INSERT]
- Annual growth rate at current org, no leave: [INSERT]% (typical: 3-5% cost-of-living, 5-10% promotion track)
- Field convexity: [convex / linear / unsure] (convex: law, finance, surgery, certain academic. Linear: pharmacy, software, science, certain consulting.)
- Network attachment plan during leave: [none / quarterly / ongoing part-time]
- Spouse income (for household-level affordability): $[INSERT]

---

## Scenario A — Continuous work, no leave

Year 0:  $[salary]
Year 5:  $[salary × (1+g)^5]
Year 10: $[salary × (1+g)^10]

This is the baseline. Every other scenario is measured against this.

---

## Scenario B — 1-year pause, aggressive on-ramp

- Year 1: 0 income
- Years 2-10: assume 90-95% of baseline trajectory (network-attached, linear field) or 75-85% (convex field)
- Lifetime delta vs Scenario A: roughly 5-10% (linear) or 15-25% (convex)

---

## Scenario C — 2-year pause, aggressive on-ramp

- Years 1-2: 0 income
- Years 3-10: assume 85-90% of baseline trajectory (linear) or 65-75% (convex)
- Lifetime delta: roughly 12-20% (linear) or 25-35% (convex)

---

## Scenario D — 3-year pause, conservative on-ramp

- Years 1-3: 0 income
- Years 4-10: assume 75-85% of baseline (linear) or 55-65% (convex)
- Lifetime delta: roughly 25-35% (linear) or 35-50% (convex)

---

## What this is and isn't

It IS: a rough quantification to convert "I'd lose ground forever" into specific numbers in your scale.

It is NOT: a recommendation. The numbers are necessary inputs to a values-driven decision; they are not themselves the decision.

The biggest lever in any of these scenarios is the on-ramp assumption, not the pause length. A two-year pause with deliberate network attachment beats a one-year pause with full detachment, in most fields, on most data.

---

## What to do with this

Run the numbers. Look at the differences between scenarios in YOUR salary scale, not in abstract percentages. Ask yourself: which of these is "affordable" — meaning, you'd be willing to bear the difference for the experience? Which is "unaffordable"? The line between those, in YOUR numbers, is one of your decision tools.`;

const ARTIFACTS: Artifact[] = [
  {
    id: ART_PARTNER_SCRIPT,
    dossier_id: STRESS2_DOSSIER_ID,
    kind: "script",
    title: "Partner conversation script — structured pre-commitment talk",
    content: PARTNER_SCRIPT_CONTENT,
    intended_use:
      "Print this. Both of you read it ahead of time. Run the conversation in a single two-hour block, not at home, no phones. The structure is what makes it different from the unstructured versions you've already had.",
    state: "ready",
    kind_note:
      "Built around forcing the stated-vs-accommodation distinction in stage 1. The artificial structure is load-bearing — don't skip stages.",
    supersedes: null,
    last_updated: iso(NOW - 8 * HOUR),
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: ART_CLINIC_CHECKLIST,
    dossier_id: STRESS2_DOSSIER_ID,
    kind: "checklist",
    title: "First fertility-clinic visit — baseline data checklist",
    content: CLINIC_CHECKLIST_CONTENT,
    intended_use:
      "Bring this to your first clinic visit. The visit is for baseline data — not for treatment, not for decisions. Be explicit with the scheduler about that framing.",
    state: "ready",
    kind_note: null,
    supersedes: null,
    last_updated: iso(NOW - 7 * HOUR),
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: ART_JOURNAL_PROMPTS,
    dossier_id: STRESS2_DOSSIER_ID,
    kind: "checklist",
    title: "Six-prompt journaling sequence (one week, alone)",
    content: JOURNAL_PROMPTS_CONTENT,
    intended_use:
      "Run this alone, not with your partner. Twenty minutes per prompt, handwrite if you can. Don't reread until day seven. The marked passages on day seven are the deliverable.",
    state: "ready",
    kind_note:
      "Designed to surface pre-decision vs. chronic-avoidance ambivalence by asking the same underlying question through six different framings. Convergence indicates pre-decision; divergence indicates avoidance.",
    supersedes: null,
    last_updated: iso(NOW - 14 * HOUR),
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: ART_FINANCE_SHEET,
    dossier_id: STRESS2_DOSSIER_ID,
    kind: "comparison",
    title: "Financial scenario sheet — 1-year, 2-year, 3-year pause vs. continuous work",
    content: FINANCE_SHEET_CONTENT,
    intended_use:
      "Populate the bracketed cells with your numbers. The deliverable is the differences between scenarios in your scale, not the absolute numbers in the abstract.",
    state: "draft",
    kind_note:
      "Draft — still parametric. Will move to ready once user populates the salary and growth-rate cells in the next session.",
    supersedes: null,
    last_updated: iso(NOW - 3 * HOUR),
    created_at: iso(NOW - 8 * HOUR),
  },
];

// ===========================================================================
// Considered and rejected (12)
// ===========================================================================

const CONSIDERED_AND_REJECTED: ConsideredAndRejected[] = [
  {
    id: "stress2-cr-1",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Frame this as a pro/con list",
    why_compelling:
      "Easy to construct, immediately tractable, gives the chooser something to point at. Many decision-support frameworks default to it.",
    why_rejected:
      "Pro/con lists work well for decisions where the items are commensurable. Wanting a child versus protecting a career versus preserving autonomy versus partner alignment are not items on the same axis. Forcing them into a pro/con structure creates the illusion of a comparison and obscures the real work, which is figuring out which axis is load-bearing for HER.",
    cost_of_error:
      "Moderate — produces a confident-feeling decision that bypasses the actual question.",
    sources: [],
    created_at: iso(NOW - 44 * HOUR),
  },
  {
    id: "stress2-cr-2",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Recommend 'just go for it, you'll never feel ready'",
    why_compelling:
      "It's the conventional wisdom and, for some people, it's actually right — readiness can be the wrong frame.",
    why_rejected:
      "It collapses 'you'll never feel ready' (sometimes true, useful for lower-stakes decisions) with 'so any felt unreadiness should be ignored' (false, dangerous on irreversible choices). For a chooser whose ambivalence might be chronic-avoidance, this advice produces a child she didn't want.",
    cost_of_error:
      "High — irreversible direction in a case where the framing might be wrong.",
    sources: [],
    created_at: iso(NOW - 42 * HOUR),
  },
  {
    id: "stress2-cr-3",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Recommend 'listen to your gut'",
    why_compelling:
      "Validates her own intuition, deference to felt-sense, lighter touch.",
    why_rejected:
      "The gut is the thing producing the ambivalence — listening to it harder doesn't add information. The point of the dossier is to provide structure that the gut alone is not providing. 'Listen to your gut' is the right advice for a chooser whose gut has a clear answer; it's the wrong advice for one whose gut has produced six months of ambivalence already.",
    cost_of_error:
      "Low to moderate — wastes the structured-investigation opportunity.",
    sources: [],
    created_at: iso(NOW - 40 * HOUR),
  },
  {
    id: "stress2-cr-4",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Build an expected-utility calculation across paths",
    why_compelling:
      "Decision theory has well-developed tools. Could give a quantitative recommendation.",
    why_rejected:
      "Requires the chooser to assign numerical utilities to outcomes whose nature she doesn't yet know — what the experience of motherhood is for her, what the experience of not-having-a-child at 50 is for her. Numbers fabricated under that constraint produce false precision and crowd out the qualitative work that's actually decisive.",
    cost_of_error:
      "Moderate — creates a confident-looking answer from inputs that don't support it.",
    sources: [],
    created_at: iso(NOW - 38 * HOUR),
  },
  {
    id: "stress2-cr-5",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: SUB_AMH_ID,
    path: "Front-load the urgency — start with 'AMH declines fast, decide quickly'",
    why_compelling:
      "Forces engagement, breaks the deferral pattern.",
    why_rejected:
      "It's also wrong on the data — AMH at 35-38 is gradual, not cliff-shaped. And urgency framing on irreversible decisions has the worst regret outcomes in the affective-forecasting literature. 'Quickly' is not a feature here; it's the failure mode.",
    cost_of_error:
      "High — pushes a chooser toward yes-by-pressure rather than yes-by-want.",
    sources: [],
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: "stress2-cr-6",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: SUB_FRIENDS_ID,
    path: "Use her friends-cohort as a reference class for what 35 looks like",
    why_compelling:
      "Concrete, available data. Lets her benchmark against people she knows.",
    why_rejected:
      "Wrong reference class. Each friend's decision is heavily individual-circumstance bound — partner, finances, health, biology — and the noise dominates the signal at the level of n = 4 or 8 friends. The work to disentangle which friend's situation is informative would itself cost more than the information gained. Closed the sub.",
    cost_of_error:
      "Low — but actively misleading if relied on, so worth recording.",
    sources: [],
    created_at: iso(NOW - 32 * HOUR),
  },
  {
    id: "stress2-cr-7",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Recommend therapy as the principal intervention",
    why_compelling:
      "Therapy is well-suited to ambivalence work, especially with a competent therapist.",
    why_rejected:
      "Defer, not reject. Therapy may be the right move and several of the prompts in the journaling sequence are explicitly therapy-borrowed. But framing the dossier as 'go to therapy' would offload the work the user came to the dossier specifically to do. If after the structured month the ambivalence has not resolved or sharpened, therapy is the natural next move and should be raised then.",
    cost_of_error:
      "Low — the journaling sequence captures most of what a few sessions of therapy would surface, at lower cost in time and attention.",
    sources: [],
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: "stress2-cr-8",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Treat embryo-banking as a default hedge regardless of intent",
    why_compelling:
      "Removes the time-pressure component of the decision entirely. If she banks now, the wanting question can be answered at 38 or 40 with no biology penalty.",
    why_rejected:
      "Premature without the AMH baseline. For a chooser at the 50th percentile of ovarian reserve at 35, the cost-benefit of banking is moderate; for one at the 10th percentile, it's strongly favorable; for one at the 90th percentile, it's an expensive intervention with low marginal benefit. The recommendation must wait on the clinic visit. Worth keeping on the table for the re-decision point.",
    cost_of_error:
      "Moderate — banking is real-money and real-medical-procedure expense to recommend in advance of the data that would calibrate it.",
    sources: [],
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: "stress2-cr-9",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: SUB_PARTNER_ID,
    path: "Recommend that her partner come to the next dossier session",
    why_compelling:
      "His position is load-bearing, and a session with both of them in the room would surface his preference faster than the script alone.",
    why_rejected:
      "Premature. She needs her own clarity before she can hold his without it overriding hers — that's the whole point of the journaling-before-conversation ordering. If after the structured month the conversation has not converged the picture, then a joint session is the right escalation. Not now.",
    cost_of_error:
      "Moderate — bringing him in too early collapses her work into the joint frame and risks losing what she'd surface alone.",
    sources: [],
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress2-cr-10",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Run the question through a regret-minimization calculation explicitly",
    why_compelling:
      "Loomes-Sugden regret theory is well-suited to irreversible decisions and the affective-forecasting literature backs it up.",
    why_rejected:
      "Defer, not reject. The framing is in the dossier (under three-way decision and under open-grief) but as a guide for the user's own grief inventory, not as a calculation we do for her. Doing the regret-minimization explicitly without her grief inventory would produce numbers without the inputs they need.",
    cost_of_error:
      "Low — sequencing call.",
    sources: [],
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress2-cr-11",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Open with sympathy and validation rather than premise challenge",
    why_compelling:
      "The user is in real distress. The premise challenge can read as cold.",
    why_rejected:
      "The user explicitly asked for help separating the wanting from the pressure. Sympathy without premise challenge produces warmth and no traction. The premise challenge IS the work she came for; doing it is the deliverable. Sympathy is woven into the tone, not the structure.",
    cost_of_error:
      "Low — but worth being explicit about the choice so the user doesn't read coldness where carefulness was intended.",
    sources: [],
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress2-cr-12",
    dossier_id: STRESS2_DOSSIER_ID,
    sub_investigation_id: SUB_AMBIV_ID,
    path: "Treat the ambivalence as itself the answer ('you don't want this')",
    why_compelling:
      "It's a defensible reading of the literature on chronic-avoidance ambivalence. Some of her phrasing in session 1 leaned this direction.",
    why_rejected:
      "Cannot be confidently asserted without the journaling output. Pre-decision and chronic-avoidance look identical from outside; calling it now risks projecting onto her. The structured journaling is what gives HER the data on which it is, and her conclusion will land differently than a third party's would.",
    cost_of_error:
      "High — telling someone they don't want a child when they actually do is among the worst possible third-party framings.",
    sources: [],
    created_at: iso(NOW - 8 * HOUR),
  },
];

// ===========================================================================
// Next actions (6)
// ===========================================================================

const NEXT_ACTIONS: NextAction[] = [
  {
    id: "stress2-na-1",
    dossier_id: STRESS2_DOSSIER_ID,
    action: "Run the six-prompt journaling sequence (one week, alone, before partner conversation)",
    rationale:
      "The journaling output is the highest-information single thing you'll generate. Everything downstream — the partner conversation framing, the grief inventory, the recommendation — gets sharper once it exists.",
    priority: 1,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress2-na-2",
    dossier_id: STRESS2_DOSSIER_ID,
    action: "Schedule fertility-clinic baseline visit (AMH + day-3 FSH + AFC; partner does semen analysis independently)",
    rationale:
      "Converts your reproductive picture from generic-statistical to specific. Useful regardless of which way the decision lands; not having it is what makes 35 feel like a cliff.",
    priority: 2,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 12 * HOUR),
  },
  {
    id: "stress2-na-3",
    dossier_id: STRESS2_DOSSIER_ID,
    action: "Run the structured partner conversation using the script (after journaling, not before)",
    rationale:
      "He has been answering 'will I support you' rather than 'what do I want.' The script is built to force the distinction. Two hours, no phones, not at home.",
    priority: 3,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 10 * HOUR),
  },
  {
    id: "stress2-na-4",
    dossier_id: STRESS2_DOSSIER_ID,
    action: "Populate the financial scenario sheet with your salary, growth rate, and field-convexity input",
    rationale:
      "The generic version is parametric. Once your numbers are in, the differences between scenarios are concrete in your scale and become a real input to the decision.",
    priority: 4,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 8 * HOUR),
  },
  {
    id: "stress2-na-5",
    dossier_id: STRESS2_DOSSIER_ID,
    action: "Mark a re-decision date six months out and put it on the calendar (literally)",
    rationale:
      "The 'not yet' option works only if it has a defined endpoint. Without the calendar entry, not-yet drifts into soft-no by default.",
    priority: 5,
    completed: true,
    completed_at: iso(NOW - 1 * HOUR),
    created_at: iso(NOW - 4 * HOUR),
  },
  {
    id: "stress2-na-6",
    dossier_id: STRESS2_DOSSIER_ID,
    action: "After the structured month, write the grief inventory under each of the three paths (yes, no, not-yet) and bring it to the next session",
    rationale:
      "This is the section that's most genuinely blocked on you. Concrete grief differentiates the paths in a way no other input does.",
    priority: 6,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 3 * HOUR),
  },
];

// ===========================================================================
// Reasoning trail (3)
// ===========================================================================

const REASONING_TRAIL: ReasoningTrailEntry[] = [
  {
    id: "stress2-rt-1",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-1",
    note:
      "Held off on a direct recommendation in session 1 because the framing of 'should I' was loading the dice. Reframed the early work around premise challenge before any analysis. The user's relief at being asked 'what's actually under the question' was load-bearing — confirmed the reframe was the right move.",
    tags: ["framing", "premise-challenge", "session-1"],
    created_at: iso(NOW - 44 * HOUR),
  },
  {
    id: "stress2-rt-2",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    note:
      "Considered closing the partner sub-investigation early after first read on Gottman. Held it open after noticing the user's three different descriptions of his position across sessions — that variation is itself the finding, and it warranted a script-as-artifact rather than a section-only treatment.",
    tags: ["sub-investigation", "partner", "scope-decision"],
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress2-rt-3",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    note:
      "Reframed the recommendation from 'don't decide yet' to 'choose not-yet, with a 6-month window and a defined re-decision date.' The first version sounded like avoidance; the second is an active stance. This is a tone change, not a substance change, but it matters for whether the user can hold the recommendation as a decision rather than a deferral.",
    tags: ["recommendation", "framing", "session-3"],
    created_at: iso(NOW - 2 * HOUR),
  },
];

// ===========================================================================
// Ruled out (2)
// ===========================================================================

const RULED_OUT: RuledOut[] = [
  {
    id: "stress2-ro-1",
    dossier_id: STRESS2_DOSSIER_ID,
    subject: "Deciding based on age pressure alone",
    reason:
      "The 35-cliff framing overstates the gradient (Broer 2014, Dunson 2004), and pressure-driven decisions on irreversible choices have the worst outcomes in the affective-forecasting literature. Both the 'must decide now' and the 'age doesn't matter' poles are off; age belongs in the calculus, not as the calculus.",
    sources: [],
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: "stress2-ro-2",
    dossier_id: STRESS2_DOSSIER_ID,
    subject: "Using friends-cohort as a reference class",
    reason:
      "Friend decisions are noisy projections of individual circumstance (partner, finances, health, biology) that don't transfer cleanly. The work to disentangle the informative cases would itself cost more than the information gained. Closed the sub-investigation; recorded for future reference so the angle isn't reopened by accident.",
    sources: [],
    created_at: iso(NOW - 20 * HOUR),
  },
];

// ===========================================================================
// Investigation log — ~90 entries
// ===========================================================================

function buildInvestigationLog(): InvestigationLogEntry[] {
  const out: InvestigationLogEntry[] = [];

  const sourceCitations = [
    {
      citation:
        "Broer et al. (2014) — Anti-Müllerian Hormone: ovarian reserve testing",
      url: "https://academic.oup.com/humupd/article/20/5/688/623013",
      why: "AMH population trajectory primary source",
    },
    {
      citation:
        "Dunson, Baird & Colombo (2004) — Increased infertility with age",
      url: "https://www.fertstert.org/article/S0015-0282(03)03192-1/fulltext",
      why: "Per-cycle conception probability by age",
    },
    {
      citation:
        "Bertrand, Goldin & Katz (2010) — Dynamics of the Gender Gap for Young Professionals",
      url: "https://www.aeaweb.org/articles?id=10.1257/app.2.3.228",
      why: "Motherhood-penalty headline magnitude and structure",
    },
    {
      citation: "Goldin (2014) — A Grand Gender Convergence",
      url: "https://www.aeaweb.org/articles?id=10.1257/aer.104.4.1091",
      why: "Convex-vs-linear-hours occupational structure",
    },
    {
      citation:
        "van Harreveld, van der Pligt & de Liver (2009) — The agony of ambivalence",
      url: "https://www.sciencedirect.com/science/article/abs/pii/S0065260108004036",
      why: "Pre-decision vs. chronic-avoidance ambivalence distinction",
    },
    {
      citation:
        "Newby-Clark & Ross (1999/2003) — Conceiving the past and the future",
      url: "https://psycnet.apa.org/record/2003-99641-008",
      why: "Simultaneous-cognitions correlate with affective-forecasting accuracy",
    },
    {
      citation: "Gottman Institute — life-stage transitions in long partnerships",
      url: "https://www.gottman.com/about/research/",
      why: "Mutual accommodation in major-decision conversations",
    },
    {
      citation: "Esther Perel — Mating in Captivity (2006)",
      url: "https://www.estherperel.com/books",
      why: "Stated vs. revealed preference shaping in long partnerships",
    },
    {
      citation: "Loomes & Sugden (1982) — Regret theory",
      url: "https://www.jstor.org/stable/2232669",
      why: "Anticipated regret as decision predictor on irreversible choices",
    },
    {
      citation: "ASRM — Testing measures of ovarian reserve",
      url: "https://www.asrm.org/practice-guidance/practice-committee-documents/",
      why: "Clinical guidance on AMH/FSH/AFC interpretation",
    },
  ];

  const summaries = {
    source_consulted: (i: number) => {
      const s = sourceCitations[i % sourceCitations.length];
      return `Read ${s.citation.split("—")[0].trim()} — ${s.why}`;
    },
    sub_investigation_spawned: [
      "Spawned sub: AMH/FSH trajectory at 35",
      "Spawned sub: career-reentry path-dependence",
      "Spawned sub: ambivalence as signal vs. avoidance",
      "Spawned sub: partner stated vs. revealed preferences",
      "Spawned sub: financial scenario modeling",
      "Spawned sub: peer-comparison reference class (later abandoned)",
    ],
    sub_investigation_returned: [
      "Sub returned: AMH/FSH — gradient gentler than cliff framing",
      "Sub returned: career-reentry — path-dependent, network attachment dominates",
      "Sub returned: ambivalence — pre-decision vs. chronic-avoidance distinction operationalized",
      "Sub abandoned: peer comparison — wrong reference class",
    ],
    section_upserted: [
      "Added summary section",
      "Added ambivalence finding section",
      "Added fertility baseline section",
      "Added career-reentry section",
      "Added partner-preferences section",
      "Added three-way decision recommendation",
      "Added ruled-out: age-pressure-alone section",
      "Added open-question: grief inventory section",
    ],
    section_revised: [
      "Revised summary — pivoted from 'should you try' to 'smallest-investigation' framing",
      "Revised ambivalence section — added the persistent-ambivalence-as-data callout",
      "Revised fertility section — added the population-percentile range explicitly",
      "Revised career section — reframed from 'pause vs. don't' to 'what does pause look like'",
      "Revised partner section — captured the three different position descriptions across sessions",
      "Revised three-way recommendation — made not-yet an active stance with re-decision date",
    ],
    artifact_added: [
      "Drafted partner conversation script",
      "Drafted clinic-visit baseline checklist",
      "Drafted six-prompt journaling sequence",
      "Drafted financial scenario sheet (parametric)",
    ],
    artifact_revised: [
      "Revised partner script — sharpened the stage-1 independent-position prompt",
      "Revised journaling sequence — added the day-7 reread ritual",
      "Revised clinic checklist — moved partner semen analysis from primary list to parallel-track callout",
    ],
    path_rejected: [
      "Rejected: pro/con-list framing (incommensurable axes)",
      "Rejected: 'just go for it, you'll never feel ready' (collapses important distinction)",
      "Rejected: 'listen to your gut' (gut is the thing producing the ambivalence)",
      "Rejected: expected-utility calculation (false precision from fabricated inputs)",
      "Rejected: front-loaded urgency framing (wrong on data, bad regret outcomes)",
      "Rejected: friends-cohort reference class (wrong reference class)",
      "Deferred: therapy as principal intervention (good move post-month, not now)",
      "Deferred: embryo-banking as default hedge (premature without AMH baseline)",
      "Deferred: bring partner into next session (premature without her own clarity first)",
      "Deferred: explicit regret-minimization calculation (needs grief inventory first)",
      "Rejected: open with sympathy-only, no premise challenge (would lose traction)",
      "Rejected: assert ambivalence-is-the-answer prematurely (cannot be projected from outside)",
    ],
    decision_flagged: [
      "Flagged decision: structured introspection month vs. clinic-visit-this-month",
      "Flagged decision: parallel-track journaling and clinic, or sequential",
    ],
    input_requested: [
      "Requested input: when you imagine waking up at 40 without having tried, what specifically do you feel?",
      "Requested input: salary and field convexity for the financial scenario sheet",
    ],
    plan_revised: [
      "Revised plan: reordered items 3 and 4 (introspection before partner conversation)",
      "Revised plan: added item 5 (grief inventory) gated on items 3 and 4",
    ],
    stuck_declared: ["Blocked on grief-inventory — can only be answered by the user"],
  };

  for (let i = 0; i < 92; i++) {
    let entry_type: InvestigationLogEntryType;
    const r = i % 20;
    if (r < 10) entry_type = "source_consulted";
    else if (r < 13) entry_type = "section_upserted";
    else if (r < 15) entry_type = "section_revised";
    else if (r < 16) entry_type = "sub_investigation_spawned";
    else if (r < 17) entry_type = "sub_investigation_returned";
    else if (r < 18) entry_type = "artifact_added";
    else if (r < 19) entry_type = "artifact_revised";
    else {
      const rest: InvestigationLogEntryType[] = [
        "path_rejected",
        "decision_flagged",
        "input_requested",
        "plan_revised",
        "stuck_declared",
      ];
      entry_type = rest[i % rest.length];
    }

    let summary: string;
    let payload: Record<string, unknown> = {};
    if (entry_type === "source_consulted") {
      const cit = sourceCitations[i % sourceCitations.length];
      summary = summaries.source_consulted(i);
      payload = {
        citation: cit.citation,
        url: cit.url,
        why: cit.why,
        what_learned: "Relevant to " + cit.why + ".",
      };
    } else {
      const list = summaries[entry_type];
      if (Array.isArray(list) && list.length > 0) {
        summary = list[i % list.length];
      } else {
        summary = `${entry_type.replace(/_/g, " ")} entry #${i}`;
      }
      if (entry_type === "path_rejected") {
        payload = {
          path: summary.replace(/^Rejected: |^Deferred: /, ""),
          why_rejected: "See considered-and-rejected entry for full reasoning.",
        };
      } else if (entry_type === "sub_investigation_spawned") {
        payload = {
          scope: summary,
          questions: ["q1", "q2", "q3"],
        };
      } else if (entry_type === "sub_investigation_returned") {
        payload = {
          findings: ["finding a", "finding b"],
        };
      } else if (
        entry_type === "section_upserted" ||
        entry_type === "section_revised"
      ) {
        const sectionIds = [
          SEC_SUMMARY,
          SEC_AMBIV,
          SEC_FERTILITY,
          SEC_CAREER,
          SEC_PARTNER,
          SEC_THREE_WAY,
          SEC_RULED_AGE,
          SEC_OPEN_GRIEF,
        ];
        payload = { section_id: sectionIds[i % sectionIds.length] };
      } else if (
        entry_type === "artifact_added" ||
        entry_type === "artifact_revised"
      ) {
        const ids = [
          ART_PARTNER_SCRIPT,
          ART_CLINIC_CHECKLIST,
          ART_JOURNAL_PROMPTS,
          ART_FINANCE_SHEET,
        ];
        payload = { artifact_id: ids[i % ids.length] };
      }
    }

    // Spread entries across the last ~46 hours, newest-first at i=0.
    const createdAt = iso(NOW - i * 30 * MIN);

    const subIds = [
      SUB_AMH_ID,
      SUB_CAREER_ID,
      SUB_AMBIV_ID,
      SUB_PARTNER_ID,
      SUB_FINANCE_ID,
      SUB_FRIENDS_ID,
    ];
    const subId = i % 7 === 3 ? subIds[i % subIds.length] : null;

    out.push({
      id: `stress2-log-${String(i).padStart(3, "0")}`,
      dossier_id: STRESS2_DOSSIER_ID,
      work_session_id:
        i < 30
          ? "stress2-ws-3"
          : i < 65
            ? "stress2-ws-2"
            : "stress2-ws-1",
      sub_investigation_id: subId,
      entry_type,
      payload,
      summary,
      created_at: createdAt,
    });
  }
  return out;
}

const INVESTIGATION_LOG: InvestigationLogEntry[] = buildInvestigationLog();

function deriveCounts(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const e of INVESTIGATION_LOG) {
    counts[e.entry_type] = (counts[e.entry_type] ?? 0) + 1;
  }
  return counts;
}

export const STRESS2_INVESTIGATION_LOG_COUNTS: Record<string, number> =
  deriveCounts();

// ===========================================================================
// Work sessions (3)
// ===========================================================================

const WORK_SESSIONS: WorkSession[] = [
  {
    id: "stress2-ws-1",
    dossier_id: STRESS2_DOSSIER_ID,
    started_at: iso(NOW - 47 * HOUR),
    ended_at: iso(NOW - 41 * HOUR),
    trigger: "intake",
    token_budget_used: 18400,
    input_tokens: 14600,
    output_tokens: 3800,
    cost_usd: 0.42,
    end_reason: "ended_turn",
  },
  {
    id: "stress2-ws-2",
    dossier_id: STRESS2_DOSSIER_ID,
    started_at: iso(NOW - 26 * HOUR),
    ended_at: iso(NOW - 18 * HOUR),
    trigger: "resume",
    token_budget_used: 28200,
    input_tokens: 21900,
    output_tokens: 6300,
    cost_usd: 0.71,
    end_reason: "delivered",
  },
  {
    id: "stress2-ws-3",
    dossier_id: STRESS2_DOSSIER_ID,
    started_at: iso(NOW - 10 * HOUR),
    ended_at: null,
    trigger: "user_open",
    token_budget_used: 11200,
    input_tokens: 8900,
    output_tokens: 2300,
    cost_usd: 0.27,
    end_reason: null,
  },
];

// ===========================================================================
// Pre-visit change log (~28 entries)
// ===========================================================================

export const STRESS2_CHANGE_LOG: ChangeLogEntry[] = [
  {
    id: "stress2-ch-1",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: SEC_SUMMARY,
    kind: "section_updated",
    change_note: "Rewrote summary around 'smallest-investigation' framing",
    created_at: iso(NOW - 1 * HOUR),
  },
  {
    id: "stress2-ch-2",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: null,
    kind: "debrief_updated",
    change_note: "Updated all four debrief fields — session closeout",
    created_at: iso(NOW - 22 * MIN),
  },
  {
    id: "stress2-ch-3",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: SEC_THREE_WAY,
    kind: "section_updated",
    change_note: "Reframed recommendation from 'don't decide yet' to 'not-yet with re-decision date'",
    created_at: iso(NOW - 2 * HOUR),
  },
  {
    id: "stress2-ch-4",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: null,
    kind: "working_theory_updated",
    change_note: "Tightened working theory — added 'not yet with 6-month window' as the recommended stance",
    created_at: iso(NOW - 3 * HOUR),
  },
  {
    id: "stress2-ch-5",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: SEC_OPEN_GRIEF,
    kind: "needs_input_added",
    change_note: "Opened: when you imagine waking up at 40 without having tried, what specifically do you feel?",
    created_at: iso(NOW - 4 * HOUR),
  },
  {
    id: "stress2-ch-6",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: SEC_AMBIV,
    kind: "section_updated",
    change_note: "Added the persistent-ambivalence-as-data callout",
    created_at: iso(NOW - 4 * HOUR),
  },
  {
    id: "stress2-ch-7",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: null,
    kind: "next_action_added",
    change_note: "Mark a re-decision date six months out (literally on the calendar)",
    created_at: iso(NOW - 4 * HOUR),
  },
  {
    id: "stress2-ch-8",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: SEC_FERTILITY,
    kind: "section_updated",
    change_note: "Added the population-percentile range explicitly to fertility section",
    created_at: iso(NOW - 5 * HOUR),
  },
  {
    id: "stress2-ch-9",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: SEC_CAREER,
    kind: "section_updated",
    change_note: "Reframed career section from 'pause vs don't' to 'what does pause look like'",
    created_at: iso(NOW - 6 * HOUR),
  },
  {
    id: "stress2-ch-10",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: null,
    kind: "considered_and_rejected_added",
    change_note: "Rejected: assert ambivalence-is-the-answer prematurely",
    created_at: iso(NOW - 8 * HOUR),
  },
  {
    id: "stress2-ch-11",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: SEC_PARTNER,
    kind: "section_updated",
    change_note: "Captured the three different partner-position descriptions across sessions",
    created_at: iso(NOW - 8 * HOUR),
  },
  {
    id: "stress2-ch-12",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-3",
    section_id: null,
    kind: "artifact_updated",
    change_note: "Sharpened the stage-1 independent-position prompt in the partner script",
    created_at: iso(NOW - 8 * HOUR),
  },
  {
    id: "stress2-ch-13",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: null,
    kind: "sub_investigation_completed",
    change_note: "Ambivalence sub returned with operationalization",
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress2-ch-14",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: null,
    kind: "artifact_added",
    change_note: "Drafted six-prompt journaling sequence",
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress2-ch-15",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: null,
    kind: "sub_investigation_spawned",
    change_note: "Spawned partner stated-vs-revealed sub-investigation",
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress2-ch-16",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: SEC_OPEN_GRIEF,
    kind: "section_created",
    change_note: "Added grief-inventory open question",
    created_at: iso(NOW - 12 * HOUR),
  },
  {
    id: "stress2-ch-17",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: null,
    kind: "plan_updated",
    change_note: "Reordered plan items: introspection before partner conversation",
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress2-ch-18",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: null,
    kind: "sub_investigation_abandoned",
    change_note: "Abandoned peer-comparison sub — wrong reference class",
    created_at: iso(NOW - 20 * HOUR),
  },
  {
    id: "stress2-ch-19",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: null,
    kind: "ruled_out_added",
    change_note: "Ruled out: friends-cohort as reference class",
    created_at: iso(NOW - 20 * HOUR),
  },
  {
    id: "stress2-ch-20",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: SEC_THREE_WAY,
    kind: "section_created",
    change_note: "Added three-way decision recommendation (yes / no / not-yet)",
    created_at: iso(NOW - 24 * HOUR),
  },
  {
    id: "stress2-ch-21",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: SEC_RULED_AGE,
    kind: "section_created",
    change_note: "Ruled out: deciding based on age pressure alone",
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: "stress2-ch-22",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-2",
    section_id: null,
    kind: "sub_investigation_completed",
    change_note: "Career-reentry sub returned with path-dependence findings",
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: "stress2-ch-23",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-1",
    section_id: SEC_PARTNER,
    kind: "section_created",
    change_note: "Added partner-preferences section",
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: "stress2-ch-24",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-1",
    section_id: null,
    kind: "sub_investigation_completed",
    change_note: "AMH/FSH trajectory sub returned",
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: "stress2-ch-25",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-1",
    section_id: SEC_FERTILITY,
    kind: "section_created",
    change_note: "Added fertility-baseline section",
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: "stress2-ch-26",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-1",
    section_id: SEC_AMBIV,
    kind: "section_created",
    change_note: "Added ambivalence finding section",
    created_at: iso(NOW - 38 * HOUR),
  },
  {
    id: "stress2-ch-27",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-1",
    section_id: null,
    kind: "plan_updated",
    change_note: "Approved initial 5-item plan",
    created_at: iso(NOW - 2 * DAY + 50 * MIN),
  },
  {
    id: "stress2-ch-28",
    dossier_id: STRESS2_DOSSIER_ID,
    work_session_id: "stress2-ws-1",
    section_id: SEC_SUMMARY,
    kind: "section_created",
    change_note: "Initial summary section drafted",
    created_at: iso(NOW - 30 * HOUR),
  },
];

// ===========================================================================
// Export the full DossierFull
// ===========================================================================

export const stress2CaseFile: DossierFull = {
  dossier: DOSSIER,
  sections: SECTIONS,
  needs_input: [
    {
      id: "stress2-ni-1",
      dossier_id: STRESS2_DOSSIER_ID,
      question:
        "Before we go further: when you imagine waking up at 40 without having tried, what specifically do you feel — grief, relief, nothing in particular? One honest sentence. The specificity matters more than the framing; if 'nothing in particular' is honest, that's the answer.",
      blocks_section_ids: [SEC_OPEN_GRIEF, SEC_THREE_WAY],
      created_at: iso(NOW - 4 * HOUR),
      answered_at: null,
      answer: null,
    },
  ],
  decision_points: [
    {
      id: "stress2-dp-1",
      dossier_id: STRESS2_DOSSIER_ID,
      title:
        "Commit to a 3-month structured introspection phase (medical baseline + partner conversation + journaling), or go straight to a fertility-clinic consult this month?",
      options: [
        {
          label:
            "Three-month structured month: journaling first, partner conversation second, clinic visit third",
          implications:
            "Sequenced introspection. The journaling output sharpens the partner conversation; the partner conversation sharpens the clinic-visit framing. Costs you ~3 months of pre-decision time but produces meaningfully better decision inputs at the re-decision point. The 6-month re-decision window stays intact regardless of which path you pick.",
          recommended: true,
        },
        {
          label:
            "Clinic-visit-this-month, journaling and partner conversation in parallel",
          implications:
            "Faster on the medical data, slower on quality of introspection. The risk is that walking into the clinic without the journaling work primes the conversation toward the medicalized framing rather than the underlying-want framing. Acceptable if the time pressure feels real to you in a way the data doesn't yet support.",
          recommended: false,
        },
      ],
      recommendation:
        "Three-month structured. The biology gives you that month; the pressure is what would have you skip it. The clinic visit is more informative after the journaling than before.",
      blocks_section_ids: [],
      created_at: iso(NOW - 5 * HOUR),
      resolved_at: null,
      chosen: null,
      kind: "generic",
    },
  ],
  reasoning_trail: REASONING_TRAIL,
  ruled_out: RULED_OUT,
  work_sessions: WORK_SESSIONS,
  artifacts: ARTIFACTS,
  sub_investigations: SUB_INVESTIGATIONS,
  investigation_log: INVESTIGATION_LOG,
  considered_and_rejected: CONSIDERED_AND_REJECTED,
  next_actions: NEXT_ACTIONS,
};
