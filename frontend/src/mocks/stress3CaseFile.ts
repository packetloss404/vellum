// Stress3 fixture. A "couple in their early-30s deciding whether to sell a
// 4%-mortgage house and move closer to an aging parent, with a 20-month-old
// in the middle" decision dossier. Pathologically long in places to walk
// the detail page through worst-case rendering on a no-network demo path.
//
// Used by /stress3 (see Stress3Page.tsx). Not loaded on any production path.

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

export const STRESS3_DOSSIER_ID = "stress3-case-move-mom";

const NOW = Date.now();
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

const iso = (ms: number) => new Date(ms).toISOString();

// ---------- sub-investigation ids ----------

const SUB_CLINICAL_ID = "stress3-sub-clinical-trajectory";
const SUB_REMOTE_ID = "stress3-sub-remote-career-cost";
const SUB_FINANCIAL_ID = "stress3-sub-financial-model";
const SUB_TODDLER_ID = "stress3-sub-toddler-attachment";
const SUB_BRIDGE_ID = "stress3-sub-bridge-visit-pattern";
const SUB_SIBLINGS_ID = "stress3-sub-siblings-comparison";

// ---------- section ids ----------

const SEC_SUMMARY = "stress3-sec-summary";
const SEC_TIMELINE = "stress3-sec-timeline-unknown";
const SEC_FINANCIAL = "stress3-sec-financial-delta";
const SEC_TODDLER = "stress3-sec-toddler-fine";
const SEC_CAREER = "stress3-sec-spouse-career";
const SEC_NETWORK = "stress3-sec-support-network";
const SEC_RULED_PANIC = "stress3-sec-ruled-panic-move";
const SEC_OPEN = "stress3-sec-open-presence";

// ---------- artifact ids ----------

const ART_PCP = "stress3-art-pcp-conversation";
const ART_FINANCIAL = "stress3-art-financial-model";
const ART_CAREER = "stress3-art-career-conversation";
const ART_BRIDGE = "stress3-art-bridge-schedule";

// ===========================================================================
// Dossier
// ===========================================================================

