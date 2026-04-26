// Day-5 stress fixture #4. A career-pivot decision memo: 37yo pharmacy
// technician (8+ years) self-teaching her way into healthcare data
// analytics. Domain: drug data, prior-auth, NCPDP/837/835, controlled
// substances. Currently mid-bootcamp (SQL/Python/Pandas), no portfolio.
// The agent's task is not to estimate "realism" as a percentage but to
// reframe the question into "which plan, on what timeline, with what
// portfolio." Two real GitHub/LinkedIn references appear ONLY as
// analytical anchors in the comparable-trajectories sub-investigation.

import type {
  Artifact,
  ChangeLogEntry,
  ConsideredAndRejected,
  DecisionPoint,
  DossierFull,
  InvestigationLogEntry,
  InvestigationLogEntryType,
  NeedsInput,
  NextAction,
  ReasoningTrailEntry,
  RuledOut,
  Section,
  SubInvestigation,
  WorkSession,
} from "../api/types";

export const STRESS4_DOSSIER_ID = "stress4-pivot-pharmtech";

const NOW = Date.now();
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

const iso = (ms: number) => new Date(ms).toISOString();

// ---------- sub-investigation ids ----------

const SUB_TRAJECTORIES_ID = "stress4-sub-comparable-trajectories";
const SUB_SUNSHINEKEYS_ID = "stress4-sub-ref-sunshinekeys";
const SUB_MERRIGAN_ID = "stress4-sub-ref-megan-merrigan";
const SUB_PORTFOLIO_ID = "stress4-sub-portfolio-spec";
const SUB_TARGET_ROLES_ID = "stress4-sub-target-roles";
const SUB_BOOTCAMP_AUDIT_ID = "stress4-sub-bootcamp-audit";

// ---------- section ids ----------

const SEC_SUMMARY = "stress4-sec-summary";
const SEC_REFRAME = "stress4-sec-reframe";
const SEC_DOMAIN_WEDGE = "stress4-sec-domain-wedge";
const SEC_TARGET_ROLES = "stress4-sec-target-roles";
const SEC_TIMELINE = "stress4-sec-timeline";
const SEC_PORTFOLIO = "stress4-sec-portfolio";
const SEC_BOOTCAMP_LIMITS = "stress4-sec-bootcamp-limits";
const SEC_RULED_GENERIC = "stress4-sec-ruled-generic-da";
const SEC_OPEN_WEDGE = "stress4-sec-open-wedge";

// ---------- artifact ids ----------

const ART_PORTFOLIO_SPEC = "stress4-art-portfolio-spec";
const ART_BOOTCAMP_CHECKLIST = "stress4-art-bootcamp-checklist";
const ART_WEDGE_SCRIPT = "stress4-art-wedge-script";
const ART_QUERY_TEMPLATES = "stress4-art-query-templates";

// ===========================================================================
// Dossier
// ===========================================================================

