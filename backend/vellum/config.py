import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


BACKEND_DIR = Path(__file__).resolve().parent.parent


def _resolve_db_path() -> Path:
    """Resolve VELLUM_DB_PATH. Relative paths anchor to BACKEND_DIR — not CWD —
    so scripts run from the repo root (e.g. ``scripts/day2_smoke.py``) use the
    same DB as ``uvicorn`` started from ``backend/``. Absolute paths pass
    through untouched."""
    raw = os.getenv("VELLUM_DB_PATH")
    if not raw:
        return (BACKEND_DIR / "vellum.db").resolve()
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (BACKEND_DIR / p).resolve()


DB_PATH = _resolve_db_path()

MODEL = os.getenv("VELLUM_MODEL", "claude-opus-4-7")
MODEL_ALT = os.getenv("VELLUM_MODEL_ALT", "claude-sonnet-4-6")

# Per-workload model routing.
# INTAKE_MODEL: intake is a constrained conversational flow, not deep
#   investigation — Sonnet 4.6 delivers the same quality at ~40% of Opus cost.
# SUMMARY_MODEL: reserved for the Phase-3 `summarize_session` tool. Structured
#   synthesis on known data; Haiku 4.5 is enough. Reads applied at the call
#   site when that tool lands.
INTAKE_MODEL = os.getenv("VELLUM_INTAKE_MODEL", "claude-sonnet-4-6")
SUMMARY_MODEL = os.getenv("VELLUM_SUMMARY_MODEL", "claude-haiku-4-5")

SECTION_TOKEN_BUDGET = int(os.getenv("VELLUM_SECTION_TOKEN_BUDGET", "30000"))
LOOP_DETECTION_THRESHOLD = int(os.getenv("VELLUM_LOOP_DETECTION_THRESHOLD", "3"))