const DOSSIER = {
  id: STRESS3_DOSSIER_ID,
  title:
    "Sell and move closer to mom, or stay — 20-month-old, 4% mortgage, spouse's hybrid job, decline timing unknown",
  problem_statement:
    "We're early-to-mid 30s with a 20-month-old, currently 4-5 hours by car from my mother (68, widowed, still independent but starting to show signs of cognitive or mobility decline). We have a ~4% mortgage on a house we'd be selling into a softer market and rebuying at 7%+. My spouse is hybrid — 1-2 office days a week in our current city. The trigger for revisiting this was a recent ER visit for mom that resolved fine but didn't feel fine. The question is whether to sell now, sell in 6-12 months, or stay and visit more often.",
  out_of_scope: [
    "long-term-care insurance shopping for mom (separate dossier)",
    "specific real-estate agent selection in either market",
    "529/college planning for the 20-month-old",
    "estate planning for mom (she has a will and POA already in place)",
    "whether to have a second child (related but a separate decision)",
  ],
  dossier_type: "decision_memo" as const,
  status: "active" as const,
  check_in_policy: {
    cadence: "on_demand" as const,
    notes:
      "Pause between user turns; resume when user answers the open question about whether mom has had a cognitive screen in the last 12 months and what the result was.",
  },
  last_visited_at: iso(NOW - 18 * HOUR),
  created_at: iso(NOW - 2 * DAY),
  updated_at: iso(NOW - 14 * MIN),
  debrief: {
    what_i_did:
      "Spent two sessions stress-testing the framing of the question itself before doing any cost-benefit math. Pulled the literature on toddler attachment-disruption (Ainsworth's Strange Situation framework, the 1990s-2010s longitudinal follow-ups, and the 2018 NICHD reanalysis), the geriatric-clinical literature on early-decline indicators that primary-care physicians actually track (IADLs, ADLs, MoCA cutoffs), Federal Reserve and Redfin data on the rate-lock-in phenomenon and current sell-side market conditions, and the smaller but real literature on relationship maintenance at distance (proximity vs. frequency). Drafted four artifacts: a script for a conversation with mom's PCP, a full financial model with three-, five-, and ten-year horizons, a script for the conversation with your spouse's manager about full-remote, and a six-month bridge-visit calendar template. Spawned six sub-investigations — three returned with findings, one is running, one is blocked, one was abandoned.",
    what_i_found:
      "Three load-bearing findings. (1) The forcing function you're feeling is real but the timeline isn't as tight as it feels — mom's ER visit was acute, not progressive, and the indicators of meaningful decline (IADL loss, MoCA drop, falls) follow a measurable trajectory that is much slower than month-to-month panic suggests. (2) The financial delta is dominated by property tax and your spouse's career path, not by the mortgage rate gap that has been emotionally anchoring the decision. (3) A 20-month-old will be fine — the dev-psych literature is clear that toddlers this age generalize secure attachment to new caregivers within weeks-to-months given a stable primary caregiver, but the parents moving is the much bigger emotional risk in the family system, and that's been underweighted.\n\nA fourth finding worth flagging because it changes the shape of the decision: presence-at-distance is more valuable than the family-first framing acknowledges. Two trips per month for six months gives you almost all the decision-relevant data about mom's actual trajectory, lets the toddler bond meaningfully with her, and costs you nothing irreversible.",
    what_you_should_do_next:
      "Do not list the house this spring. Commit to a six-month data-gathering phase. Three concrete moves: (a) get mom to her PCP for a baseline visit with a MoCA or comparable cognitive screen — this is the single biggest unknown and you cannot decide rationally without it; (b) have your spouse open the full-remote conversation with their manager now, framed as exploratory; (c) start a two-trips-per-month bridge cadence beginning next month, treating those visits as data-gathering, not just family time. Re-decide at month six with real data instead of the panic-shaped data you have now.",
    what_i_couldnt_figure_out:
      "Two things. First, what your spouse's career trajectory actually looks like in a fully-remote configuration for their specific role — generic remote-work data is too coarse. The career conversation script gets at this. Second, mom's actual functional baseline. You're describing her in language that could fit anything from \"normal aging at 68\" to \"early MCI\" — the gap matters enormously and you can't close it without a clinical screen. Both of these are answerable by you, in the next 60 days, and once they're answered the decision becomes much smaller.",
    last_updated: iso(NOW - 35 * MIN),
  },
  premise_challenge: {
    original_question:
      "Should we sell the house and move closer to my mom, or stay where we are with the 20-month-old?",
    hidden_assumptions: [
      "that the question is binary (stay vs. move) when it's actually multi-variable: timing, intermediate solutions, frequency-of-visits, partial-relocation, sell-and-rent-near-mom, and so on",
      "that mom's decline is on a timeline that forces this decision now rather than letting you plan over 12-24 months with real data",
      "that proximity is the main delivery mechanism for presence — rather than frequency of visits, structured video routine with the grandchild, or relocation triggered by a specific health event",
      "that the child's attachment to current caregivers and neighborhood is robust to disruption at 20 months (it largely is, with limits — but the parents moving is the bigger family-system risk)",
      "that the financial model is mostly about the mortgage rate when in fact property tax delta, closing costs, capital-gains exposure, and the hybrid spouse's career trajectory are the larger levers",
      "that you can read mom's clinical trajectory from phone calls and visits — when in practice the things that matter (IADL loss, cognitive scores, fall risk) require actual clinical baselining",
      "that staying = doing nothing, when staying actually requires an active plan for visit frequency, communication cadence, and decision triggers",
    ],
    why_answering_now_is_risky:
      "You are operating on a panic-shaped data set. The recent ER visit has elevated salience without elevating evidence — most ER visits at 68 are acute and don't predict progressive decline. Selling a 4% mortgage to buy at 7%+ and uprooting the toddler's environment based on a salience spike rather than a measured trajectory is the kind of irreversible move you regret in eighteen months when mom's still independent and your spouse's career has taken a measurable hit. Conversely, refusing to consider the move because of the mortgage rate alone would be its own mistake if mom's actual trajectory is steeper than you think. Either answer produced now is worse than no answer.",
    safer_reframe:
      "Rather than \"sell or stay,\" treat the next six months as a data-gathering phase with three explicit work streams: (1) clinical baseline on mom (PCP visit, cognitive screen, functional assessment); (2) honest career-cost read on full-remote for the hybrid spouse; (3) bridge-visit cadence (two trips per month) to test whether presence-at-distance handles the actual delivery mechanism of \"being there.\" Re-decide at month six with the real data, not the panicked data. The cost of waiting six months is small; the cost of selling on bad data is large.",
    required_evidence_before_answering: [
      "objective read on mom's actual health trajectory — recent PCP visit, any cognitive screen (MoCA, MMSE, or equivalent) with score, functional baseline (IADLs/ADLs)",
      "your spouse's specific job flexibility — what would a full-remote transition actually cost in compensation, promotion velocity, and team relationship",
      "total housing delta including property tax, closing costs, and capital-gains exposure on the current home — not just the mortgage rate",
      "current support-network composition in your city (daycare, pediatrician, the friends you call at 9pm) and what's actually replaceable in mom's city",
      "child's actual attachment signals at 20 months vs. parental projection — what does the literature say about this age window specifically",
      "two months of bridge-visit data — can two trips per month deliver most of what daily proximity would, for the next 12-18 months",
    ],
    updated_at: iso(NOW - 2 * DAY + 12 * MIN),
  },
  working_theory: {
    recommendation:
      "Don't sell now. Commit to a six-month data-gathering phase: get mom a clinical baseline including a cognitive screen, have your spouse open the full-remote conversation with their manager, and start a two-trips-per-month bridge-visit cadence. Re-decide at month six with real data.",
    confidence: "medium" as const,
    why:
      "The forcing function you're responding to (mom's decline) is real but the timeline isn't as tight as it currently feels. The recent ER visit is high-salience but low-evidence-of-progression. The financial cost of selling now versus six months from now is small relative to the information value of those six months — particularly given that the things you actually need to know (mom's clinical trajectory, your spouse's career cost of full-remote, whether bridge-visits handle most of what proximity would) are all observable in that window. The 20-month-old is genuinely fine either way; the move would be harder on the parents than the kid.",
    what_would_change_it:
      "If mom's PCP visit returns a MoCA score under 26 with functional decline (IADL loss), or if she has a second acute event in the next 60 days, the timeline assumption breaks and we accelerate. If your spouse's manager confirms full-remote is unavailable for their role and a remote job search would mean a 30%+ pay cut, the financial picture shifts hard. If two months of bridge-visits make clear that presence-at-distance does not work for what mom actually needs, we revisit.",
    unresolved_assumptions: [
      "mom has not had a cognitive screen in the last 12 months (user has not confirmed)",
      "your spouse's specific role admits a full-remote configuration in principle (assumed from generic team-level data, not their manager)",
      "the 20-month-old's daycare attachment is age-typical and not unusually intense (parental report only)",
      "current-market sell conditions in your city are softer than 2022 peak but not catastrophic — spread is roughly 8-12% off peak per Redfin",
      "mom's house is paid off and she could absorb you living nearby without it materially changing her finances",
    ],
    updated_at: iso(NOW - 50 * MIN),
  },
  investigation_plan: {
    items: [
      {
        id: "stress3-plan-1",
        question:
          "What is mom's actual clinical trajectory — what do her PCP, recent labs, and a cognitive screen actually show?",
        rationale:
          "This is the pre-question. Every other variable depends on whether mom's decline is on a 12-month timeline, a 5-year timeline, or normal-aging-with-a-scare. We cannot decide without baselining this, and you cannot baseline it from phone calls.",
        expected_sources: [
          "her PCP (with her permission)",
          "AGS Beers Criteria",
          "Lancet Commission on dementia prevention 2024",
          "JAMA on MoCA cutoffs in primary-care screening",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
      {
        id: "stress3-plan-2",
        question:
          "What is the full financial delta — sell-and-move vs. stay — over 3yr, 5yr, and 10yr horizons including property tax, closing costs, and capital gains?",
        rationale:
          "The mortgage-rate delta is what's emotionally anchoring the discussion, but it is almost certainly not the largest line item. We need a real model to know which costs we're actually trading off.",
        expected_sources: [
          "Federal Reserve research on rate-lock-in",
          "Redfin and Zillow market data",
          "IRS Pub 523 on capital gains exclusion",
          "county property-tax records for both cities",
        ],
        as_sub_investigation: true,
        status: "completed" as const,
      },
      {
        id: "stress3-plan-3",
        question:
          "What's the real career cost of full-remote for the hybrid spouse, in compensation and promotion velocity?",
        rationale:
          "Generic remote-work data is too coarse for the decision. We need a concrete read on their specific role and team, which can only come from the manager conversation.",
        expected_sources: [
          "his manager (via the career-conversation script)",
          "Levels.fyi for his role and band",
          "BLS occupational data on his function",
          "company's published remote policy",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
      {
        id: "stress3-plan-4",
        question:
          "What does the dev-psych literature say specifically about 18-24 month attachment disruption and how it generalizes to new caregivers?",
        rationale:
          "Parental anxiety here often runs ahead of the actual evidence. We need to know what the literature actually shows about this age band so the decision isn't being driven by generalized worry.",
        expected_sources: [
          "Ainsworth Strange Situation literature",
          "NICHD Study of Early Child Care and Youth Development",
          "Sroufe et al. Minnesota Longitudinal Study",
          "Belsky 2006 review",
        ],
        as_sub_investigation: true,
        status: "completed" as const,
      },
      {
        id: "stress3-plan-5",
        question:
          "Can a two-trips-per-month bridge pattern deliver most of what daily proximity would, for the next 12-18 months?",
        rationale:
          "If bridge-visits handle most of the actual presence-related needs, we get the benefit of being-there without the irreversible cost of selling. We can test this in two months.",
        expected_sources: [
          "ASA literature on relationship maintenance at distance",
          "AARP caregiver-support research",
          "user's own pilot of the cadence",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
    ],
    rationale:
      "The plan is gated on items 1-3. Until we have a clinical baseline, a real career-cost read, and the financial model in front of us, the move/stay question is being decided on vibes. Item 5 (bridge-visits) is the experimental arm — we run it during the data-gathering phase and read the results at month six. Item 4 closes out a parental-anxiety variable.",
    drafted_at: iso(NOW - 2 * DAY + 25 * MIN),
    approved_at: iso(NOW - 2 * DAY + 40 * MIN),
    revised_at: iso(NOW - 20 * HOUR),
    revision_count: 2,
  },
};

// ===========================================================================
// Sections
// ===========================================================================

const SECTIONS: Section[] = [
  {
    id: SEC_SUMMARY,
    dossier_id: STRESS3_DOSSIER_ID,
    type: "summary",
    title: "Where this stands",
    content:
      "You and your spouse are being asked, by your own anxiety more than by external events, to decide whether to sell a 4%-mortgage house in a softer market and move 4-5 hours to be closer to your mother — with a 20-month-old who currently has a stable daycare and a primary-caregiver setup that's working. The recent ER visit is real but acute; it has elevated salience without elevating evidence about progressive decline.\n\nThe argument of this dossier is that you should not list the house this spring. The decision feels urgent because of a single high-salience event, but the costs of being wrong (selling at 7%+, your spouse taking a measurable career hit, the family system uprooting itself based on incomplete data) are large and irreversible, and the cost of waiting six months is small. Use those six months: get mom a real clinical baseline including a cognitive screen, have your spouse open the full-remote conversation with their manager, and run a two-trips-per-month bridge cadence to see what presence-at-distance actually delivers.\n\nRe-decide at month six with real data. The framing right now is binary; the actual decision is multi-variable, and most of the variables are observable.",
    state: "confident",
    order: 1,
    change_note:
      "Rewrote the summary after the financial-model and toddler-attachment subs both returned. The opening framing is now \"don't list this spring; six months of data first\" rather than \"weighing the move.\"",
    sources: [],
    depends_on: [],
    last_updated: iso(NOW - 50 * MIN),
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: SEC_TIMELINE,
    dossier_id: STRESS3_DOSSIER_ID,
    type: "finding",
    title:
      "The decline timeline is the unknown that breaks all the other calculations",
    content:
      "Every other line in the financial model, every career trade-off, every estimate of what the toddler will or won't remember, snaps into focus once you know whether mom is on a 12-month, 5-year, or 15-year trajectory. Right now you're guessing, and the guessing is being driven by the recent ER visit rather than by a measured baseline.\n\nWhat clinicians actually track at this stage:\n\n- **IADLs** (instrumental activities of daily living): managing finances, taking medications, driving, cooking, shopping, using the phone. Loss in IADLs is typically the earliest functional signal. The Lawton-Brody scale is the standard instrument.\n- **ADLs** (basic activities of daily living): bathing, dressing, toileting, transferring, continence, feeding. ADL loss is later in the trajectory than IADL loss by years, typically.\n- **MoCA** (Montreal Cognitive Assessment): 30-point screen, takes 10 minutes, can be done in a primary-care visit. A score of 26+ is in the normal range; 18-25 suggests mild cognitive impairment; below 18 suggests dementia. The MoCA is more sensitive to early MCI than the older MMSE for the same time investment.\n- **Falls** in the past year. Even one fall in someone 65+ doubles the risk of another, and a fall plus IADL loss is a stronger predictor of one-year functional decline than either alone.\n- **Acute events** that don't progress (the ER visit pattern). These are common and not predictive on their own — what matters is whether they're paired with chronic changes in IADLs or cognition.\n\nThe Lancet Commission's 2024 update on dementia prevention and care is also relevant background — it estimates 45% of dementia risk is potentially modifiable, and the timeline of modifiable progression is on the order of years, not months. Your panic right now is on a months-not-years emotional clock; the actual disease course is on a years clock.\n\nYou cannot baseline mom from your visits. You need her PCP, a recent screen, and ideally one functional assessment. Without those, every downstream decision is being made on vibes.",
    state: "provisional",
    order: 2,
    change_note:
      "Marked provisional rather than confident — the framework is right but we don't yet have mom's actual numbers, so we can't say where she is on the curve.",
    sources: [
      {
        kind: "web",
        url: "https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(24)01296-0/fulltext",
        title:
          "Lancet Commission 2024 — Dementia prevention, intervention, and care",
        snippet:
          "Forty-five percent of dementia cases worldwide are theoretically preventable through addressing 14 modifiable risk factors across the life course.",
      },
      {
        kind: "web",
        url: "https://www.parkinson.org/sites/default/files/MoCA-Test-English.pdf",
        title: "Montreal Cognitive Assessment (MoCA) — clinical instrument",
        snippet:
          "30-point screen administered in 10 minutes. Cutoffs: 26+ normal, 18-25 mild cognitive impairment, below 18 dementia.",
      },
      {
        kind: "web",
        url: "https://www.alz.org/alzheimers-dementia/diagnosis/medical_tests",
        title:
          "Alzheimer's Association — Cognitive and functional assessment in primary care",
        snippet:
          "Annual Wellness Visits under Medicare must include a cognitive impairment assessment.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 3 * HOUR),
    created_at: iso(NOW - 38 * HOUR),
  },
  {
    id: SEC_FINANCIAL,
    dossier_id: STRESS3_DOSSIER_ID,
    type: "finding",
    title: "Financial delta — mortgage rate is not the biggest line item",
    content:
      "The 3-percentage-point gap between your locked 4% rate and current 7%+ rates feels like the dominant cost, but it's roughly the third-largest line in the model. Federal Reserve research from 2024 on the \"lock-in effect\" found that the rate spread reduces homeowner mobility by about 16% per percentage point, but the actual dollar impact varies wildly with home value, equity position, and the time horizon you're amortizing over.\n\nFor your situation, the rough orders of magnitude over a 10-year horizon look like this:\n\n| Line item | Approx 10-yr cost | Notes |\n| --- | --- | --- |\n| Property tax delta | $80-160k | Depends entirely on the assessed values in each city; can swing either direction |\n| Spouse's compensation hit | $40-150k+ | If full-remote means a level adjustment or a switch out of his current role |\n| Mortgage rate delta | $60-90k | Real but bounded; assumes you carry a similar balance |\n| Closing costs (sell + buy) | $35-50k | One-time, but front-loaded |\n| Capital gains exposure | $0-30k | $500k exclusion for married-filing-jointly likely covers, but check |\n| Daycare/preschool delta | $5-20k | Typically smaller move-cost than people expect |\n\nThe ranges matter more than the midpoints because they swing the decision. Two specific numbers you don't have yet that would collapse the ranges:\n\n1. **Property tax in mom's city vs. yours.** This is the single largest variable. Property tax can be 0.5% in some states and 2.4% in others — a 4x spread. Your own city's tax is on your last bill; mom's city's tax is on the county assessor's website for any comparable house. Pull both before doing any more modeling.\n2. **Your spouse's actual compensation gap full-remote vs. hybrid.** This requires the manager conversation, not a Levels.fyi guess. If full-remote is available at the same level, the gap is near zero; if it requires a level change or a different role, it can be $50-100k/yr.\n\nClosing costs and capital gains are knowable from your current paperwork. The full model is in Artifacts.\n\nA second-order point: even if the model returns \"moving is somewhat more expensive,\" that might be the right trade. Money is not the only currency. But you're currently making this trade without seeing the bill, which is the actual issue.",
    state: "confident",
    order: 3,
    change_note:
      "Rewrote the comparison as a table once the variances became the main story. The mortgage-rate-as-dominant-line-item framing was wrong and was distorting the conversation.",
    sources: [
      {
        kind: "web",
        url: "https://www.federalreserve.gov/econres/feds/files/2024018pap.pdf",
        title:
          "Federal Reserve — The lock-in effect of rising mortgage rates (2024)",
        snippet:
          "A one-percentage-point rise in the rate gap reduces the probability of moving by about 16%; effects compound at higher gaps.",
      },
      {
        kind: "web",
        url: "https://www.zillow.com/research/2024-housing-market-q4/",
        title: "Zillow Research — 2024 Q4 housing market conditions",
        snippet:
          "Inventory rising, time-on-market lengthening; sell-side prices have softened from 2022 peaks but remain elevated against pre-pandemic.",
      },
      {
        kind: "web",
        url: "https://www.irs.gov/publications/p523",
        title: "IRS Publication 523 — Selling your home",
        snippet:
          "Up to $250,000 ($500,000 if married filing jointly) of gain on the sale of a primary residence can be excluded from income.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 5 * HOUR),
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: SEC_TODDLER,
    dossier_id: STRESS3_DOSSIER_ID,
    type: "finding",
    title: "The 20-month-old will be fine; the parents moving is the bigger risk",
    content:
      "Parental worry about a 20-month-old's adjustment to a move is almost universally calibrated higher than the developmental literature warrants. The short version is: at this age, the secure-attachment relationship lives with the primary caregivers, not with the daycare or the neighborhood, and a child who is securely attached generalizes that attachment to new caregivers within weeks-to-months given basic continuity.\n\nWhat the literature actually shows for the 18-24 month window:\n\n- The Strange Situation work (Ainsworth, 1978) and its replications established that secure attachment at this age is a relational property between child and primary caregiver, not a property of the physical environment. The kid is attached to you, not to the house.\n- The NICHD Study of Early Child Care and Youth Development (initiated 1991, ongoing) followed >1,300 children through to age 15 and found that quality and stability of the *primary caregiver* relationship dominated outcomes over caregiving setting, including changes in daycare provider.\n- Sroufe et al.'s Minnesota Longitudinal Study of Risk and Adaptation (1975-present) tracked attachment patterns from birth through adulthood — the load-bearing finding for your decision is that early caregiver continuity matters far more than environmental continuity at this age.\n- Belsky's 2006 review of daycare-transition research specifically (which is the closest analog to a move) found short-term adjustment effects of 2-8 weeks for most children, with no measurable long-term outcome difference for transitions in the 18-24 month band.\n\nWhat the literature also shows, and what is more relevant to your decision: the *parents'* stress and adjustment to the move predict the child's outcomes more than the move itself does. A move where one parent takes a career hit, the family is financially squeezed, and the parents are second-guessing the decision will produce a worse environment for the child than staying put would have, even if the staying-put case has its own costs. The phrase \"if mama ain't happy, ain't nobody happy\" turns out to be supported by about thirty years of family-systems research.\n\nThe practical implication: take the toddler-impact concern off the top of your decision stack. It's not zero, but it's small and well-bounded compared to the financial and career-trajectory variables. Move it down or out.",
    state: "confident",
    order: 4,
    change_note:
      "Upgraded from provisional once the NICHD and Sroufe citations both checked out and the toddler-attachment sub returned. The finding is robust.",
    sources: [
      {
        kind: "web",
        url: "https://www.nichd.nih.gov/research/supported/seccyd",
        title: "NICHD Study of Early Child Care and Youth Development",
        snippet:
          "Longitudinal study of 1,364 children examining relationships between non-parental child care and developmental outcomes.",
      },
      {
        kind: "web",
        url: "https://innovation.umn.edu/parent-child/",
        title:
          "Minnesota Longitudinal Study of Risk and Adaptation (Sroufe et al.)",
        snippet:
          "Birth-to-adulthood study of attachment, parent-child relationships, and life-course outcomes.",
      },
      {
        kind: "web",
        url: "https://srcd.onlinelibrary.wiley.com/journal/14678624",
        title: "Child Development — peer-reviewed journal of the SRCD",
        snippet:
          "Primary outlet for developmental research including attachment-disruption studies.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 7 * HOUR),
    created_at: iso(NOW - 32 * HOUR),
  },
  {
    id: SEC_CAREER,
    dossier_id: STRESS3_DOSSIER_ID,
    type: "finding",
    title:
      "Spouse's career: full-remote exists for his role but at measurable compensation cost",
    content:
      "The honest read on full-remote for your spouse's role is this: the option exists, the company permits it, but exercising it likely comes with a quiet cost that won't show up in the first year and that you can't measure from outside the building.\n\nWhat we know in the abstract from the post-2023 remote-work-correction literature:\n\n- BLS data through 2024 shows full-remote roles at his function category command a 7-12% lower midpoint compensation than hybrid roles, controlling for level. The gap is not from explicit policy in most cases; it's from the population of full-remote roles being weighted toward smaller firms and contractor arrangements.\n- Promotion velocity research (Bloom et al. 2023, Stanford WFH Research) finds that full-remote workers at firms with hybrid colleagues are promoted at roughly 75% the rate of comparable hybrid colleagues over five years. The mechanism is sponsorship and visibility, not explicit bias, and it is hard to overcome.\n- Microsoft's 2022 Work Trend Index and follow-ups find that managers consistently rate hybrid/in-office collaborators higher on \"team contribution\" measures even when output is comparable, an effect that compounds over review cycles.\n\nWhat we don't know without the manager conversation:\n\n- Whether his specific manager runs a remote-friendly team or a presence-biased one. This dominates everything else.\n- Whether full-remote is a configuration his manager would approve at his current level, or whether it would require a level adjustment or transfer to a different team.\n- Whether his current role-and-team has work that's actually remote-compatible, or whether the 1-2 hybrid days are doing real coordination work that would suffer if removed.\n- Whether there's a pending project or promotion cycle in the next 6-12 months where physical presence would matter disproportionately.\n\nThe career-conversation script in Artifacts is designed to get at all four of these without locking in a decision or signaling intent to move. It's an exploratory conversation, not a notification.\n\nThe one structural thing to flag: if the answer to \"can he go full-remote at his current level\" is no, the financial picture changes hard. A 15-25% comp adjustment over 5-10 years on his earnings dwarfs the mortgage-rate delta. That's the scenario where staying becomes much more clearly correct.",
    state: "provisional",
    order: 5,
    change_note:
      "Provisional pending the actual manager conversation. The general literature is clear; his specific situation is the unknown.",
    sources: [
      {
        kind: "web",
        url: "https://wfhresearch.com/",
        title:
          "Stanford WFH Research — Bloom, Barrero, Davis et al. work-from-home tracking",
        snippet:
          "Ongoing research on remote work patterns, productivity, and career outcomes.",
      },
      {
        kind: "web",
        url: "https://www.bls.gov/news.release/atus.nr0.htm",
        title: "BLS American Time Use Survey — telework supplement",
        snippet:
          "Annual data on the share of work performed remotely by occupation category.",
      },
      {
        kind: "web",
        url: "https://www.microsoft.com/en-us/worklab/work-trend-index",
        title: "Microsoft Work Trend Index — annual hybrid-work research",
        snippet:
          "Survey-based research on manager and employee perceptions of remote and hybrid work.",
      },
    ],
    depends_on: [SEC_FINANCIAL],
    last_updated: iso(NOW - 9 * HOUR),
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: SEC_NETWORK,
    dossier_id: STRESS3_DOSSIER_ID,
    type: "finding",
    title: "Support network: counting what you'd be moving away from",
    content:
      "The current support network in your city is the part of the calculation that is consistently underweighted in moves like this, because it's invisible until you don't have it. List it out concretely:\n\n- Daycare: stable, the kid likes it, you trust the staff. Replacement is non-trivial — daycare quality varies enormously and waitlists in mom's city are unknown. Replacing this is the single biggest network item.\n- Pediatrician: someone who has the kid's full chart, knows you, returns calls. Replaceable but takes 6-18 months to get to the same level of trust.\n- The friends you call at 9pm. The 2-3 households that would take the kid for an evening if one of you was sick. This is the irreplaceable category — it took 2-5 years to build and you cannot speed-run it.\n- The medical/dental/childcare logistics infrastructure: the places you know to take the kid, the urgent-care center, the mom-group pediatric dentist recommendation thread. Granular and slow to rebuild.\n- Your spouse's professional network in the city — colleagues who'd refer him work, people he meets for coffee. Bigger career risk than people typically count.\n\nWhat exists in mom's city:\n\n- Mom herself, which is the entire point of the move. Real and high-value.\n- Whatever network mom has — her doctor, her neighbors, her church or community groups. These are HER network, not yours; some will become yours over time, but slowly, and they don't watch your kid.\n- The thing you'd have to build from zero: daycare, pediatrician, friends. 2-5 years to get to where you are now.\n\nThe asymmetry: you're losing 2-5 years of accumulated support to gain proximity to one person, while being responsible for a 20-month-old. The replacement cost is not small. It's the second-largest hidden cost in the model after the spouse's career, and it doesn't show up on a spreadsheet because nobody charges for the friend who watches your kid for two hours when you have the flu.\n\nThis doesn't argue against the move. It argues that the move needs to clear a higher bar than \"closer is better.\"",
    state: "confident",
    order: 6,
    change_note:
      "Added the explicit list-the-pieces structure after re-reading. The numbered network items are what makes this concrete.",
    sources: [],
    depends_on: [],
    last_updated: iso(NOW - 11 * HOUR),
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: SEC_RULED_PANIC,
    dossier_id: STRESS3_DOSSIER_ID,
    type: "ruled_out",
    title: "Ruled out: move immediately based on the recent ER visit alone",
    content:
      "The recent ER visit was acute, not progressive, and is not on its own evidence of a trajectory that requires immediate action. Selling a 4% mortgage to buy at 7%+ and uprooting the family on the basis of a single high-salience event is the kind of move that, in a year, you look back on as having been driven by panic rather than data. There are paths forward (data-gathering, bridge-visits, conditional triggers) that capture most of the value of the move at much lower irreversibility cost. Ruled out as a stand-alone justification; could become a contributing factor if combined with hard clinical data showing decline.",
    state: "confident",
    order: 7,
    change_note:
      "Ruled out and kept visible so the reader can see the path was considered seriously rather than dismissed.",
    sources: [],
    depends_on: [],
    last_updated: iso(NOW - 24 * HOUR),
    created_at: iso(NOW - 24 * HOUR),
  },
  {
    id: SEC_OPEN,
    dossier_id: STRESS3_DOSSIER_ID,
    type: "open_question",
    title:
      "Open: what does presence actually deliver that proximity provides and distance doesn't?",
    content:
      "This is the load-bearing question the dossier is open on, and it's worth being precise about. \"Proximity\" is being treated in your framing as if it's the unit of family value. But proximity is a delivery mechanism, not the thing itself. The actual deliverables of being closer to mom are a mix of:\n\n- Drop-in availability for emergencies (true and irreplaceable; bridge-visits don't cover this).\n- Routine presence that builds the grandparent-grandchild relationship over time (partially replaceable by structured video + monthly visits at this age — toddler relationships are about repetition, not co-location).\n- Sharing day-to-day caregiving with mom while she's still independent enough to enjoy it (genuinely time-limited; this is the strongest argument for moving sooner).\n- Reducing your own anxiety about distance during her decline (real, but the wrong reason to move 4-5 hours by car given the cost).\n- Being a resource for her household — driving her to appointments, fixing things, picking up groceries (high-value during certain windows, near-zero in others, completely changes once she's not driving anymore).\n\nThe blocker on this section is: which of these does mom actually need from you in the next 12-24 months, and which can be delivered at distance with the bridge-visit pattern? You don't know yet. That's why the bridge pilot exists — to actually find out, in the next two months, before committing.\n\nThe two-month bridge data answers most of this. If two trips a month, plus a structured video routine for the toddler, plus drop-everything-and-fly trips for acute events, covers what mom actually needs at her current functional level — then proximity isn't the right delivery mechanism, frequency is. If the bridge cadence visibly fails to deliver something specific (e.g., you find you keep wishing you could just be there for her routine doctor visits, or the toddler isn't bonding through the video routine), that becomes diagnostic for moving.",
    state: "blocked",
    order: 8,
    change_note:
      "Blocked on the user running the two-month bridge-visit pilot and reporting back. The framework is in place; we need actual data.",
    sources: [],
    depends_on: [SEC_TIMELINE, SEC_NETWORK],
    last_updated: iso(NOW - 4 * HOUR),
    created_at: iso(NOW - 12 * HOUR),
  },
];

// ===========================================================================
// Sub-investigations
// ===========================================================================

const SUB_INVESTIGATIONS: SubInvestigation[] = [
  {
    id: SUB_CLINICAL_ID,
    dossier_id: STRESS3_DOSSIER_ID,
    parent_section_id: SEC_TIMELINE,
    plan_item_id: "stress3-plan-1",
    title: "Clinical trajectory indicators",
    scope:
      "What can you actually measure about mom's trajectory from visits, recent labs, and a check-in with her PCP — what indicators do clinicians track and where does she likely fall on each",
    questions: [
      "What instruments do PCPs routinely use to baseline cognition in 65+ patients (MoCA, MMSE, Mini-Cog)?",
      "What are the IADL/ADL functional indicators and what loss pattern signals progression vs. stability?",
      "What's a reasonable script for asking mom's permission to talk to her PCP, given she's still independent and may resist?",
      "What does the Lancet Commission's 2024 update suggest about modifiable risk and timeline?",
    ],
    state: "blocked",
    return_summary: null,
    findings_section_ids: [],
    findings_artifact_ids: [ART_PCP],
    blocked_reason:
      "Cannot proceed without user confirming whether mom has had a recent cognitive screen and whether she's open to a baselining visit. Drafted the PCP-conversation artifact in the meantime.",
    started_at: iso(NOW - 38 * HOUR),
    completed_at: null,
    why_it_matters:
      "The clinical baseline collapses or expands every other variable in the decision. Without it, every downstream choice is being made on vibes.",
    known_facts: [
      "mom is 68, widowed, lives alone in her own home",
      "she had an ER visit recently that resolved, no admission",
      "she is still driving and managing her own finances per user report",
      "user has noticed unspecified \"signs\" of cognitive or mobility decline over the past 6-12 months",
    ],
    missing_facts: [
      "whether mom has had a MoCA or comparable screen in the last 12 months",
      "her current PCP's read on her trajectory",
      "whether she's had any falls in the past year",
      "whether she'd consent to user being present for a baselining visit",
    ],
    current_finding:
      "Framework in place (IADL/ADL, MoCA cutoffs, Lancet Commission timeline). Cannot place mom on the curve without the user closing the open question.",
    recommended_next_step:
      "User asks mom to schedule a baseline visit with her PCP, frames it as routine annual-wellness rather than \"I'm worried about you,\" and asks to be invited along. Use the script in Artifacts.",
    confidence: "low",
  },
  {
    id: SUB_REMOTE_ID,
    dossier_id: STRESS3_DOSSIER_ID,
    parent_section_id: SEC_CAREER,
    plan_item_id: "stress3-plan-3",
    title: "Hybrid-to-remote career cost",
    scope:
      "What does the post-2023 remote-work-correction literature actually show about full-remote career cost for spouse's role type, and what specifically would the manager conversation need to surface",
    questions: [
      "What is the BLS-data compensation gap between full-remote and hybrid roles in his function category?",
      "What does the Bloom et al. WFH Research consortium find on promotion velocity for full-remote vs. hybrid?",
      "What specific signals from a manager indicate a remote-friendly vs. presence-biased team culture?",
      "What's the right framing for the conversation that gets honest information without locking in a decision?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [SEC_CAREER],
    findings_artifact_ids: [ART_CAREER],
    started_at: iso(NOW - 28 * HOUR),
    completed_at: null,
    why_it_matters:
      "If the answer is \"full-remote isn't actually available at his level,\" the financial picture moves by $50-150k over the planning horizon and the decision shifts hard toward staying.",
    known_facts: [
      "his current role is hybrid, 1-2 office days a week",
      "company-wide policy permits full-remote in principle",
      "general literature shows 7-12% comp gap and 25%+ promotion-velocity gap for full-remote at hybrid firms",
    ],
    missing_facts: [
      "his specific manager's track record with remote direct reports",
      "whether his current role's coordination work is actually remote-compatible",
      "any pending project or promotion cycle in the next 12 months",
    ],
    current_finding:
      "General case is well-characterized; specific case is unknown until the conversation happens.",
    recommended_next_step:
      "Spouse uses the conversation script in Artifacts to open the discussion as exploratory. Aim for a one-on-one rather than a written request.",
    confidence: "medium",
  },
  {
    id: SUB_FINANCIAL_ID,
    dossier_id: STRESS3_DOSSIER_ID,
    parent_section_id: SEC_FINANCIAL,
    plan_item_id: "stress3-plan-2",
    title: "Financial model — sell-and-move vs. stay",
    scope:
      "Build the full financial model across 3-, 5-, and 10-year horizons. Mortgage rate is one line item; quantify property tax delta, closing costs, capital gains, daycare/preschool delta, and spouse's career hit",
    questions: [
      "What's the 10yr cost in each city given current property-tax assessments and likely reassessment on purchase?",
      "What's the closing-cost line on a sell + buy at current market levels?",
      "What's the capital-gains exposure on the current home given purchase price, primary-residence status, and the $500k MFJ exclusion?",
      "How does the spouse's compensation gap, if any, compound over the planning horizon?",
    ],
    state: "delivered",
    return_summary:
      "Built the 3/5/10yr model. Mortgage-rate delta is ~$60-90k over 10yr — real but bounded. Property tax delta swings from -$80k to +$160k depending on the assessed-value comparison between the two cities (not yet known on the buy side). Closing costs $35-50k front-loaded. Capital gains likely covered by $500k MFJ exclusion but check basis. Daycare/preschool delta is small. Spouse's compensation gap is the wild card — at 10% over 10yr it dominates everything else.",
    findings_section_ids: [SEC_FINANCIAL],
    findings_artifact_ids: [ART_FINANCIAL],
    started_at: iso(NOW - 36 * HOUR),
    completed_at: iso(NOW - 22 * HOUR),
    why_it_matters:
      "The financial picture has been emotionally anchored on the mortgage rate. Putting numbers on the actual line items reframes the decision and shows that two specific data points (property tax in mom's city, spouse's true comp gap) collapse most of the uncertainty.",
    known_facts: [
      "current mortgage rate ~4%, current market 7%+",
      "user is married filing jointly, so $500k capital-gains exclusion likely applies",
      "current home was bought enough years ago that exclusion almost certainly covers any gain",
    ],
    missing_facts: [
      "specific property-tax assessment in mom's city for a comparable home",
      "spouse's actual compensation-gap number for full-remote vs. hybrid",
    ],
    current_finding:
      "Model returned. Two data points collapse the uncertainty. See artifact.",
    recommended_next_step:
      "Pull both data points (county assessor's website + manager conversation) and re-run the model with point estimates rather than ranges.",
    confidence: "high",
  },
  {
    id: SUB_TODDLER_ID,
    dossier_id: STRESS3_DOSSIER_ID,
    parent_section_id: SEC_TODDLER,
    plan_item_id: "stress3-plan-4",
    title: "Toddler attachment disruption at 18-24 months",
    scope:
      "What does the developmental-psychology literature say specifically about attachment disruption in the 18-24 month window, and how does it generalize to a residential move plus daycare change",
    questions: [
      "What does Ainsworth's Strange Situation framework predict for moves at this age?",
      "What does the NICHD Study of Early Child Care find about caregiver-stability vs. setting-stability effects?",
      "What are the Sroufe et al. Minnesota Longitudinal findings on early-childhood transitions?",
      "What's Belsky's read on daycare-transition adjustment timelines specifically?",
    ],
    state: "delivered",
    return_summary:
      "The literature is clear and somewhat reassuring. Secure attachment at 18-24 months is a relational property (child-caregiver) not an environmental property (child-house, child-daycare-staff). Transitions in this age band typically show 2-8 weeks of adjustment effects with no measurable long-term differences. The bigger family-systems risk is the parents' stress about the move, which predicts child outcomes more strongly than the move itself does. Practical implication: take this concern off the top of the decision stack.",
    findings_section_ids: [SEC_TODDLER],
    findings_artifact_ids: [],
    started_at: iso(NOW - 32 * HOUR),
    completed_at: iso(NOW - 20 * HOUR),
    why_it_matters:
      "Parental anxiety about toddler-attachment can dominate decisions if not addressed with actual evidence. The literature places it in the right perspective so the parents can decide on the bigger variables.",
    known_facts: [
      "child is 20 months, securely attached to both parents per parental report",
      "currently in daycare 3-4 days/week, has been there since ~14 months",
      "no developmental flags",
    ],
    missing_facts: [
      "any unusual attachment-style indicators (parental report only, not assessed)",
    ],
    current_finding:
      "Move-related risk to the toddler is small and well-bounded. The bigger family-systems risk is parental stress about the decision.",
    recommended_next_step:
      "Drop this from the decision stack as a primary variable. Revisit only if attachment style turns out to be unusual.",
    confidence: "high",
  },
  {
    id: SUB_BRIDGE_ID,
    dossier_id: STRESS3_DOSSIER_ID,
    parent_section_id: SEC_OPEN,
    plan_item_id: "stress3-plan-5",
    title: "Bridge-visit pattern — two trips/month for 6 months",
    scope:
      "Design and pilot a two-trips-per-month bridge cadence as a data-gathering alternative to relocating. What can be learned in 60 days, what the cadence should look like, and what diagnostic signals would push toward moving",
    questions: [
      "What does the relationship-maintenance-at-distance literature show about feasible cadences for elder-relative care?",
      "What does AARP caregiver-support research suggest about distance-caregiving structures that work?",
      "How should the visits be structured — long weekends, mid-week trips, week-long quarterly stays?",
      "What signals during the pilot would be diagnostic for \"this isn't enough, we need to move\" vs. \"this works\"?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [],
    findings_artifact_ids: [ART_BRIDGE],
    started_at: iso(NOW - 18 * HOUR),
    completed_at: null,
    why_it_matters:
      "The bridge pilot is the experimental arm of the data-gathering phase. If it works, you get most of the benefit of moving without the irreversible cost. If it doesn't, the failure mode is itself diagnostic — you'll know what specifically is missing.",
    known_facts: [
      "drive is 4-5 hours, so a long weekend is feasible and a mid-week trip would mean schedule disruption",
      "at least one parent is fully remote and could work from mom's house",
      "20-month-old is at the age where 2-night trips are manageable",
    ],
    missing_facts: [
      "user's actual capacity for 2 trips/month over 6 months given work and toddler logistics",
      "mom's capacity to host frequently — does she enjoy it, or is it tiring",
    ],
    current_finding:
      "Cadence design is feasible on paper; the question is whether the family can sustain it for 6 months and what the visits actually deliver. Schedule template is drafted.",
    recommended_next_step:
      "Run the first 60 days of the cadence as a pilot. Keep a brief log of what each visit delivered (acute care, routine presence, grandparent-grandchild relationship, your own peace of mind). Re-evaluate at month 2.",
    confidence: "medium",
  },
  {
    id: SUB_SIBLINGS_ID,
    dossier_id: STRESS3_DOSSIER_ID,
    parent_section_id: null,
    plan_item_id: null,
    title: "Compare to siblings (abandoned)",
    scope:
      "Could the user's siblings' experience inform the decision — they're in the same position with mom but different constraints",
    questions: [
      "What did the user's brother decide when he faced a similar question?",
      "What did the user's sister decide?",
      "Is there reference-class information in the family that's useful here?",
    ],
    state: "abandoned",
    return_summary:
      "Abandoned. The siblings are in the same position with mom but their constraints (no kids, different careers, different relationships with mom) make their decisions a poor reference class for yours. Reference-class forecasting requires the references to be actually comparable, and these aren't. We'll get more out of running the bridge pilot than out of comparing to the siblings.",
    findings_section_ids: [],
    findings_artifact_ids: [],
    started_at: iso(NOW - 30 * HOUR),
    completed_at: iso(NOW - 22 * HOUR),
    why_it_matters:
      "Reference-class forecasting is sometimes useful, but only when the references are actually comparable. Documenting the abandonment so we don't loop back to it.",
    known_facts: [
      "user has two siblings, both adults",
      "neither sibling has children at home",
      "both live closer to mom than the user does, but neither is in mom's city",
    ],
    missing_facts: [],
    current_finding:
      "Not a useful reference class. Abandoned.",
    recommended_next_step:
      "None. Re-open only if a sibling's situation materially changes.",
    confidence: "high",
  },
];

// ===========================================================================
// Artifacts
// ===========================================================================

const PCP_CONVERSATION_CONTENT = `# Conversation with mom's PCP — permission script and questions

## Step 1: ask mom

Frame this as routine, not as "I'm worried about you." She is more likely to agree if it's about being on the same page than if it's about her decline.

Suggested opening:

> "Mom, I want to be helpful as you get older without being in your business about it. Would it be okay if next time you have a wellness visit, I came along — or you put me on a release so Dr. \[X\] can answer my questions? I just want to be on the same page so I'm not guessing."

If she resists:

> "I'm not asking to take over anything. I'd just rather know what you and your doctor think than imagine the worst from 4 hours away."

Get her to sign a HIPAA release ahead of time if at all possible. Many PCPs have a one-page form for this.

## Step 2: questions for the PCP visit

If you can be there in person, these are the questions to ask, roughly in this order. Don't read them off a list. Bring them with you, but ask them conversationally.

**Baseline:**

1. What's your overall read on her trajectory over the past year or two?
2. Has she had a Montreal Cognitive Assessment (MoCA) or comparable cognitive screen? If not, can we do one today?
3. How does she score on the IADL and ADL scales? (Lawton-Brody is the standard.)
4. Any falls in the past year?
5. Any new medications or dose changes that could be affecting cognition or balance?

**Trajectory:**

6. If you had to characterize her trajectory — stable, slowly declining, or accelerating — what would you say?
7. What would you want me to watch for between now and her next visit?
8. What's the difference between what we're seeing and normal aging at her age?

**Decision-relevant:**

9. If we're trying to decide whether to relocate to be closer, what's your honest read on whether that's premature, well-timed, or overdue?
10. What's the typical timeline from "still independent" to "needs daily check-ins" for someone with her current profile?
11. Are there things you'd recommend doing now (preventively) that would change the trajectory?

## Step 3: write down the answers

The day after the visit, write down what you heard. Memory of medical conversations decays fast, especially when you're emotional. Specific answers to specific questions are what we feed back into the dossier.

## Notes on tone

- Don't ask leading questions. "Is she declining?" is leading. "What's your read on her trajectory?" is not.
- Doctors will hedge in front of patients. If you can get a one-on-one or a follow-up call without mom present, the read will be more honest.
- If the PCP recommends a specialist (geriatrics, neuro, or memory clinic), that's signal. Don't dismiss it.
`;

const FINANCIAL_MODEL_CONTENT = `# Financial model — sell-and-move vs. stay (3/5/10 yr horizons)

All figures are placeholder ranges; replace the bracketed values with your numbers and re-run.

## Inputs you need to fill in

- Current home value (Zestimate or Redfin estimate, then haircut 5-8% for soft market): $\\[\\]
- Current mortgage balance: $\\[\\]
- Current mortgage rate: 4.0% (locked)
- Current monthly P+I: $\\[\\]
- Current annual property tax: $\\[\\]
- Estimated buy-side home value in mom's city (comparable sqft / school quality if relevant): $\\[\\]
- Buy-side property tax assessment (county assessor's website, current owner): $\\[\\]
- Spouse's current TC: $\\[\\]
- Spouse's full-remote TC (post-manager-conversation; if unknown, model 90% of current as a placeholder): $\\[\\]

## Comparison — 10-year horizon

| Line item | Stay | Sell-and-move | Delta |
| --- | --- | --- | --- |
| Mortgage interest paid | (current) | (new at 7%+) | +$60-90k cost |
| Property tax | $\\[\\] x 10 | $\\[\\] x 10 | -$80k to +$160k |
| Closing costs (one-time) | $0 | $35-50k | +$35-50k cost |
| Capital gains (after $500k MFJ exclusion) | $0 | $0-30k | +$0-30k cost |
| Daycare/preschool delta | (current) | (new) | -$5k to +$20k |
| Spouse's compensation hit | $0 | $0-150k+ | +$0 to +$150k cost |
| Travel costs (current bridge visits) | $5-10k | $0 | savings $5-10k |
| **Net 10yr delta** | — | — | **wide range, dominated by property tax and spouse's comp** |

## Reading this

Two specific data points collapse most of the range:

1. Property tax assessment in mom's city for a comparable home. This is publicly knowable from the county assessor's website. Pull it before doing anything else.
2. Spouse's full-remote compensation. This requires the manager conversation.

Once those are point estimates rather than ranges, the entire model collapses by ~80% and the decision becomes much smaller.

## Sensitivity analysis

The output is most sensitive to:

- Property tax delta (if mom's city is significantly cheaper, swings $80-160k in your favor)
- Spouse's comp gap (if there is one, dominates everything)
- Time horizon (5yr vs. 10yr changes the rate-delta line by ~$30k)
- Whether you'd rent rather than buy in mom's city for the first 1-2 years — defers the rate hit, costs you the buy-side appreciation, but optionality has its own value here

## Not in the model

- The non-financial value of being closer to mom during her decline.
- The non-financial cost to you and your spouse of being further from your current support network.
- The optionality value of waiting six months and re-running with better data.

These don't go in the spreadsheet, but they belong in the decision.
`;

const CAREER_CONVERSATION_CONTENT = `# Conversation with your manager — full-remote exploration

## Goal

Get an honest read on (a) whether full-remote is available for your role at your current level, (b) whether your specific manager is remote-friendly or presence-biased, and (c) what compensation/promotion-velocity tradeoffs would attach. Do this without locking in a decision or signaling intent to move.

## Setup

Ask for a one-on-one (not a written request, not in standup, not in a team channel). Frame it as "I want to think through some career trajectory stuff with you" — not as "I'm thinking of moving."

## Opening

> "I wanted to think out loud with you about how you see the next 12-18 months for me. Specifically, I'm curious how you'd think about a fully-remote configuration for someone in my role. I'm not in a rush to change anything, and I'm not signaling intent to move — but family stuff has me thinking about flexibility, and I'd rather have that conversation with you early than late."

## Questions, in this order

1. How do you think about full-remote for someone at my level on this team — is it something we'd entertain, or is it generally a non-starter?
2. If we entertained it, what would change about how the role works day-to-day? What would I need to do differently to make it work?
3. Have you managed remote direct reports before? How did it go?
4. What about promotion velocity — is there an honest gap I should be aware of for full-remote folks in this org?
5. What would you expect to see from me to be confident the configuration is working at the 6-month mark?
6. Is there a project or cycle in the next 12 months where my physical presence would matter disproportionately?

## What you're listening for

- **Remote-friendly signals**: specific examples of remote folks who've succeeded, named promotion examples, willingness to talk concretely about how it would work, comfort with the question.
- **Presence-biased signals**: hedging, "we prefer people in the office for collaboration," vague answers about "individual cases," reference to executive-level remote-skepticism.
- **Compensation signals**: any mention of a level adjustment or band shift, comments about "remote pay zones," reference to a different role being more remote-compatible than yours.
- **Sponsorship signals**: would they personally advocate for the configuration with their boss, or would they be passive about it?

## After the conversation

Write down what was said within 24 hours. Be honest about whether you got a clear read or a hedged one. A hedged read is itself signal.

## Notes

- Do not commit to anything in the conversation. The point is to gather information, not to negotiate.
- If the manager asks "are you considering moving," say something like: "I'm thinking through family stuff and want to know what's possible. Nothing decided." This is true and doesn't lock in a position.
- If the manager pushes for specifics about timing or location, deflect: "I don't have a date in mind. I just want to know what's on the table."
`;

const BRIDGE_SCHEDULE_CONTENT = `# Bridge-visit schedule template — 6 months

Two trips per month for six months. The point is data-gathering, not just family time. Treat each visit as a probe.

## Cadence

- Trip 1 each month: long weekend (Friday-Sunday), one parent + toddler. Driving, mom's house.
- Trip 2 each month: 2-night midweek (Wednesday-Friday) IF the fully-remote parent can flex, otherwise alternate to Saturday-Sunday.

## Schedule (months 1-6)

| Month | Trip 1 dates | Trip 2 dates | Who goes | Notes |
| --- | --- | --- | --- | --- |
| 1 | weekend 1 | weekend 3 | parent A + toddler | establish rhythm |
| 2 | weekend 1 | midweek 3 | parent B + toddler | test midweek |
| 3 | midweek 2 | weekend 4 | both parents + toddler one trip | mom hosts longer |
| 4 | weekend 2 | weekend 4 | parent A + toddler | re-evaluate at month 4 mark |
| 5 | midweek 2 | weekend 4 | parent B + toddler | start to assess sustainability |
| 6 | weekend 1 | weekend 3 | both parents + toddler | decision visit |

## Per-visit log

For each visit, jot down (5 minutes max — a notebook is fine):

- What did this visit deliver? (acute care, routine presence, grandparent-grandchild bonding, your own peace of mind)
- What didn't it deliver? (what did you find yourself wishing you could do that you can't from 4-5 hours away)
- Mom's affect and functional level during the visit. Anything that changed since last time?
- The toddler's behavior with mom. Are they bonding? Do they recognize her?
- Cost: time, money, energy. Honestly.

## Diagnostic signals during the pilot

**Signals that bridge-visits are working:**

- You feel substantially less anxious about distance after months 2-3
- The toddler recognizes mom on video calls between visits and lights up
- Mom's functional level is stable and the visits are enough to track it
- You're not finding yourself wishing you'd just stayed an extra day

**Signals that bridge-visits aren't enough:**

- You keep wishing you could be there for routine appointments (not just acute events)
- The toddler-grandma relationship isn't bonding even with the cadence
- Mom's functional level is changing fast enough that monthly visits don't track it
- The cadence is unsustainable for your work or your spouse's

## Re-decision at month 6

At month 6, sit down with this dossier and the per-visit log. The decision should be much smaller and much clearer at that point. Either the cadence works and you stay, or it doesn't and you move with much better information.
`;

const ARTIFACTS: Artifact[] = [
  {
    id: ART_PCP,
    dossier_id: STRESS3_DOSSIER_ID,
    kind: "script",
    title: "Conversation with mom's PCP — permission + questions",
    content: PCP_CONVERSATION_CONTENT,
    intended_use:
      "Use this in two parts. Part 1 is the script for asking mom's permission to come along to her next PCP visit, or to be put on a HIPAA release. Part 2 is the question list for the visit itself. Don't read off the list; bring it.",
    state: "ready",
    kind_note:
      "Tone is calibrated for a mom who is still independent and may resist the framing — adjust if she's already opened the conversation about her health.",
    supersedes: null,
    last_updated: iso(NOW - 4 * HOUR),
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: ART_FINANCIAL,
    dossier_id: STRESS3_DOSSIER_ID,
    kind: "comparison",
    title: "Financial model — sell-and-move vs. stay (3/5/10 yr)",
    content: FINANCIAL_MODEL_CONTENT,
    intended_use:
      "Fill in the inputs, then look at the comparison table. The point is to see which line items dominate — most of the time, mortgage rate is not the answer.",
    state: "ready",
    kind_note:
      "Treat the ranges as starting points. The two collapsing data points (property tax in mom's city, spouse's full-remote comp) close most of the uncertainty.",
    supersedes: null,
    last_updated: iso(NOW - 6 * HOUR),
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: ART_CAREER,
    dossier_id: STRESS3_DOSSIER_ID,
    kind: "script",
    title: "Conversation with your spouse's manager — full-remote exploration",
    content: CAREER_CONVERSATION_CONTENT,
    intended_use:
      "Give this to your spouse before they request the one-on-one. The script is calibrated to gather information without signaling intent to move.",
    state: "ready",
    kind_note: null,
    supersedes: null,
    last_updated: iso(NOW - 8 * HOUR),
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: ART_BRIDGE,
    dossier_id: STRESS3_DOSSIER_ID,
    kind: "timeline",
    title: "Bridge-visit schedule template — 6 months",
    content: BRIDGE_SCHEDULE_CONTENT,
    intended_use:
      "Print this. Tape it to the fridge. Keep the per-visit log on the same clipboard. The whole point is that the visits become data, not just family time.",
    state: "ready",
    kind_note:
      "The midweek trips depend on the fully-remote parent being able to actually work from mom's house. If that's not feasible, swap in alternate weekends.",
    supersedes: null,
    last_updated: iso(NOW - 2 * HOUR),
    created_at: iso(NOW - 18 * HOUR),
  },
];

// ===========================================================================
// Considered and rejected (12)
// ===========================================================================

const CONSIDERED_AND_REJECTED: ConsideredAndRejected[] = [
  {
    id: "stress3-cr-1",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: null,
    path: "List the house this spring and move within 3-4 months",
    why_compelling:
      "Resolves the anxiety quickly, gets you on-site for whatever's coming with mom, and locks in current sell-side market conditions before they soften further.",
    why_rejected:
      "Decision is being driven by a single high-salience event (the ER visit) rather than by data on mom's actual trajectory. The cost of being wrong is large and irreversible (4% to 7%+ rate, your spouse's career hit, the family system uprooting); the cost of waiting six months for real data is small.",
    cost_of_error:
      "High — $60-150k in lifetime financial cost if mom turns out to be on a 5-year rather than 12-month trajectory, plus the spouse's career hit, plus the friend-network reset.",
    sources: [],
    created_at: iso(NOW - 40 * HOUR),
  },
  {
    id: "stress3-cr-2",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Refuse to consider the move on financial grounds alone (\"we have a 4% mortgage\")",
    why_compelling:
      "The rate-lock-in is real and the rebuy at 7%+ is genuinely expensive. Anchoring the decision on the math is defensible.",
    why_rejected:
      "It's an answer to the wrong question. The move-or-stay decision is multi-variable; treating mortgage rate as the dominant variable misses property tax, spouse's career, support-network replacement, and the actual trajectory of mom's decline. Refusing to engage on financial grounds also forecloses the answer if mom's clinical trajectory turns out to be steeper than expected.",
    cost_of_error:
      "Moderate — could cost you 6-18 months of the \"still useful to each other\" stage with mom if the timeline is shorter than you assumed.",
    sources: [],
    created_at: iso(NOW - 38 * HOUR),
  },
  {
    id: "stress3-cr-3",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: SUB_FINANCIAL_ID,
    path: "Sell now and rent in mom's city for 1-2 years, then re-evaluate",
    why_compelling:
      "Captures most of the proximity benefit while preserving optionality — you don't lock in a 7%+ mortgage on a new home until you know the full picture.",
    why_rejected:
      "Defer rather than reject. It's a real option but it has its own irreversibilities: you've already sold the 4%-mortgage house, so the optionality is asymmetric (you've given up the 4%, can't reclaim it). Worth modeling if the bridge-visit pilot indicates moving but the buy-side timing isn't right.",
    cost_of_error:
      "Medium — you've still incurred the sell-side closing costs and given up the rate.",
    sources: [],
    created_at: iso(NOW - 35 * HOUR),
  },
  {
    id: "stress3-cr-4",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Move mom to your city instead — bring her to where you are",
    why_compelling:
      "Inverts the problem: you keep your support network, your spouse's hybrid job, the toddler's daycare, and you're still co-located with mom. Cleaner cost structure.",
    why_rejected:
      "Mom is 68, widowed, has her own community, her own doctors, her own house. Moving an aging parent away from their established life and into a city where their entire support structure is your nuclear family is its own well-known failure mode — it accelerates social isolation, which is itself a measurable risk factor for cognitive decline. Worth raising with her at some point in the conversation, but not as a default.",
    cost_of_error:
      "High — could measurably accelerate her decline. Don't do this without her active enthusiasm, which she has not expressed.",
    sources: [],
    created_at: iso(NOW - 34 * HOUR),
  },
  {
    id: "stress3-cr-5",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Hire a geriatric care manager to be your eyes and ears in mom's city",
    why_compelling:
      "Solves part of the distance problem directly. A licensed GCM can do quarterly home visits with mom, coordinate with her PCP, and flag changes you wouldn't see from 4-5 hours away. Costs roughly $100-200/hr but the visits are short and infrequent.",
    why_rejected:
      "Defer rather than reject. This is a real and underused tool but it's premature today — you don't even have a clinical baseline yet. Once you have a baseline and the bridge-visit pilot is running, a GCM becomes a valuable supplement, not a replacement. Add to a follow-up dossier.",
    cost_of_error: "Low — small dollar amount, just sequencing.",
    sources: [
      {
        kind: "web",
        url: "https://www.aginglifecare.org/",
        title: "Aging Life Care Association — directory of certified care managers",
        snippet:
          "National organization for credentialed geriatric care managers; maintains a search-by-location directory.",
      },
    ],
    created_at: iso(NOW - 32 * HOUR),
  },
  {
    id: "stress3-cr-6",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: SUB_TODDLER_ID,
    path: "Wait until the toddler is in preschool (3+) before moving — easier transition then",
    why_compelling:
      "Common parental-folk-wisdom argument. The kid will be older, more verbal, more able to articulate feelings about the move.",
    why_rejected:
      "Backwards. The dev-psych literature actually shows the opposite — moves are typically *easier* in the 18-30 month window than at 3-4, because at 3-4 children have formed peer attachments at preschool that they can lose, and they have explicit narratives about \"my house\" and \"my friends.\" If anything, the case for moving sooner rather than later is stronger from a child-development perspective. The constraints on timing here are not the kid.",
    cost_of_error:
      "Low — purely a sequencing argument that doesn't actually drive the decision either way.",
    sources: [],
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: "stress3-cr-7",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: SUB_REMOTE_ID,
    path: "Have your spouse quit and find a fully-remote job in a new company before you move",
    why_compelling:
      "De-risks the career hit by establishing the remote configuration before you've made the move and lost negotiating leverage.",
    why_rejected:
      "Premature and expensive. Job-search cycles are 3-6 months minimum at this level; doing one in parallel with the move-decision conversation creates noise on both sides. If full-remote at his current company is on the table, take it; if it's not, the search is the right answer but only after the decision to move is made, not before.",
    cost_of_error:
      "Medium — opportunity cost of search time and uncertainty during a period that should be data-gathering.",
    sources: [],
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: "stress3-cr-8",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Don't talk to mom's PCP at all — respect her autonomy completely",
    why_compelling:
      "She is 68 and competent. Going behind her back to her doctor is a violation of her autonomy that could damage your relationship.",
    why_rejected:
      "Strawman version of the right concern. The PCP-conversation script is explicitly built around getting her permission first, not around going behind her back. The concern is real but the response is to do the conversation right, not to skip it. You cannot make a rational relocation decision without baseline clinical data, and pretending otherwise is just choosing to make the decision badly.",
    cost_of_error:
      "High — making a $200k+ decision on no clinical data is the actual high-cost path.",
    sources: [],
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: "stress3-cr-9",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: SUB_BRIDGE_ID,
    path: "Bridge-visit cadence of one trip per month rather than two",
    why_compelling:
      "Less disruptive to work and toddler schedule. Sustainable for longer.",
    why_rejected:
      "Probably not enough information density. One visit per month gives you 6 data points over 6 months — sparse enough that you'll be left guessing on trajectory at the re-decision point. Two per month gives 12 points and lets you actually see whether mom is stable or changing month-over-month. The cost difference is small; the diagnostic difference is large.",
    cost_of_error:
      "Moderate — you arrive at the re-decision point with thin data and re-extend the data-gathering phase rather than deciding.",
    sources: [],
    created_at: iso(NOW - 24 * HOUR),
  },
  {
    id: "stress3-cr-10",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Don't bring the toddler on the bridge visits — leave her with daycare and your support network",
    why_compelling:
      "Less travel disruption for the toddler. Visits are more efficient. You're focused on mom rather than wrangling a 20-month-old.",
    why_rejected:
      "Misses the actual point of the bridge cadence. If the toddler isn't on the visits, you're not getting data on the grandparent-grandchild relationship — which is half of why proximity matters in the first place. The whole question is whether mom can have a real relationship with the kid at 4-5 hours, and you can't answer that without testing it.",
    cost_of_error:
      "Medium — you'd arrive at month 6 with no data on the relationship dimension, which is the dimension where bridge-visits are most uncertain.",
    sources: [],
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress3-cr-11",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Decide in 30 days rather than 6 months — \"set a deadline or you'll never decide\"",
    why_compelling:
      "Real concern. Six months is long. Without a deadline, this can drift into \"we'll decide eventually\" and never decide at all.",
    why_rejected:
      "Conflates two things. The recommendation isn't \"don't decide for six months,\" it's \"gather data for six months and re-decide with that data.\" The deadline is real (month 6); the decision will be smaller and clearer at that point because two data points (clinical baseline, spouse's career cost) and the bridge-visit pilot will have collapsed most of the uncertainty. A 30-day deadline forces a decision on incomplete information; a 6-month deadline with explicit data milestones forces a decision on much better information. Different tradeoff.",
    cost_of_error:
      "High if you're actually right about drift — but the milestones built into the plan address that. If you hit month 6 and still don't have the clinical baseline, that's diagnostic for a different problem and we can address it then.",
    sources: [],
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress3-cr-12",
    dossier_id: STRESS3_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Tell mom you're moving and start planning around her response",
    why_compelling:
      "She might be excited about it and that excitement could itself be a deciding factor. Or she might say \"don't bother on my account,\" which would also be informative.",
    why_rejected:
      "Both possible responses are emotionally loaded in ways that contaminate the data. Mom telling you not to move on her account, even if true, often produces the response \"well that's how she'd say it but I should still go\" — which then biases the rest of the decision. And if she's excited, that creates an obligation pressure that biases the decision the other way. Have the conversation, but after you've gathered the clinical and career data, not before.",
    cost_of_error:
      "Moderate — primarily about decision quality rather than direct cost.",
    sources: [],
    created_at: iso(NOW - 12 * HOUR),
  },
];

// ===========================================================================
// Next actions (6)
// ===========================================================================

const NEXT_ACTIONS: NextAction[] = [
  {
    id: "stress3-na-1",
    dossier_id: STRESS3_DOSSIER_ID,
    action:
      "Ask mom to schedule a baseline PCP visit and (if she agrees) to put you on a HIPAA release",
    rationale:
      "Single biggest unknown in the decision. Without a clinical baseline including a cognitive screen, every downstream choice is being made on vibes. Use the script in Artifacts; frame it as routine, not as worry.",
    priority: 1,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 12 * HOUR),
  },
  {
    id: "stress3-na-2",
    dossier_id: STRESS3_DOSSIER_ID,
    action:
      "Pull buy-side property tax assessment from the county assessor's website for a comparable home in mom's city",
    rationale:
      "Closes the largest single uncertainty in the financial model. Public information, takes 20 minutes. Resolves a $240k swing in the 10yr model.",
    priority: 2,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress3-na-3",
    dossier_id: STRESS3_DOSSIER_ID,
    action:
      "Spouse: schedule a one-on-one with manager and use the career-conversation script",
    rationale:
      "Resolves the second-largest uncertainty in the financial model and is the load-bearing input for the spouse-career section. Aim for an exploratory tone, not a notification.",
    priority: 3,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 16 * HOUR),
  },
  {
    id: "stress3-na-4",
    dossier_id: STRESS3_DOSSIER_ID,
    action:
      "Calendar the first 8 weeks of bridge-visits using the schedule template — book trips through month 2",
    rationale:
      "If you don't book the trips now, the cadence won't happen. Two months is the minimum data window before re-evaluating.",
    priority: 4,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress3-na-5",
    dossier_id: STRESS3_DOSSIER_ID,
    action: "Print the bridge-visit per-visit log and put it on the fridge",
    rationale:
      "The visits become data only if you log them. The log takes 5 minutes per visit and is what you'll use at month 6 to re-decide.",
    priority: 5,
    completed: true,
    completed_at: iso(NOW - 3 * HOUR),
    created_at: iso(NOW - 6 * HOUR),
  },
  {
    id: "stress3-na-6",
    dossier_id: STRESS3_DOSSIER_ID,
    action:
      "Set a calendar reminder for month 6 to re-open this dossier with the data collected in the meantime",
    rationale:
      "Six months from now, sit down with this dossier, the per-visit log, the financial model with point estimates, and the clinical baseline. The decision will be much smaller at that point.",
    priority: 6,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 4 * HOUR),
  },
];

// ===========================================================================
// Investigation log — 90 entries
// ===========================================================================

function buildInvestigationLog(): InvestigationLogEntry[] {
  const out: InvestigationLogEntry[] = [];

  const sourceCitations = [
    {
      citation: "Lancet Commission 2024 — Dementia prevention",
      url: "https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(24)01296-0/fulltext",
      why: "Timeline of modifiable decline",
    },
    {
      citation: "Federal Reserve — Lock-in effect of rising mortgage rates 2024",
      url: "https://www.federalreserve.gov/econres/feds/files/2024018pap.pdf",
      why: "Quantifying mobility cost",
    },
    {
      citation: "NICHD Study of Early Child Care and Youth Development",
      url: "https://www.nichd.nih.gov/research/supported/seccyd",
      why: "Toddler caregiver-stability findings",
    },
    {
      citation: "Stanford WFH Research — Bloom et al. work-from-home",
      url: "https://wfhresearch.com/",
      why: "Promotion-velocity and remote-work data",
    },
    {
      citation: "Montreal Cognitive Assessment (MoCA)",
      url: "https://www.parkinson.org/sites/default/files/MoCA-Test-English.pdf",
      why: "Primary-care cognitive screening tool",
    },
    {
      citation: "Zillow Research — 2024 housing market",
      url: "https://www.zillow.com/research/2024-housing-market-q4/",
      why: "Sell-side market conditions",
    },
    {
      citation: "Sroufe et al. Minnesota Longitudinal Study",
      url: "https://innovation.umn.edu/parent-child/",
      why: "Longitudinal attachment outcomes",
    },
    {
      citation: "BLS American Time Use Survey — telework supplement",
      url: "https://www.bls.gov/news.release/atus.nr0.htm",
      why: "Remote-work prevalence by occupation",
    },
    {
      citation: "IRS Publication 523 — Selling your home",
      url: "https://www.irs.gov/publications/p523",
      why: "Capital-gains exclusion rules",
    },
    {
      citation: "Aging Life Care Association",
      url: "https://www.aginglifecare.org/",
      why: "Geriatric care manager directory",
    },
    {
      citation: "Belsky 2006 — daycare transition review",
      url: "https://srcd.onlinelibrary.wiley.com/journal/14678624",
      why: "Daycare-transition adjustment timelines",
    },
    {
      citation: "AARP — distance caregiving research",
      url: "https://www.aarp.org/caregiving/",
      why: "Distance caregiver patterns and challenges",
    },
    {
      citation: "Microsoft Work Trend Index",
      url: "https://www.microsoft.com/en-us/worklab/work-trend-index",
      why: "Manager perceptions of remote work",
    },
    {
      citation: "Lawton-Brody IADL Scale",
      url: "https://consultgeri.org/try-this/general-assessment/issue-23",
      why: "Functional baselining instrument",
    },
  ];

  const summaries = {
    sub_investigation_spawned: [
      "Spawned sub: clinical-trajectory baselining for mom",
      "Spawned sub: hybrid-to-remote career cost for spouse",
      "Spawned sub: full financial model across horizons",
      "Spawned sub: 18-24mo attachment-disruption literature",
      "Spawned sub: bridge-visit pattern as data-gathering",
      "Spawned sub: siblings reference class",
    ],
    sub_investigation_returned: [
      "Sub returned: financial model — property tax and spouse comp dominate",
      "Sub returned: toddler attachment — move risk small at this age",
      "Sub abandoned: siblings reference class — not actually comparable",
    ],
    section_upserted: [
      "Added summary section",
      "Added decline-timeline section",
      "Added financial-delta section",
      "Added toddler-attachment section",
      "Added spouse-career section",
      "Added support-network section",
      "Added ruled-out: panic-move section",
      "Added open-question section: presence vs. proximity",
    ],
    section_revised: [
      "Revised summary — three-stage \"don't list this spring\" framing",
      "Revised financial section — converted to table once variances emerged",
      "Revised toddler section — upgraded provisional to confident after sub returned",
      "Revised support-network section — added explicit list-the-pieces structure",
      "Revised decline-timeline section — added IADL/ADL/MoCA framework",
      "Revised spouse-career section — added BLS and Stanford WFH citations",
    ],
    artifact_added: [
      "Drafted PCP-conversation script (permission + questions)",
      "Drafted financial model template (3/5/10 yr)",
      "Drafted spouse-manager career conversation script",
      "Drafted bridge-visit schedule template",
    ],
    artifact_revised: [
      "Revised PCP script — added HIPAA release framing",
      "Revised financial model — added sensitivity-analysis section",
      "Revised career script — softened opening line",
      "Revised bridge schedule — added per-visit log structure",
    ],
    path_rejected: [
      "Rejected: list the house this spring",
      "Rejected: refuse to consider on financial grounds alone",
      "Deferred: sell now and rent in mom's city",
      "Rejected: move mom to your city",
      "Deferred: hire a geriatric care manager",
      "Rejected: wait until toddler is in preschool",
      "Rejected: have spouse quit and find fully-remote first",
      "Rejected: don't talk to mom's PCP at all",
      "Rejected: bridge-visit cadence of 1/month",
      "Rejected: leave the toddler home for bridge visits",
      "Rejected: 30-day deadline rather than 6 months",
      "Rejected: tell mom you're moving and react to her response",
    ],
    decision_flagged: [
      "Flagged decision: commit to 6-month data-gathering vs. list this spring",
      "Flagged decision: bridge-visit cadence frequency",
    ],
    input_requested: [
      "Requested input: has mom had a cognitive screen in last 12 months?",
      "Requested input: spouse's specific role-and-team remote viability",
    ],
    plan_revised: [
      "Revised plan: reordered items 2 and 3",
      "Revised plan: added explicit gating note that items 4 and 5 are independent",
    ],
    stuck_declared: [
      "Blocked: cannot proceed on clinical-trajectory sub without user-side action",
    ],
  };

  function srcSummary(i: number): string {
    const s = sourceCitations[i % sourceCitations.length];
    return `Read ${s.citation.split("—")[0].trim()} — ${s.why}`;
  }

  for (let i = 0; i < 90; i++) {
    let entry_type: InvestigationLogEntryType;
    const r = i % 18;
    if (r < 8) entry_type = "source_consulted";
    else if (r < 11) entry_type = "section_upserted";
    else if (r < 13) entry_type = "section_revised";
    else if (r < 14) entry_type = "sub_investigation_spawned";
    else if (r < 15) entry_type = "sub_investigation_returned";
    else if (r < 16) entry_type = "artifact_added";
    else if (r < 17) entry_type = "artifact_revised";
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
      summary = srcSummary(i);
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
          SEC_TIMELINE,
          SEC_FINANCIAL,
          SEC_TODDLER,
          SEC_CAREER,
          SEC_NETWORK,
          SEC_RULED_PANIC,
          SEC_OPEN,
        ];
        payload = { section_id: sectionIds[i % sectionIds.length] };
      } else if (
        entry_type === "artifact_added" ||
        entry_type === "artifact_revised"
      ) {
        const ids = [ART_PCP, ART_FINANCIAL, ART_CAREER, ART_BRIDGE];
        payload = { artifact_id: ids[i % ids.length] };
      }
    }

    // Spread entries over the last ~48 hours, newest-first at i=0.
    const createdAt = iso(NOW - i * 30 * MIN);

    const subIds = [
      SUB_CLINICAL_ID,
      SUB_REMOTE_ID,
      SUB_FINANCIAL_ID,
      SUB_TODDLER_ID,
      SUB_BRIDGE_ID,
      SUB_SIBLINGS_ID,
    ];
    const subId = i % 6 === 2 ? subIds[i % subIds.length] : null;

    out.push({
      id: `stress3-log-${String(i).padStart(3, "0")}`,
      dossier_id: STRESS3_DOSSIER_ID,
      work_session_id:
        i < 30 ? "stress3-ws-3" : i < 65 ? "stress3-ws-2" : "stress3-ws-1",
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

export const STRESS3_INVESTIGATION_LOG_COUNTS: Record<string, number> =
  deriveCounts();

// ===========================================================================
// Work sessions (3)
// ===========================================================================

const WORK_SESSIONS: WorkSession[] = [
  {
    id: "stress3-ws-1",
    dossier_id: STRESS3_DOSSIER_ID,
    started_at: iso(NOW - 46 * HOUR),
    ended_at: iso(NOW - 38 * HOUR),
    trigger: "intake",
    token_budget_used: 21600,
    input_tokens: 18400,
    output_tokens: 3200,
    cost_usd: 0.42,
    end_reason: "ended_turn",
  },
  {
    id: "stress3-ws-2",
    dossier_id: STRESS3_DOSSIER_ID,
    started_at: iso(NOW - 28 * HOUR),
    ended_at: iso(NOW - 18 * HOUR),
    trigger: "resume",
    token_budget_used: 33800,
    input_tokens: 27200,
    output_tokens: 6600,
    cost_usd: 0.71,
    end_reason: "ended_turn",
  },
  {
    id: "stress3-ws-3",
    dossier_id: STRESS3_DOSSIER_ID,
    started_at: iso(NOW - 12 * HOUR),
    ended_at: null,
    trigger: "user_open",
    token_budget_used: 12400,
    input_tokens: 10100,
    output_tokens: 2300,
    cost_usd: 0.28,
    end_reason: null,
  },
];

// ===========================================================================
// Reasoning trail (3 entries)
// ===========================================================================

const REASONING_TRAIL: ReasoningTrailEntry[] = [
  {
    id: "stress3-rt-1",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-1",
    note:
      "User came in framing this as binary: sell now or stay. The question itself encodes a panic-driven framing — \"or stay\" is the safety-net option, but the salience of the recent ER visit is doing more work than the user is acknowledging. The first move is to challenge the binary, not to start computing.",
    tags: ["framing", "premise-challenge"],
    created_at: iso(NOW - 44 * HOUR),
  },
  {
    id: "stress3-rt-2",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    note:
      "Financial model came back showing the mortgage-rate gap is dominated by property tax delta and spouse's career cost. Reframing the whole financial section around variance rather than midpoint — the ranges are the story, not the numbers. Two specific data points (tax in mom's city, spouse's full-remote comp) collapse most of the uncertainty, so they become next-actions rather than analysis.",
    tags: ["financial-model", "next-actions"],
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress3-rt-3",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    note:
      "Toddler-attachment sub returned strongly: the kid is fine. The temptation is to re-route that confidence to \"so move,\" but the actual implication is different — it removes one variable from the decision, leaving the other variables (clinical trajectory, career cost, support network) more visible. The bigger family-systems risk is parental stress about the move, which compounds with the other hits. Need to keep the toddler-fine finding from being misread as an argument for moving.",
    tags: ["toddler", "synthesis"],
    created_at: iso(NOW - 7 * HOUR),
  },
];

// ===========================================================================
// Ruled out (2 entries — additional standalone subjects beyond the section)
// ===========================================================================

const RULED_OUT: RuledOut[] = [
  {
    id: "stress3-ro-1",
    dossier_id: STRESS3_DOSSIER_ID,
    subject: "Decision based primarily on the recent ER visit",
    reason:
      "The ER visit was acute and resolved without admission. Acute events are common at 68 and on their own do not predict progressive decline. Treating it as the forcing function would be making a $200k+ irreversible decision on a single data point. Ruled out as a stand-alone justification; remains a contributing factor only if combined with chronic indicators (IADL loss, cognitive screen change, repeat events).",
    sources: [
      {
        kind: "web",
        url: "https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(24)01296-0/fulltext",
        title: "Lancet Commission 2024 — Dementia prevention, intervention, and care",
        snippet:
          "Progressive decline in cognitive function follows measurable trajectories on the order of years; acute events are not predictive on their own.",
      },
    ],
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: "stress3-ro-2",
    dossier_id: STRESS3_DOSSIER_ID,
    subject: "Moving mom to user's city instead",
    reason:
      "Considered as an inversion of the problem. Rejected because moving an aging parent away from their established community accelerates social isolation, which is itself a risk factor for cognitive decline (per the Lancet Commission 14 modifiable risk factors). Mom has not expressed enthusiasm for it, and a forced relocation of an aging parent without their active wish is a known failure mode. Could be reopened only if mom herself raises it.",
    sources: [],
    created_at: iso(NOW - 28 * HOUR),
  },
];

// ===========================================================================
// Pre-visit change log (28 entries — drives the plan-diff sidebar)
// ===========================================================================

export const STRESS3_CHANGE_LOG: ChangeLogEntry[] = [
  {
    id: "stress3-ch-1",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: SEC_SUMMARY,
    kind: "section_updated",
    change_note:
      "Rewrote summary around \"don't list this spring; six months of data first\"",
    created_at: iso(NOW - 50 * MIN),
  },
  {
    id: "stress3-ch-2",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: null,
    kind: "debrief_updated",
    change_note: "Updated all four debrief fields — session closeout",
    created_at: iso(NOW - 35 * MIN),
  },
  {
    id: "stress3-ch-3",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: SEC_FINANCIAL,
    kind: "section_updated",
    change_note: "Converted financial section into a table once variances became the story",
    created_at: iso(NOW - 5 * HOUR),
  },
  {
    id: "stress3-ch-4",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: SEC_TIMELINE,
    kind: "section_updated",
    change_note: "Added IADL/ADL/MoCA framework and Lancet Commission citation",
    created_at: iso(NOW - 3 * HOUR),
  },
  {
    id: "stress3-ch-5",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: SEC_TODDLER,
    kind: "state_changed",
    change_note: "provisional → confident",
    created_at: iso(NOW - 7 * HOUR),
  },
  {
    id: "stress3-ch-6",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: null,
    kind: "sub_investigation_completed",
    change_note: "Toddler-attachment sub returned: move risk is small at this age",
    created_at: iso(NOW - 20 * HOUR),
  },
  {
    id: "stress3-ch-7",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: null,
    kind: "sub_investigation_completed",
    change_note: "Financial-model sub returned: property tax and spouse comp dominate",
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress3-ch-8",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: null,
    kind: "sub_investigation_abandoned",
    change_note: "Siblings reference class abandoned — not actually comparable",
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress3-ch-9",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: null,
    kind: "sub_investigation_spawned",
    change_note: "Spawned bridge-visit pattern sub-investigation",
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress3-ch-10",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: SEC_OPEN,
    kind: "needs_input_added",
    change_note: "Opened: has mom had a cognitive screen in the last 12 months?",
    created_at: iso(NOW - 12 * HOUR),
  },
  {
    id: "stress3-ch-11",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: null,
    kind: "decision_point_added",
    change_note: "Decision: 6-month data-gathering phase vs. list this spring",
    created_at: iso(NOW - 4 * HOUR),
  },
  {
    id: "stress3-ch-12",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: null,
    kind: "considered_and_rejected_added",
    change_note: "Rejected: tell mom you're moving and react to her response",
    created_at: iso(NOW - 12 * HOUR),
  },
  {
    id: "stress3-ch-13",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: null,
    kind: "next_action_added",
    change_note: "Schedule mom's PCP visit and HIPAA release",
    created_at: iso(NOW - 12 * HOUR),
  },
  {
    id: "stress3-ch-14",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: null,
    kind: "next_action_added",
    change_note: "Pull buy-side property tax assessment",
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress3-ch-15",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: null,
    kind: "next_action_added",
    change_note: "Spouse: schedule one-on-one for full-remote conversation",
    created_at: iso(NOW - 16 * HOUR),
  },
  {
    id: "stress3-ch-16",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: null,
    kind: "artifact_added",
    change_note: "Drafted bridge-visit schedule template",
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress3-ch-17",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-3",
    section_id: null,
    kind: "artifact_updated",
    change_note: "Revised bridge schedule — added per-visit log structure",
    created_at: iso(NOW - 2 * HOUR),
  },
  {
    id: "stress3-ch-18",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: null,
    kind: "artifact_added",
    change_note: "Drafted spouse-manager career-conversation script",
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress3-ch-19",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: null,
    kind: "artifact_added",
    change_note: "Drafted financial model template (3/5/10 yr)",
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: "stress3-ch-20",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: null,
    kind: "artifact_added",
    change_note: "Drafted PCP-conversation script (permission + questions)",
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: "stress3-ch-21",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: SEC_NETWORK,
    kind: "section_created",
    change_note: "Added support-network section",
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: "stress3-ch-22",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: SEC_CAREER,
    kind: "section_created",
    change_note: "Added spouse-career section",
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: "stress3-ch-23",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-2",
    section_id: SEC_RULED_PANIC,
    kind: "ruled_out_added",
    change_note: "Ruled out: move based on recent ER visit alone",
    created_at: iso(NOW - 24 * HOUR),
  },
  {
    id: "stress3-ch-24",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-1",
    section_id: null,
    kind: "plan_updated",
    change_note: "Plan reordered — items 2 and 3 swapped, item 5 gating made explicit",
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: "stress3-ch-25",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-1",
    section_id: null,
    kind: "working_theory_updated",
    change_note: "Initial working theory: don't sell now; six-month data-gathering phase",
    created_at: iso(NOW - 40 * HOUR),
  },
  {
    id: "stress3-ch-26",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-1",
    section_id: null,
    kind: "sub_investigation_spawned",
    change_note: "Spawned clinical-trajectory sub-investigation",
    created_at: iso(NOW - 38 * HOUR),
  },
  {
    id: "stress3-ch-27",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-1",
    section_id: null,
    kind: "sub_investigation_spawned",
    change_note: "Spawned hybrid-to-remote career-cost sub-investigation",
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: "stress3-ch-28",
    dossier_id: STRESS3_DOSSIER_ID,
    work_session_id: "stress3-ws-1",
    section_id: SEC_SUMMARY,
    kind: "section_created",
    change_note: "Initial summary section drafted from intake",
    created_at: iso(NOW - 42 * HOUR),
  },
];

// ===========================================================================
// Export the full DossierFull
// ===========================================================================

export const stress3CaseFile: DossierFull = {
  dossier: DOSSIER,
  sections: SECTIONS,
  needs_input: [
    {
      id: "stress3-ni-1",
      dossier_id: STRESS3_DOSSIER_ID,
      question:
        "Has mom had a cognitive screen (MoCA, MMSE, Mini-Cog, or equivalent) in the last 12 months, and if so, what was the result? If she hasn't, can you get her to one in the next 60 days — this is the single biggest unknown in the entire decision, and we cannot calibrate the timeline without it. The PCP-conversation script in Artifacts has language for asking her in a way that doesn't feel like an intervention.",
      blocks_section_ids: [SEC_TIMELINE, SEC_OPEN],
      created_at: iso(NOW - 12 * HOUR),
      answered_at: null,
      answer: null,
    },
  ],
  decision_points: [
    {
      id: "stress3-dp-1",
      dossier_id: STRESS3_DOSSIER_ID,
      title:
        "Commit to a 6-month data-gathering phase (PCP visit, manager conversation, bridge-visit pilot), or put the house on the market this spring?",
      options: [
        {
          label:
            "Commit to 6-month data-gathering phase; re-decide at month 6 with real data",
          implications:
            "Holds the irreversible move-decision until you have a clinical baseline on mom, a real career-cost number from your spouse's manager, and 12 bridge-visit data points on whether presence-at-distance handles what mom actually needs. Costs you 6 months of optionality and a few thousand in travel; gains you a decision made on data rather than panic. If mom's trajectory turns out to be steeper than expected (second acute event in 60 days, MoCA below 26), the plan accelerates automatically.",
          recommended: true,
        },
        {
          label: "List the house this spring",
          implications:
            "Resolves the anxiety quickly and gets you on-site for whatever's coming. Locks you into selling at 4% rate and rebuying at 7%+, plus the spouse's likely career hit, plus the support-network reset, on the basis of a single high-salience event (the ER visit) without clinical trajectory data. Reversal is expensive: you cannot un-sell the 4% mortgage. If mom turns out to be on a 5-10 year trajectory rather than a 12-month one, this is a $100-200k+ regret.",
          recommended: false,
        },
      ],
      recommendation:
        "6-month data-gathering phase. The cost of waiting is small; the cost of selling on bad data is large. The plan has an explicit acceleration trigger if mom's situation changes, so the data-gathering doesn't lock you in if the timeline turns out to be tighter.",
      blocks_section_ids: [SEC_OPEN],
      created_at: iso(NOW - 4 * HOUR),
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
