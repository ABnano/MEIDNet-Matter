"""POST /api/readiness: the Design Readiness report of a goal."""
from __future__ import annotations

from fastapi import APIRouter, Request

from matter.api.deps import get_services
from matter.schemas.goal import Goal
from matter.services import goals as G
from matter.services import readiness as R

router = APIRouter()


@router.post("/readiness", summary="Can this dataset and model support this goal?")
def readiness(goal: Goal, request: Request) -> dict:
    s = get_services(request)
    v = G.validate(goal, s)                     # GoalInvalid -> 422 with field messages
    return R.assess(v, s)
