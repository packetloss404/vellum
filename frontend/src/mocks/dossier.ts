// Hero-demo fixture for /demo. Hand-written as if the dossier agent had
// produced it after a first work session on a real scenario: a friend's
// mother, Marjorie, passed with old credit-card debts, and collectors
// are now calling the friend. The friend asked what percentage to open
// negotiations at; the agent pushed back — don't negotiate yet, first
// confirm the debt is owed.
//
// The content is plausibly real and legal-adjacent but NOT legal advice.
// All timestamps are computed relative to "now" so the fixture stays
// evergreen; spacing is in the last ~20 hours.

import type { ChangeLogEntry, DossierFull } from "../api/types";

const NOW = Date.now();
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

const iso = (ms: number) => new Date(ms).toISOString();

const DOSSIER_ID = "demo-dossier-cc-debt";
const WORK_SESSION_ID = "demo-work-session-1";

const SECTION_SOL_ID = "demo-section-sol";
const SECTION_FDCPA_ID = "demo-section-fdcpa";
const SECTION_ESTATE_ID = "demo-section-estate";

export const MOCK_DOSSIER_FULL: DossierFull = {
  dossier: {
    id: DOSSIER_ID,
    title: "Credit card debt — Marjorie",
    problem_statement:
      "What percentage should I open negotiations at? Marjorie (a friend's mother) passed last fall with old credit-card balances across two cards. Collectors have been calling the friend for the past few weeks and she's ready to settle. Before picking an opening number, we need to confirm the debt is actually owed — the statute of limitations may have run, and the collector has not sent written validation under the FDCPA.",
    out_of_scope: [
      "tax treatment of forgiven balances",
      "funeral and burial costs",
      "estate planning for the friend's own affairs",
    ],
    dossier_type: "decision_memo",
    status: "active",
    check_in_policy: {
      cadence: "on_demand",
      notes:
        "Pause between user turns; resume when the user answers the open question about validation.",
    },
    last_visited_at: iso(NOW - 20 * HOUR),
    created_at: iso(NOW - 2 * DAY),
    updated_at: iso(NOW - 1 * HOUR),
  },

  sections: [
    {
      id: SECTION_SOL_ID,
      dossier_id: DOSSIER_ID,
      type: "finding",
      title: "Statute of limitations",
      content:
        "Credit-card debt is typically governed by each state's statute of limitations on written or open-account contracts — three to six years in most states, measured from the date of last payment or last activity on the account. Once the SoL has run, the collector can still ask for payment, but they cannot successfully sue to collect; a time-barred debt is often called \"zombie debt\" for this reason. The trap: in many states a partial payment or written acknowledgment can restart the clock, and in some states even a verbal admission will do it. Before your friend says anything that could be read as acknowledgment — including \"I'll pay what I can\" on a recorded call — we need the date of Marjorie's last payment on each account and her state of residence.",
      state: "confident",
      order: 1,
      change_note:
        "Flagged SoL as a blocker on negotiations — acknowledgment risk is the reason to pause.",
      sources: [],
      depends_on: [],
      last_updated: iso(NOW - 3 * HOUR),
      created_at: iso(NOW - 18 * HOUR),
    },
    {
      id: SECTION_FDCPA_ID,
      dossier_id: DOSSIER_ID,
      type: "finding",
      title: "FDCPA validation",
      content:
        "Under the Fair Debt Collection Practices Act (15 U.S.C. § 1692g), a debt collector must — within five days of its initial communication with the consumer — send a written notice stating the amount of the debt, the name of the creditor to whom it is owed, and the consumer's right to dispute. If the consumer disputes the debt in writing within thirty days of receiving that notice, the collector must cease collection activity until they mail written validation — typically documentation from the original creditor showing the account, balance, and chain of assignment. Pressing for payment after a written dispute, without validation in hand, exposes the collector to statutory damages. Your friend has received phone calls but — per her recollection — no written notice identifying the original creditor and account. That is the first thing to confirm.",
      state: "confident",
      order: 2,
      change_note:
        "Added section on FDCPA validation window — this is the lever for pausing collector contact while we figure out the rest.",
      sources: [
        {
          kind: "web",
          url: "https://www.consumerfinance.gov/rules-policy/regulations/1006/34/",
          title: "12 CFR § 1006.34 — Notice for validation of debts (Regulation F)",
          snippet:
            "A debt collector must provide a validation notice containing the debt's itemization, the creditor's name, and the consumer's dispute rights.",
        },
      ],
      depends_on: [],
      last_updated: iso(NOW - 1 * HOUR),
      created_at: iso(NOW - 14 * HOUR),
    },
    {
      id: SECTION_ESTATE_ID,
      dossier_id: DOSSIER_ID,
      type: "finding",
      title: "Estate vs. personal liability",
      content:
        "If the cards were in Marjorie's name alone and there was no joint account, the obligation generally belongs to her estate and not to her surviving family. Unsecured creditors file claims against the estate, and if the estate has no assets, the debt is effectively uncollectible — surviving children do not inherit it. The exceptions: (a) a co-signer or true joint account holder (not merely an authorized user), (b) community-property states, where a surviving spouse may have exposure for debts incurred during the marriage, and (c) a small number of states with \"filial responsibility\" statutes, which historically target medical and long-term-care debt rather than consumer credit but are worth checking. Collectors are allowed to contact the estate's representative to file a claim; they are not allowed to imply a relative is personally liable when they are not.",
      state: "provisional",
      order: 3,
      change_note:
        "Provisional pending confirmation that your friend was not a joint account holder and that Marjorie's state is not community-property.",
      sources: [],
      depends_on: [],
      last_updated: iso(NOW - 4 * HOUR),
      created_at: iso(NOW - 12 * HOUR),
    },
  ],

  needs_input: [
    {
      id: "demo-needs-input-1",
      dossier_id: DOSSIER_ID,
      question:
        "Has the collector ever sent written validation of the debt under 15 U.S.C. § 1692g? If your friend hasn't received a letter naming the original creditor, the account number, and the amount, the thirty-day dispute window hasn't started — and there's nothing yet to negotiate against.",
      blocks_section_ids: [SECTION_FDCPA_ID, SECTION_SOL_ID],
      created_at: iso(NOW - 5 * HOUR),
      answered_at: null,
      answer: null,
    },
  ],

  decision_points: [
    {
      id: "demo-decision-1",
      dossier_id: DOSSIER_ID,
      title:
        "How to respond to the most recent collector letter",
      options: [
        {
          label: "Send a formal FDCPA validation request",
          implications:
            "Written, certified mail, within thirty days of first contact. Collector must cease collection activity until they produce documentation from the original creditor. Costs nothing, buys time, and forces the collector to prove the debt is real and assigned to them before any number is on the table.",
          recommended: true,
        },
        {
          label: "Send a cease-and-desist letter",
          implications:
            "Stops collector contact immediately, but also forecloses dialogue. The collector's remaining options are to drop the matter or sue. If the SoL has already run, this is attractive; if it hasn't, it can accelerate litigation on their timeline.",
          recommended: false,
        },
        {
          label: "Ignore the letter until they escalate",
          implications:
            "Preserves silence (no acknowledgment risk), but forfeits the validation-window leverage and leaves your friend without a paper trail if this ends up in court. Also doesn't stop the calls.",
          recommended: false,
        },
      ],
      recommendation:
        "Start with the validation request. It's the lowest-cost, highest-information move: the collector either produces documentation (and we negotiate from a known footing) or they don't (and collection must stop). Hold cease-and-desist in reserve for after we know the SoL status.",
      blocks_section_ids: [],
      created_at: iso(NOW - 7 * HOUR),
      resolved_at: null,
      chosen: null,
    },
  ],

  reasoning_trail: [
    {
      id: "demo-reasoning-1",
      dossier_id: DOSSIER_ID,
      work_session_id: WORK_SESSION_ID,
      note: "Refused to answer the percentage question on first pass. The user asked what to open at; the prior question — is this debt owed, validated, and within the statute — dominates the answer. An opening offer on a time-barred or unvalidated debt is a gift to the collector and can restart the SoL clock. Put the percentage work behind that gate.",
      tags: ["strategy_shift", "premise_pushback"],
      created_at: iso(NOW - 19 * HOUR),
    },
    {
      id: "demo-reasoning-2",
      dossier_id: DOSSIER_ID,
      work_session_id: WORK_SESSION_ID,
      note: "Chose FDCPA validation as the active move over cease-and-desist. Validation is information-positive: it either produces the paper trail we need or it shuts the collector down procedurally. Cease-and-desist is louder and can push the collector toward litigation before we know whether the SoL has run.",
      tags: ["calibration"],
      created_at: iso(NOW - 7 * HOUR),
    },
    {
      id: "demo-reasoning-3",
      dossier_id: DOSSIER_ID,
      work_session_id: WORK_SESSION_ID,
      note: "Held the estate-vs-personal-liability section at provisional rather than confident. Most signs point to Marjorie's estate being the only obligor, but we haven't confirmed the account structure (joint vs. authorized user) or ruled out a community-property wrinkle. Don't let the user over-rely on this section until those are answered.",
      tags: ["calibration"],
      created_at: iso(NOW - 4 * HOUR),
    },
  ],

  ruled_out: [
    {
      id: "demo-ruled-out-1",
      dossier_id: DOSSIER_ID,
      subject: "Debt consolidation loan",
      reason:
        "Marjorie is no longer alive to take one out, and your friend isn't the obligor. Not applicable.",
      sources: [],
      created_at: iso(NOW - 16 * HOUR),
    },
    {
      id: "demo-ruled-out-2",
      dossier_id: DOSSIER_ID,
      subject: "Filing bankruptcy on the estate",
      reason:
        "There is no estate of any size to file for — no probate assets, no real property. Bankruptcy has nothing to discharge and no one to discharge it for.",
      sources: [],
      created_at: iso(NOW - 15 * HOUR),
    },
    {
      id: "demo-ruled-out-3",
      dossier_id: DOSSIER_ID,
      subject: "Hiring a debt settlement company",
      reason:
        "User explicitly excluded — wants to handle this directly. Fees (typically 15–25% of enrolled debt) would also erode any settlement savings on a balance this size.",
      sources: [],
      created_at: iso(NOW - 13 * HOUR),
    },
  ],

  work_sessions: [
    {
      id: WORK_SESSION_ID,
      dossier_id: DOSSIER_ID,
      started_at: iso(NOW - 20 * HOUR),
      ended_at: iso(NOW - 1 * HOUR),
      trigger: "user_open",
      token_budget_used: 18500,
    },
  ],
};

