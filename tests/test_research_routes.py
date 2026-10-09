"""The research routes: the vendored engine, the pipeline blocks and their sources, the studies and the checkpoints."""
import json
import os
import re

import pytest

from tests.conftest import ROOT, make_client

RESEARCH = os.path.join(ROOT, "examples", "research")
MANIFEST = os.path.join(ROOT, "checkpoints", "manifest.json")
needs_artefacts = pytest.mark.skipif(not os.path.isfile(os.path.join(RESEARCH, "studies", "index.json")),
                                     reason="research artefacts not built (scripts/build_studies.py)")
FORBIDDEN = re.compile(r"honest", re.I)


def test_the_engine_snapshot_is_the_one_matter_imports():
    import meidnet
    import meidnet.symmetry  # noqa: F401  the symmetry decoder exists only in the snapshot
    from meidnet_eval import stages
    assert meidnet.__version__.startswith("2.4.0")
    assert stages.validate(verbose=False) == []
    import importlib.resources as ir
    assert (ir.files("meidnet") / "element_features_cgcnn.json").is_file()


def test_blocks_payload_has_ten_blocks_and_no_published_column(client):
    r = client.get("/api/pipeline/blocks")
    assert r.status_code == 200
    d = r.json()
    assert [b["id"] for b in d["blocks"]] == [f"S{i}" for i in range(10)]
    assert sum(len(b["metrics"]) for b in d["blocks"]) >= 37
    # the home page's block x dataset matrix: every executed study has a verdict for every block it ran
    assert set(d["dataset_verdicts"]) == {"perov5", "mp-perovskites", "user-246", "mp20", "jarvis-dp"}
    assert all(d["dataset_verdicts"][k].get("S1") for k in d["dataset_verdicts"]), d["dataset_verdicts"]
    assert "published" not in d["configs"]
    assert not FORBIDDEN.search(json.dumps(d))
    r = client.get("/api/pipeline/blocks/s6")
    assert r.status_code == 200 and r.json()["id"] == "S6"
    assert client.get("/api/pipeline/blocks/S99").status_code == 404


def test_component_sources_are_served_from_an_allowlist(client):
    files = client.get("/api/pipeline/components").json()
    names = {f["file"] for f in files}
    assert "stages.py" in names and "conditional_generate.py" in names
    r = client.get("/api/pipeline/components/stages.py")
    assert r.status_code == 200 and "def export_blocks" in r.text
    assert r.headers["x-matter-sha256"] == next(f["sha256"] for f in files if f["file"] == "stages.py")
    for bad in ("..%2Fsettings.py", "__init__.py", "stages", "x.txt", "%2Fetc%2Fpasswd"):
        assert client.get(f"/api/pipeline/components/{bad}").status_code == 404, bad
    for f in files:
        assert not FORBIDDEN.search(client.get(f"/api/pipeline/components/{f['file']}").text), f["file"]


@needs_artefacts
def test_studies_are_served_and_the_upload_study_carries_aggregates_only(client):
    idx = client.get("/api/studies").json()["studies"]
    assert [s["id"] for s in sorted(idx, key=lambda s: s["order"])] == ["perov5", "mp-perovskites", "user-246", "mp20", "jarvis-dp"]
    for s in idx:
        d = client.get(f"/api/studies/{s['id']}").json()
        assert d["schema"] == "meidnet-matter/study/1" and d["verdicts"]
        assert not FORBIDDEN.search(json.dumps(d)), s["id"]
    u = json.dumps(client.get("/api/studies/user-246").json()).lower()
    for forbidden in ('"cif"', '"formula"', '"candidates"'):
        assert forbidden not in u
    mp20 = client.get("/api/studies/mp20").json()
    assert len(mp20["accepted"]) == mp20["calibration"]["funnel"]["final"] == 7
    from pymatgen.core import Structure                           # every accepted cell is still a crystal (contact test)
    from meidnet_eval.d1_mlip_check import COLLAPSED, contact_ratio
    for a in mp20["accepted"]:
        cif = client.get(f"/api/studies/mp20/files/{a['file']}").text
        assert contact_ratio(Structure.from_str(cif, fmt="cif")) >= COLLAPSED, a["formula"]
    dp = client.get("/api/studies/jarvis-dp").json()       # the case study of several routes: every structure served, every route counted
    assert dp["routes"] and dp["stability"]["n"] > 0 and len(dp["accepted"]) == sum(dp["accepted_classes"].values())
    for a in dp["accepted"]:
        r = client.get(f"/api/studies/jarvis-dp/files/{a['file']}")
        assert r.status_code == 200 and "_cell_length_a" in r.text, a["file"]
        assert a["route"] in {x["title"] for x in dp["routes"]}
    assert client.get("/api/studies/nope").status_code == 404
    assert client.get("/api/studies/mp20/files/../../settings.py").status_code in (404, 400)


@needs_artefacts
def test_study_files_only_the_listed_ones(client):
    mp20 = client.get("/api/studies/mp20").json()
    name = next(n for n in mp20["files"] if n.endswith(".csv"))
    r = client.get(f"/api/studies/mp20/files/{name}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert client.get("/api/studies/mp20/files/not-listed.csv").status_code == 404


@pytest.mark.skipif(not os.path.isfile(MANIFEST), reason="no checkpoints manifest")
def test_checkpoints_are_listed_with_checksums(client):
    d = client.get("/api/checkpoints").json()
    ids = {c["id"] for c in d["checkpoints"]}
    assert {"perov5-2k", "mp20-wyck", "mp20-main", "desc-full", "mp-grounded"} <= ids
    assert all(c["sha256"] for c in d["checkpoints"] if c.get("ship"))
    assert not any(c["id"].startswith("u246") for c in d["checkpoints"])
    one = client.get("/api/checkpoints/mp20-wyck").json()
    assert one["geometry"] == "wyckoff" and "band_gap" in one["properties"]
    assert client.get("/api/checkpoints/nothing").status_code == 404


def test_health_reports_the_engine(settings):
    with make_client(settings) as c:
        h = c.get("/health").json()
        assert h["status"] == "ok" and h["engine"]["symmetry_decoder"] is True
        assert "judge_ready" in h and "research_artefacts" in h
