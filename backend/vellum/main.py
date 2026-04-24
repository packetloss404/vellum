import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db, storage
from .agent.orchestrator import ORCHESTRATOR
from .agent.scheduler import SCHEDULER
# Import purely for side-effect: registers sub_runtime.spawn_handler into
# handlers.HANDLER_OVERRIDES["spawn_sub_investigation"] on module load. If
# we DON'T import this, the default stub in tools/handlers.py runs — it
# inserts a row in `running` state and returns without ever executing a
# real sub-agent loop. 21 sub-investigations accumulated as zombies in
# prod before this was caught (dos_cbf0 + dos_fc07, day 4).
from .agent import sub_runtime  # noqa: F401
from .api.agent_routes import router as agent_router
from .api.auth import require_api_token
from .api.intake_routes import router as intake_router
from .api.routes import router as crud_router
from .api.settings_routes import router as settings_router
from .config import ANTHROPIC_API_KEY, DEFAULT_SETTINGS
from .lifecycle import reconcile_at_startup

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not ANTHROPIC_API_KEY:
        # Don't block startup — fixture-only use (e.g. /demo) still works
        # without a key — but surface the omission loudly so it isn't
        # discovered via a cryptic 401 on the first agent turn.
        logger.warning(
            "ANTHROPIC_API_KEY is not set. The backend will boot, but any "
            "dossier or intake agent call will fail. Set the key in "
            "backend/.env before exercising the agent."
        )
    # Seed default setting values before reconcile so any downstream
    # consumer (e.g. a budget check during reactive-wake) sees a populated
    # row rather than a None fallback. Idempotent — only inserts missing keys.
    try:
        storage.seed_default_settings(DEFAULT_SETTINGS)
    except Exception:
        logger.exception("failed to seed default settings; continuing")
    reconcile_at_startup()  # logs its own summary; may set wake_pending for crashed runs
    SCHEDULER.start()
    yield
    await SCHEDULER.stop()
    await ORCHESTRATOR.shutdown()


def create_app() -> FastAPI:
    db.init_db()
    app = FastAPI(title="Vellum", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api_dependencies = [Depends(require_api_token)]
    app.include_router(crud_router, dependencies=api_dependencies)
    app.include_router(agent_router, dependencies=api_dependencies)
    app.include_router(intake_router, dependencies=api_dependencies)
    app.include_router(settings_router, dependencies=api_dependencies)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
