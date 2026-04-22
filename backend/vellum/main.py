import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .agent.orchestrator import ORCHESTRATOR
from .api.agent_routes import router as agent_router
from .api.intake_routes import router as intake_router
from .api.routes import router as crud_router
from .config import ANTHROPIC_API_KEY
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
    reconcile_at_startup()  # logs its own summary
    yield
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
    app.include_router(crud_router)
    app.include_router(agent_router)
    app.include_router(intake_router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
