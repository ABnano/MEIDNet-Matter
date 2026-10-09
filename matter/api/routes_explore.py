"""Explore: the demo dataset as a map of the learned representation, and one material at a time with its cell and its
nearest neighbours in the full latent space (built by matter.demo_build.build_explore)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from matter.api.deps import get_services
from matter.api.errors import ApiError

router = APIRouter(tags=["explore"])


def _artefacts(services, project_id: str):
    art = getattr(services, "artefacts", None)
    if art is None or art.project.get("project_id") != project_id:
        raise ApiError("not_found", f"unknown project '{project_id}'", status=404)
    return art


@router.get("/explore/{project_id}", summary="Every training material as a point of the default model's latent map")
def explore(project_id: str, services=Depends(get_services)):
    art = _artefacts(services, project_id)
    path = os.path.join(art.dir, "explore.json")
    if not os.path.isfile(path):
        raise ApiError("not_available", "this demo ships no explore map (rebuild it with meidnet-matter build-demo)", status=503)
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/explore/{project_id}/materials/{material_id}", summary="One material: its values, its cell, its nearest neighbours in the latent space")
def material(project_id: str, material_id: str, k: int = 6, services=Depends(get_services)) -> dict:
    art = _artefacts(services, project_id)
    try:
        i = art.materials.ids.index(material_id)
    except ValueError:
        raise ApiError("not_found", f"no material {material_id} in this dataset", status=404) from None
    row = art.materials.row(i)
    out = {**row, "cell": art.cell(material_id), "neighbours": [], "encoder_prediction": None,
           "note": "Nearest neighbours by cosine in the full 128-dimensional structure latent of the default model, among the training materials."}
    index = art.latents(art.project["default_model"])
    if index is not None and material_id in index.ids:
        j = index.ids.index(material_id)
        near = index.nearest(index.z[j], k=min(50, k + 1))
        out["neighbours"] = [n for n in near if n["material_id"] != material_id][:k]
        out["encoder_prediction"] = {c: float(index.pred[j, c_i]) for c_i, c in enumerate(index.columns)}
    return out
