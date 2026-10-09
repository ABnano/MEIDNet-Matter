"""All API routes, mounted under /api by matter.app."""
from __future__ import annotations

from fastapi import APIRouter, Request

from matter.api import (routes_explore, routes_generate, routes_pipeline, routes_read, routes_readiness, routes_runs, routes_schema,
                        routes_studies, routes_train)
from matter.version import build_info

api_router = APIRouter()
api_router.include_router(routes_read.router)
api_router.include_router(routes_readiness.router)
api_router.include_router(routes_runs.router)
api_router.include_router(routes_schema.router)
api_router.include_router(routes_pipeline.router)
api_router.include_router(routes_studies.router)
api_router.include_router(routes_generate.router)
api_router.include_router(routes_explore.router)
api_router.include_router(routes_train.router)


@api_router.get("/version", summary="What is running: versions, git commit, mode")
def version(request: Request) -> dict:
    settings = request.app.state.settings
    return build_info(settings.build_info, settings.public)
