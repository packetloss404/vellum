import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


BACKEND_DIR = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.getenv("VELLUM_DB_PATH", BACKEND_DIR / "vellum.db")).resolve()

MODEL = os.getenv("VELLUM_MODEL", "claude-opus-4-7")
MODEL_ALT = os.getenv("VELLUM_MODEL_ALT", "claude-sonnet-4-6")

SECTION_TOKEN_BUDGET = int(os.getenv("VELLUM_SECTION_TOKEN_BUDGET", "30000"))
LOOP_DETECTION_THRESHOLD = int(os.getenv("VELLUM_LOOP_DETECTION_THRESHOLD", "3"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
