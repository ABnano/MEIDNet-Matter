"""The version is declared once and the health and version routes answer without a model."""
import os
import re

from matter import __version__
from tests.conftest import ROOT, make_client


def test_health_answers_without_a_model(settings, tmp_path):
    settings.checkpoints_dir = str(tmp_path / "no-checkpoints")           # nothing to load: the API still answers
    with make_client(settings) as c:
        r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"] == __version__ and body["mode"] == "local"
    assert body["model_loaded"] is False
    assert re.match(r"^\d+\.\d+\.\d+", body["meidnet_version"])


def test_health_reports_the_loaded_model(client, checkpoint):
    assert client.get("/health").json()["model_loaded"] is True


def test_version_route_reports_the_engine_and_the_commit(client):
    body = client.get("/api/version").json()
    assert body["matter"] == __version__
    assert body["meidnet"] == body["meidnet_installed"] or body["meidnet_installed"] is None
    assert body["git_sha"] and body["mode"] == "local"


def test_the_version_is_the_same_everywhere():
    with open(os.path.join(ROOT, "CITATION.cff"), encoding="utf-8") as f:
        assert f'version: "{__version__}"' in f.read()
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    assert "## [Unreleased]" in text or f"## [{__version__}]" in text


def test_unknown_api_route_is_a_json_404(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
