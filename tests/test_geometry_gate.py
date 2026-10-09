"""The geometry gate of the engine (0.8.0): a sound bulk crystal passes; a slab (thick empty layer) and a sparse cell are
not bulk crystals, after relaxation (bulk_problem) and when the generator draws them (plausible)."""
import pytest

pytest.importorskip("pymatgen")


def _rocksalt(a=5.64):
    from pymatgen.core import Lattice, Structure
    return Structure.from_spacegroup("Fm-3m", Lattice.cubic(a), ["Na", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])


def test_a_sound_crystal_passes():
    from meidnet_eval.d1_mlip_check import COLLAPSED, bulk_problem, contact_ratio, empty_layer, packing_fraction
    s = _rocksalt()
    assert bulk_problem(s) == "" and contact_ratio(s) >= COLLAPSED
    assert empty_layer(s) < 3.0 and packing_fraction(s) > 0.3


def test_a_slab_and_a_sparse_cell_are_not_bulk():
    from pymatgen.core import Lattice, Structure
    from meidnet_eval.conditional_generate import plausible
    from meidnet_eval.d1_mlip_check import MAX_EMPTY_LAYER, MIN_PACKING, bulk_problem, empty_layer, packing_fraction
    s = _rocksalt()
    slab = Structure(Lattice.from_parameters(s.lattice.a, s.lattice.b, s.lattice.c + 12.0, 90, 90, 90), s.species,
                     s.cart_coords, coords_are_cartesian=True)          # the same atoms, 12 A of vacuum along c
    assert empty_layer(slab) > MAX_EMPTY_LAYER and "empty layer" in bulk_problem(slab)
    ok, why = plausible(slab)
    assert not ok and why.startswith("empty layer thicker than")
    sparse = _rocksalt(a=10.0)                                         # the atoms of a crystal spread through a cage
    assert empty_layer(sparse) <= MAX_EMPTY_LAYER and packing_fraction(sparse) < MIN_PACKING and "packing" in bulk_problem(sparse)
    ok, why = plausible(sparse)
    assert not ok and why.startswith("packing fraction below")
    assert plausible(s) == (True, "")
