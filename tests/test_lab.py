"""Explore and Train Lite (0.10.0), through the routes and through the Python client routed in-process."""
import csv
import io
import os
import time

import pytest

from tests.conftest import DEMO_DIR, make_client

H = {"X-Matter-Session": "lab-tab-1"}
needs_assets = pytest.mark.skipif(not os.path.isfile(os.path.join(DEMO_DIR, "trainlite", "subset.npz")), reason="the demo ships no Train Lite subset")


def _client_for(test_client):
    """A Matter client whose requests go through the application in-process."""
    from matter.client import Matter

    def transport(method, url, body, headers):
        path = url[len("http://testserver"):]
        r = test_client.request(method, path, content=body, headers=headers)
        return r.status_code, r.content, dict(r.headers)
    return Matter("http://testserver", session="lab-py-1", transport=transport)


@needs_assets
def test_explore_serves_the_map_and_one_material_with_its_cell_and_neighbours(client):
    payload = client.get("/api/explore/perov5-demo").json()
    assert payload["schema"] == "meidnet-matter/explore/1" and payload["n"] == len(payload["points"]) > 1000
    cols = payload["columns"]
    row = dict(zip(cols, payload["points"][0]))
    assert {"material_id", "formula", "x", "y", "dir_gap", "heat_all", "site_key"} <= set(row)
    m = client.get(f"/api/explore/perov5-demo/materials/{row['material_id']}").json()
    assert m["formula"] == row["formula"] and m["cell"] and len(m["cell"]["sites"]) == 5 and len(m["cell"]["lattice"]) == 3
    assert m["neighbours"] and all(n["material_id"] != row["material_id"] for n in m["neighbours"])
    assert m["neighbours"][0]["cosine"] <= 1.0001 and m["encoder_prediction"] and "dir_gap" in m["encoder_prediction"]
    assert client.get("/api/explore/perov5-demo/materials/nope").status_code == 404
    assert client.get("/api/explore/other/materials/x").status_code == 404


@needs_assets
def test_train_options_describe_the_fixed_experiment(client):
    o = client.get("/api/train/options").json()
    assert o["available"] and o["epochs"] == [10, 20, 50] and o["subset"]["train"] > 0 and o["subset"]["val"] > 0
    assert "val_mae" in o["full_model"] and o["full_model"]["model_id"] and o["limits"]["seconds"] > 0
    est = [o["estimated_seconds"][str(e)] for e in o["epochs"]]          # measured on the public server: 23, 52, 133 s
    assert est == sorted(est) and est[-1] < o["limits"]["seconds"]


@needs_assets
def test_a_training_runs_measures_and_can_be_downloaded(client):
    r = client.post("/api/train", json={"epochs": 7}, headers=H)
    assert r.status_code == 422                                   # only the three options
    r = client.post("/api/train", json={"epochs": 10, "seed": 3}, headers=H)
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]
    assert job_id.startswith("lite-")
    for _ in range(300):
        j = client.get(f"/api/train/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            break
        time.sleep(1)
    assert j["status"] == "done", j.get("error")
    assert len(j["history"]) == 10 and j["history"][-1]["epoch"] == 10 and "dir_gap" in j["history"][-1]["val_mae"]
    res = j["result"]
    assert res["epochs_run"] == 10 and res["n_val"] > 0 and set(res["val"]["mae"]) == {"heat_all", "dir_gap"}
    assert res["against_spread"]["dir_gap"]["full_model_mae"] > 0 and res["map"]["points"] and len(res["predictions"]["rows"]) == res["n_val"]
    assert "does not drive generation" in res["what_this_is"]
    full = client.get(f"/api/train/{job_id}?view=full", headers=H).json()
    assert "session_id" not in full and full["provenance"]["meidnet_version"]
    assert client.get(f"/api/train/{job_id}/model.pt").status_code == 200
    cfg = client.get(f"/api/train/{job_id}/config.yaml").text
    assert "epochs: 10" in cfg and "seed: 3" in cfg
    rows = list(csv.DictReader(io.StringIO(client.get(f"/api/train/{job_id}/predictions.csv").text)))
    assert len(rows) == res["n_val"] and {"reference_dir_gap", "predicted_dir_gap"} <= set(rows[0])
    assert any(t["job_id"] == job_id for t in client.get("/api/train", headers=H).json())
    # the saved model loads with the engine and reads the properties it was trained on
    from meidnet.checkpoint import load_checkpoint
    lm = load_checkpoint(os.path.join(client.app.state.services.trainings.path(job_id), "model.pt"), device="cpu")
    assert list(lm.stats.columns) == ["heat_all", "dir_gap"] and lm.model.max_sites == 5


def test_the_python_client_speaks_to_the_server(client):
    m = _client_for(client)
    assert m.health()["version"] and m.project()["project_id"] == "perov5-demo"
    assert any(s["id"] == "mp20" for s in m.studies()) and m.study("mp20")["accepted"]
    assert m.blocks()["blocks"] and m.checkpoints()
    from matter.client import MatterError
    with pytest.raises(MatterError) as e:
        m.run("run-none")
    assert e.value.status == 404 and e.value.code == "run_not_found"


@needs_assets
def test_the_python_client_explores_and_trains(client):
    m = _client_for(client)
    pts = m.explore()
    assert len(pts) > 1000 and {"material_id", "formula", "x", "y", "dir_gap"} <= set(pts[0])
    d = m.material(pts[0]["material_id"], k=3)
    assert d["cell"] and len(d["neighbours"]) == 3
    assert m.train_options()["available"]
    job = m.wait(m.train(epochs=10, seed=1), timeout=600, every=1)
    assert job["status"] == "done" and job["result"]["epochs_run"] == 10
    assert m.urls.train_model(job["job_id"]).endswith(f"/api/train/{job['job_id']}/model.pt")
