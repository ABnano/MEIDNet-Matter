"""Read routes: the project, its dataset, its models, the families, and goal validation."""
from __future__ import annotations

from fastapi import APIRouter, Request

from matter.api.deps import get_services
from matter.api.errors import ApiError
from matter.schemas.goal import Goal
from matter.services import families as F
from matter.services import goals as G

router = APIRouter()


def _project(services, project_id: str) -> dict:
    if project_id != services.artefacts.project["project_id"]:
        raise ApiError("not_found", f"unknown project '{project_id}'", status=404)
    return services.artefacts.project


@router.get("/projects", summary="The projects of this server")
def projects(request: Request) -> list[dict]:
    s = get_services(request)
    p = s.artefacts.project
    return [{"project_id": p["project_id"], "title": p["title"], "description": p["description"], "dataset_id": p["dataset_id"],
             "models": p["models"], "default_model": p["default_model"]}]


@router.get("/projects/{project_id}", summary="One project: dataset summary, models, default goal, limits")
def project(project_id: str, request: Request) -> dict:
    s = get_services(request)
    p = dict(_project(s, project_id))
    p["dataset"] = s.artefacts.dataset_summary()
    p["models"] = [s.registry.info(m, with_evaluation=False) for m in p["models"]]
    p["limits"] = dict(G.PUBLIC_LIMITS) if s.settings.public else None
    p["mode"] = s.settings.mode
    p["default_goal_summary"] = G.summary_text(Goal.model_validate(p["default_goal"]), s.artefacts)
    return p


@router.get("/projects/{project_id}/dataset", summary="The dataset in detail, with the ambiguity grid")
def dataset(project_id: str, request: Request) -> dict:
    s = get_services(request)
    _project(s, project_id)
    return s.artefacts.dataset_summary(with_grid=True)


@router.get("/models/{model_id}", summary="A model with its held-out evaluation")
def model(model_id: str, request: Request) -> dict:
    return get_services(request).registry.info(model_id)


@router.get("/families", summary="The material families the engine can build")
def families(request: Request) -> list[dict]:
    get_services(request)
    return F.list_families()


@router.get("/families/{name}", summary="One family with its variant, elements, dataset coverage and rules")
def family(name: str, request: Request, variant: str | None = None) -> dict:
    s = get_services(request)
    return F.family_payload(name, variant, s.artefacts.dataset.get("family_coverage"), s.artefacts.dataset.get("elements"))


@router.post("/goals/validate", summary="Check a goal and show how it runs")
def validate_goal(goal: Goal, request: Request) -> dict:
    s = get_services(request)
    try:
        v = G.validate(goal, s)
    except G.GoalInvalid as e:
        return {"ok": False, "errors": e.fields, "message": e.message, "summary": G.summary_text(goal, s.artefacts)}
    return {"ok": True, "generation": v.generation, "targets_explained": v.explained, "windows": v.windows, "notes": v.notes,
            "estimated_seconds": v.estimated_seconds, "summary": G.summary_text(goal, s.artefacts),
            "family": {"name": v.family.name, "variant": v.family.variant, "n_sites": v.family.n_sites,
                       "rules": [r["id"] for r in F.rule_entries(v.family)]}}
