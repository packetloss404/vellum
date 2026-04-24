"""verify_phase4_run.py — audit a live demo run.

Run AFTER a dossier has had at least one full agent session. Takes a
dossier id, hits the local backend, and prints a pass/fail report on
the Phase 4 acceptance criteria from the step-by-step demo guide.

Usage:
    cd vellum
    .venv/Scripts/python.exe scripts/verify_phase4_run.py dos_abc123

Exits 0 if everything passed, 1 otherwise. The report is the point —
the exit code is mostly for CI-style chaining.

Doesn't touch the DB. Just reads what the backend serves at
GET /api/dossiers/{id} and derives each check from the JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional


DEFAULT_BASE = "http://127.0.0.1:8731"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    dossier_id: str
    title: str
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))

    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)


def fetch_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_premise_challenge(dossier: dict) -> CheckResult:
    pc = dossier.get("premise_challenge")
    if not pc:
        return CheckResult(
            "premise challenge populated",
            False,
            "dossier.premise_challenge is null — agent never called record_premise_challenge",
        )
    required = [
        "original_question",
        "hidden_assumptions",
        "why_answering_now_is_risky",
        "safer_reframe",
        "required_evidence_before_answering",
    ]
    missing = [f for f in required if not pc.get(f)]
    if missing:
        return CheckResult(
            "premise challenge populated",
            False,
            f"missing/empty fields: {', '.join(missing)}",
        )
    assumptions = pc.get("hidden_assumptions") or []
    evidence = pc.get("required_evidence_before_answering") or []
    return CheckResult(
        "premise challenge populated",
        True,
        f"{len(assumptions)} hidden_assumptions, {len(evidence)} required_evidence items",
    )


def check_plan_approved(dossier: dict) -> CheckResult:
    plan = dossier.get("investigation_plan")
    if not plan:
        return CheckResult(
            "plan drafted and approved",
            False,
            "no investigation_plan on dossier",
        )
    approved_at = plan.get("approved_at")
    item_count = len(plan.get("items") or [])
    if not approved_at:
        return CheckResult(
            "plan drafted and approved",
            False,
            f"plan has {item_count} items but approved_at is null",
        )
    return CheckResult(
        "plan drafted and approved",
        True,
        f"{item_count} items, approved at {approved_at}",
    )


def check_sub_identity(full: dict) -> CheckResult:
    subs = full.get("sub_investigations") or []
    if not subs:
        return CheckResult(
            "sub-investigations have title + why_it_matters",
            False,
            "zero sub-investigations spawned",
        )
    missing_title = [s["id"] for s in subs if not s.get("title")]
    missing_why = [s["id"] for s in subs if not s.get("why_it_matters")]
    if missing_title or missing_why:
        bits = []
        if missing_title:
            bits.append(f"{len(missing_title)} missing title")
        if missing_why:
            bits.append(f"{len(missing_why)} missing why_it_matters")
        return CheckResult(
            "sub-investigations have title + why_it_matters",
            False,
            f"{len(subs)} total; " + "; ".join(bits),
        )
    return CheckResult(
        "sub-investigations have title + why_it_matters",
        True,
        f"{len(subs)} subs, all titled + rationaled",
    )


def check_confidence_drift(base: str, dossier_id: str, full: dict) -> CheckResult:
    subs = full.get("sub_investigations") or []
    non_unknown = [
        s for s in subs
        if s.get("confidence") and s["confidence"] != "unknown"
    ]
    try:
        change_log = fetch_json(f"{base}/api/dossiers/{dossier_id}/change-log")
    except Exception as exc:
        return CheckResult(
            "confidence drift observed",
            False,
            f"could not fetch change_log: {exc}",
        )
    drift_entries = [
        e for e in change_log
        if e.get("kind") == "state_changed"
        and "sub-investigation" in (e.get("change_note") or "")
    ]
    if drift_entries or non_unknown:
        detail = (
            f"{len(drift_entries)} state_changed drift entries; "
            f"{len(non_unknown)} subs with non-unknown confidence"
        )
        return CheckResult("confidence drift observed", True, detail)
    return CheckResult(
        "confidence drift observed",
        False,
        "no sub confidence above 'unknown' and no state_changed entries on subs",
    )


def check_working_theory(base: str, dossier_id: str, dossier: dict) -> CheckResult:
    wt = dossier.get("working_theory")
    if not wt:
        return CheckResult(
            "working theory revised at least once",
            False,
            "dossier.working_theory is null — agent never called update_working_theory",
        )
    try:
        change_log = fetch_json(f"{base}/api/dossiers/{dossier_id}/change-log")
    except Exception as exc:
        return CheckResult(
            "working theory revised at least once",
            False,
            f"could not fetch change_log: {exc}",
        )
    wt_entries = [e for e in change_log if e.get("kind") == "working_theory_updated"]
    # >=2 implies a revision happened (first-write + at least one update).
    # A single entry = set-and-forget; not a revision.
    if len(wt_entries) >= 2:
        return CheckResult(
            "working theory revised at least once",
            True,
            f"{len(wt_entries)} working_theory_updated entries (first-write + {len(wt_entries) - 1} revisions)",
        )
    return CheckResult(
        "working theory revised at least once",
        False,
        f"{len(wt_entries)} working_theory_updated entries — agent set theory once and never revised",
    )


def check_unresolved_assumptions(dossier: dict) -> CheckResult:
    wt = dossier.get("working_theory")
    if not wt:
        return CheckResult(
            "unresolved_assumptions populated",
            False,
            "no working_theory",
        )
    assumptions = wt.get("unresolved_assumptions") or []
    if assumptions:
        return CheckResult(
            "unresolved_assumptions populated",
            True,
            f"{len(assumptions)} assumptions listed",
        )
    return CheckResult(
        "unresolved_assumptions populated",
        False,
        "working_theory.unresolved_assumptions is empty — agent didn't surface any",
    )


def check_session_summary(full: dict) -> CheckResult:
    summaries = full.get("session_summaries") or []
    if not summaries:
        return CheckResult(
            "summarize_session called (not just fallback)",
            False,
            "no session summaries at all — no work sessions have ended",
        )
    real = [s for s in summaries if (s.get("summary") or "").strip()]
    fallback = len(summaries) - len(real)
    if real:
        return CheckResult(
            "summarize_session called (not just fallback)",
            True,
            f"{len(real)}/{len(summaries)} sessions have real narratives ({fallback} fallback)",
        )
    return CheckResult(
        "summarize_session called (not just fallback)",
        False,
        f"all {len(summaries)} sessions are fallback rows — agent never called summarize_session",
    )


def check_budget_and_cost(base: str, full: dict) -> tuple[CheckResult, float]:
    """Returns (check, total_cost_usd_for_this_dossier)."""
    sessions = full.get("work_sessions") or []
    total_cost = sum(float(s.get("cost_usd") or 0) for s in sessions)
    # Not strictly a pass/fail — more an information line. But a run with $0
    # spent means the agent never called the API, which is a pass/fail concern.
    if total_cost <= 0:
        return (
            CheckResult(
                "cost accounted (>$0 this dossier)",
                False,
                "total cost is $0 — agent may have never actually run",
            ),
            total_cost,
        )
    try:
        today = fetch_json(f"{base}/api/budget/today")
        state = today.get("state", "ok")
        spent = today.get("spent_usd", 0)
        cap = today.get("daily_cap_usd", 0)
    except Exception:
        state, spent, cap = "unknown", 0, 0
    return (
        CheckResult(
            "cost accounted (>$0 this dossier)",
            True,
            f"${total_cost:.2f} on this dossier (today total ${spent:.2f} of ${cap:.2f} cap, state={state})",
        ),
        total_cost,
    )


def check_activity_indicator_consistency(base: str, dossier_id: str, full: dict) -> CheckResult:
    """Weak check: verify resume-state + agent-status agree on whether a
    session is in-flight. If resume-state says an active session exists but
    agent-status says not running (and no task is visible), the UI's
    activity indicator would claim "idle" during what's actually a leaked
    session. Rare but worth flagging.
    """
    try:
        resume = fetch_json(f"{base}/api/dossiers/{dossier_id}/resume-state")
        status = fetch_json(f"{base}/api/dossiers/{dossier_id}/agent/status")
    except Exception as exc:
        return CheckResult(
            "no leaked active session",
            False,
            f"could not fetch resume-state / agent-status: {exc}",
        )
    active_ws = resume.get("active_work_session_id")
    running = status.get("running", False)
    if active_ws and not running:
        return CheckResult(
            "no leaked active session",
            False,
            f"resume-state says work_session {active_ws} is active but no agent task — leaked session",
        )
    return CheckResult(
        "no leaked active session",
        True,
        f"resume-state {'active' if active_ws else 'idle'} agrees with status running={running}",
    )


def run(base: str, dossier_id: str) -> Report:
    try:
        full = fetch_json(f"{base}/api/dossiers/{dossier_id}")
    except Exception as exc:
        print(f"FATAL: could not fetch dossier {dossier_id} from {base}: {exc}")
        sys.exit(2)
    dossier = full["dossier"]
    report = Report(dossier_id=dossier_id, title=dossier.get("title", "(no title)"))

    report.add(**check_premise_challenge(dossier).__dict__)
    report.add(**check_plan_approved(dossier).__dict__)
    report.add(**check_sub_identity(full).__dict__)
    report.add(**check_confidence_drift(base, dossier_id, full).__dict__)
    report.add(**check_working_theory(base, dossier_id, dossier).__dict__)
    report.add(**check_unresolved_assumptions(dossier).__dict__)
    report.add(**check_session_summary(full).__dict__)
    cost_check, _ = check_budget_and_cost(base, full)
    report.add(**cost_check.__dict__)
    report.add(**check_activity_indicator_consistency(base, dossier_id, full).__dict__)

    return report


def format_report(report: Report) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append(f"Phase 4 demo-run audit — {report.dossier_id}")
    lines.append(f"  {report.title}")
    lines.append("")
    width = max(len(c.name) for c in report.checks) + 2
    for c in report.checks:
        tag = "PASS" if c.passed else "FAIL"
        name = c.name.ljust(width)
        lines.append(f"  [{tag}] {name} {c.detail}")
    lines.append("")
    passed = report.passed_count()
    total = len(report.checks)
    verdict = "all checks passed" if report.all_passed() else f"{total - passed} of {total} failed"
    lines.append(f"Summary: {passed}/{total} — {verdict}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit a Phase 4 demo run on a single dossier."
    )
    parser.add_argument("dossier_id", help="e.g. dos_abc123")
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"backend base URL (default {DEFAULT_BASE})",
    )
    args = parser.parse_args()
    report = run(args.base, args.dossier_id)
    print(format_report(report))
    return 0 if report.all_passed() else 1


if __name__ == "__main__":
    sys.exit(main())
