import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from assessment_agent.api.routes import router


def create_assessment_app() -> FastAPI:
    """Create the Assessment Agent FastAPI application."""
    app = FastAPI(
        title="AIEIC Assessment Agent",
        description=(
            "Automated assessment agent for CSC 580 lab submissions. "
            "Part of the AIEIC Lab Agentic Design Framework. "
            "Handles code grading, report evaluation, anomaly detection, "
            "and personalized feedback generation."
        ),
        version="0.1.0",
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

    @app.get("/health")
    async def health():
        return {"status": "healthy", "agent": "assessment"}

    return app
