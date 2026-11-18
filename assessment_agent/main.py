import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from assessment_agent import config
from aied_db import get_db, ping
from assessment_agent.api.assignment_routes import router as assignment_router
from assessment_agent.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests set ``app.state.database`` to mongomock before starting the
    # client. Production establishes one pool and fails early if Atlas is
    # unavailable.
    if not hasattr(app.state, "database"):
        ping()
        app.state.database = get_db()
    yield


def create_assessment_app() -> FastAPI:
    """Create the Assessment Agent FastAPI application."""
    app = FastAPI(
        title="AIEIC Assessment Agent",
        description=(
            "Automated assessment agent for CSC 580 lab submissions. "
            "Part of the AIEIC Lab Agentic Design Framework. "
            "Grades submissions against instructor-provided rubrics and "
            "writes feedback."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    # Browser UIs (the instructor UI) call this agent directly. Set CORS_ORIGINS to a
    # comma-separated list of allowed origins; the default covers the Vite dev server.
    origins = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(assignment_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy", "agent": "assessment"}

    return app
