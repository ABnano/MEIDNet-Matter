"""Runs: start a search, follow it, read its candidates, compare them, export."""
from __future__ import annotations

import os

import numpy as np
from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from matter.api.deps import get_services, require_owner, session_id
from matter.api.errors import ApiError
from matter.schemas.goal import Goal
from matter.services import goals as G
from matter.services import runs as RUNS
from matter.services.export import candidate_json, candidates_csv

router = APIRouter()


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: Goal
    acknowledge_exploratory: bool = Field(False, description="start although the readiness report did not recommend it")


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_ids: list[str] = Field(min_length=2, max_length=6)


def _run(services, run_id: str) -> dict:
    return services.runs.get(run_id)


def _candidate(run: dict, candidate_id: str) -> dict:
    for c in run.get("candidates", []):
        if c["candidate_id"] == candidate_id:
            return c
    raise ApiError("not_found", f"no candidate {candidate_id} in run {run['run_id']}", status=404)


@router.post("/runs", status_code=201, summary="Start a candidate search")
def create_run(body: RunCreate, request: Request, x_matter_session: str | None = Header(default=None)) -> dict:
    s = get_services(request)
    sid = session_id(request, x_matter_session, mutating=True)
    if s.settings.public:
        s.runs.cleanup()
    v = G.validate(body.goal, s)
    model_id = body.goal.model_id or s.artefacts.project["default_model"]
    readiness = s.backend.assess_readiness(v, s)
    if readiness["exploratory_required"] and not body.acknowledge_exploratory:
        raise ApiError("exploratory_required", "the readiness report does not recommend this target; set acknowledge_exploratory to run "
                       "anyway in exploratory mode", status=400)
    mode = "exploratory" if readiness["exploratory_required"] else "standard"
    if readiness.get("search_advice") and body.goal.diverse_set is None:
        v.generation["per_target"] = max(v.generation["per_target"], readiness["search_advice"]["per_target_min"])
        v.generation["min_cosine_sep"] = min(v.generation["min_cosine_sep"], readiness["search_advice"]["min_cosine_sep_max"])
        v.notes.append("one-to-many target: at least 3 candidates per target, kept apart in the latent space")
        v.estimated_seconds = G.estimated_seconds(v.generation)
    run = s.runs.create(sid, v, readiness, model_id, mode, G.summary_text(body.goal, s.artefacts))
    s.jobs.start(run["run_id"], sid, RUNS.execute_search, run, s)
    return RUNS.summary(run)


@router.get("/runs", summary="The runs of this session")
def list_runs(request: Request, x_matter_session: str | None = Header(default=None)) -> list[dict]:
    s = get_services(request)
    sid = session_id(request, x_matter_session)
    return s.runs.list(sid if s.settings.public else None)


@router.get("/runs/{run_id}", summary="A run: status view (progress, log tail, candidates) or full")
def get_run(run_id: str, request: Request, view: str = "status") -> dict:
    s = get_services(request)
    run = _run(s, run_id)
    if view == "full":
        return RUNS.public_record(run)
    return RUNS.status_view(run)


@router.post("/runs/{run_id}/stop", summary="Stop a running search; what was found is kept")
def stop_run(run_id: str, request: Request, x_matter_session: str | None = Header(default=None)) -> dict:
    s = get_services(request)
    run = _run(s, run_id)
    require_owner(request, x_matter_session, run, "search")
    stopped = s.jobs.stop(run_id)
    return {"ok": True, "stopping": stopped, "status": run["status"]}


@router.get("/runs/{run_id}/candidates", summary="The candidates found so far, with their evidence")
def candidates(run_id: str, request: Request) -> list[dict]:
    return _run(get_services(request), run_id).get("candidates", [])


@router.get("/runs/{run_id}/candidates/{candidate_id}", summary="One candidate")
def candidate(run_id: str, candidate_id: str, request: Request) -> dict:
    return _candidate(_run(get_services(request), run_id), candidate_id)


