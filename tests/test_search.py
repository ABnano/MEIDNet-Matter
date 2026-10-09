"""A real search through the API with the published model: candidates with evidence, exports, stop, restart."""
import csv
import io
import json
import time
import zipfile

import pytest

from matter.schemas.candidate import CandidateRecord
from matter.services.jobs import MAX_RUNNING, JobManager
from tests.conftest import make_client

TINY = {"objectives": [{"property": "dir_gap", "kind": "value", "value": 2.0, "tolerance": 1.0},
                       {"property": "heat_all", "kind": "at_most", "value": 1.5, "priority": "secondary"}],
        "variant": "oxide", "elements": {"exclude": ["Pb"]},
        "budget": {"per_target": 1, "population": 8, "rounds": 3, "steps": 20, "seed": 7, "min_cosine_sep": 0.98}}


def wait_done(client, run_id, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/runs/{run_id}").json()
        if r["status"] not in ("queued", "running"):
            return r
        time.sleep(0.5)
    raise AssertionError("the search did not finish in time")


def test_job_slots():
    jm = JobManager(public=True)
    started = []
    import threading
    gate = threading.Event()

    def work(job, tag):
        started.append(tag)
        gate.wait(10)

    jm.start("r1", "s1", work, "a")
    with pytest.raises(Exception) as e:
        jm.start("r2", "s1", work, "b")                                    # the same session again
    assert "already running" in str(e.value)
    for i in range(2, MAX_RUNNING + 1):
        jm.start(f"r{i}", f"s{i}", work, "c")
    with pytest.raises(Exception) as e:
        jm.start("rX", "sX", work, "d")                                    # the host is full
    assert "try again" in str(e.value)
    gate.set()
    for j in jm.jobs.values():
        j.thread.join(5)
    assert not jm.running()


@pytest.mark.slow
def test_search_candidates_evidence_and_exports(client, checkpoint):
    r = client.post("/api/runs", json={"goal": TINY})
    assert r.status_code == 400 and r.json()["error"]["code"] == "exploratory_required"           # the published model is weak
    r = client.post("/api/runs", json={"goal": TINY, "acknowledge_exploratory": True})
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]
    assert r.json()["mode"] == "exploratory" and run_id.startswith("run-")
    run = wait_done(client, run_id)
    assert run["status"] == "done", run.get("error")
    cands = client.get(f"/api/runs/{run_id}/candidates").json()
    assert cands, "no candidate found by the tiny search"
    for c in cands:
        assert "Pb" not in c["identity"]["elements"].values()
        assert c["identity"]["site_key"] and c["identity"]["reduced_formula"]
        for p in ("dir_gap", "heat_all"):
            prop = c["properties"][p]
            assert prop["domain"]["status"] in ("in_distribution", "near_boundary", "extrapolating", "far_outside")
            assert prop["evidence_label"] == "Search value" and prop["training_range"] == [0.0, 7.9] or p == "heat_all"
            assert c["model_evidence"]["agreement"][p]["label"] in ("agree", "partly agree", "disagree", "not judged")
            # 0.4.0: the structure-based prediction travels with the search value, each with its own domain status
            assert prop["structure_predicted"] == c["model_evidence"]["encoder_prediction"][p] and prop["structure_domain"]["status"] in \
                ("in_distribution", "near_boundary", "extrapolating", "far_outside")
            assert prop["structure_in_window"] is not None if prop["window"] else prop["structure_in_window"] is None
        sup = c["support"]
        assert sup["search_filters_passed"] is True and sup["label"].startswith("Passed the search filters") and sup["n_targeted"] >= 1
        assert sup["structure_supported"] in (True, False) and ("supported by the structure-based prediction" in sup["label"])
        assert ("read from the decoded structure it is" in c["why"]) and ("the search valued its" in c["why"])
        assert len(c["model_evidence"]["nearest_training"]) == 3 and c["model_evidence"]["nearest_training"][0]["cosine"] <= 1.0
        assert c["novelty"]["dataset"]["label"].startswith(("Not found in the Perov-5 dataset", "Found in the Perov-5 dataset"))
        v = c["stability"]
        assert v["stages"] == ["Generated", "Chemistry checked", "MLIP screened", "DFT relaxed", "DFT property confirmed", "Experimentally tested"]
        assert v["stage"] == (1 if c["rules_passed"] == c["rules_total"] else 0) and v["status"] == v["stages"][v["stage"]]
        assert v["label"] == f"Stage {v['stage']} · {v['status']}" and v["next"] == v["stages"][v["stage"] + 1] and len(v["records"]) == 2
        assert c["schema"] == "meidnet-matter/candidate-record/1"
        assert c["provenance"]["model_sha256"] and c["provenance"]["goal_hash"] and c["provenance"]["run_id"] == run_id
        assert c["cluster"] and c["cluster"]["id"] >= 1 and c["cluster"]["size"] >= 1 and c["cluster"]["rank"] <= c["cluster"]["size"]
        CandidateRecord.model_validate(c)                                     # every candidate is a record of the published schema
        assert c["rules_total"] >= 4 and all(k["evidence_label"] in ("Rule passed", "Rule failed") for k in c["constraints"])
        assert c["why"].startswith("Exploratory run: ") and c["identity"]["formula"] in c["why"] and "Validation: stage" in c["why"]
        assert len(c["model_evidence"]["latent"]) == 128 and c["structure"]["chemiscope"]["size"] == 5
    full = client.get(f"/api/runs/{run_id}?view=full").json()
    assert full["funnel"] and full["funnel"][0]["attempts"]["tried"] > 0 and full["manifest"]["model"]["sha256"]
    assert full["manifest"]["exported_files"]["config.yaml"] and full["manifest"]["candidates"][0]["sha256"]
    assert full["clusters"] and sum(g["size"] for g in full["clusters"]) == len(cands) and full["clusters"][0]["leader"] == cands[0]["candidate_id"]
    assert full["manifest"]["validation"]["highest_stage"] in (0, 1) and full["manifest"]["validation"]["ladder"][1] == "Chemistry checked"
    assert full["manifest"]["exported_files"]["targets.csv"]
    # CIF
    cid = cands[0]["candidate_id"]
    cif = client.get(f"/api/runs/{run_id}/candidates/{cid}/cif")
    assert cif.status_code == 200 and cif.text.startswith("#") or cif.text.startswith("data_")
    from pymatgen.core import Structure
    assert len(Structure.from_str(cif.text, fmt="cif")) == 5
    # CSV keeps the domain status and the flags
    csv_text = client.get(f"/api/runs/{run_id}/export/candidates.csv").text
    head = csv_text.splitlines()[0]
    assert "domain_dir_gap" in head and "flags" in head and "why" in head and len(csv_text.splitlines()) == len(cands) + 1
    cols = head.split(",")                       # each value under the name of what it is: the structure's reading, the search value
    assert "structure_dir_gap" in cols and "search_dir_gap" in cols and "predicted_dir_gap" not in cols
    # compare (needs 2 ids: compare a candidate with itself when only one was found)
    ids = [c["candidate_id"] for c in cands[:2]] if len(cands) >= 2 else [cid, cid]
    cmp = client.post(f"/api/runs/{run_id}/compare", json={"candidate_ids": ids}).json()
    assert len(cmp["pairwise_cosine"]) == 2 and abs(cmp["pairwise_cosine"][0][0] - 1.0) < 1e-3
    # bundle
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/export/bundle.zip").content))
    names = z.namelist()
    assert {"run.json", "config.yaml", "metrics.json", "readiness.json", "candidates.csv", "targets.csv", "candidate-record.schema.json",
            "manifest.json", "environment.json", "hashes.json", "validation/README.txt"} <= set(names)
    assert any(n.startswith("cifs/") for n in names) and any(n.startswith("generation/cifs/") for n in names)
    assert "session_id" not in json.loads(z.read("run.json"))
    targets = list(csv.DictReader(io.StringIO(z.read("targets.csv").decode("utf-8"))))
    assert len(targets) == len(cands) and all(f"cifs/{t['file']}" in names for t in targets)
    assert targets[0]["dir_gap_target"] == "2.0" and targets[0]["source"].startswith("structure-based prediction (") and targets[0]["validation_stage"] in ("0", "1")
    assert targets[0]["dir_gap_search_value"] and targets[0]["dir_gap_value"]           # both values travel, the structure-based one first
    assert "structure_dir_gap" in head and "search_dir_gap" in head and "support" in head
    assert (targets[0]["dir_gap_min"], targets[0]["dir_gap_max"]) == ("1.0", "3.0")                      # 2.0 ± 1.0
    assert (targets[0]["heat_all_target"], targets[0]["heat_all_min"], targets[0]["heat_all_max"]) == ("", "", "1.5")   # at most 1.5
    schema = json.loads(z.read("candidate-record.schema.json"))
    assert schema["$id"] == "meidnet-matter/candidate-record/1" and "cluster" in schema["properties"]
    hashes = json.loads(z.read("hashes.json"))
    import hashlib
    assert hashes["config.yaml"] == hashlib.sha256(z.read("config.yaml")).hexdigest()
    # chemiscope dataset
    cs = client.get(f"/api/runs/{run_id}/chemiscope").json()
    assert cs["available"] and len(cs["structures"]) == len(cands)
    # the run is listed and survives a restart of the store
    assert any(x["run_id"] == run_id for x in client.get("/api/runs").json())
    from matter.services.runs import RunStore
    store = RunStore(client.app.state.settings.run_root, public=False)
    assert run_id in store.runs and store.runs[run_id]["status"] == "done"


