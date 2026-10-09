"""A generation request and the versioned result record of a generation job.

The request names a model and the band-gap values asked for; the result carries, for every candidate, the label read
from the returned structure, the independent judge's value, whether both lie inside the window (the consensus), and the
evidence a reader needs to weigh it.  Relaxation is not run on this server: the record carries the command for it.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

GENERATION_SCHEMA_ID = "meidnet-matter/generation-result/1"


class GenerateRequest(BaseModel, extra="forbid"):
    model_id: str = Field("mp20-wyck", description="A checkpoint with a symmetry decoder (see /api/checkpoints).")
    property: Literal["band_gap"] = Field("band_gap", description="The property the targets refer to.")
    targets: list[float] = Field(..., min_length=1, max_length=8, description="Requested values, eV.")
    per_target: int = Field(10, ge=1, le=50, description="Structures to keep per target.")
    window_eV: float = Field(0.5, ge=0.1, le=2.0, description="Accept a structure when BOTH judges are within this of the request.")
    require_anion: bool = Field(True, description="Force at least one anion site, so the result is a compound rather than an intermetallic.")
    exclude_elements: list[str] = Field(default_factory=lambda: ["Ac", "Np", "Pa", "Pm", "Pu", "Tc", "Th", "U"],
                                        description="Element symbols the decoder may not use (default: the radioactive ones).")
    seed: int = Field(0, ge=0, le=2**31 - 1)
    oversample: int = Field(40, ge=1, le=200, description="Draws attempted per structure kept.")


def result_schema() -> dict:
    """The JSON Schema of a generation record, for GET /api/schema/generation-result."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": GENERATION_SCHEMA_ID, "type": "object",
        "required": ["schema", "job_id", "status", "request", "candidates"],
        "properties": {
            "schema": {"const": GENERATION_SCHEMA_ID}, "job_id": {"type": "string"},
            "status": {"enum": ["queued", "running", "done", "stopped", "error", "interrupted"]},
            "request": GenerateRequest.model_json_schema(),
            "model": {"type": "object", "description": "model id, file, sha256, properties, geometry"},
            "judge": {"type": "object", "description": "name, fidelity, qualification on the dataset's test split, availability"},
            "funnel": {"type": "object", "description": "attempted, kept, judged, consensus"},
            "rejected": {"type": "object", "additionalProperties": {"type": "integer"}},
            "per_target": {"type": "array"},
            "candidates": {"type": "array", "items": {"type": "object", "properties": {
                "candidate_id": {"type": "string"}, "target_eV": {"type": "number"}, "formula": {"type": "string"},
                "natoms": {"type": "integer"}, "spacegroup": {"type": "integer"},
                "label_structure_eV": {"type": ["number", "null"], "description": "the model's label read from the returned structure"},
                "label_formation_energy_eV_atom": {"type": ["number", "null"]},
                "judge_eV": {"type": ["number", "null"], "description": "a second model's reading of the returned structure (MEGNet, no part in generation); like the label, an estimate of the PBE gap"},
                "consensus": {"type": "boolean"}, "metal_by_judge": {"type": ["boolean", "null"]},
                "charge_balanced": {"type": ["boolean", "null"]}, "known_formula": {"type": ["boolean", "null"]},
                "recorded_gaps_eV": {"type": "array"}, "amd_nearest_reference": {"type": ["number", "null"]},
                "novel_by_amd": {"type": ["boolean", "null"]}, "lattice": {"type": "object"}, "volume_per_atom": {"type": "number"},
                "geometry": {"type": ["object", "null"], "description": "contact_ratio (closest atoms over the sum of their radii; "
                             "under 0.6 the cell needs relaxation before any use), empty_layer_A and packing (generated cells with an "
                             "empty layer over 6 A or a packing fraction under 0.12 are not kept)"},
                "file": {"type": "string"}, "sha256": {"type": "string"},
                "stability": {"type": "object", "description": "always 'not assessed' on this server; relax locally"}}}},
            "relax_command": {"type": "string"}, "provenance": {"type": "object"},
        },
        "notes": ["Two judges of different lineage must agree for a candidate to count as consensus.",
                  "No relaxation and no hull energy are computed on the server: stability is not assessed here."],
    }
