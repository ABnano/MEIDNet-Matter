"""The readiness verdict rule on constructed indicators, and the report on the real demo project."""
import copy

import pytest

from matter.services import readiness as R
from matter.services.support import EXTRAPOLATION_SENTENCE


def _ind(fid_word="good", tgt_status="in_distribution", n_box=500, fam_status="ok", align="ok", recov="ok"):
    return {
        "fidelity": {"status": "ok", "per_property": {"dir_gap": {"label": "Band gap", "unit": "eV", "word": fid_word, "mae": 0.1, "std": 1.0}}},
        "target_support": {"status": "ok", "per_property": {"dir_gap": {"label": "Band gap", "unit": "eV", "status": tgt_status}},
                           "numbers": {"n_box": n_box, "n_train": 10000, "fraction": n_box / 10000}},
        "family_support": {"status": fam_status, "title": "Chemical-family support"},
        "alignment": {"status": align, "title": "Cross-modal alignment"},
        "recoverability": {"status": recov, "title": "Held-out reconstruction"},
        "ambiguity": {"status": "info", "one_to_many": True, "numbers": {"n_box": n_box, "n_formulas": 40}},
    }


def test_verdict_rule_every_branch():
    assert R.verdict_of(_ind()) == ("SUPPORTED", [], False)
    v, reasons, expl = R.verdict_of(_ind(fid_word="weak"))
    assert v == "NOT_RECOMMENDED" and expl and "weak" in reasons[0]
    assert R.verdict_of(_ind(tgt_status="far_outside"))[0] == "NOT_RECOMMENDED"
    assert R.verdict_of(_ind(n_box=0))[0] == "NOT_RECOMMENDED"
    assert R.verdict_of(_ind(fam_status="not_ok"))[0] == "NOT_RECOMMENDED"
    for kw in (dict(fid_word="fair"), dict(tgt_status="near_boundary"), dict(tgt_status="extrapolating"), dict(n_box=50),
               dict(align="caution"), dict(recov="not_computed"), dict(fam_status="caution"), dict(align="not_ok")):
        v, reasons, expl = R.verdict_of(_ind(**kw))
        assert v == "CAUTION" and reasons and not expl, kw
    ind = _ind()
    ind["ambiguity"]["one_to_many"] = True                                        # E never changes the verdict
    assert R.verdict_of(ind)[0] == "SUPPORTED"


DEFAULT = {"objectives": [{"property": "dir_gap", "kind": "value", "value": 2.0, "tolerance": 0.3},
                          {"property": "heat_all", "kind": "at_most", "value": 1.0, "priority": "secondary"}],
           "variant": "oxide", "elements": {"exclude": ["Pb"]}}


@pytest.mark.slow
def test_report_on_the_demo_project(client, checkpoint):
    r = client.post("/api/readiness", json=DEFAULT)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["verdict"] in ("SUPPORTED", "CAUTION", "NOT_RECOMMENDED")
    assert set(rep["indicators"]) == {"fidelity", "alignment", "recoverability", "target_support", "ambiguity", "family_support"}
    fid = rep["indicators"]["fidelity"]["per_property"]
    assert fid["dir_gap"]["basis"] == "nonzero" and fid["dir_gap"]["word"] == "weak"           # the published model, as benchmarked
    assert fid["heat_all"]["word"] == "weak" and fid["heat_all"]["knn_word"] == "good"
    assert rep["verdict"] == "NOT_RECOMMENDED" and rep["exploratory_required"]
    assert any("does not reliably predict" in s for s in rep["indicators"]["fidelity"]["sentences"])
    assert any("optimistic" in s for s in rep["indicators"]["fidelity"]["sentences"])          # the test-split caveat
    tgt = rep["indicators"]["target_support"]
    assert tgt["per_property"]["dir_gap"]["status"] == "in_distribution"
    half = max(0.05 * 7.9, 0.3)                                                        # the wider of 5 % of the span and the tolerance
    assert tgt["numbers"]["n_box"] > 0 and rep["windows"]["dir_gap"] == pytest.approx([2.0 - half, 2.0 + half])
    amb = rep["indicators"]["ambiguity"]
    assert amb["numbers"]["n_formulas"] >= 1 and amb["numbers"]["n_clusters"] is not None
    fam = rep["indicators"]["family_support"]
    assert fam["groups"]["X"]["absent"] == [] and fam["space"]["rule_passing"] > 0
    assert rep["summary"] and rep["goal_hash"] and rep["computed_in_ms"] < 60000


@pytest.mark.slow
def test_extrapolating_target_and_halide_gap(client, checkpoint):
    far = copy.deepcopy(DEFAULT)
    far["objectives"][0]["value"] = 9.5                                              # beyond the 0–7.9 eV training range
    rep = client.post("/api/readiness", json=far).json()
    d = rep["indicators"]["target_support"]["per_property"]["dir_gap"]
    assert d["status"] == "far_outside" and EXTRAPOLATION_SENTENCE in d["reason"]
    assert rep["verdict"] == "NOT_RECOMMENDED" and any("far outside" in r for r in rep["reasons"])
    halide = copy.deepcopy(DEFAULT)
    halide["variant"] = "halide"
    rep = client.post("/api/readiness", json=halide).json()
    fam = rep["indicators"]["family_support"]
    assert set(fam["groups"]["X"]["absent"]) == {"Cl", "Br", "I"} and fam["status"] in ("caution", "not_ok")
    assert any("do not occur" in s for s in fam["sentences"])


@pytest.mark.slow
def test_one_to_many_advice_when_the_window_is_crowded(client, checkpoint):
    crowded = {"objectives": [{"property": "heat_all", "kind": "value", "value": 1.4, "tolerance": 0.3}], "variant": "oxide"}
    rep = client.post("/api/readiness", json=crowded).json()
    amb = rep["indicators"]["ambiguity"]
    assert amb["one_to_many"] and amb["numbers"]["n_box"] >= 10 and rep["search_advice"]["diverse_set"]
    assert any("many possible structures" in s for s in amb["sentences"])


def test_invalid_goal_is_a_422_with_fields(client):
    r = client.post("/api/readiness", json={"objectives": [{"property": "band_gap", "kind": "value", "value": 1.0}]})
    assert r.status_code == 422
    assert r.json()["error"]["fields"][0]["loc"] == "objectives.0.property"
