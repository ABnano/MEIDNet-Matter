"""Is a structure really a perovskite?  The corner-sharing test, importable without side effects.

Same test that built the strict MP-perovskite set (mp_perovskite_dataset.py, which cannot be imported because it downloads
on import): one cation B with 6 O neighbours (an octahedron), every O bridging exactly two B, each pair of B sharing at most
one O (corner sharing -- ilmenite, LiNbO3-type and hexagonal face-sharing cells fail here), and the other cation A with at
least 8 O within 3.6 A.  On the MP oxides it removed exactly the 70 ilmenite (R-3) cells and kept the perovskites.
"""
import numpy as np


def perovskite_roles(s):
    """(A, B) element symbols if s is a corner-sharing BO6 perovskite with an A cation of >= 8 O neighbours, else None."""
    cats = sorted({sp.symbol for sp in s.species if sp.symbol != "O"})
    if len(cats) != 2:
        return None
    o_idx = [i for i, site in enumerate(s) if site.specie.symbol == "O"]
    stats = {}
    for el in cats:
        idx = [i for i, site in enumerate(s) if site.specie.symbol == el]
        counts, dmins = [], []
        for i in idx:
            nb = [n for n in s.get_neighbors(s[i], 4.0) if n.specie.symbol == "O"]
            if not nb:
                return None
            dmin = min(n.nn_distance for n in nb)
            counts.append(sum(1 for n in nb if n.nn_distance <= 1.25 * dmin)); dmins.append(dmin)
        stats[el] = (np.mean(counts), np.mean(dmins), idx)
    B = min(cats, key=lambda e: stats[e][1]); A = [e for e in cats if e != B][0]
    if not (abs(stats[B][0] - 6) < 0.01):
        return None
    dB = stats[B][1] * 1.25
    for i in o_idx:                                        # every O bridges exactly two B
        nB = sum(1 for n in s.get_neighbors(s[i], dB) if n.specie.symbol == B)
        if nB != 2:
            return None
    for i in stats[B][2]:                                  # corner sharing only: each pair of B shares at most one O
        shared = {}
        for o in s.get_neighbors(s[i], dB):
            if o.specie.symbol != "O":
                continue
            for b in s.get_neighbors(o, dB):
                if b.specie.symbol == B and not (b.index == i and np.allclose(b.image, 0)):
                    k = (b.index, tuple(np.round(b.image, 0)))          # image is relative to the cell site, i.e. absolute
                    shared[k] = shared.get(k, 0) + 1
        if not shared or max(shared.values()) > 1:
            return None
    nA = [sum(1 for n in s.get_neighbors(s[i], 3.6) if n.specie.symbol == "O") for i in stats[A][2]]
    if np.mean(nA) < 8:
        return None
    return A, B


def is_perovskite(s):
    try:
        return perovskite_roles(s) is not None
    except Exception:
        return False
