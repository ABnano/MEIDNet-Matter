"""The static mirror's pre-rendered API (scripts/build_mirror.py): every read the site's pages make is a file, the files
are what the application serves, and nothing in them sends a visitor back to a server path the mirror does not have."""
import importlib.util
import json
import os

import pytest

from tests.conftest import ROOT

pytest.importorskip("meidnet_eval")


def _builder():
    spec = importlib.util.spec_from_file_location("build_mirror", os.path.join(ROOT, "scripts", "build_mirror.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mirror(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("mirror"))
    summary = _builder().prerender(out, log=lambda *a: None)
    return out, summary


def _json(out, rel):
    with open(os.path.join(out, "static-api", rel), encoding="utf-8") as f:
        return json.load(f)


def test_every_read_the_pages_make_is_a_file(mirror):
    out, summary = mirror
    assert summary["files"] > 100
    blocks = _json(out, "api/pipeline/blocks.json")
    assert [b["id"] for b in blocks["blocks"]] == [f"S{i}" for i in range(10)]
    for b in blocks["blocks"]:
        assert _json(out, f"api/pipeline/blocks/{b['id']}.json")["id"] == b["id"]
    for c in _json(out, "api/pipeline/components.json"):
        assert os.path.getsize(os.path.join(out, "static-api", "api", "pipeline", "components", c["file"])) == c["bytes"]
    for s in _json(out, "api/studies.json")["studies"]:
        study = _json(out, f"api/studies/{s['id']}.json")
        for name, meta in (study.get("files") or {}).items():
            assert os.path.getsize(os.path.join(out, "static-api", "api", "studies", s["id"], "files", name)) == meta["bytes"], name


def test_the_mirror_holds_no_model_files_and_says_where_they_are(mirror):
    out, _ = mirror
    for c in _json(out, "api/checkpoints.json")["checkpoints"]:
        assert c["download_url"] is None and c["available"] is False
        one = _json(out, f"api/checkpoints/{c['id']}.json")
        assert one["download_url"] is None


def test_the_names_match_the_frontends_mapping():
    b = _builder()
    assert b.target("/o", "/api/studies/mp20", "json") == os.path.join("/o", "static-api", "api/studies/mp20.json")
    assert b.target("/o", "/api/generate/x?view=full", "json") == os.path.join("/o", "static-api", "api/generate/x@view=full.json")
    with pytest.raises(SystemExit):
        b.target("/o", "/api/studies/a#b", "raw")
