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
