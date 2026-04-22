// Day-5 stress fixture. A "what does this look like when the agent
// actually runs for two days" dossier. Pathologically long in places:
// a 95-char title, a 300-ish char problem statement, 8 sections (one
// with a markdown table, one with nested lists, one with a code block,
// one ruled-out), 6 sub-investigations, 4 artifacts (one ~1500 chars),
// 12 considered-and-rejected entries, 6 next actions, 200 investigation
// log entries, 3 work sessions, a pre-visit change-log of 30 entries.
//
// Used by /stress (see StressPage.tsx) to walk the detail page through
// worst-case rendering. Not loaded on any production path.

import type {
  Artifact,
  ChangeLogEntry,
  ConsideredAndRejected,
  DossierFull,
  InvestigationLogEntry,
  InvestigationLogEntryType,
  NextAction,
  Section,
  SubInvestigation,
  WorkSession,
} from "../api/types";

export const STRESS_DOSSIER_ID = "stress-case-12345";

const NOW = Date.now();
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

const iso = (ms: number) => new Date(ms).toISOString();

// ---------- sub-investigations ----------

const SUB_SOL_ID = "stress-sub-sol-deep";
const SUB_ESTATE_ID = "stress-sub-estate";
const SUB_CA_ID = "stress-sub-ca-specifics";
const SUB_AZ_ID = "stress-sub-az-specifics";
const SUB_NEGOTIATION_ID = "stress-sub-negotiation-bench";
const SUB_CFPB_ID = "stress-sub-cfpb-complaints";

// ---------- section ids ----------

const SEC_SUMMARY = "stress-sec-summary";
const SEC_SOL = "stress-sec-sol";
const SEC_VALIDATION = "stress-sec-validation";
const SEC_ESTATE_NO = "stress-sec-estate-no";
const SEC_TACTICS = "stress-sec-tactics";
const SEC_CA_SPECIFIC = "stress-sec-ca";
const SEC_RULED_CONSOLIDATION = "stress-sec-ruled-consolidation";
const SEC_OPEN = "stress-sec-open-question";

// ---------- artifact ids ----------

const ART_LETTER = "stress-art-validation-letter";
const ART_SCRIPT = "stress-art-collector-call-script";
const ART_COMPARISON = "stress-art-tactic-comparison";
const ART_CHECKLIST = "stress-art-pre-call-checklist";

// ===========================================================================
// Dossier
// ===========================================================================

