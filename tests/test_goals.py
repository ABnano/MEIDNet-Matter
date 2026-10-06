"""From a goal to the engine's generation settings, and the checks before anything runs."""
import pytest

from matter.schemas.goal import Goal
from matter.services import goals as G


def _art():
    """A stand-in for the demo artefacts: two properties with training statistics."""
    class Art:
        dataset = {"properties": {
            "dir_gap": {"label": "Direct band gap", "unit": "eV", "std": 1.5, "min": 0.0, "max": 7.9, "span": 7.9, "zero_share": 0.96, "n": 100,
                        "percentiles": {"p1": 0.0, "p5": 0.0, "p95": 0.0, "p99": 2.0},
                        "nonzero": {"n": 4, "std": 1.5, "min": 0.3, "max": 7.9, "percentiles": {"p1": 0.4, "p5": 0.5, "p95": 5.6, "p99": 7.08}}},
            "heat_all": {"label": "Formation enthalpy", "unit": "eV/atom", "std": 0.74, "min": -0.64, "max": 5.16, "span": 5.8, "zero_share": 0.0, "n": 100,
                         "percentiles": {"p1": 0.18, "p5": 0.48, "p95": 2.9, "p99": 3.82}}}}

        def property(self, c):
            return self.dataset["properties"][c]
    return Art()


def goal(**kw):
    base = {"objectives": [{"property": "dir_gap", "kind": "value", "value": 2.0, "tolerance": 0.3},
                           {"property": "heat_all", "kind": "at_most", "value": 1.0, "priority": "secondary"}],
            "variant": "oxide", "elements": {"exclude": ["Pb"]}}
    base.update(kw)
    return Goal.model_validate(base)


def test_value_and_bound_translate_to_objectives_targets_and_windows():
    t = G.translate(goal(), _art())
    g = t.generation
    assert g["objectives"][0] == {"property": "dir_gap", "loss": "l2", "weight": 10000.0, "select_weight": 1.0}
    assert g["objectives"][1] == {"property": "heat_all", "loss": "at_most", "weight": 6000.0, "select_weight": 0.4}
    assert g["targets"] == [{"dir_gap": 2.0, "heat_all": 1.0}]
    assert t.windows == [{"name": "property_window", "property": "dir_gap", "min": 1.7, "max": 2.3},
                         {"name": "property_window", "property": "heat_all", "max": 1.0}]
    assert g["exclude_elements"] == ["Pb"] and g["output_prefix"] == "oxide"
    assert any("± 0.3 eV" in s for s in t.explained)


def test_range_values_maximize_and_minimize():
    t = G.translate(goal(objectives=[{"property": "dir_gap", "kind": "range", "low": 1.4, "high": 1.6},
                                     {"property": "heat_all", "kind": "values", "values": [0.5, 1.0]}]), _art())
    assert t.generation["targets"] == [{"dir_gap": 1.5, "heat_all": 0.5}, {"dir_gap": 1.5, "heat_all": 1.0}]
    assert t.windows[0] == {"name": "property_window", "property": "dir_gap", "min": 1.4, "max": 1.6}
    t = G.translate(goal(objectives=[{"property": "dir_gap", "kind": "maximize"}, {"property": "heat_all", "kind": "minimize"}]), _art())
    assert t.generation["objectives"][0]["loss"] == "at_least" and t.generation["targets"][0]["dir_gap"] == 7.08     # p99 of the non-zero gaps
    assert t.generation["objectives"][1]["loss"] == "at_most" and t.generation["targets"][0]["heat_all"] == 0.18     # p1
    assert any("99th percentile" in s and "non-zero" in s for s in t.explained)


def test_presets_priorities_and_diverse_set():
    t = G.translate(goal(elements={"exclude": ["Cd"], "presets": ["pb_free", "no_precious"]}, diverse_set=True,
                         budget={"per_target": 1, "min_cosine_sep": 0.995}), _art())
    g = t.generation
    assert g["exclude_elements"][:2] == ["Cd", "Pb"] and "Pt" in g["exclude_elements"]
    assert g["per_target"] == 3 and g["min_cosine_sep"] == 0.98


def test_public_limits_clamp_with_notes():
    gen = G.translate(goal(budget={"rounds": 99, "steps": 5000, "population": 256, "per_target": 50},
                           objectives=[{"property": "dir_gap", "kind": "values", "values": [1.0, 2.0, 3.0]}],
                           rule_overrides={"bond_window": {"cutoff": 20.0, "from": 1}}), _art()).generation
    notes = []
    gen = G.apply_limits(gen, True, notes)
    assert gen["rounds"] == 6 and gen["steps"] == 400 and gen["population"] == 32 and gen["per_target"] == 6
    assert len(gen["targets"]) == 2 and gen["overrides"] == {"bond_window": {"cutoff": 8.0}}
    assert any("rounds: 99 → 6" in n for n in notes) and any("targets: 3 → 2" in n for n in notes)
    local = G.apply_limits(G.translate(goal(budget={"rounds": 99}), _art()).generation, False, [])
    assert local["rounds"] == 99


def test_schema_rejects_incomplete_objectives_and_unknown_fields():
    with pytest.raises(ValueError):
        Goal.model_validate({"objectives": [{"property": "dir_gap", "kind": "range", "low": 2.0, "high": 1.0}]})
    with pytest.raises(ValueError):
        Goal.model_validate({"objectives": [{"property": "dir_gap", "kind": "at_least"}]})
    with pytest.raises(ValueError):
        Goal.model_validate({"objectives": [{"property": "dir_gap", "value": 1.0}], "unknown": 1})
    with pytest.raises(ValueError):
        Goal.model_validate({"objectives": [{"property": "dir_gap", "value": 1.0}, {"property": "dir_gap", "value": 2.0}]})


def test_summary_text():
    assert G.summary_text(goal(), _art()) == "Eg 2 ± 0.3 eV · ΔHf ≤ 1 eV/atom · Pb-free · oxide perovskite"
    assert G.summary_text(goal(elements={"exclude": ["Pb", "Cd"]}, variant="halide",
                               objectives=[{"property": "dir_gap", "kind": "range", "low": 1.4, "high": 1.6}]), _art()) == \
        "Eg 1.4–1.6 eV · no Pb, Cd · halide perovskite"
    assert G.estimated_seconds({"rounds": 3, "steps": 300, "population": 24, "targets": [{}]}) == pytest.approx(53.4, abs=0.1)
