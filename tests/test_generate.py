"""Generation jobs: validation, public caps, and one short end-to-end job when the model file is present."""
import os
import time

import pytest

from tests.conftest import ROOT, make_client

MODEL = os.path.join(ROOT, "checkpoints", "mp20_wyck.pt")
needs_model = pytest.mark.skipif(not os.path.isfile(MODEL), reason="mp20_wyck.pt not fetched (scripts/fetch_assets.py --only mp20-wyck)")
H = {"X-Matter-Session": "test-session-1"}


def test_the_request_schema_is_published(client):
    s = client.get("/api/schema/generation-result").json()
    assert s["schema_id"] == "meidnet-matter/generation-result/1"
    assert "candidates" in s["properties"]


def test_requests_are_validated(client):
    r = client.post("/api/generate", json={"model_id": "mp20-wyck", "targets": [], "per_target": 3}, headers=H)
    assert r.status_code == 422
    r = client.post("/api/generate", json={"model_id": "mp20-wyck", "targets": [1.5], "exclude_elements": ["Xx"]}, headers=H)
    assert r.status_code in (422, 503)                 # unknown element, or no model file on this machine
    r = client.post("/api/generate", json={"model_id": "perov5-2k", "targets": [1.5]}, headers=H)
    assert r.status_code in (422, 404, 503)            # that model has no symmetry decoder
    r = client.post("/api/generate", json={"model_id": "mp20-wyck", "targets": [9.0]}, headers=H)
    assert r.status_code in (422, 503)                 # out of range


def test_public_mode_caps_the_request(public_settings):
    from matter.schemas.generation import GenerateRequest
    from matter.services.generation import validate_request
    with make_client(public_settings) as c:
        services = c.app.state.services
        if not services.catalog or "mp20-wyck" not in services.catalog.ids():
            pytest.skip("no manifest")
        req, notes = validate_request(GenerateRequest(model_id="mp20-wyck", targets=[0.5, 1.0, 1.5, 2.0], per_target=30, window_eV=1.5),
                                      True, services.catalog)
        assert len(req["targets"]) == 3 and req["per_target"] == 10 and req["window_eV"] == 1.0
        assert len(notes) >= 3


@needs_model
def test_a_short_job_runs_to_completion(client):
    r = client.post("/api/generate", json={"model_id": "mp20-wyck", "targets": [1.5], "per_target": 1, "oversample": 20, "seed": 1}, headers=H)
    assert r.status_code == 201, r.text
    job = r.json()["job_id"]
    for _ in range(120):
        d = client.get(f"/api/generate/{job}").json()
        if d["status"] in ("done", "stopped", "error"):
            break
        time.sleep(1)
    assert d["status"] in ("done", "stopped"), d.get("error")
    full = client.get(f"/api/generate/{job}?view=full").json()
    assert full["schema"] == "meidnet-matter/generation-result/1"
    for c in full["candidates"]:
        assert c["label_structure_eV"] is not None                 # the label is read from the returned structure
        assert c["stability"]["status"] == "not assessed"
        cif = client.get(f"/api/generate/{job}/candidates/{c['candidate_id']}/cif")
        assert cif.status_code == 200 and "_cell_length_a" in cif.text
    assert client.get(f"/api/generate/{job}/export/cifs.zip").status_code == 200
    assert client.get(f"/api/generate/{job}", headers=H).status_code == 200