const DOSSIER = {
  id: STRESS_DOSSIER_ID,
  title:
    "Credit card debt negotiation — renegotiating deceased parent's credit card debts when there's no estate (CA/AZ jurisdiction)",
  problem_statement:
    "My close friend's mother passed last October leaving two credit-card balances (Chase ~$8,400, Citi ~$3,100). There is effectively no estate — no probate assets, a leased apartment, modest personal effects. Collectors are calling my friend directly at her California number, and also reaching her brother in Arizona. She wants to handle it without a debt-settlement firm. She is asking what percentage to open at; before that, we need to confirm the debt is owed, validated under the FDCPA, and still within each state's statute of limitations. CA/AZ rules diverge meaningfully on SoL length, acknowledgment, and community-property exposure.",
  out_of_scope: [
    "tax treatment of forgiven balances (1099-C)",
    "funeral and burial cost recovery",
    "estate planning for the surviving family",
    "medical debt at the hospice facility",
    "the mother's auto loan (already paid off)",
  ],
  dossier_type: "decision_memo" as const,
  status: "active" as const,
  check_in_policy: {
    cadence: "on_demand" as const,
    notes:
      "Pause between user turns; resume when user answers the open question about written validation and confirms the date of last payment on each account.",
  },
  last_visited_at: iso(NOW - 22 * HOUR),
  created_at: iso(NOW - 2 * DAY),
  updated_at: iso(NOW - 12 * MIN),
  debrief: {
    what_i_did:
      "Spent two sessions pinning down the SoL landscape across CA and AZ, pulled and read the relevant FDCPA and Regulation F provisions, cross-referenced CFPB consent decrees from the last three years against the two collectors currently calling your friend, and drafted four reusable artifacts: a validation-request letter, a phone-call script, a comparison table of tactical options, and a pre-call checklist. Opened six sub-investigations — two returned with findings, one is still running against the CFPB complaint database, one was abandoned because the hypothesis collapsed.",
    what_i_found:
      "Three load-bearing findings. (1) Neither card has a written validation on file, which means the FDCPA § 1692g 30-day window hasn't even started for the most recent collector — that's the lever. (2) The Chase balance is past CA's 4-year written-contract SoL if the date-of-last-payment estimate is correct; the Citi balance is likely still within window. (3) Under CA probate law, with no estate, the surviving children have no personal liability for these debts — this should be the backstop framing in every call. Also: the Citi collector (MRS BPO) has a live CFPB consent-order obligation to provide itemization on request.\n\nCollector call frequency spiked after the mother's death notice was indexed, which is typical of debt-buyer scraping of obituary data. Nothing actionable there, but worth calling out so your friend doesn't take the call volume as evidence of a stronger case than the collector actually has.",
    what_you_should_do_next:
      "Send the validation-request letter (see Artifacts) by certified mail this week. Do NOT make a partial payment, acknowledge the debt as valid, or give a new payment date — any of those can restart the SoL clock in CA. Answer the one open question so we can calibrate an opening offer if validation returns clean.",
    what_i_couldnt_figure_out:
      "Whether the original Chase card was opened jointly or as an authorized-user arrangement. If it was joint, CA's community-property rule could pull the surviving spouse back in — though there is no surviving spouse, only the two adult children. Your friend should check the card's original application; an answer of \"authorized user\" closes this risk entirely.",
    last_updated: iso(NOW - 30 * MIN),
  },
  investigation_plan: {
    items: [
      {
        id: "stress-plan-1",
        question:
          "What is the statute of limitations on credit-card debt in California, and has it likely run on either balance?",
        rationale:
          "SoL is the pre-question. If the debt is time-barred, the negotiation changes completely — we don't negotiate, we force validation and wait them out.",
        expected_sources: [
          "CA Code Civ. Proc. § 337",
          "consumerfinance.gov",
          "nclc.org",
        ],
        as_sub_investigation: true,
        status: "completed" as const,
      },
      {
        id: "stress-plan-2",
        question:
          "What is the SoL in Arizona, and does the brother's Arizona residence pull AZ rules in for any reason?",
        rationale:
          "Collectors may forum-shop. AZ has a shorter open-account SoL (3 years) than CA, which changes our stance if the brother is ever served.",
        expected_sources: [
          "A.R.S. § 12-543",
          "Arizona judicial branch decisions",
        ],
        as_sub_investigation: true,
        status: "completed" as const,
      },
      {
        id: "stress-plan-3",
        question:
          "Under CA/AZ probate and community-property law, are the surviving children personally liable for these debts given there is no estate?",
        rationale:
          "The answer drives the opening line of every call. If there's zero personal liability, we decline engagement, full stop.",
        expected_sources: [
          "CA Probate Code § 13100",
          "A.R.S. Title 14",
          "nolo.com",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
      {
        id: "stress-plan-4",
        question:
          "Have either of the two collectors (Midland Credit Management, MRS BPO) been subject to recent CFPB enforcement that would change our leverage?",
        rationale:
          "A current consent decree limits what the collector can ask for on a call and can be cited as negotiation leverage.",
        expected_sources: [
          "consumerfinance.gov/enforcement",
          "PACER",
        ],
        as_sub_investigation: true,
        status: "in_progress" as const,
      },
      {
        id: "stress-plan-5",
        question:
          "Given the likely validation and SoL picture, what's a reasonable opening-offer range if we do decide to negotiate?",
        rationale:
          "This is what the user originally asked. It's gated on items 1-4; we hold it until those return.",
        expected_sources: [
          "user-paste of collector letters",
          "NCLC practice manuals",
        ],
        as_sub_investigation: false,
        status: "planned" as const,
      },
    ],
    rationale:
      "Plan is gated on SoL and validation — the percentage question doesn't come into play until we know we're negotiating a real obligation. The four sub-investigations run in parallel; item 5 waits on them.",
    drafted_at: iso(NOW - 2 * DAY + 20 * MIN),
    approved_at: iso(NOW - 2 * DAY + 35 * MIN),
    revised_at: iso(NOW - 18 * HOUR),
    revision_count: 2,
  },
};

// ===========================================================================
// Sections
// ===========================================================================

const SECTIONS: Section[] = [
  {
    id: SEC_SUMMARY,
    dossier_id: STRESS_DOSSIER_ID,
    type: "summary",
    title: "Where this stands",
    content:
      "Your friend is being contacted by two debt collectors on balances left behind when her mother passed. There is no estate to collect from. The core question is not what percentage to open at — it is whether she has to, or should, engage at all. This memo lays out three gates she should clear before any negotiation begins: written validation under the FDCPA, a statute-of-limitations check in both California and Arizona, and a clear disposition on personal liability under CA probate law. If any of the three returns \"no,\" the path forward is not negotiation — it's procedural pushback and, where warranted, a complaint to the CFPB.",
    state: "confident",
    order: 1,
    change_note:
      "Rewrote the summary after SoL and FDCPA sections both hardened — the opening framing is now \"three gates\" rather than \"opening offer range.\"",
    sources: [],
    depends_on: [],
    last_updated: iso(NOW - 45 * MIN),
    created_at: iso(NOW - 30 * HOUR),
  },
  {
    id: SEC_SOL,
    dossier_id: STRESS_DOSSIER_ID,
    type: "finding",
    title:
      "Statute of limitations — California (4 years, written contract) and Arizona (3 years, open account)",
    content:
      "California treats credit-card debt as a written contract under CCP § 337, which gives collectors **four years** from the date of last payment or acknowledgment to file suit. Arizona treats it as an open account under A.R.S. § 12-543, which is **three years**. In both states a partial payment, a written acknowledgment, or — crucially, in CA — even a verbal admission on a recorded call can restart the clock.\n\nThe trap for your friend: many collectors open calls with something like \"I just need to confirm this is Marjorie's daughter — you are responsible for this account, correct?\" There is no good answer to that question. An uneducated \"yes\" can be read as acknowledgment; a denial can be transcribed as a dispute (which ironically helps us). The only safe answer is: **\"I am not discussing this on the phone. Send written validation of the debt to this address.\"**\n\nOn the Chase account, the date of last payment appears to be Q2 2021 (your friend's estimate; needs confirmation from the original statements). That puts the Chase balance past CA's 4-year window as of approximately June 2025 — time-barred. The Citi account's last payment appears to be Q1 2022, which puts it within window until Q1 2026, i.e. still live today.",
    state: "confident",
    order: 2,
    change_note:
      "Upgraded from provisional after NCLC's 2024 state-by-state SoL table confirmed CA's 4-year written-contract treatment and the acknowledgment-restart rule.",
    sources: [
      {
        kind: "web",
        url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CCP&sectionNum=337",
        title: "CCP § 337 — Statute of limitations: written contracts",
        snippet:
          "An action upon any contract, obligation or liability founded upon an instrument in writing … within four years.",
      },
      {
        kind: "web",
        url: "https://www.azleg.gov/ars/12/00543.htm",
        title: "A.R.S. § 12-543 — Oral debt, stated or open accounts; relief on ground of fraud or mistake; three year limitation",
        snippet:
          "There shall be commenced and prosecuted within three years after the cause of action accrues … an action on an open account.",
      },
      {
        kind: "web",
        url: "https://library.nclc.org/collection-actions/02.01/time-barred-debts-state-table-2024.html",
        title: "NCLC — Time-barred debts, state-by-state reference (2024)",
        snippet:
          "State-by-state SoL, revival rules, and whether oral acknowledgment restarts the clock.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 2 * HOUR),
    created_at: iso(NOW - 40 * HOUR),
  },
  {
    id: SEC_VALIDATION,
    dossier_id: STRESS_DOSSIER_ID,
    type: "finding",
    title: "FDCPA validation — the 30-day dispute window hasn't started",
    content:
      "Under 15 U.S.C. § 1692g and the CFPB's Regulation F (12 CFR § 1006.34), a debt collector must — within five days of its initial communication — send a written notice that includes the amount of the debt, the name of the creditor to whom it is owed, and the consumer's right to dispute it. Phone calls alone do not satisfy this.\n\nRegulation F further requires an **itemization date** and the **consumer's account number** (truncated or full) in the validation notice. The dispute window runs for thirty days from the consumer's receipt of that notice. During the window, if the consumer sends a written dispute, the collector **must cease collection activity** until they mail documentation from the original creditor establishing ownership of the debt and the balance.\n\nYour friend reports she has received phone calls but no written notice matching these requirements. That means the thirty-day window hasn't started — the lever is fully available. The draft validation-request letter in Artifacts cites the specific CFR provisions; sending it by certified mail starts the clock on the collector's response obligation and, if they can't validate, effectively ends the matter.",
    state: "confident",
    order: 3,
    change_note:
      "Added the Reg F itemization-date detail after MRS BPO's own public FAQ admitted they don't auto-send itemized notices for accounts they acquired through bulk purchase.",
    sources: [
      {
        kind: "web",
        url: "https://www.consumerfinance.gov/rules-policy/regulations/1006/34/",
        title: "12 CFR § 1006.34 — Notice for validation of debts (Reg F)",
        snippet:
          "A debt collector must provide a validation notice containing the itemization, the creditor's name, and the consumer's dispute rights.",
      },
      {
        kind: "web",
        url: "https://www.law.cornell.edu/uscode/text/15/1692g",
        title: "15 U.S.C. § 1692g — Validation of debts",
        snippet:
          "Within five days after the initial communication … a debt collector shall … send the consumer a written notice.",
      },
    ],
    depends_on: [],
    last_updated: iso(NOW - 3 * HOUR),
    created_at: iso(NOW - 36 * HOUR),
  },
  {
    id: SEC_ESTATE_NO,
    dossier_id: STRESS_DOSSIER_ID,
    type: "finding",
    title: "No estate, no personal liability for the children",
    content:
      "Under California Probate Code § 13100 and general common-law principles, an unsecured debt of a decedent is owed by the decedent's estate — not by the surviving family members. Collectors are permitted to contact an estate representative to file a claim against the estate. They are **not** permitted to imply that a relative who is not a co-signer, joint account holder, or community-property obligor is personally on the hook.\n\nExceptions to watch:\n\n- **Joint account holders** (as distinct from authorized users). If your friend was on the card as a joint account holder — i.e. her name is on the cardholder agreement — she is personally liable for the full balance. Authorized-user status does not carry this liability.\n- **Community-property states**, which includes both CA and AZ. A surviving *spouse* can be liable for debts incurred during the marriage out of community assets; a surviving *child* generally cannot. The mother in this matter had no surviving spouse, so this exception is inactive.\n- **\"Filial responsibility\" statutes** exist in about thirty states and have historically targeted medical and long-term-care debt, not consumer credit. California has no such statute on consumer credit; Arizona has one on its books but it is largely unenforced against unsecured consumer obligations.\n\nBottom line for your friend: absent a co-signer or joint-account relationship, she owes nothing on these balances personally. Every call should open and close with that fact.",
    state: "confident",
    order: 4,
    change_note:
      "Moved from provisional to confident once your friend confirmed verbally she was never on either card as a joint account holder (needs written confirmation from the original applications — see open question).",
    sources: [
      {
        kind: "web",
        url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=PROB&sectionNum=13100",
        title: "CA Probate Code § 13100 — Collection of personal property without administration",
        snippet:
          "The successor of the decedent may … without procuring letters of administration … collect any item of property.",
      },
      {
        kind: "web",
        url: "https://www.nolo.com/legal-encyclopedia/are-adult-children-responsible-parent-s-debts.html",
        title: "Nolo — Are adult children responsible for parent's debts?",
        snippet:
          "As a general rule, no. The estate is. Exceptions are narrow and state-specific.",
      },
    ],
    depends_on: [SEC_SOL],
    last_updated: iso(NOW - 5 * HOUR),
    created_at: iso(NOW - 34 * HOUR),
  },
  {
    id: SEC_TACTICS,
    dossier_id: STRESS_DOSSIER_ID,
    type: "recommendation",
    title: "Comparison of the tactical options",
    content:
      "Four paths forward, ranked by information-positive first:\n\n| Path | Cost | Info value | Risk | When to use |\n| --- | --- | --- | --- | --- |\n| FDCPA validation request | $8 cert. mail | **High** — forces paper trail | Low | First move, always |\n| Cease-and-desist letter | $8 cert. mail | Low | Medium — can accelerate litigation if SoL hasn't run | After SoL confirmed run |\n| CFPB complaint | Free (online) | Medium | Low — collectors respond fast | After validation request is ignored |\n| Negotiate a lump-sum settlement | Balance-dependent | High once validated | High if SoL is live & balance is real | Only after gates 1–3 clear |\n\nThe validation request is the first move in every scenario because it costs $8, takes ten minutes, and forces information out of the collector that we need regardless of which path we end up on. Cease-and-desist is tempting but shuts down the conversation entirely and can push the collector to sue before the SoL has run; we hold it in reserve. A CFPB complaint is a useful escalation lever once we have evidence of a specific violation (failure to provide validation within the window, continuing to call after written dispute, misrepresenting personal liability of a non-obligor).\n\nOn Chase specifically: because our current read is that the SoL has already run, a cease-and-desist is cleanly defensible. On Citi: validation first, wait for response, evaluate.",
    state: "confident",
    order: 5,
    change_note:
      "Rewrote the comparison as a table after the first draft's prose got unwieldy. The four-column format is easier to act on.",
    sources: [],
    depends_on: [SEC_SOL, SEC_VALIDATION],
    last_updated: iso(NOW - 90 * MIN),
    created_at: iso(NOW - 20 * HOUR),
  },
  {
    id: SEC_CA_SPECIFIC,
    dossier_id: STRESS_DOSSIER_ID,
    type: "evidence",
    title: "California-specific citations and a code snippet for the validation letter",
    content:
      "CA-specific rules your friend should know cold:\n\n1. CCP § 337 — 4-year SoL on written contracts\n    - Runs from date of last payment or written acknowledgment\n    - Restarted by: partial payment, written acknowledgment, or verbal admission on a recorded line\n    - Not restarted by: refusing to engage, requesting validation\n2. Rosenthal Fair Debt Collection Practices Act (CA Civ. Code § 1788 et seq.) — the state analog to the federal FDCPA, with these extensions:\n    - Applies to **original creditors**, not just third-party collectors (federal FDCPA does not)\n    - Allows private right of action with attorneys' fees\n    - Damages cap is separate from federal\n3. CA Civ. Code § 1788.18 — collectors must provide validation of the original creditor within 15 days of a written request from the consumer, on top of the federal 30-day window\n\nHere's the exact header block the validation letter should include, verbatim:\n\n```\nVia Certified Mail, Return Receipt Requested\nCertified Mail Tracking No.: [INSERT]\n\nRe: Your reference number [INSERT — from collector's letter if any]\n    Original creditor (reported): [INSERT]\n    Account number (last four): [INSERT]\n    Amount reported: $[INSERT]\n\n    This is a dispute under 15 U.S.C. § 1692g(b) and a request\n    for validation under California Civil Code § 1788.18.\n```\n\nThe certified-mail tracking number matters — it's what establishes the date of receipt for the 30-day clock. Keep the return receipt; it's your proof if the collector keeps calling after the dispute lands.",
    state: "provisional",
    order: 6,
    change_note:
      "Kept provisional because the CA Civ. Code § 1788.18 citation needs a second-source confirmation — NCLC's write-up frames the timing slightly differently than the statute text.",
    sources: [
      {
        kind: "web",
        url: "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=CIV&division=3.&title=1.6C.&part=4.&chapter=&article=",
        title: "CA Civ. Code § 1788 et seq. — Rosenthal FDCPA",
        snippet:
          "California's state-law analog to the federal FDCPA, extending several provisions to original creditors.",
      },
    ],
    depends_on: [SEC_VALIDATION],
    last_updated: iso(NOW - 7 * HOUR),
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: SEC_RULED_CONSOLIDATION,
    dossier_id: STRESS_DOSSIER_ID,
    type: "ruled_out",
    title: "Debt consolidation loan",
    content:
      "A consolidation loan assumes there's an obligor whose cash flow can service a new combined monthly payment. The obligor here is a deceased estate with no assets. Your friend has no personal obligation and therefore no reason to take on a new loan. Ruled out.",
    state: "confident",
    order: 7,
    change_note: "Ruled out and kept visible so the reader sees the path was considered.",
    sources: [],
    depends_on: [],
    last_updated: iso(NOW - 28 * HOUR),
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: SEC_OPEN,
    dossier_id: STRESS_DOSSIER_ID,
    type: "open_question",
    title: "Open: was your friend ever on either card as a joint account holder?",
    content:
      "We need written confirmation from the original card applications. Authorized-user status is common and does NOT create personal liability. Joint account holder status is rarer and DOES. Everything downstream turns on this — if the answer comes back \"joint,\" the no-personal-liability framing collapses for that card and we have to replan.",
    state: "blocked",
    order: 8,
    change_note: "Blocked pending user answer; don't start calls until this is answered.",
    sources: [],
    depends_on: [SEC_ESTATE_NO],
    last_updated: iso(NOW - 4 * HOUR),
    created_at: iso(NOW - 8 * HOUR),
  },
];

// ===========================================================================
// Sub-investigations
// ===========================================================================

const SUB_INVESTIGATIONS: SubInvestigation[] = [
  {
    id: SUB_SOL_ID,
    dossier_id: STRESS_DOSSIER_ID,
    parent_section_id: SEC_SOL,
    scope: "Pin down the California statute-of-limitations landscape for credit-card debt, including the exact rule on verbal acknowledgment",
    questions: [
      "What statute governs — CCP § 337 (written), § 339 (oral), or the Rosenthal Act?",
      "Does verbal acknowledgment on a recorded line restart the clock in CA?",
      "What is the revival rule for a post-SoL partial payment?",
      "Are there any 2023–2024 appellate decisions that narrow or expand the 4-year window?",
    ],
    state: "delivered",
    return_summary:
      "CCP § 337 governs (4 years, written contract). Verbal acknowledgment on a recorded line CAN restart the clock per *Martinez v. Portfolio Recovery* (Cal. App. 2019); safer to assume yes in all cases. Post-SoL partial payment does not revive in CA unless coupled with a written acknowledgment of the full balance. No 2023–2024 appellate decisions altered the 4-year baseline.",
    findings_section_ids: [SEC_SOL],
    findings_artifact_ids: [],
    started_at: iso(NOW - 40 * HOUR),
    completed_at: iso(NOW - 30 * HOUR),
  },
  {
    id: SUB_ESTATE_ID,
    dossier_id: STRESS_DOSSIER_ID,
    parent_section_id: SEC_ESTATE_NO,
    scope: "Resolve whether the surviving children have any theory of personal liability under CA probate + community-property + filial-responsibility law",
    questions: [
      "Is there a CA filial-responsibility statute that reaches consumer debt?",
      "Does the community-property rule reach surviving children (not spouse)?",
      "What does CA Probate Code § 13100 say about small-estate claims in this specific fact pattern?",
    ],
    state: "delivered",
    return_summary:
      "No CA filial-responsibility statute reaches consumer credit debt. Community-property rule reaches surviving spouse only; surviving children are not obligors. § 13100 small-estate procedure is available but not mandatory — with no assets, there is nothing to collect against, period. The only way back to personal liability is a joint-account or co-signer relationship, which needs to be confirmed against the original applications (see open question).",
    findings_section_ids: [SEC_ESTATE_NO],
    findings_artifact_ids: [],
    started_at: iso(NOW - 36 * HOUR),
    completed_at: iso(NOW - 26 * HOUR),
  },
  {
    id: SUB_CA_ID,
    dossier_id: STRESS_DOSSIER_ID,
    parent_section_id: SEC_CA_SPECIFIC,
    scope: "California-specific protections beyond federal FDCPA — the Rosenthal Act, CA Civ. Code § 1788.18 validation timing",
    questions: [
      "What does Rosenthal extend that the federal FDCPA doesn't?",
      "What's the exact validation-request timeline under § 1788.18?",
      "Does Rosenthal give a private right of action on its own?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [],
    findings_artifact_ids: [],
    started_at: iso(NOW - 18 * HOUR),
    completed_at: null,
  },
  {
    id: SUB_AZ_ID,
    dossier_id: STRESS_DOSSIER_ID,
    parent_section_id: null,
    scope: "Arizona-specific statute of limitations and collector-licensing rules — in case the brother's AZ residence becomes a forum issue",
    questions: [
      "What is AZ's SoL on open-account credit-card debt?",
      "Does AZ have a collector-licensing requirement that the current collectors are out of compliance with?",
      "Does AZ's filial-responsibility statute reach consumer credit?",
    ],
    state: "abandoned",
    return_summary:
      "Abandoned: the brother has told the collector to cease contact with him personally, and we do not expect forum-shopping to AZ given the primary obligor (the estate) was resident in CA. If that changes we'll reopen. Preliminary finding: AZ SoL is 3 years on open-account debt per A.R.S. § 12-543; AZ has collector-licensing but both collectors appear to be licensed; filial-responsibility does not reach consumer credit.",
    findings_section_ids: [],
    findings_artifact_ids: [],
    started_at: iso(NOW - 30 * HOUR),
    completed_at: iso(NOW - 14 * HOUR),
  },
  {
    id: SUB_NEGOTIATION_ID,
    dossier_id: STRESS_DOSSIER_ID,
    parent_section_id: null,
    scope: "Benchmark opening-offer percentages for settled-lump-sum negotiations on debt-buyer portfolios similar to these",
    questions: [
      "What's the typical acquisition price of a 3–5 year old credit-card debt on the secondary market?",
      "What opening-offer percentage have NCLC practitioners reported getting accepted on post-SoL accounts?",
      "How does that shift when the account is still within window?",
    ],
    state: "running",
    return_summary: null,
    findings_section_ids: [],
    findings_artifact_ids: [],
    started_at: iso(NOW - 10 * HOUR),
    completed_at: null,
  },
  {
    id: SUB_CFPB_ID,
    dossier_id: STRESS_DOSSIER_ID,
    parent_section_id: null,
    scope: "CFPB enforcement history against the two named collectors — Midland Credit Management and MRS BPO",
    questions: [
      "Are either collector currently under a consent order?",
      "Any 2022–2024 CFPB complaints specific to deceased-estate collections?",
      "Any pattern of failure-to-validate complaints against either?",
    ],
    state: "delivered",
    return_summary:
      "MRS BPO has a live 2023 consent order requiring itemization on request for any account acquired through bulk purchase — directly relevant here. Midland has a 2015 order (largely expired) and a 2022 CFPB complaint pattern around deceased-estate contact. Complaints to the CFPB portal on either collector get a median 14-day response; useful as escalation if validation request is ignored.",
    findings_section_ids: [],
    findings_artifact_ids: [ART_LETTER],
    started_at: iso(NOW - 14 * HOUR),
    completed_at: iso(NOW - 6 * HOUR),
  },
];

// ===========================================================================
// Artifacts
// ===========================================================================

const VALIDATION_LETTER_CONTENT = `# Validation-request letter — Midland Credit Management

**Via Certified Mail, Return Receipt Requested**
Certified Mail Tracking No.: _[fill in at post office]_

---

**Midland Credit Management, Inc.**
Attn: Dispute Resolution
350 Camino de la Reina, Suite 100
San Diego, CA 92108

Re: Your reference number _[from collector's letter]_
Original creditor (reported): Chase Bank, N.A.
Account number (last four): _[from collector's letter]_
Amount reported: $_[from collector's letter]_

Dear Sir or Madam:

This letter constitutes a **dispute** under 15 U.S.C. § 1692g(b) and a **request for validation** of the above-referenced debt under both the federal Fair Debt Collection Practices Act and California Civil Code § 1788.18.

Please provide the following within thirty (30) days of receipt:

1. A copy of the original signed cardholder agreement between the consumer and the original creditor identified above;
2. An itemized statement of the current balance, including principal, interest, fees, and the date of each;
3. Documentation of the chain of assignment from the original creditor to your firm, including any intervening debt purchasers;
4. The date of the last payment on this account;
5. The name and address of the original creditor's records custodian.

Until your firm provides the foregoing, you must cease collection activity on this account pursuant to 15 U.S.C. § 1692g(b). This letter is **not** an acknowledgment that the debt is owed, nor that the consumer is the proper obligor.

Please direct all further communication regarding this account to the undersigned, in writing, at the address below. Telephone contact is not consented to.

Sincerely,

_[Your friend's name]_
_[Address]_
_[Date]_

cc: Consumer Financial Protection Bureau (if no response within 30 days)`;

const CALL_SCRIPT_CONTENT = `# If they call — what to say

**Do not confirm your identity beyond your first name.**

When they ask if you are responsible for this account:
> "I am not discussing this on the phone. Please send written validation of this debt, including the original cardholder agreement, to this address: [ADDRESS]."

If they push:
> "I'm ending this call. Any further contact should be in writing."

**Hang up.** Do not apologize. Do not promise to call back.`;

const COMPARISON_CONTENT = `# Tactical options — comparison

| Path | Cost | Info value | Risk | First pick? |
| --- | --- | --- | --- | --- |
| FDCPA validation request | $8 | High | Low | Yes |
| Cease-and-desist letter | $8 | Low | Medium | No |
| CFPB complaint | Free | Medium | Low | After 30-day window |
| Lump-sum settlement | Balance-dependent | High once validated | High | Only after all gates |

Validation first, always. Settlement last, and only if validation comes back clean.`;

const CHECKLIST_CONTENT = `# Pre-call checklist

- [ ] Confirm joint-account vs. authorized-user status on each card (see open question)
- [ ] Pull original statements to confirm date of last payment on each card
- [ ] Keep a written log of every collector call: date, time, collector name, what was said
- [ ] Do NOT confirm identity on the phone
- [ ] Do NOT confirm the debt is yours
- [ ] Do NOT promise a payment date
- [ ] Do NOT make a partial payment, even a symbolic one
- [ ] Send validation-request letter by certified mail
- [ ] Keep the green return-receipt card
- [ ] File CFPB complaint if no response within 30 days`;

const ARTIFACTS: Artifact[] = [
  {
    id: ART_LETTER,
    dossier_id: STRESS_DOSSIER_ID,
    kind: "letter",
    title: "Validation-request letter (Chase / Midland)",
    content: VALIDATION_LETTER_CONTENT,
    intended_use:
      "Send by certified mail, return receipt requested, to Midland Credit Management. This starts the FDCPA 30-day clock.",
    state: "ready",
    kind_note:
      "A near-identical version for the Citi / MRS BPO account is in draft; swap the creditor block and resend.",
    supersedes: null,
    last_updated: iso(NOW - 2 * HOUR),
    created_at: iso(NOW - 16 * HOUR),
  },
  {
    id: ART_SCRIPT,
    dossier_id: STRESS_DOSSIER_ID,
    kind: "script",
    title: "If they call — short phone script",
    content: CALL_SCRIPT_CONTENT,
    intended_use:
      "Keep this by the phone. The script is deliberately short so you don't improvise under pressure.",
    state: "ready",
    kind_note: null,
    supersedes: null,
    last_updated: iso(NOW - 6 * HOUR),
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: ART_COMPARISON,
    dossier_id: STRESS_DOSSIER_ID,
    kind: "comparison",
    title: "Tactical options — comparison table",
    content: COMPARISON_CONTENT,
    intended_use:
      "A one-screen view of the four paths forward. Print it out and tape it to the fridge.",
    state: "ready",
    kind_note: null,
    supersedes: null,
    last_updated: iso(NOW - 3 * HOUR),
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: ART_CHECKLIST,
    dossier_id: STRESS_DOSSIER_ID,
    kind: "checklist",
    title: "Pre-call checklist",
    content: CHECKLIST_CONTENT,
    intended_use:
      "Walk through this before making any outbound call to a collector, or immediately after hanging up from an inbound one.",
    state: "draft",
    kind_note: "Draft — will move to ready once your friend confirms joint-vs-authorized-user status.",
    supersedes: null,
    last_updated: iso(NOW - 1 * HOUR),
    created_at: iso(NOW - 4 * HOUR),
  },
];

// ===========================================================================
// Considered and rejected (12)
// ===========================================================================

const CONSIDERED_AND_REJECTED: ConsideredAndRejected[] = [
  {
    id: "stress-cr-1",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Hire a debt-settlement firm",
    why_compelling:
      "Offloads the emotional labor of dealing with collectors. Some firms have volume-negotiation leverage on debt-buyer portfolios.",
    why_rejected:
      "User explicitly excluded. Also: typical fees of 15–25% of enrolled debt would eat most of any settlement savings on a balance this size; many firms pressure clients to stop paying ALL debts to force settlement, which tanks credit and creates additional SoL risk.",
    cost_of_error:
      "Moderate — wasted fees, prolonged process, potential credit damage.",
    sources: [],
    created_at: iso(NOW - 40 * HOUR),
  },
  {
    id: "stress-cr-2",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "File bankruptcy on behalf of the estate",
    why_compelling:
      "Discharges unsecured debt. A clean legal endpoint.",
    why_rejected:
      "No estate of any size exists to file for. Bankruptcy has no obligor and no assets to administer — the filing would be dismissed at intake.",
    cost_of_error: "Low — the filing fee and the time to prepare it.",
    sources: [],
    created_at: iso(NOW - 39 * HOUR),
  },
  {
    id: "stress-cr-3",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: SUB_NEGOTIATION_ID,
    path: "Open negotiations immediately at 20% of the reported balance",
    why_compelling:
      "Debt-buyer portfolios are typically acquired at 4–8 cents on the dollar, so 20% leaves room for the collector to profit and is a plausible opening anchor.",
    why_rejected:
      "Premature. Opening a negotiation is itself an acknowledgment of the debt and the party's obligation to pay it, and in CA an acknowledgment can restart the SoL clock. Also: we don't yet know that the debt has been validly transferred to the current collector.",
    cost_of_error:
      "High — restarts the SoL on the Chase balance (currently likely past window), converts a $0 obligation into a $1,600 obligation.",
    sources: [],
    created_at: iso(NOW - 35 * HOUR),
  },
  {
    id: "stress-cr-4",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Ignore all calls until served with a lawsuit",
    why_compelling:
      "Costs nothing. Forces the collector to bear legal costs before any obligation to respond.",
    why_rejected:
      "Forfeits the validation-window leverage. Also: a default judgment is a real risk if the collector does sue and the consumer doesn't respond; default judgments can be collected against later, potentially for decades.",
    cost_of_error:
      "High — a default judgment turns a procedurally-weak claim into a collectable one.",
    sources: [],
    created_at: iso(NOW - 34 * HOUR),
  },
  {
    id: "stress-cr-5",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Immediately escalate to CFPB complaint before sending validation request",
    why_compelling:
      "Fast pressure on the collector. Signals the consumer is organized.",
    why_rejected:
      "Weakens the paper trail. CFPB complaints are most effective as a response to a specific documented violation — sending one preemptively, before the collector has had a chance to respond to a validation request, dilutes the complaint's weight. Save it for the 31st day if no validation arrives.",
    cost_of_error: "Low — we can always file later.",
    sources: [],
    created_at: iso(NOW - 32 * HOUR),
  },
  {
    id: "stress-cr-6",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: SUB_AZ_ID,
    path: "Preemptively notify the AZ brother's employer that a debt collector may contact them",
    why_compelling:
      "Workplace contact by collectors is a common FDCPA violation pattern. Getting ahead of it would speed any § 1692c(a)(3) complaint.",
    why_rejected:
      "Volunteers information the collector doesn't currently have. The brother has already told the collector to cease contact with him personally; escalating preemptively to his employer invites calls there.",
    cost_of_error:
      "Low — but violates the \"don't volunteer information\" principle.",
    sources: [],
    created_at: iso(NOW - 28 * HOUR),
  },
  {
    id: "stress-cr-7",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Send a cease-and-desist as the first move on both accounts",
    why_compelling:
      "Stops collector contact immediately and is a one-page letter.",
    why_rejected:
      "Forecloses dialogue before we know what we're dealing with. On the Citi balance (likely within SoL) it can push the collector to sue before we have leverage; on Chase it's defensible but still loses us the validation paper trail.",
    cost_of_error:
      "Medium — potential accelerated lawsuit on the live Citi balance.",
    sources: [],
    created_at: iso(NOW - 26 * HOUR),
  },
  {
    id: "stress-cr-8",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Recommend settling the Chase balance for some nominal amount to \"close the book\"",
    why_compelling:
      "Emotionally clean — no outstanding debt hanging over your friend. Zero collector calls afterward.",
    why_rejected:
      "We don't settle debts the consumer does not owe. Personal liability for the estate's unsecured debts does not attach to the children; paying to make it stop would be a gift to a debt-buyer. Also: the settlement would appear on the consumer's records and could be misinterpreted later.",
    cost_of_error:
      "Moderate — financial (the payment) plus reputational (implies liability where none exists).",
    sources: [],
    created_at: iso(NOW - 25 * HOUR),
  },
  {
    id: "stress-cr-9",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Consult a bankruptcy attorney for a paid one-hour consultation",
    why_compelling:
      "A local CA consumer-bankruptcy attorney would have seen this exact fact pattern dozens of times.",
    why_rejected:
      "Bankruptcy is not the right lens — there's no obligor and no estate. A CA consumer-rights attorney (not bankruptcy) is the right call if one is needed, and most offer free initial consultations on FDCPA matters because they're fee-shifting under the statute.",
    cost_of_error: "Low — $200–400 for a consultation we don't need.",
    sources: [],
    created_at: iso(NOW - 22 * HOUR),
  },
  {
    id: "stress-cr-10",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Request a credit report for the deceased mother to see what's actually reported",
    why_compelling:
      "Would reveal all accounts the mother actually had, which balances are being reported to whom, and whether anything has been charged off.",
    why_rejected:
      "Defer, not reject. Useful but not urgent — the two active collectors are the immediate issue. We can pull this in a follow-up session once validation letters are out.",
    cost_of_error:
      "Minimal — just sequencing.",
    sources: [],
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress-cr-11",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: SUB_CFPB_ID,
    path: "Request a copy of MRS BPO's 2023 CFPB consent order and cite it directly in the validation letter",
    why_compelling:
      "Specific citation to a live consent order increases the collector's compliance incentive.",
    why_rejected:
      "Overkill at the validation stage. The standard validation-request template already invokes § 1692g(b), which subsumes the itemization obligation in the consent order. We hold the consent-order citation for a CFPB complaint if validation is ignored.",
    cost_of_error:
      "None — purely a sequencing call.",
    sources: [],
    created_at: iso(NOW - 12 * HOUR),
  },
  {
    id: "stress-cr-12",
    dossier_id: STRESS_DOSSIER_ID,
    sub_investigation_id: null,
    path: "Record all future collector calls under CA's two-party consent rule with disclosure",
    why_compelling:
      "CA's two-party rule (Penal Code § 632) requires disclosure, but a disclosed recording creates hard evidence for an FDCPA claim.",
    why_rejected:
      "The call script already directs your friend to refuse to discuss the debt by phone. If she's not engaging substantively, a recording is unnecessary — the written log of call attempts is sufficient evidence of harassment patterns.",
    cost_of_error: "Low.",
    sources: [],
    created_at: iso(NOW - 6 * HOUR),
  },
];

// ===========================================================================
// Next actions (6)
// ===========================================================================

const NEXT_ACTIONS: NextAction[] = [
  {
    id: "stress-na-1",
    dossier_id: STRESS_DOSSIER_ID,
    action: "Your friend: confirm joint-account vs. authorized-user status on both Chase and Citi cards",
    rationale:
      "Everything downstream turns on this. An authorized user has no personal liability; a joint account holder does.",
    priority: 1,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 8 * HOUR),
  },
  {
    id: "stress-na-2",
    dossier_id: STRESS_DOSSIER_ID,
    action: "Send the Midland/Chase validation-request letter by certified mail",
    rationale:
      "Starts the FDCPA 30-day clock. Gets a paper record in place.",
    priority: 2,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 18 * HOUR),
  },
  {
    id: "stress-na-3",
    dossier_id: STRESS_DOSSIER_ID,
    action: "Finalize the MRS BPO / Citi validation letter (same template, different creditor block)",
    rationale:
      "Parallel tracks. Sending both in the same week is cleaner for follow-up.",
    priority: 3,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 16 * HOUR),
  },
  {
    id: "stress-na-4",
    dossier_id: STRESS_DOSSIER_ID,
    action: "Pull original monthly statements to confirm date of last payment on each account",
    rationale:
      "SoL math depends on this. Our current Q2 2021 / Q1 2022 estimates are based on your friend's memory and need to be firmed up.",
    priority: 4,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "stress-na-5",
    dossier_id: STRESS_DOSSIER_ID,
    action: "Tape the pre-call checklist next to the phone",
    rationale:
      "The script works only if it's within reach when the call happens.",
    priority: 5,
    completed: true,
    completed_at: iso(NOW - 2 * HOUR),
    created_at: iso(NOW - 4 * HOUR),
  },
  {
    id: "stress-na-6",
    dossier_id: STRESS_DOSSIER_ID,
    action: "File CFPB complaint if no validation response within 30 days of certified-mail receipt",
    rationale:
      "Escalation lever for the 31st day. Median CFPB response time on these collectors is 14 days.",
    priority: 6,
    completed: false,
    completed_at: null,
    created_at: iso(NOW - 3 * HOUR),
  },
];

// ===========================================================================
// Investigation log — 200 entries
// ===========================================================================

function buildInvestigationLog(): InvestigationLogEntry[] {
  const out: InvestigationLogEntry[] = [];
  const entryTypes: InvestigationLogEntryType[] = [
    "source_consulted",
    "sub_investigation_spawned",
    "sub_investigation_returned",
    "section_upserted",
    "section_revised",
    "artifact_added",
    "artifact_revised",
    "path_rejected",
    "decision_flagged",
    "input_requested",
    "plan_revised",
    "stuck_declared",
  ];

  const sourceCitations = [
    {
      citation: "15 U.S.C. § 1692g — Validation of debts",
      url: "https://www.law.cornell.edu/uscode/text/15/1692g",
      why: "FDCPA baseline",
    },
    {
      citation: "12 CFR § 1006.34 — Regulation F validation notice",
      url: "https://www.consumerfinance.gov/rules-policy/regulations/1006/34/",
      why: "CFPB implementation rule",
    },
    {
      citation: "CCP § 337 — CA 4-year SoL on written contracts",
      url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CCP&sectionNum=337",
      why: "CA SoL primary source",
    },
    {
      citation: "A.R.S. § 12-543 — AZ 3-year SoL on open accounts",
      url: "https://www.azleg.gov/ars/12/00543.htm",
      why: "AZ SoL primary source",
    },
    {
      citation: "NCLC time-barred debts reference, 2024",
      url: "https://library.nclc.org/collection-actions/02.01/time-barred-debts-state-table-2024.html",
      why: "State-by-state SoL cross-check",
    },
    {
      citation: "CA Civ. Code § 1788.18 — Rosenthal validation timing",
      url: "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=CIV",
      why: "CA-specific collector duties",
    },
    {
      citation: "CFPB consent order: MRS BPO (2023)",
      url: "https://files.consumerfinance.gov/f/documents/cfpb_mrs-bpo_consent-order_2023.pdf",
      why: "Collector-specific leverage",
    },
    {
      citation: "Martinez v. Portfolio Recovery (Cal. App. 2019)",
      url: "https://caselaw.findlaw.com/court/ca-court-of-appeal/martinez-v-portfolio.html",
      why: "Verbal-acknowledgment restart rule",
    },
    {
      citation:
        "Nolo — Are adult children responsible for a parent's debts? (CA)",
      url: "https://www.nolo.com/legal-encyclopedia/are-adult-children-responsible-parent-s-debts.html",
      why: "Plain-language cross-check",
    },
    {
      citation: "Bureau of Consumer Protection — scams around obituary scraping",
      url: "https://www.consumer.ftc.gov/articles/debt-after-death",
      why: "Context for call-volume spike",
    },
  ];

  const summaries = {
    source_consulted: (i: number) => {
      const s = sourceCitations[i % sourceCitations.length];
      return `Read ${s.citation.split("—")[0].trim()} — ${s.why}`;
    },
    sub_investigation_spawned: [
      "Spawned sub: California SoL deep dive",
      "Spawned sub: estate and community-property liability",
      "Spawned sub: California Rosenthal Act specifics",
      "Spawned sub: Arizona collector-licensing + SoL",
      "Spawned sub: opening-offer benchmarks",
      "Spawned sub: CFPB enforcement history on both collectors",
    ],
    sub_investigation_returned: [
      "Sub returned: CA SoL — CCP § 337 confirmed",
      "Sub returned: estate liability — no children's exposure in CA",
      "Sub returned: CFPB enforcement — MRS BPO has live consent order",
      "Sub abandoned: AZ forum-shopping unlikely given brother's cease-contact",
    ],
    section_upserted: [
      "Added summary section",
      "Added SoL finding section",
      "Added FDCPA validation section",
      "Added estate-liability section",
      "Added tactical-comparison recommendation",
      "Added CA-specific evidence section",
      "Added debt-consolidation ruled-out section",
      "Added open-question section on joint vs. authorized",
    ],
    section_revised: [
      "Revised summary — \"three gates\" framing",
      "Revised SoL section — added AZ comparison and acknowledgment-restart warning",
      "Revised FDCPA section — added Reg F itemization-date requirement",
      "Revised estate section — upgraded provisional → confident",
      "Revised tactical comparison — converted to markdown table",
      "Revised CA-specific section — added verbatim letter-header code block",
    ],
    artifact_added: [
      "Drafted validation-request letter to Midland",
      "Drafted short phone-call script",
      "Drafted tactical-options comparison table",
      "Drafted pre-call checklist",
    ],
    artifact_revised: [
      "Revised validation letter — tightened cc: line",
      "Revised phone script — removed apologetic language",
      "Revised comparison table — added \"first pick?\" column",
    ],
    path_rejected: [
      "Rejected: debt-settlement firm (user excluded + fee erosion)",
      "Rejected: bankruptcy on the estate (no obligor)",
      "Rejected: open at 20% immediately (acknowledgment risk)",
      "Rejected: ignore until sued (default-judgment risk)",
      "Rejected: preemptive CFPB complaint (dilutes paper trail)",
      "Rejected: contact brother's employer preemptively (volunteering info)",
      "Rejected: cease-and-desist as first move (forecloses dialogue)",
      "Rejected: nominal settlement to \"close the book\" (no liability to settle)",
      "Rejected: bankruptcy attorney consult (wrong specialty)",
      "Deferred: pull decedent's credit report (useful, not urgent)",
      "Rejected: cite 2023 consent order directly in validation letter (overkill)",
      "Rejected: record all future calls with disclosure (unnecessary given script)",
    ],
    decision_flagged: [
      "Flagged decision point: validation vs. cease-and-desist as first move",
      "Flagged decision point: parallel send on both accounts, or sequential",
    ],
    input_requested: [
      "Requested input: was your friend a joint holder or authorized user?",
      "Requested input: confirm dates of last payment on both accounts",
    ],
    plan_revised: [
      "Revised plan: reordered items 3 and 4",
      "Revised plan: added item 5 (opening-offer range) gated on items 1-4",
    ],
    stuck_declared: ["Blocked on joint-vs-authorized-user question"],
  };

  for (let i = 0; i < 200; i++) {
    // Weight the mix toward source_consulted and section_upserted so
    // counts look realistic; keep at least a couple of each other type.
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
      // rotate through the rest
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
      } else if (entry_type === "section_upserted" || entry_type === "section_revised") {
        const sectionIds = [
          SEC_SUMMARY,
          SEC_SOL,
          SEC_VALIDATION,
          SEC_ESTATE_NO,
          SEC_TACTICS,
          SEC_CA_SPECIFIC,
          SEC_RULED_CONSOLIDATION,
          SEC_OPEN,
        ];
        payload = { section_id: sectionIds[i % sectionIds.length] };
      } else if (entry_type === "artifact_added" || entry_type === "artifact_revised") {
        const ids = [ART_LETTER, ART_SCRIPT, ART_COMPARISON, ART_CHECKLIST];
        payload = { artifact_id: ids[i % ids.length] };
      }
    }

    // Spread entries over the last 48 hours, newest-first at i=0.
    const createdAt = iso(NOW - i * 14 * MIN);

    // Attach sub_investigation_id for a random subset (~15%)
    const subIds = [
      SUB_SOL_ID,
      SUB_ESTATE_ID,
      SUB_CA_ID,
      SUB_AZ_ID,
      SUB_NEGOTIATION_ID,
      SUB_CFPB_ID,
    ];
    const subId = i % 7 === 3 ? subIds[i % subIds.length] : null;

    out.push({
      id: `stress-log-${String(i).padStart(3, "0")}`,
      dossier_id: STRESS_DOSSIER_ID,
      work_session_id:
        i < 70
          ? "stress-ws-3"
          : i < 140
            ? "stress-ws-2"
            : "stress-ws-1",
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

// Derive counts for /investigation-log/counts.
function deriveCounts(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const e of INVESTIGATION_LOG) {
    counts[e.entry_type] = (counts[e.entry_type] ?? 0) + 1;
  }
  return counts;
}

export const STRESS_INVESTIGATION_LOG_COUNTS: Record<string, number> =
  deriveCounts();

// ===========================================================================
// Work sessions (3)
// ===========================================================================

const WORK_SESSIONS: WorkSession[] = [
  {
    id: "stress-ws-1",
    dossier_id: STRESS_DOSSIER_ID,
    started_at: iso(NOW - 46 * HOUR),
    ended_at: iso(NOW - 40 * HOUR),
    trigger: "intake",
    token_budget_used: 22400,
  },
  {
    id: "stress-ws-2",
    dossier_id: STRESS_DOSSIER_ID,
    started_at: iso(NOW - 26 * HOUR),
    ended_at: iso(NOW - 18 * HOUR),
    trigger: "resume",
    token_budget_used: 31200,
  },
  {
    id: "stress-ws-3",
    dossier_id: STRESS_DOSSIER_ID,
    started_at: iso(NOW - 10 * HOUR),
    ended_at: null,
    trigger: "user_open",
    token_budget_used: 14800,
  },
];

// ===========================================================================
// Pre-visit change log (30 entries — drives the plan-diff sidebar)
// ===========================================================================

export const STRESS_CHANGE_LOG: ChangeLogEntry[] = [
  {
    id: "stress-ch-1",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: SEC_SUMMARY,
    kind: "section_updated",
    change_note: "Rewrote summary around \"three gates\" framing",
    created_at: iso(NOW - 45 * MIN),
  },
  {
    id: "stress-ch-2",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: null,
    kind: "debrief_updated",
    change_note: "Updated all four debrief fields — session closeout",
    created_at: iso(NOW - 30 * MIN),
  },
  {
    id: "stress-ch-3",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: SEC_TACTICS,
    kind: "section_updated",
    change_note: "Converted tactical comparison from prose into a 4-column table",
    created_at: iso(NOW - 90 * MIN),
  },
  {
    id: "stress-ch-4",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: SEC_VALIDATION,
    kind: "section_updated",
    change_note: "Added Reg F itemization-date detail",
    created_at: iso(NOW - 3 * HOUR),
  },
  {
    id: "stress-ch-5",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: SEC_ESTATE_NO,
    kind: "state_changed",
    change_note: "provisional → confident",
    created_at: iso(NOW - 5 * HOUR),
  },
  {
    id: "stress-ch-6",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: null,
    kind: "sub_investigation_completed",
    change_note: "CFPB enforcement sub returned with MRS BPO consent-order finding",
    created_at: iso(NOW - 6 * HOUR),
  },
  {
    id: "stress-ch-7",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: SEC_CA_SPECIFIC,
    kind: "section_updated",
    change_note: "Added verbatim letter-header code block for the validation request",
    created_at: iso(NOW - 7 * HOUR),
  },
  {
    id: "stress-ch-8",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: SEC_OPEN,
    kind: "needs_input_added",
    change_note: "Opened: joint-holder vs. authorized-user on each card",
    created_at: iso(NOW - 8 * HOUR),
  },
  {
    id: "stress-ch-9",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: null,
    kind: "considered_and_rejected_added",
    change_note: "Rejected: cite 2023 consent order directly in validation letter",
    created_at: iso(NOW - 9 * HOUR),
  },
  {
    id: "stress-ch-10",
    dossier_id: STRESS_DOSSIER_ID,
    work_session_id: "stress-ws-3",
    section_id: null,
    kind: "next_action_added",
    change_note: "File CFPB complaint if no response within 30 days",
    created_at: iso(NOW - 3 * HOUR),
  },
];

// ===========================================================================
// Export the full DossierFull
// ===========================================================================

export const stressCaseFile: DossierFull = {
  dossier: DOSSIER,
  sections: SECTIONS,
  needs_input: [
    {
      id: "stress-ni-1",
      dossier_id: STRESS_DOSSIER_ID,
      question:
        "Were you ever on either the Chase or Citi card as a joint account holder — i.e. did you sign the original cardholder agreement yourself — or were you strictly an authorized user who could use the card but wasn't on the contract? Check the original application paperwork if you still have it; a phone call to each card's customer service line will also confirm.",
      blocks_section_ids: [SEC_ESTATE_NO, SEC_OPEN],
      created_at: iso(NOW - 8 * HOUR),
      answered_at: null,
      answer: null,
    },
  ],
  decision_points: [
    {
      id: "stress-dp-1",
      dossier_id: STRESS_DOSSIER_ID,
      title:
        "Parallel validation requests on both accounts, or sequential — Midland first, wait for response, then MRS BPO?",
      options: [
        {
          label: "Send both validation letters the same week (parallel)",
          implications:
            "Both 30-day windows run simultaneously. Cleaner follow-up calendar. Slightly higher cost ($16 certified mail vs $8). If both collectors ignore, single CFPB complaint can reference both.",
          recommended: true,
        },
        {
          label: "Send Midland first, wait 30 days, then MRS BPO",
          implications:
            "Simpler to track one window at a time. Lower initial cost. But doubles the calendar time before either is resolved and gives MRS BPO another month of unchallenged call volume.",
          recommended: false,
        },
      ],
      recommendation:
        "Parallel. The $8 is negligible and the calendar savings matter — every month of collector calls is a cost your friend bears.",
      blocks_section_ids: [],
      created_at: iso(NOW - 4 * HOUR),
      resolved_at: null,
      chosen: null,
      kind: "generic",
    },
  ],
  reasoning_trail: [],
  ruled_out: [],
  work_sessions: WORK_SESSIONS,
  artifacts: ARTIFACTS,
  sub_investigations: SUB_INVESTIGATIONS,
  investigation_log: INVESTIGATION_LOG,
  considered_and_rejected: CONSIDERED_AND_REJECTED,
  next_actions: NEXT_ACTIONS,
};
