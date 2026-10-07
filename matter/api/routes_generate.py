"""Generation jobs: a band-gap request in, structures with two judgements out."""
from __future__ import annotations

import io
import os
import zipfile

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse, StreamingResponse

from matter.api.deps import get_services, session_id
from matter.api.errors import ApiError
from matter.schemas.generation import GENERATION_SCHEMA_ID, GenerateRequest, result_schema
from matter.services import generation as GEN

router = APIRouter(tags=["generate"])


@router.post("/generate", status_code=201, summary="Start a generation job for one or more band-gap targets")
def create(body: GenerateRequest, request: Request, x_matter_session: str | None = Header(default=None), services=Depends(get_services)) -> dict:
    sid = session_id(request, x_matter_session, mutating=True)
    settings = services.settings
    if settings.public:
        services.generations.cleanup()
    req, notes = GEN.validate_request(body, settings.public, services.catalog)
    if not services.catalog.available(req["model_id"]):
        raise ApiError("model_unavailable", f"{req['model_id']} is not present on this server", status=503)
    est = int(8 + 1.5 * sum(req["per_target"] for _ in req["targets"]) * (1 + len(req["targets"])))
    job = services.generations.create(sid, req, notes, services.catalog.info(req["model_id"]), services.judge.describe(), est)
    try:
        services.jobs.start(job["job_id"], sid, GEN.execute_generation, job, services, max_seconds=GEN.GEN_PUBLIC_LIMITS["seconds"])
    except ApiError:
        services.generations.remove(job["job_id"])
        raise
    return GEN.summary(job)


@router.get("/generate", summary="This session's generation jobs")
def list_jobs(request: Request, x_matter_session: str | None = Header(default=None), services=Depends(get_services)) -> list[dict]:
    sid = session_id(request, x_matter_session)
    return services.generations.list(sid if services.settings.public else None)


@router.get("/generate/{job_id}", summary="A job's status (default) or its whole record (view=full)")
def get_job(job_id: str, view: str = "status", services=Depends(get_services)) -> dict:
    job = services.generations.get(job_id)
    if view == "full":
        return {k: v for k, v in job.items() if not k.startswith("_")}
    return GEN.status_view(job)


@router.post("/generate/{job_id}/stop", summary="Ask a running job to stop after the current draw")
def stop(job_id: str, services=Depends(get_services)) -> dict:
    job = services.generations.get(job_id)
    stopping = services.jobs.stop(job_id)
    return {"ok": True, "stopping": stopping, "status": job["status"]}


@router.get("/generate/{job_id}/candidates/{candidate_id}/cif", summary="One generated cell")
def cif(job_id: str, candidate_id: str, services=Depends(get_services)):
    job = services.generations.get(job_id)
    for c in job.get("candidates", []):
        if c["candidate_id"] == candidate_id:
            path = os.path.join(services.generations.path(job_id), c["file"])
            if os.path.isfile(path):
                return FileResponse(path, media_type="chemical/x-cif", filename=f"{c['formula']}_{candidate_id}.cif")
    raise ApiError("not_found", f"no candidate {candidate_id} in {job_id}", status=404)


@router.get("/generate/{job_id}/export/cifs.zip", summary="Every generated cell, the table, the record and the relax command")
def export_zip(job_id: str, services=Depends(get_services)):
    job = services.generations.get(job_id)
    if job["status"] in ("queued", "running"):
        raise ApiError("busy", "the job is still running; download when it has finished", status=409, retry_after_s=15)
    folder = services.generations.path(job_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                p = os.path.join(root, name)
                z.write(p, os.path.relpath(p, folder))
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{job_id}.zip"'})


@router.get("/schema/generation-result", summary="The JSON Schema of a generation record")
def schema() -> dict:
    return {"schema_id": GENERATION_SCHEMA_ID, **result_schema()}
