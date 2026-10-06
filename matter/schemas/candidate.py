"""The candidate record: the versioned JSON document that a candidate leaves Matter as.

Every candidate of a run carries `"schema": "meidnet-matter/candidate-record/1"`. The record holds the structure,
the targets and the predicted values with their domain status, the chemistry rules with their values, the model's
own evidence (encoder prediction, nearest training materials, local density, latent), the novelty check, the
validation ladder with the records reached so far, the cluster the candidate belongs to, and the provenance
(software versions, model sha256, dataset fingerprint, goal hash, run id). `GET /api/schema/candidate-record`
returns the JSON Schema; `meidnet score` on Prism reads the CIFs and `targets.csv` of a run bundle.

A later version of the record adds fields; it never changes the meaning of an existing one. The version number
in the schema id changes when that promise cannot be kept.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_ID = "meidnet-matter/candidate-record/1"
DomainStatus = Literal["in_distribution", "near_boundary", "extrapolating", "far_outside"]


class Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class DomainBlock(Loose):
    status: DomainStatus
    word: str
    reason: str | None = None


class PropertyEvidence(Loose):
    label: str
    unit: str
    objective: str | None = None
    target: float | None = None
    predicted: float
    difference: float | None = None
    uncertainty: float | None = None
    uncertainty_note: str = ""
    training_range: list[float | None]
    domain: DomainBlock
    in_window: bool | None = None
    window: list[float | None] | None = None
    evidence_label: str
    dft_value: float | None = None
    dft_label: str | None = None


class RuleResult(Loose):
    id: str
    rule: str
    title: str
    text: str = ""
    passed: bool
    value: float | None = None
    window: list[float | None] | None = None
    detail: str = ""
    evidence_label: str


class Identity(Loose):
    formula: str
    reduced_formula: str
    site_key: str | None = None
    elements: dict[str, str]
    family: str
    variant: str | None = None
    backend: str
    model_id: str


class StructureBlock(Loose):
    file: str
    lattice_a: float | None = None
    n_sites: int
    chemiscope: dict
    sites: list[dict]
    lattice: list[list[float]]


class NoveltyCheck(Loose):
    checked_against: str
    found: bool
    match: dict | None = None
    label: str


class Novelty(Loose):
    method: str
    dataset: NoveltyCheck
    training_split: NoveltyCheck


class ModelEvidence(Loose):
    encoder_prediction: dict[str, float]
    agreement: dict[str, dict]
    latent_norm: float | None = None
    latent_hit_clip: bool = False
    score: float | None = None
    nearest_training: list[dict]
    latent_distance: float | None = None
    local_density: dict
    latent: list[float]


class ValidationRecord(Loose):
    stage: int = Field(ge=0, le=5)
    label: str
    method: str
    outcome: str
    passed: bool | None = None


class Validation(Loose):
    """The six-stage ladder: 0 Generated, 1 Chemistry checked, 2 MLIP screened, 3 DFT relaxed, 4 DFT property confirmed,
    5 Experimentally tested. `stage` is the highest stage with a passing record; `records` keeps every stage's result."""
    status: str
    stage: int = Field(ge=0, le=5)
    label: str
    stages: list[str] = Field(min_length=6, max_length=6)
    next: str | None = None
    records: list[ValidationRecord]


class Cluster(Loose):
    """Candidates whose encoder latents are within the cluster cosine of a leader: alternatives for the same target."""
    id: int = Field(ge=1)
    size: int = Field(ge=1)
    leader: str
    rank: int = Field(ge=1)
    cosine_to_leader: float


class Provenance(Loose):
    run_id: str
    model_id: str
    mode: Literal["standard", "exploratory"]
    created: str
    backend: str | None = None
    matter_version: str | None = None
    meidnet_version: str | None = None
    git_commit: str | None = None
    model_sha256: str | None = None
    dataset_id: str | None = None
    dataset_fingerprint: str | None = None
    goal_hash: str | None = None
    project_id: str | None = None
    family: str | None = None
    variant: str | None = None


class CandidateRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow", title="MEIDNet Matter candidate record")

    schema_id: str = Field(alias="schema", pattern=r"^meidnet-matter/candidate-record/1$")
    candidate_id: str
    run_id: str
    index: int
    target_index: int | None = None
    round: int | None = None
    identity: Identity
    structure: StructureBlock
    properties: dict[str, PropertyEvidence]
    domain: DomainBlock
    constraints: list[RuleResult]
    rules_passed: int
    rules_total: int
    model_evidence: ModelEvidence
    novelty: Novelty
    stability: Validation
    cluster: Cluster | None = None
    flags: list[str]
    mode: Literal["standard", "exploratory"]
    why: str
    engine: dict
    provenance: Provenance


def json_schema() -> dict:
    s = CandidateRecord.model_json_schema(by_alias=True)
    s["$id"] = SCHEMA_ID
    s["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return s


TARGETS_CSV_COLUMNS = {
    "file": "the CIF file name inside cifs/ of the run bundle (<candidate_id>.cif)",
    "candidate_id": "the candidate id",
    "formula": "the formula",
    "<property>_target": "the point target the search was given (a value objective; empty for a range, a bound or an untargeted property)",
    "<property>_min": "the lower edge of the requested window (value - tolerance, the range's low end, or an 'at least' bound)",
    "<property>_max": "the upper edge of the requested window (value + tolerance, the range's high end, or an 'at most' bound)",
    "<property>_value": "the value Matter reports for the structure: the search's prediction in this version",
    "source": "how the value was obtained: 'predicted (<model_id>)' in this version; 'dft' or 'experiment' once validated",
    "validation_stage": "the highest validation stage reached (0 Generated … 5 Experimentally tested)",
    "cluster": "the cluster id of the candidate (empty when no latent was recorded)",
}