export const MOCK_CHANGE_LOG: ChangeLogEntry[] = [
  {
    id: "demo-change-1",
    dossier_id: DOSSIER_ID,
    work_session_id: WORK_SESSION_ID,
    section_id: SECTION_FDCPA_ID,
    kind: "section_created",
    change_note: "Added section on FDCPA validation window",
    created_at: iso(NOW - 14 * HOUR),
  },
  {
    id: "demo-change-2",
    dossier_id: DOSSIER_ID,
    work_session_id: WORK_SESSION_ID,
    section_id: SECTION_SOL_ID,
    kind: "state_changed",
    change_note:
      "Flagged statute of limitations as blocker on negotiations",
    created_at: iso(NOW - 11 * HOUR),
  },
  {
    id: "demo-change-3",
    dossier_id: DOSSIER_ID,
    work_session_id: WORK_SESSION_ID,
    section_id: null,
    kind: "ruled_out_added",
    change_note:
      "Ruled out bankruptcy (no estate to file) and consolidation loan",
    created_at: iso(NOW - 15 * HOUR),
  },
  {
    id: "demo-change-4",
    dossier_id: DOSSIER_ID,
    work_session_id: WORK_SESSION_ID,
    section_id: null,
    kind: "needs_input_added",
    change_note:
      "Opened question on debt validation status under FDCPA",
    created_at: iso(NOW - 5 * HOUR),
  },
];