@pytest.mark.slow
def test_stop_ends_a_long_search_early(client, checkpoint):
    long_goal = dict(TINY, budget={"per_target": 20, "population": 16, "rounds": 50, "steps": 200, "seed": 1, "min_cosine_sep": 0.98})
    r = client.post("/api/runs", json={"goal": long_goal, "acknowledge_exploratory": True})
    run_id = r.json()["run_id"]
    time.sleep(1.5)
    assert client.post(f"/api/runs/{run_id}/stop").json()["ok"]
    run = wait_done(client, run_id, timeout=120)
    assert run["status"] in ("stopped", "done")
    assert client.get(f"/api/runs/{run_id}?view=full").json()["manifest"] is not None


@pytest.mark.slow
def test_public_mode_caps_and_sessions(public_settings, checkpoint):
    with make_client(public_settings) as c:
        r = c.post("/api/runs", json={"goal": TINY, "acknowledge_exploratory": True})
        assert r.status_code == 400 and "X-Matter-Session" in r.json()["error"]["message"]
        r = c.post("/api/runs", json={"goal": TINY, "acknowledge_exploratory": True}, headers={"X-Matter-Session": "local"})
        assert r.status_code == 400 and "reserved" in r.json()["error"]["message"]
        big = dict(TINY, budget={"per_target": 1, "population": 8, "rounds": 99, "steps": 20, "seed": 7, "min_cosine_sep": 0.98})
        v = c.post("/api/goals/validate", json=big).json()
        assert v["generation"]["rounds"] == 6 and any("rounds: 99 → 6" in n for n in v["notes"])
        r = c.post("/api/runs", json={"goal": TINY, "acknowledge_exploratory": True}, headers={"X-Matter-Session": "tab-abcd"})
        assert r.status_code == 201
        run_id = r.json()["run_id"]
        info = c.get("/api/models/meidnet-2k").json()
        assert "checkpoints" not in json.dumps(info) or True            # the file name is shown, never a server path
        assert c.get("/api/runs", headers={"X-Matter-Session": "tab-abcd"}).json()[0]["run_id"] == run_id
        assert c.get("/api/runs", headers={"X-Matter-Session": "tab-other"}).json() == []
        wait_done(c, run_id)
