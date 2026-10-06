"""The committed demo artefacts are complete, small, consistent with each other and with the model files."""
import gzip
import json
import os

import numpy as np
import pytest

from tests.conftest import DEMO_DIR, ROOT

MAX_BYTES = 6 * 1024 * 1024


def _json(name):
    with open(os.path.join(DEMO_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def _size(folder):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(folder) for f in fs)


pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(DEMO_DIR, "project.json")), reason="demo artefacts not built")


def test_artefacts_are_present_small_and_consistent():
    assert _size(DEMO_DIR) <= MAX_BYTES
    project, models, dataset, manifest = _json("project.json"), _json("models.json"), _json("dataset.json"), _json("manifest.json")
    assert project["project_id"] == "perov5-demo" and project["default_model"] in project["models"]
    assert dataset["limit"] is None and manifest["limit"] is None                       # the full dataset, not a smoke build
    assert dataset["rows"]["all"] == dataset["rows"]["train"] + dataset["rows"]["val"] + dataset["rows"]["test"] == 18928
    assert dataset["fingerprint"]["combined"] == manifest["dataset_fingerprint"]
    ids = {m["model_id"] for m in models}
    assert set(project["models"]) <= ids and set(manifest["models"]) == ids
    for m in models:
        r = _json(os.path.join("readiness", f"{m['model_id']}.json"))
        assert r["checkpoint_sha256"] == m["sha256"] == manifest["models"][m["model_id"]]
        assert r["columns"] == [p["column"] for p in m["properties"]] == dataset["columns"][3:]
        assert r["n"] == dataset["rows"]["test"]
        for c in r["columns"]:
            assert f"mae_{c}" in r["evaluation"]["property_prediction"] and f"knn_mae_{c}" in r["evaluation"]["representation"]
        assert 0 <= r["evaluation"]["representation"]["reverse_top1"] <= 1
        if m["trained_on"] == "all":
            assert any("training data" in c for c in r["caveats"])
        assert m["property_ranges"].keys() == set(r["columns"])
        for c, (lo, hi) in m["property_ranges"].items():                               # the model's ranges are the train split's
            assert abs(lo - dataset["properties"][c]["min"]) < 1e-6 and abs(hi - dataset["properties"][c]["max"]) < 1e-6
        assert "description" in m and "checkpoints" not in m["description"] and os.sep not in m["description"]
    assert set(project["default_goal"]["objectives"][0]) >= {"property", "kind", "value"}
    assert project["default_goal"]["variant"] == "oxide" and "Pb" in project["default_goal"]["elements"]["exclude"]


def test_latents_and_materials_match_the_dataset():
    dataset, models = _json("dataset.json"), _json("models.json")
    with gzip.open(os.path.join(DEMO_DIR, "materials.csv.gz"), "rt", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        rows = [line.rstrip("\n").split(",") for line in f]
    assert header[:5] == ["material_id", "split", "formula", "reduced_formula", "site_key"]
    assert len(rows) == dataset["rows"]["all"]
    train_ids = [r[0] for r in rows if r[1] == "train"]
    assert len(train_ids) == dataset["rows"]["train"]
    assert sum(1 for r in rows if r[4]) == dataset["family_like_rows"]["all"]
    for m in models:
        if not m.get("latents_file"):
            continue
        z = np.load(os.path.join(DEMO_DIR, m["latents_file"]))
        assert z["z"].dtype == np.float16 and z["z"].shape == (len(train_ids), m["latent_dim"])
        assert list(z["material_id"]) == train_ids
        assert list(z["columns"]) == [p["column"] for p in m["properties"]]
        norms = np.linalg.norm(z["z"].astype(np.float32), axis=1)
        assert np.allclose(norms, 1.0, atol=5e-3)


def test_dataset_facts_the_product_relies_on():
    d = _json("dataset.json")
    gap = d["properties"]["dir_gap"]
    assert gap["zero_share"] > 0.9 and "nonzero" in gap                                  # zero-inflated band gap
    halide = d["family_coverage"]["perovskite_abx3"]["halide"]["X"]
    assert set(halide["absent"]) == {"Cl", "Br", "I"} and halide["present"] == ["F"]       # Perov-5 has no Cl/Br/I
    oxide = d["family_coverage"]["perovskite_abx3"]["oxide"]["X"]
    assert oxide["absent"] == []
    assert d["profiles"]["all"]["share_with_10_or_more_pct"] > 80                        # one-to-many is the rule, not the exception
    grid = d["ambiguity_grid"]
    assert len(grid["n_box"]) == len(grid["axes"][grid["columns"][0]]) and max(map(max, grid["n_box"])) > 100


@pytest.mark.slow
def test_a_rebuilt_subset_is_byte_identical(tmp_path, checkpoint):
    """Determinism: the same inputs give the same bytes (so a rebuild never churns the committed files)."""
    from matter.demo_build import build
    data = os.path.join(ROOT, "data", "perov5")
    if not os.path.exists(os.path.join(data, "train.csv")):
        pytest.skip("Perov-5 CSVs not downloaded")
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        build(data, {"meidnet-2k": checkpoint}, str(out), skip_recoverability=True, limit=120, log=lambda *_: None)
    for name in ("dataset.json", "models.json", "project.json", "materials.csv.gz", "latents_train.meidnet-2k.npz", "readiness/meidnet-2k.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name