# Stuck-detection calibration knobs (day-5). Defaults chosen after walking
# through a realistic 40-turn demo run: a session budget of 15x the section
# budget covers cached-prompt sessions with several sub-investigations, and
# a revision-stall threshold of 5 lets a finding section legitimately revise
# 4-5 times as evidence accumulates before we call it stuck.
STUCK_SESSION_BUDGET_MULT = int(os.getenv("VELLUM_STUCK_SESSION_BUDGET_MULT", "15"))
STUCK_REVISION_STALL_THRESHOLD = int(
    os.getenv("VELLUM_STUCK_REVISION_STALL_THRESHOLD", "5")
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Bind host for the uvicorn server. Used at startup to warn when the API is
# exposed on a non-loopback interface without an authentication token.
HOST = os.getenv("VELLUM_HOST", os.getenv("HOST", "127.0.0.1"))

# Optional local API guard. Empty token keeps localhost development unchanged
# unless VELLUM_API_AUTH_REQUIRED is explicitly enabled.
API_TOKEN = os.getenv("VELLUM_API_TOKEN", "")
API_AUTH_REQUIRED = os.getenv("VELLUM_API_AUTH_REQUIRED", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Hard run limits. Budget signals are still soft, but these caps prevent a
# direct API/scheduler path from starting unbounded agent work.
AGENT_MAX_TURNS = int(os.getenv("VELLUM_AGENT_MAX_TURNS", "200"))
SUB_AGENT_MAX_TURNS = int(os.getenv("VELLUM_SUB_AGENT_MAX_TURNS", "60"))
AGENT_MAX_CONCURRENT_RUNS = int(os.getenv("VELLUM_AGENT_MAX_CONCURRENT_RUNS", "2"))


# ---------------------------------------------------------------------------
# Sleep mode
# ---------------------------------------------------------------------------
#
# The scheduler coroutine polls the dossiers table for wake-ready rows. 30s
# is the calibration Ian landed on — slow enough to keep wake-ups cheap when
# the system is idle, fast enough that a user resolving a needs_input and
# walking across the room doesn't feel broken. Overridable via env.
SCHEDULER_POLL_SECONDS = int(os.getenv("VELLUM_SCHEDULER_POLL_SECONDS", "30"))

# Self-healing for errored/crashed sessions. A session that ends with
# end_reason=error (or is reconciled as crashed at boot) schedules its own
# retry wake with exponential backoff: BASE * 2^(count-1), capped at CAP.
# After MAX consecutive failures the dossier is quarantined — no further
# auto-wakes until the user explicitly resumes it. Successful sessions reset
# the counter.
ERROR_RETRY_BASE_SECONDS = int(os.getenv("VELLUM_ERROR_RETRY_BASE_SECONDS", "300"))
ERROR_RETRY_MAX = int(os.getenv("VELLUM_ERROR_RETRY_MAX", "5"))
ERROR_RETRY_CAP_SECONDS = int(os.getenv("VELLUM_ERROR_RETRY_CAP_SECONDS", "21600"))

# Input-token threshold for message-history compaction. When the estimated
# input token count for a turn exceeds this value, the compactor fires before
# the next API call. Default 80000 (~80% of the 100k practical input limit)
# gives a comfortable margin. Set to 0 to disable compaction entirely.
COMPACT_INPUT_TOKEN_THRESHOLD = int(
    os.getenv("VELLUM_COMPACT_INPUT_TOKEN_THRESHOLD", "80000")
)


# ---------------------------------------------------------------------------
# Budget / pricing
# ---------------------------------------------------------------------------
#
# Per-model price table in USD per 1M tokens, for the budget-tracking surface.
# Budgets in Vellum are SOFT signals (per stuck.py:8-9) — we surface a
# decision_point when a threshold crosses, we never terminate the agent
# mid-thought. Verify pricing from https://www.anthropic.com/pricing before
# trusting the dollar column in any surfaced decision point.
MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    # Verified from platform.claude.com/docs/en/about-claude/pricing 2026-04-23.
    # Opus 4.7 pricing unchanged from 4.6.
    # cache_creation_input = 1.25x base input; cache_read_input = 0.1x base input.
    "claude-opus-4-7": {
        "input": 5.0,
        "output": 25.0,
        "cache_creation_input": 5.0 * 1.25,
        "cache_read_input": 5.0 * 0.1,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_creation_input": 3.0 * 1.25,
        "cache_read_input": 3.0 * 0.1,
    },
    "claude-haiku-4-5": {
        "input": 1.0,
        "output": 5.0,
        "cache_creation_input": 1.0 * 1.25,
        "cache_read_input": 1.0 * 0.1,
    },
}


def cost_usd_for_turn(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    """Translate a turn's usage into a dollar figure using MODEL_PRICING.

    Unknown models fall back to zero cost — caller logs/reports, doesn't
    crash. That keeps a model-name-typo from taking down the runtime loop.
    """
    import logging
    rates = MODEL_PRICING_USD_PER_MTOK.get(model)
    if rates is None:
        logging.getLogger("vellum.config").warning(
            "cost_usd_for_turn: unknown model %r — returning 0.0", model
        )
        return 0.0
    return (
        (input_tokens / 1_000_000) * rates["input"]
        + (output_tokens / 1_000_000) * rates["output"]
        + (cache_creation_input_tokens / 1_000_000) * rates["cache_creation_input"]
        + (cache_read_input_tokens / 1_000_000) * rates["cache_read_input"]
    )


# Default values for the DB-backed `settings` table. Seeded once at boot via
# storage.seed_default_settings; a user-edited value in the DB takes
# precedence (seeder skips any key that already exists). Scoped to the NEW
# budget/guard/sleep-mode knobs only — env-driven stuck thresholds above
# stay put.
DEFAULT_SETTINGS: dict[str, object] = {
    # Daily global cost soft-signal threshold (USD). When today's spend
    # crosses this, surface a decision_point. 0 disables the signal.
    "budget_daily_soft_cap_usd": 10.0,
    # Warn earlier (at this fraction of the cap) with an advisory signal.
    "budget_daily_warn_fraction": 0.8,
    # Per-session soft-signal (USD). Catches a single run blowing past a
    # reasonable envelope even if the daily rollup is fine. 0 disables.
    "budget_per_session_soft_cap_usd": 3.0,
    # Sleep mode master switch. When False, schedule_wake becomes a no-op
    # and the scheduler coroutine skips its tick work. Off means the user
    # is driving resumes manually via the /resume endpoint.
    "sleep_mode_enabled": True,
    # Maximum hours the agent can schedule itself forward in a single
    # schedule_wake call. Guardrail against "wake me in 90 days" drift.
    "schedule_wake_max_hours": 72.0,
    # Progress-forcing: surface a no_progress stuck signal when the agent
    # has gone this many turns without calling any "progress" tool (list
    # is in stuck._PROGRESS_TOOL_NAMES). 0 disables the check entirely.
    "progress_forcing_turns": 5,
    # Trust mode: when True, tier-2 stuck decision_points are auto-dismissed
    # (the agent takes the recommended/first option and continues with a
    # reasoning_trail note instead of surfacing a DP). Tier 3+ still
    # surfaces. Plan approval gates are NEVER skipped by trust mode.
    "trust_mode_enabled": False,
}
