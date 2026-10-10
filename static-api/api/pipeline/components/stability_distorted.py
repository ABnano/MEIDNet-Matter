"""Distortion-aware stability: real perovskites often tilt their octahedra (Glazer a-a-c+, space group Pnma) instead of staying
ideal cubic.  For each composition, relax a sqrt2 x sqrt2 x 2 supercell (20 atoms) from two randomly displaced starts with the
MLIP (TensorNet-PES-MatPES-PBE), keep the lowest energy, and estimate the energy above the convex hull as
    E_hull(distorted) = E_hull_MP(ground state) + max(0, E_MLIP(ours) - E_MLIP(MP ground state relaxed))
(MP data read from the cache filled by sun_validate.py / discovery_space.py; no internet needed, runs on compute nodes).
Usage: python stability_distorted.py <out.csv> <shard> <nshards> <sun_csv> [<sun_csv> ...]"""
import json, os, sys, warnings
def relax(s, steps=800):
    r = relaxer.relax(s, fmax=0.02, steps=steps)
    return r["final_structure"], float(r["trajectory"].energies[-1]) / len(s)
def spacegroup(s):
    try:
        return SpacegroupAnalyzer(s, symprec=0.1).get_space_group_symbol()
    except Exception:
        return "?"

def main():
    """The script's work; nothing runs on import."""
    warnings.filterwarnings("ignore")
    import numpy as np, pandas as pd
    from pymatgen.core import Structure, Lattice
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    HERE = os.path.dirname(os.path.abspath(__file__))
    CACHE = f"{HERE}/results/sun_cache"
    out_csv, shard, nshards = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    keys = pd.concat([pd.read_csv(p) for p in sys.argv[4:]]).drop_duplicates("key").sort_values("key").reset_index(drop=True)
    keys = keys.iloc[shard::nshards]

    import matgl
    from matgl.ext.ase import Relaxer
    relaxer = Relaxer(potential=matgl.load_model("TensorNet-PES-MatPES-PBE-2025.2"), relax_cell=True)






    rows = []
    for r in keys.itertuples():
        A, B, X = r.key.split("|")
        cubic = Structure(Lattice.cubic(r.a_relaxed), [A, B, X, X, X], [[0, 0, 0], [.5, .5, .5], [0, .5, .5], [.5, 0, .5], [.5, .5, 0]])
        s_cub, e_cub = relax(cubic, 300)
        best = (e_cub, s_cub, "cubic")
        for seed, amp in ((0, 0.08), (1, 0.15)):
            sup = cubic.copy(); sup.make_supercell([[1, 1, 0], [-1, 1, 0], [0, 0, 2]])
            rng = np.random.RandomState(seed)
            sup = Structure(sup.lattice, sup.species, sup.cart_coords + rng.normal(0, amp, (len(sup), 3)), coords_are_cartesian=True)
            s_d, e_d = relax(sup)
            if e_d < best[0] - 1e-4:
                best = (e_d, s_d, f"distorted (start {seed})")
        mp = json.load(open(f"{CACHE}/mp_{r.formula}.json")) if os.path.exists(f"{CACHE}/mp_{r.formula}.json") else []
        if mp:
            gs = min(mp, key=lambda m: m["energy_above_hull"])
            _, e_gs = relax(Structure.from_dict(gs["structure"]))
            ehull = gs["energy_above_hull"] + max(0.0, best[0] - e_gs)
            gs_sg, gs_ehull = gs["symmetry"]["symbol"], gs["energy_above_hull"]
        else:
            ehull, gs_sg, gs_ehull, e_gs = float("nan"), None, float("nan"), float("nan")
        rows.append(dict(key=r.key, formula=r.formula, e_hull_cubic_before=r.e_hull, e_cubic=e_cub, e_best=best[0],
                         gain_meV=1000 * (e_cub - best[0]), best=best[2], best_spacegroup=spacegroup(best[1]),
                         mp_gs_spacegroup=gs_sg, mp_gs_ehull=gs_ehull, e_mp_gs_mlip=e_gs, e_hull_distorted=ehull))
        print(f"{r.formula:9s} cubic E_hull {r.e_hull:.3f} -> distorted {ehull:.3f} | {best[2]} {spacegroup(best[1])} "
              f"(gain {1000*(e_cub-best[0]):.0f} meV/atom) | MP GS {gs_sg} {gs_ehull}", flush=True)
    pd.DataFrame(rows).to_csv(out_csv, index=False)


if __name__ == "__main__":
    main()
