"""The executed studies and the checkpoints they refer to (read-only artefacts built by scripts/build_studies.py)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from matter.api.deps import get_services
from matter.api.errors import ApiError

router = APIRouter(tags=["studies"])


@router.get("/studies", summary="The studies in reading order")
def studies(request: Request, services=Depends(get_services)) -> dict:
    return services.studies.index()


@router.get("/studies/{study_id}", summary="One study: facts, block verdicts, target following, candidates, checkpoints")
def study(study_id: str, services=Depends(get_services)) -> dict:
    return services.studies.get(study_id)


@router.get("/studies/{study_id}/files/{name:path}", summary="A table or structure file a study links to")
def study_file(study_id: str, name: str, services=Depends(get_services)):
    path, media = services.studies.file_path(study_id, name)
    return FileResponse(path, media_type=media, filename=os.path.basename(path))


@router.get("/checkpoints", summary="Every checkpoint with its checksum, size, role and download links")
def checkpoints(services=Depends(get_services)) -> dict:
    return services.catalog.listing()


@router.get("/checkpoints/{checkpoint_id}", summary="One checkpoint, with its training configuration")
def checkpoint(checkpoint_id: str, services=Depends(get_services)) -> dict:
    return services.catalog.info(checkpoint_id, with_config=True)


@router.get("/checkpoints/{checkpoint_id}/download", summary="The checkpoint file, when it is present on this server")
def checkpoint_download(checkpoint_id: str, services=Depends(get_services)):
    e = services.catalog.entry(checkpoint_id)
    path = services.catalog.path(checkpoint_id)
    if not path or not os.path.isfile(path):
        raise ApiError("model_unavailable", f"{checkpoint_id} is not stored on this server; download it from one of its urls", status=503)
    return FileResponse(path, media_type="application/octet-stream", filename=e["file"])
