"""Block S7's hull arithmetic and reference set, on a toy Li-Cl system: no potential is loaded, the relaxed energies are
given, so what is tested is the hull built from them, the pruning of competing phases and the known/new match."""
import json
import math

import pytest

pytest.importorskip("pymatgen")
hull_mlip = pytest.importorskip("meidnet_eval.hull_mlip")

# relaxed energies per atom as the cache stores them (one potential for every phase)
CACHE = {
    "li": dict(ok=True, composition={"Li": 1.0}, e_per_atom=0.0),
    "cl": dict(ok=True, composition={"Cl": 2.0}, e_per_atom=0.0),
    "licl": dict(ok=True, composition={"Li": 1.0, "Cl": 1.0}, e_per_atom=-1.0),
}
PHASES = [dict(id="li", formula="Li"), dict(id="cl", formula="Cl2"), dict(id="licl", formula="LiCl")]


def test_energy_above_the_hull_and_decomposition():
    e, decomp, n_used, missing = hull_mlip.hull_energy({"Li": 1, "Cl": 1}, -0.9, PHASES, CACHE)
    assert missing == [] and n_used == 3
    assert e == pytest.approx(0.1, abs=1e-6) and decomp == ["LiCl"]
    # Li2Cl lies between Li and LiCl: hull at x(Cl) = 1/3 is -2/3 eV/atom
    e, decomp, _, _ = hull_mlip.hull_energy({"Li": 2, "Cl": 1}, -0.5, PHASES, CACHE)
    assert e == pytest.approx(-0.5 + 2 / 3, abs=1e-6) and decomp == ["Li", "LiCl"]
    # below the known phases: on the hull
    e, _, _, _ = hull_mlip.hull_energy({"Li": 1, "Cl": 1}, -1.2, PHASES, CACHE)
    assert e == pytest.approx(0.0, abs=1e-9)


def test_missing_element_or_failed_relaxation_gives_no_number():
    e, decomp, _, missing = hull_mlip.hull_energy({"Li": 1, "Cl": 1}, -0.9, PHASES[:1] + PHASES[2:], CACHE)
    assert math.isnan(e) and missing == ["Cl"] and decomp == []
    failed = dict(CACHE, cl=dict(ok=False, error="RuntimeError"))
    e, _, n_used, missing = hull_mlip.hull_energy({"Li": 1, "Cl": 1}, -0.9, PHASES, failed)
    assert math.isnan(e) and missing == ["Cl"] and n_used == 2


def _atoms(elements, coords, a=4.0):
    return dict(lattice_mat=[[a, 0, 0], [0, a, 0], [0, 0, a]], elements=elements, coords=coords, cartesian=False)


@pytest.fixture()
def jarvis(tmp_path):
    rows = [
        dict(jid="J-li", formula="Li", atoms=_atoms(["Li"], [[0, 0, 0]]), ehull=0.0, optb88vdw_bandgap=0.0),
        dict(jid="J-cl", formula="Cl", atoms=_atoms(["Cl", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]]), ehull=0.0, optb88vdw_bandgap=2.0),
        dict(jid="J-licl", formula="LiCl", atoms=_atoms(["Li", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]]), ehull=0.0, optb88vdw_bandgap=6.3),
        dict(jid="J-licl-b", formula="LiCl", atoms=_atoms(["Li", "Cl"], [[0, 0, 0], [0.5, 0.5, 0]]), ehull=0.03, optb88vdw_bandgap=5.9),
        dict(jid="J-licl-c", formula="LiCl", atoms=_atoms(["Li", "Cl"], [[0, 0, 0], [0.5, 0, 0]]), ehull=0.04, optb88vdw_bandgap="na"),
        dict(jid="J-li3cl", formula="Li3Cl", atoms=_atoms(["Li", "Li", "Li", "Cl"], [[0, 0, 0], [0.5, 0, 0], [0, 0.5, 0], [0, 0, 0.5]]),
             ehull=0.4, optb88vdw_bandgap=0.0),
    ]
    path = tmp_path / "jdft_3d-toy.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return hull_mlip.Reference(f"jarvis:{path}", near=0.05, max_atoms=40, cache=str(tmp_path / "cache"), log=lambda *a: None)


def test_reference_prunes_competing_phases(jarvis):
    ids = sorted(e["id"] for e in jarvis.phases_for(["Li", "Cl"]))
    # every element's lowest phase, near-hull compounds only (Li3Cl at 0.4 eV/atom cannot shape the hull), two polymorphs per formula
    assert ids == ["J-cl", "J-li", "J-licl", "J-licl-b"]
    assert "J-licl" not in {e["id"] for e in jarvis.phases_for(["Li", "Cl"], exclude_ids={"J-licl"})}


def test_reference_match_says_known_or_new(jarvis):
    hits = jarvis.match("Li2Cl2")                     # same reduced composition as LiCl
    assert [h["id"] for h in hits] == ["J-licl", "J-licl-b", "J-licl-c"]
    assert hits[0]["gap_ref"] == pytest.approx(6.3) and hits[2]["gap_ref"] is None
    assert jarvis.match("Li2Cl") == []
    s = jarvis.structure(hits[0])
    assert s.composition.reduced_formula == "LiCl" and len(s) == 2


def test_cache_key_follows_content_not_name():
    from pymatgen.core import Lattice, Structure
    s = Structure(Lattice.cubic(4.0), ["Li", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    t = Structure(Lattice.cubic(4.0), ["Li", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    u = Structure(Lattice.cubic(4.1), ["Li", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    assert hull_mlip.struct_key("cand:", s) == hull_mlip.struct_key("cand:", t) != hull_mlip.struct_key("cand:", u)


def test_depth_below_the_known_phases():
    # LiCl at -1.25 eV/atom: on the hull, 0.25 eV/atom below the known LiCl, deeper than a new ground state plausibly lies
    e, decomp, _, _, sep = hull_mlip.hull_energy({"Li": 1, "Cl": 1}, -1.25, PHASES, CACHE, depth=True)
    assert e == pytest.approx(0.0, abs=1e-9) and sep == pytest.approx(-0.25, abs=1e-6)
    e, _, _, _, sep = hull_mlip.hull_energy({"Li": 1, "Cl": 1}, -0.9, PHASES, CACHE, depth=True)
    assert e == pytest.approx(0.1, abs=1e-6) and sep == pytest.approx(0.1, abs=1e-6)        # above the hull: the same number


def test_a_collapsed_cell_is_told_from_a_crystal():
    from pymatgen.core import Lattice, Structure
    from meidnet_eval.d1_mlip_check import COLLAPSED, contact_ratio
    rocksalt = Structure.from_spacegroup("Fm-3m", Lattice.cubic(5.64), ["Na", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    assert contact_ratio(rocksalt) > 0.9
    squeezed = Structure(Lattice.cubic(4.0), ["Te", "Te"], [[0, 0, 0], [0.3, 0, 0]])          # Te-Te 1.2 A, real bonds 2.7+
    assert contact_ratio(squeezed) < COLLAPSED
    tiny_cell = Structure(Lattice.cubic(1.5), ["Cs"], [[0, 0, 0]])                           # an atom against its own image
    assert contact_ratio(tiny_cell) < COLLAPSED
