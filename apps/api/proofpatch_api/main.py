"""FastAPI application.

The API is deliberately thin: it validates requests, stores run records, starts
the engine's orchestrator in a background pool, and serves state/artifacts. It
never duplicates verification logic.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from proofpatch import __version__

from .db import init_db
from .routes import artifacts, runs
from .schemas import HealthOut
from .settings import get_settings

# apps/api/proofpatch_api/main.py -> apps/web/dist
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="ProofPatch API",
    version=__version__,
    description="Evidence-backed verification for AI-generated patches.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router)
app.include_router(artifacts.router)


@app.get("/health", tags=["meta"])
def health() -> HealthOut:
    settings = get_settings()
    return HealthOut(ok=True, provider_mode=settings.cline_provider_id, version=__version__)


if WEB_DIST.exists():
    assets_dir = WEB_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard_index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # API routes are registered earlier and match first.
        candidate = (WEB_DIST / full_path).resolve()
        if full_path and WEB_DIST.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        index = WEB_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": "Dashboard not built."}, status_code=404)
else:

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {"ok": True, "service": "proofpatch", "version": __version__}
