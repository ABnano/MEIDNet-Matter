"""The validation ladder, the candidate clusters, targets.csv and the versioned candidate-record schema."""
import csv
import io

import numpy as np

from matter.schemas.candidate import SCHEMA_ID, TARGETS_CSV_COLUMNS, json_schema
from matter.services.enrichment import CLUSTER_COSINE, VALIDATION_STAGES, assign_clusters, validation_block
from matter.services.export import targets_csv


def _cand(cid, z, formula="SrTiO3", stage_pass=(8, 8)):
    return {"candidate_id": cid, "identity": {"formula": formula, "model_id": "meidnet-2k"},
            "model_evidence": {"latent": (list(z) if z is not None else None)},
            "properties": {"dir_gap": {"target": 2.0, "predicted": 2.1}, "heat_all": {"target": None, "predicted": -0.5}},
            "stability": validation_block(*stage_pass)}


def test_validation_ladder_has_six_stages_and_two_records_in_this_version():
    assert VALIDATION_STAGES == ["Generated", "Chemistry checked", "MLIP screened", "DFT relaxed", "DFT property confirmed", "Experimentally tested"]
    v = validation_block(8, 8)
    assert v["stage"] == 1 and v["status"] == "Chemistry checked" and v["label"] == "Stage 1 · Chemistry checked" and v["next"] == "MLIP screened"
    assert [r["stage"] for r in v["records"]] == [0, 1] and v["records"][1]["passed"] is True and "8 of 8" in v["records"][1]["outcome"]
    v = validation_block(7, 8)
    assert v["stage"] == 0 and v["status"] == "Generated" and v["next"] == "Chemistry checked" and v["records"][1]["passed"] is False
    v = validation_block(0, 0)
    assert v["stage"] == 0 and len(v["records"]) == 1


def test_assign_clusters_groups_close_latents_and_keeps_order():
    a = np.array([1.0, 0.0, 0.0]); b = np.array([0.98, 0.15, 0.0]); c = np.array([0.0, 1.0, 0.0]); d = np.array([0.0, 0.99, 0.1])
    b /= np.linalg.norm(b); d /= np.linalg.norm(d)
    assert float(a @ b) >= CLUSTER_COSINE and float(c @ d) >= CLUSTER_COSINE and float(a @ c) < CLUSTER_COSINE
    cands = [_cand("r-001", a), _cand("r-002", b, "BaTiO3"), _cand("r-003", c, "CaTiO3"), _cand("r-004", d, "KTaO3"), _cand("r-005", None, "NaNbO3")]
    groups = assign_clusters(cands)
    assert [g["id"] for g in groups] == [1, 2] and [g["size"] for g in groups] == [2, 2]
    assert groups[0]["leader"] == "r-001" and groups[0]["members"] == ["r-001", "r-002"] and groups[0]["formulas"] == ["SrTiO3", "BaTiO3"]
    assert groups[1]["leader"] == "r-003" and groups[1]["members"] == ["r-003", "r-004"]
    assert cands[0]["cluster"] == {"id": 1, "leader": "r-001", "rank": 1, "cosine_to_leader": 1.0, "size": 2}
    assert cands[1]["cluster"]["id"] == 1 and cands[1]["cluster"]["rank"] == 2 and 0.9 <= cands[1]["cluster"]["cosine_to_leader"] < 1.0
    assert cands[3]["cluster"]["id"] == 2 and cands[4]["cluster"] is None
    assert assign_clusters([]) == []


def test_targets_csv_matches_the_bundle_layout():
    cands = [_cand("r-001", [1.0, 0.0]), _cand("r-002", [0.0, 1.0], "BaTiO3", (7, 8))]
    assign_clusters(cands)
    goal = {"objectives": [{"property": "dir_gap", "kind": "value", "value": 2.0, "tolerance": 0.3}, {"property": "heat_all", "kind": "at_most", "value": 1.0}]}
    rows = list(csv.DictReader(io.StringIO(targets_csv({"candidates": cands, "goal": goal}))))
    assert [r["file"] for r in rows] == ["r-001.cif", "r-002.cif"]
    assert rows[0]["dir_gap_target"] == "2.0" and rows[0]["dir_gap_min"] == "1.7" and rows[0]["dir_gap_max"] == "2.3" and rows[0]["dir_gap_value"] == "2.1"
    assert rows[0]["heat_all_target"] == "" and rows[0]["heat_all_min"] == "" and rows[0]["heat_all_max"] == "1.0" and rows[0]["heat_all_value"] == "-0.5"
    assert rows[0]["source"] == "search value (meidnet-2k)" and rows[0]["validation_stage"] == "1" and rows[1]["validation_stage"] == "0"
    assert rows[0]["dir_gap_search_value"] == "2.1"                       # without a structure-based value the search value is reported, and said so
    assert rows[0]["cluster"] == "1" and rows[1]["cluster"] == "2"
    assert targets_csv({"candidates": []}).splitlines() == ["file,candidate_id,formula,source,validation_stage,cluster"]
    assert set(TARGETS_CSV_COLUMNS) >= {"<property>_search_value"}
    assert set(TARGETS_CSV_COLUMNS) >= {"file", "<property>_target", "<property>_min", "<property>_max", "<property>_value", "source"}


def test_request_of_each_objective_kind():
    from matter.services.export import request_of
    p = {"target": 2.0, "window": [1.1, 2.9]}
    assert request_of(None, p) == (None, None, None)
    assert request_of({"kind": "value", "tolerance": 0.5}, p) == (2.0, 1.5, 2.5)
    assert request_of({"kind": "value", "tolerance": None}, p) == (2.0, None, None)
    assert request_of({"kind": "values", "tolerance": 0.25}, p) == (2.0, 1.75, 2.25)
    assert request_of({"kind": "range", "low": 1.0, "high": 3.0}, p) == (None, 1.0, 3.0)
    assert request_of({"kind": "at_least", "value": 1.2}, p) == (None, 1.2, None)
    assert request_of({"kind": "at_most", "value": 0.0}, p) == (None, None, 0.0)
    assert request_of({"kind": "maximize"}, {"target": None, "window": [5.1, None]}) == (None, 5.1, None)


def test_candidate_record_schema_is_versioned():
    s = json_schema()
    assert s["$id"] == SCHEMA_ID == "meidnet-matter/candidate-record/1"
    assert s["properties"]["schema"]["pattern"].endswith("candidate-record/1$")
    for key in ("identity", "structure", "properties", "constraints", "model_evidence", "novelty", "stability", "cluster", "provenance", "why"):
        assert key in s["properties"], key
    assert "Validation" in s["$defs"] and s["$defs"]["Validation"]["properties"]["stages"]["minItems"] == 6


def test_schema_routes(client):
    r = client.get("/api/schema/candidate-record")
    assert r.status_code == 200
    body = r.json()
    assert body["schema"] == SCHEMA_ID and body["json_schema"]["$id"] == SCHEMA_ID and body["validation_stages"] == VALIDATION_STAGES
    assert body["cluster_cosine"] == CLUSTER_COSINE
    r = client.get("/api/schema/targets-csv")
    assert r.status_code == 200 and "file" in r.json()["columns"] and "meidnet score" in r.json()["usage"]