const DOSSIER = {
  id: STRESS4_DOSSIER_ID,
  title:
    "Career pivot at 37 — pharmacy tech to healthcare data analytics, self-taught bootcamp path (realism, timeline, leverage)",
  problem_statement:
    "37yo woman, 8+ years pharmacy tech (workflow, drug data, insurance/prior-auth, controlled substances), 4 prior years retail, no CS/stats degree. Currently part-time online bootcamp covering SQL, Python, Pandas, light Tableau, plus crash courses. No portfolio yet. Asks: how realistic is the pivot to healthcare data analytics on a self-taught path, what timeline, what would maximize odds. Reference comparators surfaced at intake: github.com/SunshineKeys, linkedin.com/in/megan-merrigan-a824a1265.",
  out_of_scope: [
    "PharmD or other clinical degree paths (user has explicitly ruled out further clinical training)",
    "Returning to retail at higher comp",
    "Non-healthcare data roles at FAANG / generic tech",
    "Coding bootcamps focused on web/SWE",
    "Visa/relocation considerations (US-based, not relocating)",
  ],
  dossier_type: "decision_memo" as const,
  status: "active" as const,
  check_in_policy: {
    cadence: "on_demand" as const,
    notes:
      "Pause between user turns. Resume when user answers the open wedge question (which pharmacy-workflow problem she can explain in 90 seconds and draw a data-flow for) — that answer materially shifts portfolio recommendations.",
  },
  last_visited_at: iso(NOW - 14 * HOUR),
  created_at: iso(NOW - 2 * DAY),
  updated_at: iso(NOW - 18 * MIN),
  debrief: {
    what_i_did:
      "Two sessions of investigation across four threads: (1) reframed the original question away from a single \"realism percentage\" toward a plan-conditional answer (which plan, what timeline, what portfolio); (2) surveyed comparable trajectories from pharmacy-tech / clinical-adjacent roles into healthcare data, including two profiles the user surfaced at intake; (3) mapped the realistic target-role spectrum across health systems, PBMs, and specialty pharmacies versus the generic-data-analyst path she was implicitly anchoring on; (4) drafted a four-artifact toolkit — portfolio project spec, bootcamp-output audit checklist, hiring-manager 90-second wedge script, and a set of target-role search query templates. Two sub-investigations are still running (specialty-pharmacy job-market depth, bootcamp portfolio-output audit). One was abandoned after the working theory absorbed its premise.",
    what_i_found:
      "Three findings worth front-loading. (1) The user's actual edge is not technical — it is being a clinical-to-data translator. A CS-only candidate can write the same SQL, but cannot explain why a PA denial cascades into a 72-hour fill delay or what an NCPDP reject code 70 means at the bench. That asymmetry is what hiring managers in payer-side analytics, PBMs, and health-system operations actually pay for. (2) The realistic timeline on a domain-bridging plan is 9–15 months to first offer, not 4–6, and not 24+. The 4–6 month bootcamp-grad-to-data-analyst story is dominated by CS-degreed candidates and does not generalize to her path; the 24+ month \"go get a stats degree\" story is overkill for the entry roles that fit her wedge. (3) Portfolio gating is the single highest-leverage variable. Two-to-three projects that no CS-only grad could plausibly produce — a prior-auth approval-rate analysis, a controlled-substance dispensing pattern detector, and a formulary tier-change impact projection — flip her from \"another self-taught applicant\" to \"the only candidate who has actually seen this data domain.\"",
    what_you_should_do_next:
      "Answer the open wedge question (which workflow problem she can explain in 90s and draw a data flow for). That answer determines which of the three portfolio projects she should ship first. In parallel, audit her current bootcamp output against the checklist artifact — most online bootcamps generate Kaggle-style work that does not transfer; we need to know what's actually shippable from her existing coursework before specifying new work.",
    what_i_couldnt_figure_out:
      "Two open threads. First, the actual hiring funnel composition for entry-level analytics roles inside PBMs and health systems is opaque from the outside — public job postings overstate the technical bar relative to what hiring managers actually screen on. We have triangulated this from BLS, Course Report, and a handful of Reddit/Blind threads, but a single conversation with a working healthcare-analytics hiring manager would resolve more than another five hours of desk research. Second, the comparator profiles surfaced at intake are partial — one fetched cleanly and gives us a useful proof-of-existence anchor; the other could not be verified by the agent (LinkedIn blocks unauthenticated fetch). We treat them both as analytical reference points, not as personal subjects.",
    last_updated: iso(NOW - 35 * MIN),
  },
  premise_challenge: {
    original_question:
      "How realistic is it for me, at 37 with no CS or stats degree and a part-time bootcamp, to pivot from pharmacy tech into healthcare data analytics — and what's the timeline?",
    hidden_assumptions: [
      "that \"realism\" can be answered as a single percentage rather than as a function of which plan she actually runs",
      "that the bottleneck is technical skill (SQL/Python depth) when it is more likely portfolio depth and healthcare-domain bridging",
      "that the right comparison class is generic bootcamp graduates competing against CS-degreed entry-level candidates, when her actual comparison class is clinical-adjacent professionals pivoting into HEALTHCARE-specific analytics — a much more favorable bracket",
      "that 37 is a meaningful obstacle in healthcare-adjacent analytics, when in fact health-system and payer-side analytics teams skew older and value clinical exposure more than youth",
      "that self-taught means competing on technical merit rather than on the clinical-to-data translator wedge that no CS-only candidate can replicate",
    ],
    why_answering_now_is_risky:
      "A confident percentage now anchors the user to the wrong reference class (generic bootcamp grads vs CS-degreed candidates) and pushes her toward the wrong job-search target (\"data analyst\" at tech-adjacent companies, where she will lose). A pessimistic number could halt a pivot that is genuinely high-odds on the domain-bridging plan; an optimistic one could waste 6 months on a plan that will not work. The honest answer is conditional, and any single-number response loses the conditional.",
    safer_reframe:
      "Replace \"how realistic\" with three sequenced questions: (1) Which plan are you running — domain-bridging into healthcare-specific analytics, or generic data-analyst into tech-adjacent? (2) What is the entry comp band, the time-to-first-offer, and the role mix you would consider acceptable on each? (3) What single piece of evidence at month 4 (one shippable portfolio project showing healthcare-data fluency) flips the working theory from medium to high confidence? Answer those, and the realism question dissolves into a plan-comparison.",
    required_evidence_before_answering: [
      "which 1-2 pharmacy-workflow problems she can explain in 90 seconds and sketch a data flow for (the wedge test)",
      "current bootcamp output audited against the checklist (what is actually shippable vs Kaggle-toy)",
      "her tolerance for the entry comp band on the domain-bridging path (typically $60-80k starting in health-system analytics) vs the generic path (typically $55-75k starting in tech-adjacent)",
      "geographic constraints — domain-bridging roles cluster around major health systems (Kaiser/Northern CA, Geisinger/PA, Intermountain/UT) and PBM hubs (Express Scripts/St. Louis, OptumRx/MN)",
      "willingness to spend 6-9 months building 2-3 healthcare-specific portfolio projects before applying broadly, vs spraying applications now",
    ],
    updated_at: iso(NOW - 2 * DAY + 12 * MIN),
  },
  working_theory: {
    recommendation:
      "Realistic on a 9-15 month timeline IF she runs the domain-bridging plan, not the technical-overlap plan. Target operations analyst, claims analyst, and clinical-analytics roles inside health systems, PBMs, and specialty pharmacies — not generic \"data analyst\" at tech companies. Build 2-3 portfolio projects no CS-only grad could plausibly produce: prior-auth approval-rate analysis, controlled-substance dispensing pattern detection, formulary tier-change impact projection. Lead every application with the clinical-to-data translator framing, not the bootcamp credential.",
    confidence: "medium" as const,
    why:
      "The pharmacy-tech-to-healthcare-data trajectory is well-trodden enough to find at least one credible public comparator (Megan Merrigan / SunshineKeys, ex-Change Healthcare pharmacy operations, currently building healthcare-data portfolio). BLS projects 23% growth in operations research analyst roles through 2032 with health systems among the top three demand sources. Healthcare data is structurally messy in ways (NCPDP reject codes, 837/835 claim segmentation, prior-auth workflow) that reward domain experience disproportionately. The path's failure mode is well-understood: applying as a generic data analyst into a CS-degreed funnel.",
    what_would_change_it:
      "One shippable healthcare-domain portfolio project at month 4 would flip confidence from medium to high — that single artifact disambiguates her from the generic self-taught pool faster than any other signal. Conversely, if month 4 arrives with only Kaggle Titanic / housing-prices style work, the timeline likely extends to 18+ months and the plan needs revision toward a junior PBM analyst track that explicitly tolerates training-on-the-job.",
    unresolved_assumptions: [
      "current bootcamp will produce SQL/Pandas fluency at the level needed (vs trailing CS-grad fluency by 6+ months) — needs the bootcamp-output audit to confirm",
      "she has access to enough de-identified or synthetic pharmacy data to build the proposed portfolio projects without IP/HIPAA exposure from her current employer",
      "geographic flexibility includes at least one PBM or major health-system metro, OR she is willing to take a remote-first claims-analyst role at lower starting comp",
    ],
    updated_at: iso(NOW - 50 * MIN),
  },
  investigation_plan: {
    items: [
      {
        id: "stress4-plan-1",
        question:
          "What is the realistic comparable-trajectory profile for a pharmacy tech transitioning to healthcare data analytics on a self-taught path?",
        rationale:
          "Anchors the realism conversation in actual examples rather than abstract odds. Determines whether to treat this as a well-trodden path or a novel one.",
        expected_sources: [
          "github.com/SunshineKeys",
          "linkedin.com/in/megan-merrigan-a824a1265",
          "BLS Occupational Outlook Handbook",
          "Course Report bootcamp outcomes data",
        ],
        as_sub_investigation: true,
        status: "completed" as const,
      },
      {
        id: "stress4-plan-2",
        question:
          "What target-role spectrum (operations analyst, claims analyst, clinical analytics, PBM analyst, specialty-pharmacy analyst) is realistically open at entry level given her profile?",
        rationale:
          "The realism question is downstream of which roles she is actually targeting. Generic data analyst at tech companies has a different funnel than claims analyst at a regional health system.",
        expected_sources: [
          "indeed.com job postings",
          "linkedin.com job postings",
          "PBM company career sites",
          "health-system analytics team org charts",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
      {
        id: "stress4-plan-3",
        question:
          "What 2-3 portfolio projects would best demonstrate the clinical-to-data translator wedge to healthcare hiring managers, and how should they be scoped to be shippable in 6-9 months?",
        rationale:
          "Portfolio depth is the single highest-leverage variable identified. Concrete project specs are deliverable artifacts; vague \"build a portfolio\" advice is not.",
        expected_sources: [
          "synthetic claims datasets (CMS public-use)",
          "NCPDP standards documentation",
          "FHIR R4 reference",
          "Epic Clarity schema overview (publicly available)",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
      {
        id: "stress4-plan-4",
        question:
          "What does her current bootcamp output actually contain, and what gaps need to be filled before the portfolio projects are buildable?",
        rationale:
          "Most online bootcamps generate Kaggle-toy work that does not transfer. We need to know what is actually shippable from existing coursework before specifying new work.",
        expected_sources: [
          "user-paste of bootcamp curriculum",
          "user-paste of completed coursework",
          "Course Report bootcamp reviews",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
      {
        id: "stress4-plan-5",
        question:
          "What is a realistic entry comp band for the domain-bridging path versus the generic data-analyst path, and what is her tolerance for each?",
        rationale:
          "Comp expectations drive whether a 9-15 month plan is acceptable at all. If she needs $90k+ at first offer, the plan must be different.",
        expected_sources: [
          "BLS wage data",
          "Glassdoor",
          "levels.fyi healthcare segment",
          "user-paste of current pharmacy-tech comp",
        ],
        as_sub_investigation: false,
        status: "planned" as const,
      },
    ],
    rationale:
      "Plan structure: comparable-trajectories first (item 1) to anchor the conversation, then target roles (item 2) and portfolio specs (item 3) in parallel because they inform each other. Bootcamp audit (item 4) runs alongside because gaps there change the portfolio scope. Comp-band conversation (item 5) is gated on items 1-4 because the realistic comp depends on which path she runs.",
    drafted_at: iso(NOW - 2 * DAY + 25 * MIN),
    approved_at: iso(NOW - 2 * DAY + 40 * MIN),
    revised_at: iso(NOW - 22 * HOUR),
    revision_count: 1,
  },
};

// ===========================================================================
// Sections
// ===========================================================================

const SECTIONS: Section[] = [
  {
    id: SEC_SUMMARY,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "summary",
    title: "Where this stands",
    content:
      "The question \"how realistic is this pivot\" assumes the answer is a percentage. It is not. Realism here is a function of which plan she runs. The technical-overlap plan (compete with CS-degreed bootcamp grads on SQL/Python depth, target generic data-analyst roles at tech companies) is genuinely hard at 37 with no CS background — that is not the plan to run. The domain-bridging plan (lead with 8+ years of pharmacy-workflow fluency, target operations analyst / claims analyst / clinical analytics inside health systems, PBMs, and specialty pharmacies, ship 2-3 portfolio projects no CS-only candidate could plausibly produce) is realistic on a 9-15 month timeline. The single highest-leverage variable is whether she has shipped one healthcare-domain portfolio project by month 4 — that artifact disambiguates her from the generic self-taught pool faster than any credential. Open question on which workflow problem she can wedge on; tactical artifacts (portfolio spec, bootcamp audit checklist, 90-second wedge script, target-role query templates) are drafted and ready.",
    state: "confident",
    order: 1,
    change_note:
      "Rewrote summary to lead with the plan-conditional framing after the premise-challenge surface hardened. Removed the \"X% chance\" anchoring entirely.",
    sources: [],
    depends_on: [],
    last_updated: iso(NOW - 50 * MIN),
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: SEC_REFRAME,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "finding",
    title: "Reframe — the question is plan-conditional, not probabilistic",
    content:
      "The original question — \"how realistic is this pivot\" — has a hidden structure that needs to be surfaced before any answer can be useful. Three observations:\n\nFirst, asking for realism as a percentage implicitly assumes a single fixed plan against which odds can be calculated. There is no single fixed plan here; there are at least two materially different ones (technical-overlap vs domain-bridging), and the realism numbers for those two plans differ by something like 3x. Quoting a single percentage for \"the pivot\" averages across plans she would never actually choose to run and produces a number that is wrong for both.\n\nSecond, the comparison class she is implicitly using is generic bootcamp graduates competing against CS-degreed candidates for entry-level data-analyst roles at tech-adjacent companies. That is a brutal funnel — the realistic acceptance rate from bootcamp-only background is in the high single digits per Course Report's 2023 outcomes data, and selection effects make even that number optimistic. But that is not her comparison class. Her actual comparison class is clinical-adjacent professionals pivoting into HEALTHCARE-specific analytics, which is a much more favorable bracket because clinical fluency is the scarce input there.\n\nThird, \"make it or don't\" is the wrong outcome variable. The right outcome variables are time-to-first-offer, entry comp band, and role mix. The pivot is realistic on all three for the domain-bridging plan; it is not realistic on any of the three for the technical-overlap plan. Producing a single number for either flattens the actual decision space.\n\nReframe: the question becomes \"which plan do you want to run, and what does month-4 evidence look like under each?\" That question is answerable and decision-useful.",
    state: "confident",
    order: 2,
    change_note:
      "Promoted from provisional after the premise-challenge surface and the comparable-trajectories sub returned consistent signals.",
    sources: [
      {
        kind: "web",
        url: "https://www.coursereport.com/reports/2023-coding-bootcamp-outcomes-report",
        title: "Course Report — 2023 Coding Bootcamp Outcomes & Demographics",
        snippet:
          "Self-reported placement rates from bootcamps cluster around 70-80% within 12 months but include any \"data-related\" role; selection bias is meaningful.",
      },
      {
        kind: "web",
        url: "https://www.bls.gov/ooh/math/operations-research-analysts.htm",
        title: "BLS Occupational Outlook — Operations Research Analysts",
        snippet:
          "Projected 23% growth 2022-2032; healthcare and finance among top demand sources.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 90 * MIN),
    created_at: iso(NOW - 38 * HOUR),
  },
  {
    id: SEC_DOMAIN_WEDGE,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "finding",
    title: "The clinical-to-data translator wedge — what hiring managers actually pay for",
    content:
      "Here is the asymmetry that makes this pivot tractable. A CS-degreed entry-level data analyst can write the same SQL she will write. They can write it faster, with cleaner abstractions, with better testing discipline, and they will still be net-worse for a healthcare-analytics hiring manager than a candidate who can answer questions like:\n\n- Why does an NCPDP reject code 70 (\"product/service not covered\") cascade into a 72-hour fill delay even after the prior auth comes back approved?\n- What's the difference between a formulary tier change that affects a maintenance medication versus an acute medication, and why does the latter generate ED utilization that the former does not?\n- When you see a sudden spike in 837P claims with modifier 25 on the same date as an E/M code, what is the workflow upstream that produced that pattern?\n- For a controlled-substance dispense, what counts as a \"corresponding responsibility\" review under the DEA's framework, and how does that show up in dispensing-system audit logs?\n\nThese are not trick questions. They are the questions that come up in week one of an operations-analytics or claims-analytics role at a PBM or health system, and the answers are not in any data-analyst curriculum. They are in eight years of working the pharmacy bench. A CS-only candidate has to learn them on the job, badly, over six months, while the work-product they generate is wrong in ways their manager cannot even diagnose because the manager often does not have the clinical fluency either.\n\nHiring managers in healthcare analytics know this. They will hire the clinical-fluent candidate with weaker SQL over the SQL-fluent candidate with no clinical context, because the SQL is teachable in three months and the clinical fluency is not teachable in three years. The wedge is real. The mistake the user is making — and that this dossier is built around correcting — is leading with the bootcamp credential instead of leading with the wedge.",
    state: "confident",
    order: 3,
    change_note:
      "Hardened from provisional after triangulating with two LinkedIn job postings (Geisinger Operations Analyst, OptumRx Claims Analyst II) and one trade-press piece on healthcare-analytics hiring.",
    sources: [
      {
        kind: "web",
        url: "https://www.cms.gov/medicare/coverage/coverage-with-evidence-development/ncpdp",
        title: "CMS — NCPDP standards reference",
        snippet:
          "National Council for Prescription Drug Programs standards govern pharmacy claims transactions; reject codes are standardized.",
      },
      {
        kind: "reasoning",
        title: "Triangulation note",
        snippet:
          "Cross-referenced three current job postings against the wedge questions; all three explicitly named at least two of the four asymmetries.",
      },
    ],
    depends_on: [SEC_REFRAME],
    last_updated: iso(NOW - 4 * HOUR),
    created_at: iso(NOW - 32 * HOUR),
  },
  {
    id: SEC_TARGET_ROLES,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "finding",
    title: "Target-role spectrum — health systems, PBMs, specialty pharmacies",
    content:
      "Five role buckets that fit the wedge, ordered roughly by accessibility from her current profile:\n\n1. **Operations analyst at a regional health system** (Kaiser Permanente Northern California, Geisinger PA, Intermountain UT, Sutter Health, Providence). Entry comp $62-78k. Day-one work: pulling SQL against Epic Clarity, building Tableau dashboards for clinic operations, supporting workflow-redesign projects. Pharmacy-workflow fluency is directly load-bearing for the pharmacy-operations subset of these teams.\n\n2. **Claims analyst at a PBM** (Express Scripts/Cigna in St. Louis, OptumRx in Minnesota, CVS Caremark in Rhode Island/Texas). Entry comp $58-72k. Day-one work: investigating reject patterns, supporting client-services with claims-data pulls, building reports against 837/835 claims and NCPDP transactions. The reject-code fluency from the pharmacy bench is exactly the asset.\n\n3. **Specialty-pharmacy analyst** at Accredo, AllianceRx Walgreens Prime, CVS Specialty, or one of the smaller specialty operations (Optime, Diplomat). Entry comp $60-75k. Day-one work: supporting the prior-auth and patient-services workflow with data; tracking turnaround times, denial reasons, appeal success rates. Direct overlap with her existing PA experience.\n\n4. **Clinical analytics analyst** inside a health-system pharmacy department (e.g. Cleveland Clinic Pharmacy Analytics, Mass General Brigham). Entry comp $65-80k. Day-one work: medication-use evaluations, formulary impact projections, controlled-substance diversion monitoring. Highest clinical bar of the five buckets, and the most direct fit for her wedge if she has a target health system in her metro.\n\n5. **Quality / population-health analyst** at a managed-care org or ACO (Kaiser, Aledade, agilon health, regional Medicaid managed-care plans). Entry comp $60-75k. Day-one work: HEDIS measure tracking, gaps-in-care reporting, risk-adjustment data quality. Less pharmacy-specific but rewards general healthcare-data fluency.\n\nThe roles she should NOT be targeting: \"data analyst\" at SaaS companies, \"business analyst\" at non-healthcare consultancies, anything labeled \"analytics engineer\" (different track entirely, demands dbt/Airflow fluency she does not have). Targeting those roles is what makes the pivot look unrealistic — the funnel is the wrong funnel.\n\nGeographic note: roles 1 and 4 cluster geographically around the named health systems. Roles 2, 3, and 5 are increasingly remote-friendly post-2022; OptumRx, Express Scripts, and most specialty pharmacies hire fully remote at the analyst tier.",
    state: "confident",
    order: 4,
    change_note:
      "Added comp bands and remote-friendliness annotations after the target-roles sub returned with a sharper picture of post-2022 hiring patterns.",
    sources: [
      {
        kind: "web",
        url: "https://www.bls.gov/oes/current/oes152031.htm",
        title: "BLS — Occupational employment, operations research analysts",
        snippet:
          "Median wage data for operations research analysts by industry; healthcare and insurance among top employers.",
      },
      {
        kind: "web",
        url: "https://www.glassdoor.com/Salaries/operations-analyst-healthcare-salary-SRCH_KO0,29.htm",
        title: "Glassdoor — Operations analyst (healthcare) salary aggregator",
        snippet:
          "Salary aggregator data for operations analyst roles at major health systems and PBMs.",
      },
    ],
    depends_on: [SEC_DOMAIN_WEDGE],
    last_updated: iso(NOW - 6 * HOUR),
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: SEC_TIMELINE,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "finding",
    title: "Timeline — 9-15 months to first offer on the domain-bridging plan",
    content:
      "Concretely, a realistic timeline for the domain-bridging plan looks like this:\n\n- **Months 1-3** (current state through ~July 2026): finish current bootcamp's SQL + Python + Pandas modules. Audit the output against the bootcamp checklist artifact — most of the deliverable artifacts from generic bootcamps are not portfolio-quality, so plan to use the coursework as scaffolding for the portfolio projects rather than as the portfolio itself. Begin Tableau Public account; complete the free Tableau eLearning track.\n- **Months 4-6**: ship the FIRST healthcare-domain portfolio project. Best candidate based on her existing wedge: a prior-auth approval-rate analysis using CMS Medicare Part D synthetic claims data, with a clear narrative around which therapeutic classes drive the most denials and what the workflow implications are. This is the artifact that flips the working theory from medium to high confidence.\n- **Months 7-9**: ship the second project (controlled-substance dispensing pattern detection on a synthetic dataset, framed around DEA corresponding-responsibility) and start light networking — targeted LinkedIn outreach to operations and pharmacy analysts at the five role buckets, asking for 20-minute informational conversations. Begin applying to entry roles where she has at least one project that maps directly.\n- **Months 10-12**: third portfolio project (formulary tier-change impact projection using CMS formulary data) and increased application volume. By this point, the wedge is concrete and demonstrable; the application-to-screen ratio shifts materially.\n- **Months 13-15**: first offer for the median candidate on this plan; faster for candidates who have a single high-leverage networking conversation in months 7-9.\n\nKey caveat: this assumes she is putting 12-15 deliberate hours per week into the plan during months 1-9, including bootcamp time. At 6-8 hours per week the timeline roughly doubles. At 20+ hours per week (i.e., if she can drop to part-time pharmacy work for a stretch) it compresses to 7-10 months.\n\nThe 4-6 month timeline that bootcamps advertise is genuinely achievable for the technical-overlap plan in tech-adjacent companies, but that is not the plan to run. The 24-36 month \"go get a stats degree\" timeline is overkill for entry-level analytics roles in healthcare, where domain experience substitutes for credentialed quant background.",
    state: "provisional",
    order: 5,
    change_note:
      "Held provisional pending bootcamp-output audit (sub-investigation in progress) and confirmation of her weekly hours commitment.",
    sources: [
      {
        kind: "web",
        url: "https://www.coursereport.com/reports/2023-coding-bootcamp-outcomes-report",
        title: "Course Report — 2023 outcomes",
        snippet:
          "Time-to-first-job distributions vary widely; median is 3-6 months but tail is long.",
      },
    ],
    depends_on: [SEC_TARGET_ROLES, SEC_DOMAIN_WEDGE],
    last_updated: iso(NOW - 8 * HOUR),
    created_at: iso(NOW - 24 * HOUR),
  },
  {
    id: SEC_PORTFOLIO,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "recommendation",
    title: "Portfolio — three projects that no CS-only grad could plausibly produce",
    content:
      "Detailed specs are in the portfolio-spec artifact. Summary here:\n\n1. **Prior-auth approval-rate analysis**. Dataset: CMS Medicare Part D synthetic claims (publicly available, 5% sample). Tools: SQL + Python + Pandas + Tableau. Deliverable: a Tableau Public dashboard plus a written narrative (Medium post or GitHub README) explaining which therapeutic classes drive the highest PA denial rates, what the workflow upstream looks like, and what the operational implications are for the pharmacy. The narrative is the wedge — anyone can build the dashboard, only she can write the narrative.\n\n2. **Controlled-substance dispensing pattern detection**. Dataset: synthetic prescriptions data (NCPDP test files plus CMS oversight reports). Tools: SQL + Python (sklearn for outlier detection) + brief writeup. Deliverable: a notebook walking through pattern-detection logic for diversion-suspicious dispensing, framed around the DEA's corresponding-responsibility obligation. This is the project that signals \"I have actually worked under DEA review\" to a clinical-analytics hiring manager.\n\n3. **Formulary tier-change impact projection**. Dataset: CMS formulary files (publicly available, by plan) plus synthetic claims. Tools: SQL + Python + Tableau. Deliverable: a model projecting member impact (out-of-pocket cost shift, expected utilization change, ED-visit risk) for a hypothetical Tier 2 to Tier 3 move on a class of common maintenance medications. This is the project that signals \"I can think about the downstream consequences of formulary decisions\" to a PBM hiring manager.\n\nAll three projects are scoped to be shippable in 4-8 weeks each by someone with bootcamp-level SQL/Python and the wedge. None require ML beyond basic outlier detection. None require infra beyond a laptop and a Tableau Public account. All three demonstrate the asymmetry that makes the pivot tractable.\n\nThe order matters: ship project 1 first, before networking, before broad applications. It is the artifact the rest of the plan rests on.",
    state: "confident",
    order: 6,
    change_note:
      "Promoted to confident after the portfolio-spec sub returned with concrete dataset paths and feasibility checks.",
    sources: [
      {
        kind: "web",
        url: "https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files",
        title: "CMS — Medicare claims synthetic public-use files",
        snippet:
          "Publicly available synthetic Medicare claims data suitable for portfolio work without HIPAA exposure.",
      },
      {
        kind: "web",
        url: "https://www.cms.gov/medicare/prescription-drug-coverage/prescriptiondrugcovgenin/formularyguidance",
        title: "CMS — Formulary guidance and public formulary files",
        snippet:
          "Plan-by-plan formulary tier data publicly available as quarterly downloads.",
      },
    ],
    depends_on: [SEC_DOMAIN_WEDGE, SEC_TARGET_ROLES],
    last_updated: iso(NOW - 5 * HOUR),
    created_at: iso(NOW - 20 * HOUR),
  },
  {
    id: SEC_BOOTCAMP_LIMITS,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "evidence",
    title: "Bootcamp limits — what online programs actually deliver and where they fall short",
    content:
      "Most online part-time bootcamps in the SQL/Python/Pandas/Tableau cluster (DataCamp, Codecademy, Coursera/IBM, Springboard, BrainStation in part-time mode, Maven Analytics) deliver real but bounded value. Honest accounting of what they reliably produce versus what they advertise:\n\nWhat they reliably produce:\n- Working SQL fluency on simple to moderate joins, aggregations, window functions if the curriculum covers them. Comparable to a junior CS-grad's SQL after a database course.\n- Working Python + Pandas fluency for data cleaning, basic exploratory analysis, simple visualizations. Comparable to a CS-grad's first applied data class.\n- Familiarity with one BI tool (usually Tableau or Power BI) at the dashboard-construction level.\n- Generic portfolio projects on standard datasets (Titanic, NYC taxi, Olist e-commerce, COVID open-data).\n\nWhat they do NOT reliably produce:\n- Domain-specific portfolio work. The generic projects are recognizable to hiring managers and signal \"bootcamp\" without further differentiation.\n- Healthcare-data fluency of any kind. Not in the curriculum, not in the project work, not in the case studies.\n- The kind of stakeholder-conversation skill (translating a business question into a data question and back) that comes from working environments. She has this from 8+ years on the pharmacy bench; it is a real asset bootcamp grads typically lack.\n- Infrastructure/engineering depth (orchestration, testing, deployment). Not relevant for the analyst tier she is targeting.\n\nImplication for her plan: the bootcamp is a means, not the end. Use the SQL/Python coursework as the technical scaffolding for the three healthcare-domain portfolio projects, and treat the bootcamp's own deliverable artifacts as discardable. The Tableau eLearning track (free, 6-8 hours) is worth doing on top of any bootcamp's BI module because most bootcamps under-cover Tableau Server / Tableau Public publishing.\n\nAudit checklist artifact has the specific question set to apply to her current coursework.",
    state: "provisional",
    order: 7,
    change_note:
      "Held provisional pending the bootcamp-output audit sub returning with a specific assessment of her current coursework.",
    sources: [
      {
        kind: "web",
        url: "https://www.coursereport.com/reports/2023-coding-bootcamp-outcomes-report",
        title: "Course Report — 2023 outcomes",
        snippet:
          "Outcomes data including job-title distribution and time-to-first-job by program type.",
      },
    ],
    depends_on: [SEC_PORTFOLIO],
    last_updated: iso(NOW - 9 * HOUR),
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: SEC_RULED_GENERIC,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "ruled_out",
    title: "Generic data-analyst at tech-adjacent companies",
    content:
      "Plausible enough on the surface that it deserves explicit ruling-out. Generic data analyst at SaaS / tech-adjacent companies (the path most bootcamps optimize for) is a path she should not run. Three reasons. (1) The funnel is dominated by CS-degreed candidates and her cohort would be 22-26 year olds with 4-year quant backgrounds; she has no advantage there and several disadvantages. (2) The work itself does not draw on her wedge — pharmacy-workflow fluency is invisible at a B2B SaaS analytics team. (3) Entry comp is similar ($55-75k) but career mobility is worse because the next role is also generic, and now the clinical experience is two years stale. The path is not impossible, just dominated by the domain-bridging path on every dimension that matters. Ruled out as a target.",
    state: "confident",
    order: 8,
    change_note:
      "Ruled out and kept visible so the reader sees the path was considered and explicitly rejected, not overlooked.",
    sources: [],
    depends_on: [SEC_DOMAIN_WEDGE],
    last_updated: iso(NOW - 12 * HOUR),
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: SEC_OPEN_WEDGE,
    dossier_id: STRESS4_DOSSIER_ID,
    type: "open_question",
    title: "Open: which pharmacy-workflow problem is your wedge?",
    content:
      "Blocked pending user answer. We need her to name one specific pharmacy-workflow problem she could explain to a non-pharmacist hiring manager in 90 seconds AND draw a data-flow diagram for on a whiteboard. Candidates from the conversation so far: prior-auth approval-rate dynamics by therapeutic class, controlled-substance corresponding-responsibility audit signals, formulary tier-change patient impact, NCPDP reject-code workflow downstream, refill-too-soon adjudication patterns. The answer determines which portfolio project to ship first and which target-role bucket to lead with.",
    state: "blocked",
    order: 9,
    change_note: "Opened as the gating question for portfolio sequencing.",
    sources: [],
    depends_on: [SEC_PORTFOLIO, SEC_DOMAIN_WEDGE],
    last_updated: iso(NOW - 6 * HOUR),
    created_at: iso(NOW - 10 * HOUR),
  },
];

// ===========================================================================
// Sub-investigations
// ===========================================================================

const SUB_INVESTIGATIONS: SubInvestigation[] = [
  {
    id: SUB_TRAJECTORIES_ID,
    dossier_id: STRESS4_DOSSIER_ID,
    parent_section_id: SEC_REFRAME,
    title: "Comparable trajectories",
    plan_item_id: "stress4-plan-1",
    scope:
      "Survey realistic comparable trajectories for pharmacy-tech to healthcare-data-analytics pivots on a self-taught path; anchor against the two profiles the user surfaced at intake (github.com/SunshineKeys, linkedin.com/in/megan-merrigan-a824a1265).",
    questions: [
      "Are there public profiles of people who have made this exact pivot, with visible portfolio work?",
      "What does their stack and project mix look like?",
      "What is the implied timeline from career-shift signals to first analyst role?",
      "Where do their portfolios converge or diverge from the projects we are recommending?",
    ],
    state: "delivered",
    return_summary:
      "Found at least one strong proof-of-existence anchor: SunshineKeys on GitHub maps to Megan Merrigan, ex-pharmacy-technician and operations role at Change Healthcare (Iowa Medicaid) for several years, currently transitioning to healthcare data analyst. Public portfolio includes a Pharmacy-Claims-Pipeline Python repo, a Healthcare-FWA-Dashboard in Power BI, plus general-purpose Python tooling (job-application-analyzer, sales analyzers, file/text utilities). Stack listed: Python, SQL, Pandas, Power BI (DAX), Tableau, Git, SQLite. This is exactly the wedge profile we are recommending — note the two healthcare-specific projects sitting alongside the generic Python work; that mix is what makes the portfolio credible. The LinkedIn URL the user mentioned (linkedin.com/in/megan-merrigan-a824a1265) appears to be the same person, but the agent could not verify the LinkedIn profile directly because LinkedIn blocks unauthenticated fetches; flagging this rather than fabricating details. Net: the trajectory is well-trodden enough to find a credible public comparator within minutes of searching, which is itself evidence the pivot is realistic.",
    findings_section_ids: [SEC_REFRAME, SEC_DOMAIN_WEDGE],
    findings_artifact_ids: [],
    why_it_matters:
      "Anchors the realism conversation in actual comparable people rather than abstract base rates. If we could not find any public comparator, the working theory would shift toward \"novel path, plan more conservatively.\"",
    known_facts: [
      "SunshineKeys GitHub profile maps to Megan Merrigan",
      "Background: pharmacy technician, ~6 years operations at Change Healthcare (Iowa Medicaid)",
      "Current direction: healthcare data analyst transition",
      "Stack: Python, SQL, Pandas, Power BI, Tableau, Git",
      "Healthcare-specific repos: Pharmacy-Claims-Pipeline, Healthcare-FWA-Dashboard",
    ],
    missing_facts: [
      "Whether she has landed a first analyst role yet (LinkedIn fetch blocked)",
      "Specific timeline from start of self-teaching to current portfolio state",
      "Whether the two healthcare projects are fully shipped or in-progress",
    ],
    current_finding:
      "Strong proof-of-existence anchor for the wedge profile; LinkedIn profile not verifiable by agent.",
    recommended_next_step:
      "User can verify the LinkedIn profile herself and reach out for a 20-minute informational conversation if Megan is open to it. That single conversation would be worth more than another 3 hours of desk research.",
    confidence: "high",
    started_at: iso(NOW - 40 * HOUR),
    completed_at: iso(NOW - 28 * HOUR),
  },
  {
    id: SUB_SUNSHINEKEYS_ID,
    dossier_id: STRESS4_DOSSIER_ID,
    parent_section_id: SEC_REFRAME,
    title: "Reference profile: github.com/SunshineKeys",
    plan_item_id: null,
    scope:
      "Verify the GitHub profile the user named as a comparator; extract stack, project mix, and any career-transition signals. Treat as analytical reference point, not personal subject.",
    questions: [
      "What stack and projects are on the profile?",
      "Are there healthcare-specific repos that signal the wedge profile?",
      "Does the profile owner self-describe a career-transition path?",
    ],
    state: "delivered",
    return_summary:
      "Profile fetched cleanly (~14 repos, 6 pinned). Stack is Python-dominant with secondary Power BI and SQL; no JS/web-framework presence. Two pinned repos are explicitly healthcare-domain — a pharmacy-claims pipeline (synthetic Medicaid claims, NDC/ICD-10/CPT/HCPCS, formulary, prior-auth, rebate reconciliation vocabulary) and a fraud/waste/abuse Power BI dashboard — sitting alongside generic Python utilities (sales analyzer, visual-report capstone, job-application tracker) and a cluster of short \"day-one through day-five\" sprint repos that read as recent intensive skill-building. This is exactly the wedge-portfolio shape the dossier recommends for a pharmacy-tech pivoter: two domain-specific deliverables that signal vocabulary and credibility, scaffolded on top of generic Python projects that prove tooling fluency.",
    findings_section_ids: [SEC_REFRAME],
    findings_artifact_ids: [],
    why_it_matters:
      "Concrete proof that the wedge-portfolio approach exists in the wild and reads as credible at a glance.",
    known_facts: [
      "~14 total repos, 6 pinned",
      "Stack: Python-dominant, with Power BI and SQL as secondary",
      "Two pinned repos are healthcare-domain (claims pipeline, FWA dashboard); rest are generic Python utilities",
      "Cluster of short sprint-style repos suggests recent intensive skill-building",
    ],
    missing_facts: [
      "Time-on-task to reach current portfolio state",
      "Whether first analyst offer has landed",
    ],
    current_finding:
      "Wedge profile exists in the wild; mix of healthcare-domain + generic Python is the right pattern.",
    recommended_next_step:
      "Use as inspiration for project structure (especially the Pharmacy-Claims-Pipeline naming convention and the Power BI healthcare-FWA dashboard framing); do not copy projects directly.",
    confidence: "high",
    started_at: iso(NOW - 38 * HOUR),
    completed_at: iso(NOW - 30 * HOUR),
  },
  {
    id: SUB_MERRIGAN_ID,
    dossier_id: STRESS4_DOSSIER_ID,
    parent_section_id: SEC_REFRAME,
    title: "Reference profile: linkedin.com/in/megan-merrigan-a824a1265",
    plan_item_id: null,
    scope:
      "Cross-reference the LinkedIn profile the user named at intake against the GitHub profile to confirm continuity and extract the role-history timeline. Treat as analytical reference point only.",
    questions: [
      "Does the LinkedIn profile correspond to the same person as the GitHub profile?",
      "What is the role-history timeline?",
      "Has the transition into a first analyst role landed yet?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [],
    findings_artifact_ids: [],
    why_it_matters:
      "Would tighten the timeline anchor if the LinkedIn profile shows a clean date for the bench-to-analytics transition. Currently blocked by LinkedIn's anti-scraping protection.",
    known_facts: [
      "LinkedIn URL was named by the user at intake",
      "GitHub profile (SunshineKeys) appears to be the same person based on naming and content",
    ],
    missing_facts: [
      "Cannot fetch LinkedIn profile from this agent without authenticated session",
      "Role-history timeline",
      "Confirmation of current employer / open-to-work status",
    ],
    current_finding:
      "LinkedIn fetch returned status code 999 (anti-bot block); profile content not directly verifiable by the agent. Flagging this rather than fabricating details from the URL alone.",
    recommended_next_step:
      "User can pull the LinkedIn profile herself and paste the relevant role-history dates back into the conversation; we will incorporate the timeline anchor on the next session.",
    confidence: "low",
    started_at: iso(NOW - 36 * HOUR),
    completed_at: null,
  },
  {
    id: SUB_PORTFOLIO_ID,
    dossier_id: STRESS4_DOSSIER_ID,
    parent_section_id: SEC_PORTFOLIO,
    title: "Portfolio project specs",
    plan_item_id: "stress4-plan-3",
    scope:
      "Specify the three healthcare-domain portfolio projects with concrete dataset paths, scope, deliverables, and feasibility checks. Validate that each is shippable in 4-8 weeks at bootcamp-level technical fluency.",
    questions: [
      "What public/synthetic datasets are usable without HIPAA exposure?",
      "What is the realistic scope of each project at bootcamp technical level?",
      "Which BI tool produces the most credible final artifact for the target hiring managers?",
      "What narrative frame does each project need to demonstrate the wedge?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [SEC_PORTFOLIO],
    findings_artifact_ids: [ART_PORTFOLIO_SPEC],
    why_it_matters:
      "Without concrete project specs, the portfolio recommendation is just \"build a portfolio\" — which is what every bootcamp says and which produces the generic Kaggle-toy work that does not transfer.",
    known_facts: [
      "CMS Medicare Part D synthetic claims (5% sample) is publicly available without HIPAA",
      "CMS formulary files are publicly available as quarterly downloads",
      "NCPDP test files are accessible via standard reference docs",
      "Tableau Public is free and the standard publishing destination",
    ],
    missing_facts: [
      "Whether the user's bootcamp has covered window functions and CTEs to the level needed for the prior-auth project",
      "Whether the synthetic claims sample size is large enough for the diversion-detection signal",
    ],
    current_finding:
      "All three projects appear shippable at bootcamp-level technical fluency; portfolio-spec artifact is in v1 form and ready for user review.",
    recommended_next_step:
      "User reviews the portfolio-spec artifact and picks one of the three to ship first based on her wedge answer.",
    confidence: "medium",
    started_at: iso(NOW - 30 * HOUR),
    completed_at: null,
  },
  {
    id: SUB_TARGET_ROLES_ID,
    dossier_id: STRESS4_DOSSIER_ID,
    parent_section_id: SEC_TARGET_ROLES,
    title: "Target-role spectrum",
    plan_item_id: "stress4-plan-2",
    scope:
      "Map the realistic target-role spectrum across health systems, PBMs, and specialty pharmacies. Pull current job postings to ground comp bands and required-skills lists in actuals rather than aggregator data.",
    questions: [
      "What are the actual entry comp bands across the five role buckets in the named geographies?",
      "Which postings explicitly call out pharmacy-tech background as preferred?",
      "What is the remote-friendliness picture post-2022?",
    ],
    state: "delivered",
    return_summary:
      "Cross-referenced 14 current postings (Geisinger, Kaiser NorCal, Intermountain, Sutter, OptumRx, Express Scripts, CVS Caremark, Accredo, AllianceRx, Cleveland Clinic, Mass General Brigham, Aledade, agilon health, Providence). Findings: (1) Comp bands cluster $58-80k entry across the five buckets; specialty-pharmacy and clinical-analytics buckets pull the higher half. (2) Three of the 14 postings explicitly list \"pharmacy technician background preferred\" or equivalent; another five list \"clinical operations background\" as preferred. (3) PBM and specialty-pharmacy roles are 60%+ remote-friendly post-2022; health-system operations roles remain mostly hybrid. (4) Required-skills lists are SQL universal, Python in 9 of 14, Tableau or Power BI in 12 of 14, Epic Clarity in 5 of 14 (all health-system roles). The Epic Clarity gap is bridgeable with targeted self-study but is the most-named technical asymmetry between her current bootcamp and the actual role demands.",
    findings_section_ids: [SEC_TARGET_ROLES],
    findings_artifact_ids: [ART_QUERY_TEMPLATES],
    why_it_matters:
      "Grounds the target-role recommendation in actual postings rather than aggregator data; identifies the Epic Clarity gap as a concrete addressable item.",
    known_facts: [
      "14 current postings reviewed across 14 employers",
      "Comp bands $58-80k entry across the buckets",
      "3/14 explicitly prefer pharmacy-tech background",
      "Epic Clarity named as required in 5/14, all health-system roles",
    ],
    missing_facts: [
      "Hiring funnel composition (applications-to-screen-to-offer ratio) at any of the named employers",
      "Whether internal-referral inflation is significant at the PBMs",
    ],
    current_finding:
      "Target-role spectrum holds; Epic Clarity gap surfaced as the one concrete bootcamp-curriculum addition worth making for health-system role bucket.",
    recommended_next_step:
      "User can decide whether to add Epic Clarity self-study (free Epic UserWeb access varies by employer) once she narrows the target bucket. Not needed for PBM or specialty-pharmacy roles.",
    confidence: "high",
    started_at: iso(NOW - 26 * HOUR),
    completed_at: iso(NOW - 12 * HOUR),
  },
  {
    id: SUB_BOOTCAMP_AUDIT_ID,
    dossier_id: STRESS4_DOSSIER_ID,
    parent_section_id: SEC_BOOTCAMP_LIMITS,
    title: "Bootcamp output audit",
    plan_item_id: "stress4-plan-4",
    scope:
      "Audit the user's current bootcamp coursework against a defined checklist; identify which deliverables are portfolio-shippable as-is, which need rework, and which gaps require additional self-study before the portfolio projects are buildable.",
    questions: [
      "What modules has she actually completed?",
      "Which deliverables, if any, are portfolio-shippable as-is?",
      "What are the specific technical gaps relative to the portfolio project requirements?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [],
    findings_artifact_ids: [ART_BOOTCAMP_CHECKLIST],
    why_it_matters:
      "Determines how much technical scaffolding she already has versus how much pre-portfolio learning is still required. Drives the timeline estimate.",
    known_facts: [
      "Bootcamp covers SQL, Python, Pandas, light Tableau",
      "She is part-time, mid-program",
      "No portfolio projects shipped yet from coursework",
    ],
    missing_facts: [
      "Specific bootcamp provider and curriculum",
      "Which modules she has already completed vs which remain",
      "Quality of the deliverable artifacts from completed modules",
    ],
    current_finding:
      "Audit checklist artifact is drafted and ready for user to walk through; sub will resolve once user pastes back the audit results.",
    recommended_next_step:
      "User walks through the bootcamp-output audit checklist and pastes results into next session.",
    confidence: "low",
    started_at: iso(NOW - 24 * HOUR),
    completed_at: null,
  },
];

// ===========================================================================
// Artifacts
// ===========================================================================

const PORTFOLIO_SPEC_CONTENT = `# Three healthcare-domain portfolio projects — full spec

The premise: ship two-to-three projects that no CS-only bootcamp grad could plausibly produce. Each leans on your eight years of pharmacy-bench fluency. Each is shippable in 4-8 weeks at bootcamp-level SQL/Python. None require ML beyond basic outlier detection. None require infra beyond a laptop and a Tableau Public account. Order matters: ship Project 1 first.

---

## Project 1 — Prior-auth approval-rate analysis (the wedge project)

**Dataset:** CMS Medicare Part D synthetic claims (5% sample), publicly downloadable. Optionally augment with the CMS Medicare Part D Drug Spending Dashboard data for therapeutic-class context.

**Tools:** SQL (loaded into SQLite or DuckDB locally) + Python/Pandas + Tableau Public for the final dashboard. Optional: a short Medium post or detailed GitHub README narrating the analysis.

**Scope:**
1. Identify therapeutic classes with the highest prior-auth denial rates (you will need to use the synthetic claims' rejected-claims signal as a proxy since the public dataset does not surface PA workflow directly).
2. For each high-denial class, build a brief workflow narrative — what the typical PA submission looks like, what the most common denial reasons are, what the operational consequences are downstream (fill delays, abandonment, ED utilization).
3. Build a Tableau Public dashboard with three views: denial rate by class, denial-rate trend over the dataset window, and a drill-through to top-N denial reasons per class.
4. Write a 1500-2500 word narrative explaining what the dashboard shows, what the operational implications are, and what a payer-side analytics team should do about it.

**Why it works:** The dashboard is not the artifact. The narrative is. Anyone with bootcamp SQL can build the dashboard. Only someone who has actually worked PA from the bench can write the narrative — and the narrative is what a payer-side analytics hiring manager will read first.

**Realistic time-to-ship:** 4-6 weeks at 12 hours per week.

---

## Project 2 — Controlled-substance dispensing pattern detection

**Dataset:** Synthetic prescriptions data, ideally constructed by you from an NCPDP test-file template. You can also use the CMS Medicare Part D synthetic data filtered to scheduled drugs for a more realistic distribution.

**Tools:** SQL + Python (sklearn for basic outlier detection, scipy for any statistical work) + a Jupyter notebook as the deliverable, posted to GitHub.

**Scope:**
1. Construct a realistic-looking synthetic dispensing dataset with a small number of intentional diversion-suspicious patterns embedded.
2. Walk through a pattern-detection pipeline: refill-too-soon clustering, multi-prescriber patterns for the same patient, geographic outliers, time-of-day patterns inconsistent with normal pharmacy operations.
3. Frame the analysis around the DEA's corresponding-responsibility obligation — what a pharmacist is required to look at and how data tooling can support that review without replacing it.

**Why it works:** Signals \"I have actually worked under DEA review,\" which is the wedge for clinical-analytics hiring managers at health systems and the diversion-monitoring teams at large retail chains.

**Realistic time-to-ship:** 5-8 weeks at 12 hours per week.

---

## Project 3 — Formulary tier-change impact projection

**Dataset:** CMS formulary files (publicly available, by plan, quarterly) plus synthetic claims for member-impact modeling.

**Tools:** SQL + Python + Tableau.

**Scope:**
1. Pick a hypothetical Tier 2 to Tier 3 move on a class of common maintenance medications.
2. Project member impact: out-of-pocket cost shift per member per month, expected utilization change (use a simple elasticity assumption from public literature), expected ED-visit risk delta for medications where non-adherence has well-documented acute consequences.
3. Build a one-page summary dashboard plus a 1000-word writeup framed as if you were briefing a P&T committee.

**Why it works:** Signals \"I can think about the downstream consequences of formulary decisions,\" which is the wedge for PBM hiring managers and any pharmacy-benefit-design team.

**Realistic time-to-ship:** 4-6 weeks at 12 hours per week.

---

## Sequencing and packaging

Ship Project 1 first, before networking, before any broad applications. It is the artifact the rest of the plan rests on. Once Project 1 is live (Tableau Public + GitHub repo + Medium post + a clean LinkedIn post linking all three), begin light targeted outreach. Project 2 ships during application ramp. Project 3 ships as the closing artifact.

Package: a GitHub repo per project plus a single portfolio landing page (free GitHub Pages site is fine) that frames all three as \"clinical-to-data translator\" work, with your pharmacy-tech background named explicitly at the top. Lead the LinkedIn About section with the same framing.`;

const BOOTCAMP_CHECKLIST_CONTENT = `# Bootcamp-output audit checklist

For each module/section your bootcamp has delivered, answer:

## SQL module
- [ ] Have you written joins on 3+ tables, including LEFT and FULL OUTER, against a non-toy dataset?
- [ ] Have you written window functions (ROW_NUMBER, LAG/LEAD, running aggregates)?
- [ ] Have you written CTEs and used them to break a complex query into readable steps?
- [ ] Can you explain the difference between WHERE and HAVING without thinking about it?
- [ ] Have you used CASE WHEN inside an aggregation?
- [ ] Do you have a deliverable artifact (notebook, repo, dashboard) that demonstrates these skills end-to-end?

## Python / Pandas module
- [ ] Can you load a CSV, clean a messy date column, group-by aggregate, and export to a clean output without referring to docs?
- [ ] Do you understand the difference between .loc, .iloc, and chained indexing?
- [ ] Have you handled missing data deliberately (not just .dropna everything)?
- [ ] Have you written at least one function that takes a DataFrame and returns a transformed DataFrame, with type hints?
- [ ] Do you have a deliverable artifact?

## Tableau / Power BI module
- [ ] Have you built and published a dashboard to Tableau Public or Power BI service?
- [ ] Does it have at least three coordinated views with cross-filtering?
- [ ] Have you used a calculated field that demonstrates real analytic intent?
- [ ] Is there a written narrative accompanying the dashboard, not just the dashboard alone?

## Portfolio readiness
- [ ] Do you have ANY healthcare-specific work in your output? (Likely no, in which case the portfolio projects fill this gap.)
- [ ] Are your existing deliverables on standard datasets (Titanic, NYC taxi, Olist, COVID open-data)? If yes, treat as discardable.
- [ ] Do you have a GitHub profile with at least three public repos?
- [ ] Do you have a Tableau Public profile with at least one published dashboard?

## Gaps to address before starting Project 1
If you answered \"no\" to any SQL or Pandas item above, work that gap before starting the portfolio project. Tableau gaps can be filled in parallel with Project 1. Healthcare-domain gaps are filled BY the portfolio projects themselves.`;

const WEDGE_SCRIPT_CONTENT = `# 90-second hiring-manager wedge script

For phone screens and in-person conversations. Practice this until it sounds natural.

---

**Opening (15s):**
\"I spent eight years as a pharmacy technician — the last several years working through a lot of prior-auth, controlled-substance, and insurance-adjudication workflow at the bench. I've spent the last several months building healthcare-data analytics skills on top of that — SQL, Python, Tableau — and I'm specifically targeting roles where the clinical fluency matters as much as the technical work.\"

**Wedge (45s):**
\"What I've found is that a lot of healthcare data work fails not because the technical work is wrong, but because the person doing it doesn't understand what the data is actually a record of. For example: [PICK ONE — prior-auth denial cascade, NCPDP reject downstream, controlled-substance dispensing audit, formulary tier change patient impact]. Most analysts have to learn that on the job over six months. I already know it. So when I'm working on something like [POINT TO YOUR PORTFOLIO PROJECT], I'm not guessing about what the data means.\"

**Close (30s):**
\"I know I don't have a CS background, and I'm not trying to compete on that axis. What I'm offering is the clinical-to-data translator work — the kind where the analytic work needs someone who has actually been at the bench. I'd love to talk about how that could fit on your team. I have a portfolio project up at [URL] that walks through a [PROJECT TYPE] analysis end-to-end if you want to see how I think.\"

---

Do not apologize for the bootcamp background. Do not apologize for the career change. Do not lead with \"I know I'm a non-traditional candidate.\" The wedge IS the framing. Lead with it.`;

const QUERY_TEMPLATES_CONTENT = `# Target-role search query templates

For Indeed, LinkedIn Jobs, and direct company career sites. Run weekly.

## Indeed / LinkedIn Jobs queries

- \"operations analyst\" pharmacy
- \"claims analyst\" pharmacy
- \"pharmacy operations\" analyst
- \"clinical analytics\" pharmacy
- \"prior authorization\" analyst
- \"specialty pharmacy\" analyst data
- \"medication use\" analyst
- \"formulary\" analyst
- \"PBM\" analyst entry
- \"managed care\" analyst pharmacy

Filters: entry-level, no security clearance required, exclude \"senior\" and \"manager\" titles.

## Direct-employer career sites worth bookmarking

Health systems: Kaiser Permanente, Geisinger, Intermountain Health, Sutter Health, Providence, Cleveland Clinic, Mass General Brigham, Cedars-Sinai, NYU Langone.

PBMs: Express Scripts (Cigna), OptumRx (UnitedHealth), CVS Caremark, Prime Therapeutics, MedImpact, Navitus.

Specialty pharmacies: Accredo, AllianceRx Walgreens Prime, CVS Specialty, Optime, Diplomat (Walgreens), BriovaRx (OptumRx).

Managed-care / ACO: Aledade, agilon health, ChenMed, Oak Street Health, Iora, regional Medicaid managed-care plans.

## Keywords that signal the wedge in postings

When you see these in a posting, prioritize: \"pharmacy technician background preferred,\" \"clinical operations experience,\" \"NCPDP,\" \"837/835,\" \"PBM operations,\" \"prior authorization workflow,\" \"DUR,\" \"medication therapy management.\"

When you see these, deprioritize (wrong funnel): \"data engineer,\" \"analytics engineer,\" \"machine learning,\" \"computer science degree required.\"`;

const ARTIFACTS: Artifact[] = [
  {
    id: ART_PORTFOLIO_SPEC,
    dossier_id: STRESS4_DOSSIER_ID,
    kind: "other",
    title: "Domain-bridging portfolio projects — full spec",
    content: PORTFOLIO_SPEC_CONTENT,
    intended_use:
      "Use as the working spec for the three healthcare-domain portfolio projects. Pick Project 1 to ship first based on your wedge answer.",
    state: "ready",
    kind_note:
      "Living document — expect to revise project 2 and 3 scope after project 1 ships and you have a clearer sense of pacing.",
    supersedes: null,
    last_updated: iso(NOW - 5 * HOUR),
    created_at: iso(NOW - 20 * HOUR),
  },
  {
    id: ART_BOOTCAMP_CHECKLIST,
    dossier_id: STRESS4_DOSSIER_ID,
    kind: "checklist",
    title: "Bootcamp-output audit checklist",
    content: BOOTCAMP_CHECKLIST_CONTENT,
    intended_use:
      "Walk through this against your current bootcamp coursework. Paste the results back so we can audit gaps and confirm timeline.",
    state: "ready",
    kind_note: null,
    supersedes: null,
    last_updated: iso(NOW - 9 * HOUR),
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: ART_WEDGE_SCRIPT,
    dossier_id: STRESS4_DOSSIER_ID,
    kind: "script",
    title: "90-second hiring-manager wedge script",
    content: WEDGE_SCRIPT_CONTENT,
    intended_use:
      "For phone screens and conversations with healthcare-analytics hiring managers. Practice until natural; do not read.",
    state: "ready",
    kind_note: null,
    supersedes: null,
    last_updated: iso(NOW - 7 * HOUR),
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: ART_QUERY_TEMPLATES,
    dossier_id: STRESS4_DOSSIER_ID,
    kind: "other",
    title: "Target-role search query templates",
    content: QUERY_TEMPLATES_CONTENT,
    intended_use:
      "Run the named queries weekly across Indeed and LinkedIn Jobs; bookmark the named employer career sites.",
    state: "ready",
    kind_note: null,
    supersedes: null,
    last_updated: iso(NOW - 11 * HOUR),
    created_at: iso(NOW - 16 * HOUR),
  },
];

// ===========================================================================
// Work sessions (3)
// ===========================================================================

const WORK_SESSIONS: WorkSession[] = [
  {
    id: "stress4-ws-1",
    dossier_id: STRESS4_DOSSIER_ID,
    started_at: iso(NOW - 2 * DAY),
    ended_at: iso(NOW - 2 * DAY + 95 * MIN),
    trigger: "intake",
    token_budget_used: 28400,
    input_tokens: 21200,
    output_tokens: 7200,
    cost_usd: 0.42,
    end_reason: "ended_turn",
  },
  {
    id: "stress4-ws-2",
    dossier_id: STRESS4_DOSSIER_ID,
    started_at: iso(NOW - 30 * HOUR),
    ended_at: iso(NOW - 22 * HOUR),
    trigger: "resume",
    token_budget_used: 38600,
    input_tokens: 28900,
    output_tokens: 9700,
    cost_usd: 0.61,
    end_reason: "ended_turn",
  },
  {
    id: "stress4-ws-3",
    dossier_id: STRESS4_DOSSIER_ID,
    started_at: iso(NOW - 6 * HOUR),
    ended_at: null,
    trigger: "user_open",
    token_budget_used: 12100,
    end_reason: "crashed",
  },
];

// ===========================================================================
// Needs input (1 open)
// ===========================================================================

const NEEDS_INPUT: NeedsInput[] = [
  {
    id: "stress4-ni-1",
    dossier_id: STRESS4_DOSSIER_ID,
    question:
      "Pick ONE pharmacy-workflow problem you could (a) explain to a non-pharmacist hiring manager in 90 seconds and (b) sketch a data-flow diagram for on a napkin. It does not have to be the most important problem in the field — it has to be the one you are most fluent in. Examples that count: a recurring prior-auth denial pattern you've seen on a specific drug class; the difference between a Schedule II count discrepancy that's a counting error vs. one that's a diversion signal; how 90-day vs. 30-day fills change adherence math; what a refill-too-soon override actually costs the pharmacy. If nothing immediately comes to mind, that's an answer too — say so, and we'll back into one from your scheduling/inventory work instead.",
    blocks_section_ids: [SEC_PORTFOLIO, SEC_OPEN_WEDGE],
    created_at: iso(NOW - 10 * HOUR),
    answered_at: null,
    answer: null,
  },
];

// ===========================================================================
// Decision points (1 open)
// ===========================================================================

const DECISION_POINTS: DecisionPoint[] = [
  {
    id: "stress4-dp-1",
    dossier_id: STRESS4_DOSSIER_ID,
    title:
      "Commit to a 9-month domain-bridging path (target operations / claims / clinical analytics inside health systems and PBMs), or pursue a faster generic 'data analyst' path with bootcamp-typical projects (target tech-adjacent roles)?",
    options: [
      {
        label:
          "Domain-bridging path: 3 healthcare-specific portfolio projects, target operations/claims/clinical analytics inside health systems, PBMs, specialty pharmacies. 9-15 months to first offer, $58-78k entry band, lower competition (your pharmacy background is a wedge).",
        implications:
          "Slower out of the gate (portfolio projects take real time to ship). Higher hit-rate per application because the resume tells a coherent story. Comp band starts mid-tier but ramps faster because clinical fluency is rare on these teams. Resume is harder to redirect into pure-tech later — but most healthcare-analytics roles can step into health-tech product/data roles within 2 years.",
        recommended: true,
      },
      {
        label:
          "Generic data-analyst path: bootcamp-typical projects (Kaggle-style, Tableau dashboards on public datasets), target any-industry data analyst at startups and tech-adjacent companies. 4-9 months to first offer if it lands, but lower hit-rate per application.",
        implications:
          "Faster IF you land — but you're competing head-on with CS-degreed candidates and full-time bootcamp grads who have more polished portfolios. Your pharmacy background is invisible / mildly negative on a generic-DA resume. Comp band is wider but the floor is lower ($50-65k entry). Easier to redirect later, but the first year is a worse fit on every dimension.",
        recommended: false,
      },
    ],
    recommendation:
      "Domain-bridging. The pharmacy-tech background is the rarest thing on your resume; spending 9 months turning it into a wedge is a higher-EV move than spending 6 months trying to look like everyone else.",
    blocks_section_ids: [SEC_TIMELINE, SEC_TARGET_ROLES],
    created_at: iso(NOW - 5 * HOUR),
    resolved_at: null,
    chosen: null,
    kind: "generic",
  },
];

// ===========================================================================
// Reasoning trail (3)
// ===========================================================================

const REASONING_TRAIL: ReasoningTrailEntry[] = [
  {
    id: "stress4-rt-1",
    dossier_id: STRESS4_DOSSIER_ID,
    work_session_id: "stress4-ws-1",
    note:
      "User framed the question as 'realistic / not realistic.' That framing is itself the problem — it implies a fixed external probability rather than a function of the plan. Spent the first turn refusing to estimate a number and instead reframing toward 'which plan, on what timeline, with what wedge.' Premise challenge fired before any substantive analysis.",
    tags: ["premise_reframe", "strategy_shift"],
    created_at: iso(NOW - 2 * DAY + 8 * MIN),
  },
  {
    id: "stress4-rt-2",
    dossier_id: STRESS4_DOSSIER_ID,
    work_session_id: "stress4-ws-2",
    note:
      "Comparable-trajectories sub returned with a critical observation: pharmacy-tech-to-healthcare-analytics is a much better-trodden path than generic bootcamp-to-DA, but it's invisible in the popular career-pivot literature. The dominant story online is 'I quit my job and went to a coding bootcamp and got a tech job' — which is the wrong reference class for her. Updated working theory accordingly: target healthcare orgs, not tech.",
    tags: ["reference_class_correction", "working_theory_update"],
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: "stress4-rt-3",
    dossier_id: STRESS4_DOSSIER_ID,
    work_session_id: "stress4-ws-2",
    note:
      "Considering surfacing a stuck signal — without a confirmed pharmacy-workflow wedge from the user, the portfolio-projects sub-investigation cannot finish. Held off because the right move is not to escalate but to ask: needs_input #1 is the unblocking question, and progress will resume once she answers. Recheck on next turn.",
    tags: ["stuck_consideration", "rejected_approach"],
    created_at: iso(NOW - 24 * HOUR),
  },
];

// ===========================================================================
// Ruled out (2)
// ===========================================================================

const RULED_OUT: RuledOut[] = [
  {
    id: "stress4-ro-1",
    dossier_id: STRESS4_DOSSIER_ID,
    subject: "Quitting the pharmacy job before landing a first analytics offer",
    reason:
      "Income gap risk is high; runway pressure shortens job search and pushes toward worse-fit first offers. The pharmacy job is also the wedge — every portfolio project gets stronger when she can describe current pharmacy ops fluently. Quit only AFTER signed offer, full stop.",
    sources: [],
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: "stress4-ro-2",
    dossier_id: STRESS4_DOSSIER_ID,
    subject:
      "Master's in health informatics as the primary credential strategy",
    reason:
      "Two-year, $40-80k investment for a credential that healthcare-analytics hiring managers report does NOT meaningfully outperform a tight portfolio + domain story. Possible later as a sponsored mid-career move once she's inside the field, but as the on-ramp it's the wrong shape: high cost, slow, and produces credentials rather than the work samples that actually move hiring decisions.",
    sources: [],
    created_at: iso(NOW - 30 * HOUR),
  },
];

// ===========================================================================
// Considered and rejected (12)
// ===========================================================================

const CONSIDERED_AND_REJECTED: ConsideredAndRejected[] = [
  {
    id: "stress4-cr-1",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: SUB_TRAJECTORIES_ID,
    path: "Quitting pharmacy job before first analytics offer",
    why_compelling:
      "Frees 30+ hours/week for bootcamp + portfolio + applications. Removes the cognitive split.",
    why_rejected:
      "Income gap pressure shortens search and pushes toward worse-fit first offers. Pharmacy job IS the wedge — every interview is stronger when she can speak current ops fluently.",
    cost_of_error:
      "6+ months of runway burn during a slower-than-expected job search; first offer pressure drives a generic-DA acceptance at a lower comp band. Hard to undo.",
    sources: [],
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: "stress4-cr-2",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: SUB_BOOTCAMP_AUDIT_ID,
    path: "Pursuing a master's in health informatics first",
    why_compelling:
      "Conventional credential, sponsored career-services pipeline, removes 'self-taught' optics from her resume.",
    why_rejected:
      "$40-80k and 2 years for a credential that healthcare-analytics hiring managers report does not meaningfully outperform a strong portfolio + domain story. Wrong shape for an on-ramp.",
    cost_of_error:
      "Two years of opportunity cost + debt. Possible re-evaluation later as a sponsored mid-career move once she is inside the field.",
    sources: [],
    created_at: iso(NOW - 32 * HOUR),
  },
  {
    id: "stress4-cr-3",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: SUB_TARGET_ROLES_ID,
    path: "Targeting Big Tech (FAANG) as primary application strategy",
    why_compelling:
      "Highest comp ceiling. Brand on resume opens future doors.",
    why_rejected:
      "Wrong comparison class. FAANG analytics roles select on either CS-degreed engineers or candidates with very deep portfolio depth. Her wedge (clinical fluency) is invisible / undervalued there.",
    cost_of_error:
      "Burned application energy, false-negative signal that 'analytics doesn't want her' when in fact health-systems analytics would.",
    sources: [],
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: "stress4-cr-4",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: null,
    path: "'Open to work' LinkedIn banner as primary outreach channel",
    why_compelling: "Zero-effort, scales to recruiter volume.",
    why_rejected:
      "Recruiter inbound on a thin profile = generic recruiter spam, not interviews. Outreach without a portfolio asset to share is a low-yield motion. Better to wait until she has ONE shippable project to anchor the profile around.",
    cost_of_error:
      "Mostly nothing — but the time spent monitoring/replying to recruiters is time NOT spent on portfolio.",
    sources: [],
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: "stress4-cr-5",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: null,
    path:
      "Cold-emailing healthcare data analysts without a portfolio asset attached",
    why_compelling:
      "Networking is the most consistently mentioned 'how I broke in' factor.",
    why_rejected:
      "Cold outreach with nothing to anchor the conversation gets a 5-10% response rate at best. Cold outreach with a specific project ('I built X using Y data — would value 15 minutes on whether the analysis approach holds up') gets 30-40%. Wait until project #1 is shippable.",
    cost_of_error:
      "Not much downside, but burns the warm-intro budget. Networks have memory; you only get one good cold email per relationship.",
    sources: [],
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: "stress4-cr-6",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: SUB_PORTFOLIO_ID,
    path: "Kaggle competition as primary portfolio anchor",
    why_compelling:
      "Quantifiable rank, well-known signal in the data community.",
    why_rejected:
      "Kaggle ranks signal model-tuning skill. Healthcare-analytics roles select on data-quality intuition, problem decomposition, and stakeholder framing — none of which Kaggle measures. Worse: a high Kaggle rank with no domain projects reads as 'tech aspiration' not 'healthcare analyst.'",
    cost_of_error:
      "Weeks of effort on a signal hiring managers don't read for these roles.",
    sources: [],
    created_at: iso(NOW - 24 * HOUR),
  },
  {
    id: "stress4-cr-7",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: SUB_BOOTCAMP_AUDIT_ID,
    path: "Tableau certification before having a project to put it on",
    why_compelling: "Resume keyword. Cheap. Signals initiative.",
    why_rejected:
      "Certs without artifacts read as 'studied.' Hiring managers want to see ONE Tableau dashboard built on a real (synthetic-but-realistic) healthcare dataset, with the cert mentioned in passing. Reverse the order.",
    cost_of_error:
      "$245 + 30 hours that should have gone to project #1. Not catastrophic.",
    sources: [],
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress4-cr-8",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Switching to a full-time bootcamp and quitting pharmacy income",
    why_compelling:
      "Faster bootcamp completion, full focus, signaling 'committed to the pivot.'",
    why_rejected:
      "Income gap risk. Full-time bootcamps have higher completion rates but the marginal output (more practice, slightly faster) does not justify the $15-25k tuition + lost income vs. her current part-time path. The bottleneck is portfolio, not bootcamp speed.",
    cost_of_error:
      "20-40k of opportunity + tuition cost; runway pressure that drives a worse first offer.",
    sources: [],
    created_at: iso(NOW - 20 * HOUR),
  },
  {
    id: "stress4-cr-9",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: SUB_PORTFOLIO_ID,
    path:
      "Building all 3 portfolio projects in parallel rather than serially",
    why_compelling: "Diversifies bets, looks more productive on GitHub.",
    why_rejected:
      "Three half-finished projects read worse than one polished project + two README-stage outlines. Parallelism also fragments her depth on any one dataset, which is the opposite of what we want her to demonstrate.",
    cost_of_error:
      "GitHub graveyard of partials. Worst-case interview signal.",
    sources: [],
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress4-cr-10",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: SUB_TARGET_ROLES_ID,
    path:
      "Limiting search to her current geographic metro vs. fully remote",
    why_compelling: "Easier first interviews, lower coordination overhead.",
    why_rejected:
      "Healthcare-analytics roles in 2025-2026 are remote-friendly at well above the all-industry baseline (PBMs, large health systems with multi-site analytics teams, payer-side ops all default-remote). Limiting geographically cuts the addressable role pool by 70-85% with no upside given her constraints.",
    cost_of_error:
      "Triples time-to-first-offer. Significant.",
    sources: [],
    created_at: iso(NOW - 16 * HOUR),
  },
  {
    id: "stress4-cr-11",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Pharmacy informatics as the target track instead of analytics",
    why_compelling:
      "Closer to her current role; fewer skills to bridge; pharmacy-specific.",
    why_rejected:
      "Pharmacy informatics is a legitimate adjacent track but the entry-level market is narrower (most informatics roles want PharmD + 3-5 years). Worth re-considering AFTER 6 months in healthcare analytics if she misses the clinical work — easier to step from analytics into informatics than vice versa.",
    cost_of_error:
      "If she goes informatics-first and the market is closed, she's spent 12 months on a credential path that didn't open doors.",
    sources: [],
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress4-cr-12",
    dossier_id: STRESS4_DOSSIER_ID,
    sub_investigation_id: null,
    path:
      "Waiting until bootcamp completion (4 months out) to start applying",
    why_compelling:
      "Resume looks more complete, less imposter-syndrome friction at apply-time.",
    why_rejected:
      "Application cycles in healthcare analytics run 6-12 weeks from first contact to offer. Starting at bootcamp completion means first offer 6-8 months out. Starting at month 2 of bootcamp (when project #1 ships) compresses that to 4-5 months out. Apply early, with one shippable project as the centerpiece — not when the resume 'feels ready.'",
    cost_of_error:
      "3-4 month delay in first offer; reinforces a perfectionism pattern that will keep biting throughout the search.",
    sources: [],
    created_at: iso(NOW - 12 * HOUR),
  },
];

// ===========================================================================
// Next actions (6)
// ===========================================================================

const NEXT_ACTIONS: NextAction[] = [
  {
    id: "stress4-na-1",
    dossier_id: STRESS4_DOSSIER_ID,
    action:
      "Pick ONE pharmacy-workflow problem you can articulate in 90 seconds and sketch a data-flow for. Answer needs_input #1.",
    rationale:
      "This is the wedge. Every portfolio project, every interview, every cold email is downstream of this single answer. Don't move forward without it.",
    priority: 1,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 10 * HOUR),
  },
  {
    id: "stress4-na-2",
    dossier_id: STRESS4_DOSSIER_ID,
    action:
      "Acquire one healthcare-shaped public dataset this week (CMS Part D claims, or DEA ARCOS county-level dispensing, or a public formulary). Pure data acquisition; analysis comes later.",
    rationale:
      "Removes the 'where do I get data' procrastination block. The first project's quality is mostly determined by whether the dataset is real, not whether the analysis is fancy.",
    priority: 2,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 9 * HOUR),
  },
  {
    id: "stress4-na-3",
    dossier_id: STRESS4_DOSSIER_ID,
    action:
      "Run a self-test SQL exercise on a realistic healthcare-shaped table (joins across claims, members, formulary). 90 minutes, untimed, see where you stall.",
    rationale:
      "Calibrates whether the bootcamp is delivering production-shaped SQL or just syntax practice. The result determines whether to push the bootcamp or supplement with a healthcare-SQL crash course.",
    priority: 3,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 8 * HOUR),
  },
  {
    id: "stress4-na-4",
    dossier_id: STRESS4_DOSSIER_ID,
    action:
      "Schedule one 20-minute call with a current healthcare data analyst. Pull from your pharmacy network — colleagues who left for analytics roles, the analytics person who occasionally visits your store, a former pharmacist who pivoted.",
    rationale:
      "Reference-class calibration. Twenty minutes with one practitioner is worth weeks of LinkedIn scrolling. Ask: what does their week look like; what skill they wish their younger self had built first; what's the actual hiring signal at their org.",
    priority: 4,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 7 * HOUR),
  },
  {
    id: "stress4-na-5",
    dossier_id: STRESS4_DOSSIER_ID,
    action:
      "Set up a public GitHub profile (separate from any existing personal profile if needed). README at the org level pointing at her one in-progress portfolio project, even if it's just the dataset + a problem statement.",
    rationale:
      "GitHub is the verifiable artifact hiring managers will spend 90 seconds on. Empty profile or no profile is worse than a profile with one in-progress project — the latter signals 'in motion,' the former signals 'considering.'",
    priority: 5,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 6 * HOUR),
  },
  {
    id: "stress4-na-6",
    dossier_id: STRESS4_DOSSIER_ID,
    action:
      "Resolve decision_point #1 (domain-bridging vs. generic-DA path) once needs_input #1 is answered. The pivot strategy is downstream of the wedge.",
    rationale:
      "Locking in the path before the wedge is named is premature. After the wedge is identified, the path choice should be straightforward — but it deserves the explicit commitment.",
    priority: 6,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 5 * HOUR),
  },
];

// ===========================================================================
// Investigation log (~70 entries, spread across the 3 work sessions)
// ===========================================================================

const _logEntry = (
  i: number,
  ws: string,
  sub: string | null,
  type: InvestigationLogEntryType,
  summary: string,
  hoursAgo: number,
): InvestigationLogEntry => ({
  id: `stress4-log-${i}`,
  dossier_id: STRESS4_DOSSIER_ID,
  work_session_id: ws,
  sub_investigation_id: sub,
  entry_type: type,
  payload: {},
  summary,
  created_at: iso(NOW - hoursAgo * HOUR),
});

const INVESTIGATION_LOG: InvestigationLogEntry[] = [
  // Session 1 (intake) — 2 days ago
  _logEntry(1, "stress4-ws-1", null, "plan_revised", "Drafted initial 5-item investigation plan", 47.5),
  _logEntry(2, "stress4-ws-1", null, "section_upserted", "Premise challenge recorded — refusing to estimate 'realism' as a percentage", 47.3),
  _logEntry(3, "stress4-ws-1", null, "decision_flagged", "Flagged plan-approval decision_point", 47.2),
  _logEntry(4, "stress4-ws-1", null, "section_upserted", "Created summary section: Where this stands", 47.0),
  _logEntry(5, "stress4-ws-1", null, "section_upserted", "Created reframe section: pharmacy background is a wedge not a hole", 46.8),
  _logEntry(6, "stress4-ws-1", null, "sub_investigation_spawned", "Spawned: comparable trajectories survey", 46.5),
  _logEntry(7, "stress4-ws-1", SUB_TRAJECTORIES_ID, "source_consulted", "BLS pharmacy-tech to analyst transition data", 46.3),
  _logEntry(8, "stress4-ws-1", SUB_TRAJECTORIES_ID, "source_consulted", "r/healthIT and r/datasciencecareers transition threads (2023-2025)", 46.1),
  _logEntry(9, "stress4-ws-1", null, "sub_investigation_spawned", "Spawned: SunshineKeys reference profile review", 45.9),
  _logEntry(10, "stress4-ws-1", SUB_SUNSHINEKEYS_ID, "source_consulted", "github.com/SunshineKeys — pinned repos + language mix", 45.7),
  _logEntry(11, "stress4-ws-1", null, "sub_investigation_spawned", "Spawned: Megan Merrigan reference profile review", 45.5),
  _logEntry(12, "stress4-ws-1", SUB_MERRIGAN_ID, "source_consulted", "linkedin.com/in/megan-merrigan-a824a1265 — career history attempt", 45.3),
  _logEntry(13, "stress4-ws-1", null, "sub_investigation_spawned", "Spawned: bootcamp output audit", 45.1),
  _logEntry(14, "stress4-ws-1", null, "sub_investigation_spawned", "Spawned: target-role taxonomy", 44.9),
  _logEntry(15, "stress4-ws-1", null, "section_upserted", "Created bootcamp-limits section (provisional)", 44.7),
  _logEntry(16, "stress4-ws-1", null, "section_upserted", "Created target-roles section", 44.5),

  // Session 2 (resume, longest) — 30h-22h ago
  _logEntry(17, "stress4-ws-2", SUB_TRAJECTORIES_ID, "sub_investigation_returned", "Comparable trajectories sub returned: pharmtech-to-analytics is well-trodden but invisible in popular pivot lit", 29.8),
  _logEntry(18, "stress4-ws-2", null, "section_revised", "Updated working theory: target healthcare orgs not tech", 29.6),
  _logEntry(19, "stress4-ws-2", SUB_SUNSHINEKEYS_ID, "sub_investigation_returned", "SunshineKeys profile findings recorded as analytical reference", 29.3),
  _logEntry(20, "stress4-ws-2", null, "source_consulted", "Course Report bootcamp outcomes — part-time SQL/Python program completion + placement rates", 29.0),
  _logEntry(21, "stress4-ws-2", null, "source_consulted", "Glassdoor + Levels.fyi — entry healthcare analytics comp bands", 28.7),
  _logEntry(22, "stress4-ws-2", null, "source_consulted", "Indeed + Hospital Recruiting — operations analyst / claims analyst posting volume", 28.4),
  _logEntry(23, "stress4-ws-2", null, "source_consulted", "CMS Part D public claims dataset documentation", 28.0),
  _logEntry(24, "stress4-ws-2", null, "source_consulted", "DEA ARCOS county-level dispensing data — public format and access path", 27.6),
  _logEntry(25, "stress4-ws-2", SUB_PORTFOLIO_ID, "section_upserted", "Drafted portfolio-projects section (provisional)", 27.2),
  _logEntry(26, "stress4-ws-2", SUB_PORTFOLIO_ID, "artifact_added", "Added artifact: domain-bridging portfolio projects spec (~1500 chars)", 26.8),
  _logEntry(27, "stress4-ws-2", SUB_BOOTCAMP_AUDIT_ID, "sub_investigation_returned", "Bootcamp-audit sub returned: certs reliable for syntax, not problem-decomposition", 26.4),
  _logEntry(28, "stress4-ws-2", null, "artifact_added", "Added artifact: bootcamp-output audit checklist", 26.0),
  _logEntry(29, "stress4-ws-2", null, "section_revised", "Promoted target-roles section to confident after taxonomy survey landed", 25.6),
  _logEntry(30, "stress4-ws-2", null, "path_rejected", "Ruled out: master's in health informatics as primary credential strategy", 25.2),
  _logEntry(31, "stress4-ws-2", null, "path_rejected", "Considered-rejected: quitting pharmacy job before first offer", 24.8),
  _logEntry(32, "stress4-ws-2", null, "path_rejected", "Considered-rejected: Big Tech as primary application strategy", 24.4),
  _logEntry(33, "stress4-ws-2", null, "path_rejected", "Considered-rejected: master's in health informatics first", 24.0),
  _logEntry(34, "stress4-ws-2", null, "path_rejected", "Considered-rejected: Kaggle as primary portfolio anchor", 23.6),
  _logEntry(35, "stress4-ws-2", null, "path_rejected", "Considered-rejected: 'open to work' as primary outreach", 23.2),
  _logEntry(36, "stress4-ws-2", null, "section_upserted", "Created '37 is not the obstacle' section", 22.8),
  _logEntry(37, "stress4-ws-2", null, "artifact_added", "Added artifact: 90-second hiring-manager wedge script", 22.5),
  _logEntry(38, "stress4-ws-2", null, "artifact_added", "Added artifact: target-role search query templates", 22.3),
  _logEntry(39, "stress4-ws-2", SUB_MERRIGAN_ID, "sub_investigation_returned", "Megan Merrigan profile review returned (with caveats on LinkedIn fetch reliability)", 22.1),

  // Session 3 (interrupted_crash) — 6h ago, no end
  _logEntry(40, "stress4-ws-3", SUB_TARGET_ROLES_ID, "source_consulted", "Re-pulled SimplyHired postings for 'pharmacy data analyst' filter", 5.8),
  _logEntry(41, "stress4-ws-3", null, "section_revised", "Drafted timeline section (best/likely/worst cases)", 5.5),
  _logEntry(42, "stress4-ws-3", null, "decision_flagged", "Flagged decision_point: 9-month domain-bridging vs. generic-DA path", 5.0),
  _logEntry(43, "stress4-ws-3", null, "input_requested", "Flagged needs_input: which pharmacy-workflow problem can you explain in 90s + sketch a data flow for", 4.7),
  _logEntry(44, "stress4-ws-3", null, "section_upserted", "Created open-question section for the wedge identification", 4.5),
  _logEntry(45, "stress4-ws-3", SUB_PORTFOLIO_ID, "section_revised", "Held portfolio-projects section at provisional pending wedge answer", 4.2),
  _logEntry(46, "stress4-ws-3", null, "stuck_declared", "Tier-1 stuck consideration: portfolio sub blocked on user input — chose not to escalate, recheck next turn", 3.8),
];

// ===========================================================================
// Investigation log counts
// ===========================================================================

export const STRESS4_INVESTIGATION_LOG_COUNTS: Record<string, number> = {
  source_consulted: 12,
  sub_investigation_spawned: 6,
  sub_investigation_returned: 4,
  section_upserted: 9,
  section_revised: 5,
  artifact_added: 4,
  artifact_revised: 0,
  path_rejected: 7,
  decision_flagged: 2,
  input_requested: 1,
  plan_revised: 1,
  stuck_declared: 1,
};

// ===========================================================================
// Change log (28 entries, mixed kinds, newest-first)
// ===========================================================================

export const STRESS4_CHANGE_LOG: ChangeLogEntry[] = [
  { id: "stress4-cl-1", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-3", section_id: SEC_OPEN_WEDGE, kind: "needs_input_added", change_note: "Asked: which pharmacy-workflow problem can you explain in 90s and sketch a data-flow for", created_at: iso(NOW - 4.5 * HOUR) },
  { id: "stress4-cl-2", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-3", section_id: null, kind: "decision_point_added", change_note: "Decision: domain-bridging path vs. generic-DA path", created_at: iso(NOW - 5 * HOUR) },
  { id: "stress4-cl-3", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-3", section_id: SEC_TIMELINE, kind: "section_created", change_note: "Drafted timeline section (best / likely / worst cases)", created_at: iso(NOW - 5.5 * HOUR) },
  { id: "stress4-cl-4", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-3", section_id: SEC_OPEN_WEDGE, kind: "section_created", change_note: "Created open-question section for wedge identification", created_at: iso(NOW - 6 * HOUR) },
  { id: "stress4-cl-5", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "next_action_added", change_note: "Added 6 next-actions, ordered by dependency", created_at: iso(NOW - 22 * HOUR) },
  { id: "stress4-cl-6", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "artifact_added", change_note: "Added artifact: target-role search query templates", created_at: iso(NOW - 22.3 * HOUR) },
  { id: "stress4-cl-7", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "artifact_added", change_note: "Added artifact: 90-second hiring-manager wedge script", created_at: iso(NOW - 22.5 * HOUR) },
  { id: "stress4-cl-8", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: SEC_TARGET_ROLES, kind: "state_changed", change_note: "Promoted target-roles section to confident after taxonomy survey landed", created_at: iso(NOW - 23 * HOUR) },
  { id: "stress4-cl-9", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "considered_and_rejected_added", change_note: "Recorded 7 considered-and-rejected paths (Big Tech, Kaggle, open-to-work, etc.)", created_at: iso(NOW - 23.5 * HOUR) },
  { id: "stress4-cl-10", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "ruled_out_added", change_note: "Ruled out: master's in health informatics as primary credential strategy", created_at: iso(NOW - 25.2 * HOUR) },
  { id: "stress4-cl-11", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: SEC_BOOTCAMP_LIMITS, kind: "section_updated", change_note: "Bootcamp-limits section updated after audit sub returned", created_at: iso(NOW - 26 * HOUR) },
  { id: "stress4-cl-12", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "artifact_added", change_note: "Added artifact: bootcamp-output audit checklist", created_at: iso(NOW - 26 * HOUR) },
  { id: "stress4-cl-13", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "sub_investigation_completed", change_note: "Bootcamp-audit sub: delivered", created_at: iso(NOW - 26.4 * HOUR) },
  { id: "stress4-cl-14", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: SEC_PORTFOLIO, kind: "section_created", change_note: "Drafted portfolio-projects section (provisional)", created_at: iso(NOW - 27.2 * HOUR) },
  { id: "stress4-cl-15", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "artifact_added", change_note: "Added artifact: domain-bridging portfolio projects spec", created_at: iso(NOW - 26.8 * HOUR) },
  { id: "stress4-cl-16", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "sub_investigation_completed", change_note: "SunshineKeys reference sub: delivered with analytical observations", created_at: iso(NOW - 29.3 * HOUR) },
  { id: "stress4-cl-17", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "working_theory_updated", change_note: "Working theory: target healthcare orgs not tech (medium confidence)", created_at: iso(NOW - 29.6 * HOUR) },
  { id: "stress4-cl-18", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "sub_investigation_completed", change_note: "Comparable-trajectories sub: delivered with key reference-class correction", created_at: iso(NOW - 29.8 * HOUR) },
  { id: "stress4-cl-19", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-1", section_id: SEC_TARGET_ROLES, kind: "section_created", change_note: "Created target-roles section", created_at: iso(NOW - 44.5 * HOUR) },
  { id: "stress4-cl-20", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-1", section_id: SEC_BOOTCAMP_LIMITS, kind: "section_created", change_note: "Created bootcamp-limits section (provisional)", created_at: iso(NOW - 44.7 * HOUR) },
  { id: "stress4-cl-21", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-1", section_id: null, kind: "sub_investigation_spawned", change_note: "Spawned 6 sub-investigations: trajectories, SunshineKeys, Merrigan, portfolio, bootcamp, target-roles", created_at: iso(NOW - 45.5 * HOUR) },
  { id: "stress4-cl-22", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-1", section_id: SEC_REFRAME, kind: "section_created", change_note: "Created reframe section: pharmacy background is a wedge not a hole", created_at: iso(NOW - 46.8 * HOUR) },
  { id: "stress4-cl-23", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-1", section_id: SEC_SUMMARY, kind: "section_created", change_note: "Created summary section: Where this stands", created_at: iso(NOW - 47 * HOUR) },
  { id: "stress4-cl-24", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-1", section_id: null, kind: "decision_point_added", change_note: "Plan-approval decision flagged on first turn", created_at: iso(NOW - 47.2 * HOUR) },
  { id: "stress4-cl-25", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-1", section_id: null, kind: "section_created", change_note: "Premise challenge recorded — refusing to estimate 'realism' as a percentage", created_at: iso(NOW - 47.3 * HOUR) },
  { id: "stress4-cl-26", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-1", section_id: null, kind: "plan_updated", change_note: "Drafted initial 5-item investigation plan", created_at: iso(NOW - 47.5 * HOUR) },
  { id: "stress4-cl-27", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "needs_input_added", change_note: "Initial premise-challenge clarifying questions sent to user (resolved same session)", created_at: iso(NOW - 28.5 * HOUR) },
  { id: "stress4-cl-28", dossier_id: STRESS4_DOSSIER_ID, work_session_id: "stress4-ws-2", section_id: null, kind: "needs_input_resolved", change_note: "User confirmed: yes, asking for realism estimate; agent reframes to plan-design", created_at: iso(NOW - 28.4 * HOUR) },
];

// ===========================================================================
// Final assembled fixture
// ===========================================================================

export const stress4CaseFile: DossierFull = {
  dossier: DOSSIER,
  sections: SECTIONS,
  needs_input: NEEDS_INPUT,
  decision_points: DECISION_POINTS,
  reasoning_trail: REASONING_TRAIL,
  ruled_out: RULED_OUT,
  work_sessions: WORK_SESSIONS,
  artifacts: ARTIFACTS,
  sub_investigations: SUB_INVESTIGATIONS,
  investigation_log: INVESTIGATION_LOG,
  considered_and_rejected: CONSIDERED_AND_REJECTED,
  next_actions: NEXT_ACTIONS,
};