@router.get("/runs/{run_id}/candidates/{candidate_id}/cif", summary="The candidate's structure as CIF")
def candidate_cif(run_id: str, candidate_id: str, request: Request):
    s = get_services(request)
    run = _run(s, run_id)
    c = _candidate(run, candidate_id)
    rel = (c.get("structure") or {}).get("file") or ("generation/" + c["engine"]["file"])
    path = os.path.join(s.runs.path(run_id), rel.replace("/", os.sep))
    if not os.path.isfile(path):
        raise ApiError("not_found", "the CIF of this candidate is not on disk", status=404)
    name = f"{c['identity']['formula']}_{candidate_id}.cif"
    return FileResponse(path, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                                                "Cache-Control": "no-cache"})


@router.get("/runs/{run_id}/candidates/{candidate_id}/record.json", summary="The candidate record as a file")
def candidate_record(run_id: str, candidate_id: str, request: Request):
    c = _candidate(_run(get_services(request), run_id), candidate_id)
    return Response(candidate_json(c), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{candidate_id}.json"'})


@router.post("/runs/{run_id}/compare", summary="Candidates side by side, with their pairwise latent cosines")
def compare(run_id: str, body: CompareRequest, request: Request) -> dict:
    run = _run(get_services(request), run_id)
    rows = [_candidate(run, cid) for cid in body.candidate_ids]
    Z = np.array([r["model_evidence"]["latent"] for r in rows], dtype=float)
    Z /= np.maximum(np.linalg.norm(Z, axis=1, keepdims=True), 1e-12)
    return {"candidates": rows, "pairwise_cosine": (Z @ Z.T).round(4).tolist(),
            "properties": {p: {"label": v["label"], "unit": v["unit"]} for p, v in rows[0]["properties"].items()}}


@router.get("/runs/{run_id}/export/candidates.csv", summary="The candidate table")
def export_csv(run_id: str, request: Request):
    run = _run(get_services(request), run_id)
    return Response(candidates_csv(run), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}_candidates.csv"'})


@router.get("/runs/{run_id}/export/candidates.json", summary="The candidates as JSON")
def export_json(run_id: str, request: Request):
    run = _run(get_services(request), run_id)
    return Response(candidate_json(run.get("candidates", [])), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}_candidates.json"'})


@router.get("/runs/{run_id}/export/bundle.zip", summary="The run bundle")
def export_bundle(run_id: str, request: Request):
    s = get_services(request)
    run = _run(s, run_id)
    if run["status"] in ("queued", "running"):
        raise ApiError("busy", "the bundle is written when the search has finished", status=409, retry_after_s=10)
    data = s.backend.export(run, "bundle", s)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{run_id}_bundle.zip"'})


@router.get("/runs/{run_id}/manifest", summary="The run manifest")
def manifest(run_id: str, request: Request) -> dict:
    run = _run(get_services(request), run_id)
    if not run.get("manifest"):
        raise ApiError("busy", "the manifest is written when the search has finished", status=409, retry_after_s=10)
    return run["manifest"]


@router.get("/runs/{run_id}/chemiscope", summary="The candidates as a chemiscope dataset")
def chemiscope(run_id: str, request: Request) -> dict:
    from meidnet.studio.chemiscope import candidates_dataset
    from matter.schemas.goal import Goal as _Goal
    s = get_services(request)
    run = _run(s, run_id)
    if not run.get("candidates"):
        return {"available": False, "note": "no candidates yet"}
    v = G.validate(_Goal.model_validate(run["goal"]), s, run_dir=s.runs.path(run_id))
    lm = s.registry.load(run["model_id"]) if s.registry.available(run["model_id"]) else None
    raw = [c["engine"] for c in run["candidates"] if "engine" in c]
    return {"available": True, **candidates_dataset(raw, v.family, s.runs.path(run_id), lm)}
