from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse
from hop_core.app_factory import create_hop_app
from hop_core.credentials import AI_PROVIDER_TYPES, register_builtin_types
from hop_core.db import get_engine, get_session_factory
from sqlalchemy import text

import models  # noqa: F401  register our tables before hop-core's startup
import runner
from migrate import migrate
from routes import runs, setup, sites
from settings import get_settings

# Model keys for the agents (Claude, OpenAI, Gemini), plus Heretto connections
# for agents' Heretto references.
register_builtin_types("heretto", *AI_PROVIDER_TYPES)

app = create_hop_app(
    settings_factory=get_settings,
    title="HOP Audit",
    description="Audits documentation websites and help centers",
    version="0.1.0",
    extra_routers=[setup.router, sites.router, runs.router],
)

_hop_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(app):
    migrate()  # before hop-core's create_all; see migrate.py
    with get_session_factory()() as db:
        runner.recover_interrupted(db)
    async with _hop_lifespan(app):
        yield


app.router.lifespan_context = lifespan


@app.get("/api/health")
def health():
    """Unauthenticated, outside the API prefix (hop-core AGENTS.md §5)."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # report, don't crash the probe
        return JSONResponse({"status": "degraded", "detail": type(exc).__name__}, status_code=503)
    return {"status": "ok"}
