"""On a shared host a generation job or a search belongs to the session that started it: only that session may stop
it, and the session id is never served or exported. Records are placed in the stores directly, so no model is needed."""
import io
import json
import os
import zipfile

import pytest

from tests.conftest import make_client

OWNER = {"X-Matter-Session": "owner-tab-1"}
OTHER = {"X-Matter-Session": "other-tab-2"}
REQUEST = {"model_id": "mp20-wyck", "targets": [1.0], "per_target": 1, "window_eV": 0.5, "require_anion": True,
           "exclude_elements": [], "seed": 1}


def _job(services, status="done"):
    if services.generations is None:
        pytest.skip("no checkpoint manifest")
    job = services.generations.create(OWNER["X-Matter-Session"], dict(REQUEST), [], {}, {}, 10)
    job["status"] = status
    services.generations.save(job)
    with open(os.path.join(services.generations.path(job["job_id"]), "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f)
    return job


def _run(services, status="done"):
    run = {"run_id": "run-sessiontest", "session_id": OWNER["X-Matter-Session"], "status": status, "created": "2026-10-09T00:00:00",
           "candidates": [], "log": [], "notes": [], "progress": {}}
    services.runs.runs[run["run_id"]] = run
    services.runs.save(run)
    return run


def test_on_a_shared_host_only_the_owner_stops_a_job(public_settings):
    with make_client(public_settings) as c:
        job_id = _job(c.app.state.services, status="running")["job_id"]
        r = c.post(f"/api/generate/{job_id}/stop", json={}, headers=OTHER)
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
        assert c.post(f"/api/generate/{job_id}/stop", json={}).status_code == 400          # no session header at all
        assert c.post(f"/api/generate/{job_id}/stop", json={}, headers=OWNER).json()["ok"]


def test_on_a_shared_host_only_the_owner_stops_a_search(public_settings):
    with make_client(public_settings) as c:
        run_id = _run(c.app.state.services, status="running")["run_id"]
        assert c.post(f"/api/runs/{run_id}/stop", headers=OTHER).status_code == 403
        assert c.post(f"/api/runs/{run_id}/stop", headers=OWNER).json()["ok"]


def test_locally_stop_needs_no_session(client):
    job_id = _job(client.app.state.services, status="running")["job_id"]
    assert client.post(f"/api/generate/{job_id}/stop", json={}).json()["ok"]
    run_id = _run(client.app.state.services, status="running")["run_id"]
    assert client.post(f"/api/runs/{run_id}/stop").json()["ok"]


def test_the_session_id_is_never_served_or_exported(public_settings):
    with make_client(public_settings) as c:
        services = c.app.state.services
        job_id = _job(services)["job_id"]
        run_id = _run(services)["run_id"]
        assert "session_id" not in c.get(f"/api/generate/{job_id}?view=full", headers=OWNER).json()
        assert "session_id" not in c.get(f"/api/runs/{run_id}?view=full", headers=OWNER).json()
        for item in c.get("/api/generate", headers=OWNER).json() + c.get("/api/runs", headers=OWNER).json():
            assert "session_id" not in item
        z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/generate/{job_id}/export/cifs.zip", headers=OWNER).content))
        assert {"job.json", "run.json"} <= set(z.namelist())
        for name in ("job.json", "run.json"):
            record = json.loads(z.read(name))
            assert record["job_id"] == job_id and "session_id" not in record
