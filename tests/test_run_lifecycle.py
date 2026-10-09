"""A run or a generation job that is gone says why: 410 when this server removed it (an hour idle), 404 with the reason
when it was never here or the server restarted; a refused search leaves no record behind."""
import time

import pytest

from matter.api.errors import ApiError
from tests.conftest import make_client

H = {"X-Matter-Session": "lifecycle-tab-1"}
GOAL = {"objectives": [{"property": "dir_gap", "kind": "value", "value": 2.0, "tolerance": 1.0}], "variant": "oxide",
        "budget": {"per_target": 1, "population": 8, "rounds": 1, "steps": 20, "seed": 1, "min_cosine_sep": 0.98}}


def _old_run(services, run_id="run-lifecycle"):
    run = {"run_id": run_id, "session_id": H["X-Matter-Session"], "status": "done", "created": "2026-10-09T00:00:00",
           "candidates": [], "log": [], "notes": [], "progress": {}, "last_access": time.time() - 7200}
    services.runs.runs[run_id] = run
    services.runs.save(run)
    return run_id


def test_an_unknown_run_says_why(public_settings):
    with make_client(public_settings) as c:
        r = c.get("/api/runs/run-neverhere", headers=H)
        assert r.status_code == 404 and r.json()["error"]["code"] == "run_not_found"
        assert "hour" in r.json()["error"]["message"] and "restart" in r.json()["error"]["message"]
        r = c.get("/api/generate/gen-neverhere", headers=H)
        assert r.status_code == 404 and r.json()["error"]["code"] == "run_not_found" and "generation job" in r.json()["error"]["message"]


def test_a_removed_run_answers_410(public_settings):
    with make_client(public_settings) as c:
        services = c.app.state.services
        run_id = _old_run(services)
        assert services.runs.cleanup() == 1
        for path in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/candidates", f"/api/runs/{run_id}/export/candidates.csv"):
            r = c.get(path, headers=H)
            assert r.status_code == 410 and r.json()["error"]["code"] == "gone", path


def test_a_refused_search_leaves_no_record(public_settings, checkpoint, monkeypatch):
    with make_client(public_settings) as c:
        services = c.app.state.services

        def busy(*args, **kwargs):
            raise ApiError("busy", "this session is already running a search", status=409, retry_after_s=10)
        monkeypatch.setattr(services.jobs, "start", busy)
        r = c.post("/api/runs", json={"goal": GOAL, "acknowledge_exploratory": True}, headers=H)
        assert r.status_code == 409
        assert not services.runs.runs, "a refused search must not leave a queued record"
        assert c.get("/api/runs", headers=H).json() == []
