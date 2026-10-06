"""Schema routes: the versioned candidate record and the targets.csv layout that Prism's `meidnet score` reads."""
from __future__ import annotations

from fastapi import APIRouter

from matter.schemas.candidate import SCHEMA_ID, TARGETS_CSV_COLUMNS, json_schema
from matter.services.enrichment import CLUSTER_COSINE, VALIDATION_STAGES

router = APIRouter()


@router.get("/schema/candidate-record", summary="The JSON Schema of a candidate record")
def candidate_record_schema() -> dict:
    return {"schema": SCHEMA_ID, "json_schema": json_schema(), "validation_stages": VALIDATION_STAGES, "cluster_cosine": CLUSTER_COSINE,
            "notes": ["Every candidate of a run is a record of this schema; GET /api/runs/{run_id}/candidates/{candidate_id}/record.json downloads one.",
                      "A later version adds fields and never changes the meaning of an existing one; the version in the schema id changes otherwise.",
                      "The run bundle holds this schema as candidate-record.schema.json next to targets.csv and cifs/."]}


@router.get("/schema/targets-csv", summary="The columns of targets.csv in a run bundle")
def targets_csv_schema() -> dict:
    return {"columns": TARGETS_CSV_COLUMNS,
            "usage": "meidnet score <bundle>/cifs --targets <bundle>/targets.csv --reference data/perov5   (MEIDNet 2.3.1 or later, on Prism)",
            "note": "In this version the values are the search's own predictions, so the conditional metrics measure how closely the predictions "
                    "follow the targets, not how the structures behave in DFT or experiment."}
