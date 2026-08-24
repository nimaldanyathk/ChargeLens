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
