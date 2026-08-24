"""ChargeLens API - AI Chargeback Risk & Evidence Responder."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import analytics, cases, dashboard, webhooks
from .config import settings
from .database import engine, init_db
from .models.entities import Chargeback


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # first run on an empty database: seed the demo data automatically
    if settings.auto_seed:
        from sqlalchemy.orm import Session
        with Session(engine) as db:
            empty = db.query(Chargeback).first() is None
        if empty:
            from .seed import seed
            seed()
    yield


app = FastAPI(
    title="ChargeLens",
    description="AI Chargeback Risk & Evidence Responder - defensive, "
                "explainable, human-in-the-loop. Synthetic data only.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(webhooks.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---- single-image deployment: serve the built frontend if present ------
# In development Vite serves the UI on :5173 and proxies /api here; in the
# Docker image the compiled dist ships alongside the API so one container
# on one port is the whole product.
import os  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .config import BACKEND_DIR  # noqa: E402

_dist = Path(os.environ.get(
    "CHARGELENS_FRONTEND_DIST", BACKEND_DIR.parent / "frontend" / "dist"))

if (_dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"),
              name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        candidate = _dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
