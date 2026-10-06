"""All API routes, mounted under /api by matter.app."""
from __future__ import annotations

from fastapi import APIRouter, Request

from matter.version import build_info

api_router = APIRouter()


@api_router.get("/version", summary="What is running: versions, git commit, mode")
def version(request: Request) -> dict:
    settings = request.app.state.settings
    return build_info(settings.build_info, settings.public)
