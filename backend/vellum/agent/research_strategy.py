"""Behaviorally distinct research strategies and completion audit helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Strategy:
    name: str
    instructions: str
    requires_disconfirmation: bool
    requires_final_audit: bool


STANDARD = Strategy(
    name="standard",
    requires_disconfirmation=False,
    requires_final_audit=True,
    instructions=(
        "STANDARD RESEARCH STRATEGY: decompose the question into a compact plan; "
        "prefer primary or official sources; corroborate every material recommendation; "
        "record sources only after reading them; search for at least one plausible counterexample; "
        "then perform a final claim-to-citation audit before delivery. Stop when the decision is "
        "well supported—do not pad the bibliography to hit a count."
    ),
)

DEEP = Strategy(
    name="deep",
    requires_disconfirmation=True,
    requires_final_audit=True,
    instructions=(
        "DEEP RESEARCH STRATEGY: first decompose the request into independently answerable claims "
        "and assign evidence standards. Run separate discovery passes for primary sources, current "
        "secondary synthesis, and adverse or contradictory evidence. Triangulate each material claim "
        "across independent sources; explicitly record a disconfirmation attempt and what would falsify "
        "the working theory. Resolve source-date, jurisdiction, and definition conflicts. Before delivery, "
        "run a final claim-level audit: every material claim must link to cited or consulted evidence, "
        "primary-required claims must have qualified primary evidence, and unsupported claims must be "
        "downgraded, removed, or called out as unresolved."
    ),
)


def for_policy(policy: Any) -> Strategy:
    depth = getattr(getattr(policy, "depth", None), "value", getattr(policy, "depth", "standard"))
    return DEEP if str(depth).lower() == "deep" else STANDARD


def render(policy: Any) -> str:
    return for_policy(policy).instructions


def render_for_sub(policy: Any) -> str:
    """Render the inherited method without advertising a parent-only tool."""
    return (
        for_policy(policy).instructions
        + " In this bounded sub-investigation, self-check your claim-to-source links before "
        "complete_sub_investigation; the parent investigator owns the final dossier-wide "
        "audit_research_completion call."
    )


def completion_requirements(policy: Any) -> dict[str, bool]:
    strategy = for_policy(policy)
    return {
        "requires_disconfirmation": strategy.requires_disconfirmation,
        "requires_final_audit": strategy.requires_final_audit,
    }
