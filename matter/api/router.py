"""All API routes, mounted under /api by matter.app."""
from __future__ import annotations

from fastapi import APIRouter, Request

from matter.api import routes_read, routes_readiness
from matter.api.errors import NotAvailableInPhase
from matter.version import build_info

api_router = APIRouter()
api_router.include_router(routes_read.router)
api_router.include_router(routes_readiness.router)


@api_router.get("/version", summary="What is running: versions, git commit, mode")
def version(request: Request) -> dict:
    settings = request.app.state.settings
    return build_info(settings.build_info, settings.public)


@api_router.post("/datasets/upload", summary="Phase 1: upload your own dataset", status_code=501)
def upload_dataset():
    raise NotAvailableInPhase(1, "Uploading your own dataset")


@api_router.post("/models/train", summary="Phase 1: train a model on your dataset", status_code=501)
def train_model():
    raise NotAvailableInPhase(1, "Training a model")
