"""
Element tables and small chemistry helpers shared by every part of MEIDNet.

The crystal modality represents each site with a one-hot vector over all 118
elements, so ``ELEMENTS`` fixes the meaning of every species index used by the
encoder, the decoder and the generation code.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from pymatgen.core.periodic_table import Element

ELEMENTS: list[str] = [str(Element.from_Z(z)) for z in range(1, 119)]
NUM_SPECIES: int = len(ELEMENTS)  # 118
ELEMENT_INDEX: dict[str, int] = {el: i for i, el in enumerate(ELEMENTS)}

DEFAULT_RADIUS = 1.5  # Å, used when pymatgen has no ionic radius for an element

# Elements that sit on an anion site are sized as that anion.  pymatgen lists every oxidation state it knows, so averaging
# over them (what MEIDNet v1 did) halves the radius of any anion that also has positive states: N 1.32 -> 0.63, F 1.19 ->
# 0.705, S 1.70 -> 0.88.  Oxygen has only one state, which is why the error stayed invisible while every rule used O as the
# anion: it made the octahedral factor r_B/r_X exceed 1 and silently rejected every fluoride, sulfide and N-rich candidate.
ANION_STATE: dict[str, int] = {"O": -2, "S": -2, "Se": -2, "Te": -2, "N": -3, "P": -3, "F": -1, "Cl": -1, "Br": -1, "I": -1}


def element_index(symbol: str) -> int:
    """Return the species index of an element symbol (raises a readable error)."""
    try:
        return ELEMENT_INDEX[symbol]
    except KeyError:
        raise ValueError(f"'{symbol}' is not a chemical element symbol") from None


@lru_cache(maxsize=None)
def ionic_radius(symbol: str, charge: int | None = None) -> float:
    """
    Ionic radius of an element in Å, as used by the lattice rule and the tolerance / octahedral factor checks.

    With ``charge`` given, the radius of that oxidation state is returned.  Without it, an element that acts as an anion
    (``ANION_STATE``) is sized as that anion, and any other element keeps MEIDNet v1's mean over the oxidation states
    pymatgen knows.  Oxygen is unaffected either way, so results produced with O on the anion sites are unchanged.
    """
    try:
        r = Element(symbol).ionic_radii or {}
        if charge is None:
            charge = ANION_STATE.get(symbol)
        if charge is not None and isinstance(r, dict):
            for key in (charge, float(charge)):
                if r.get(key):
                    return float(r[key])
        if isinstance(r, dict):
            vals = [float(x) for x in r.values() if x]
            return float(np.mean(vals)) if vals else DEFAULT_RADIUS
        return float(np.mean(r)) if r else DEFAULT_RADIUS
    except Exception:
        return DEFAULT_RADIUS
