"""Train Lite: a small, fixed MEIDNet training on the shared server (see matter.services.trainlite)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse

from matter.api.deps import get_services, require_owner, session_id
from matter.api.errors import ApiError
from matter.schemas.train import TrainRequest
from matter.services import trainlite as TL
from matter.services.runs import public_record

router = APIRouter(tags=["train"])


def _ready(services):
    if services.trainings is None or services.trainlite is None or not services.trainlite.available:
        raise ApiError("not_available", "Train Lite is not available on this server: the demo folder ships no featurised subset", status=503)


@router.get("/train/options", summary="What Train Lite trains on, the choices, the reference it is compared with")
def options(services=Depends(get_services)) -> dict:
    if services.trainlite is None:
        return {"available": False}
    return services.trainlite.describe()


@router.post("/train", status_code=201, summary="Start a small MEIDNet training (10, 20 or 50 epochs on 1,500 Perov-5 materials)")
def create(body: TrainRequest, request: Request, x_matter_session: str | None = Header(default=None), services=Depends(get_services)) -> dict:
    sid = session_id(request, x_matter_session, mutating=True)
    _ready(services)
    if services.settings.public:
        services.trainings.cleanup()
    req = TL.validate_request(body, services.settings.public)
    job = services.trainings.create(sid, req, services.trainlite.reference["subset"], TL.estimated_seconds(req["epochs"]))
    try:
        services.jobs.start(job["job_id"], sid, TL.execute_training, job, services, max_seconds=TL.TRAIN_PUBLIC_LIMITS["seconds"])
    except ApiError:
        services.trainings.remove(job["job_id"])
        raise
    return TL.summary(job)


@router.get("/train", summary="This session's training jobs")
def list_jobs(request: Request, x_matter_session: str | None = Header(default=None), services=Depends(get_services)) -> list[dict]:
    sid = session_id(request, x_matter_session)
    if services.trainings is None:
        return []
    return services.trainings.list(sid if services.settings.public else None)


@router.get("/train/{job_id}", summary="A training job: progress and curves (default) or the whole record (view=full)")
def get_job(job_id: str, view: str = "status", services=Depends(get_services)) -> dict:
    _ready(services)
    job = services.trainings.get(job_id)
    if view == "full":
        return {k: v for k, v in public_record(job).items() if not k.startswith("_")}
    return TL.status_view(job)


@router.post("/train/{job_id}/stop", summary="Stop a training after the current epoch; what was learned is kept and measured")
def stop(job_id: str, request: Request, x_matter_session: str | None = Header(default=None), services=Depends(get_services)) -> dict:
    _ready(services)
    job = services.trainings.get(job_id)
    require_owner(request, x_matter_session, job, "training job")
    stopping = services.jobs.stop(job_id)
    return {"ok": True, "stopping": stopping, "status": job["status"]}


def _file(services, job_id: str, name: str, media: str, filename: str):
    _ready(services)
    job = services.trainings.get(job_id)
    if job["status"] in ("queued", "running"):
        raise ApiError("busy", "the training is still running; download when it has finished", status=409, retry_after_s=10)
    path = os.path.join(services.trainings.path(job_id), name)
    if not os.path.isfile(path):
        raise ApiError("not_found", f"{name} was not written for {job_id}", status=404)
    return FileResponse(path, media_type=media, filename=filename)


@router.get("/train/{job_id}/model.pt", summary="The trained MEIDNet checkpoint")
def model_file(job_id: str, services=Depends(get_services)):
    return _file(services, job_id, "model.pt", "application/octet-stream", f"{job_id}.pt")


@router.get("/train/{job_id}/config.yaml", summary="The recipe with this job's epochs and seed")
def config_file(job_id: str, services=Depends(get_services)):
    return _file(services, job_id, "config.yaml", "text/yaml; charset=utf-8", f"{job_id}.yaml")


@router.get("/train/{job_id}/predictions.csv", summary="Reference and predicted values of the 500 validation materials")
def predictions_file(job_id: str, services=Depends(get_services)):
    return _file(services, job_id, "predictions.csv", "text/csv; charset=utf-8", f"{job_id}_predictions.csv")
