"""Do generated cells survive relaxation by two independent machine-learning potentials?

Two potentials of different architecture (TensorNet and CHGNet, both trained on MatPES-PBE), because one potential
agreeing with itself is not evidence.  Per candidate: whether each relaxed at all, the energy per atom, how far the
energy fell on relaxation (a sound structure falls by less than 0.1 eV/atom), how far atoms moved, whether the designed
space group survived, and the shortest interatomic distance afterwards.  The relaxed cells are kept, because a band gap
judged on a cell that then moves by an angstrom describes no material: the judges must be re-run on the relaxed cell.

Usage: python d1_mlip_check.py RESULTS_DIR [--cifs-dir DIR] [--steps 300] [--shard 0 --nshards 1] [--subset N]
       [--potentials tensornet chgnet] [--out-dir DIR]
Environment variables STEPS, SHARD, NSHARDS, SUBSET are honoured as defaults so batch scripts keep working.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

POTENTIALS = {"tensornet": "TensorNet-PES-MatPES-PBE-2025.2", "chgnet": "CHGNet-PES-MatPES-PBE-2025.2.10"}
_CACHE = {}


def relaxer(name):
    if name not in _CACHE:
        import matgl
        from matgl.ext.ase import Relaxer
        _CACHE[name] = Relaxer(potential=matgl.load_model(POTENTIALS[name]), relax_cell=True)
    return _CACHE[name]


def spacegroup(s):
    try:
        return int(SpacegroupAnalyzer(s, symprec=0.1).get_space_group_number())
    except Exception:
        return 0


def relax_one(s0, name, steps, fmax=0.05):
    """One cell, one potential -> the relaxed structure and its record."""
    res = relaxer(name).relax(s0, fmax=fmax, steps=steps)
    s1, traj = res["final_structure"], res["trajectory"]
    e0, e1 = float(traj.energies[0]) / len(s0), float(traj.energies[-1]) / len(s1)
    disp = np.array([np.linalg.norm(x) for x in (s1.cart_coords - s0.cart_coords)]) if len(s1) == len(s0) else np.array([np.nan])
    rec = {f"{name}_energy_per_atom": round(e1, 4), f"{name}_drop_per_atom": round(e0 - e1, 4),
           f"{name}_max_displacement": round(float(np.nanmax(disp)), 3), f"{name}_spacegroup_relaxed": spacegroup(s1),
           f"{name}_min_distance": round(float((s1.distance_matrix + np.eye(len(s1)) * 99).min()), 3) if len(s1) > 1 else None,
           f"{name}_ok": True}
    return s1, rec


def main():
    env = os.environ
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    ap.add_argument("--candidates", help="table with a `file` column (default RESULTS_DIR/candidates.csv)")
    ap.add_argument("--cifs-dir", help="folder the `file` column is relative to (default RESULTS_DIR)")
    ap.add_argument("--out-dir", help="where mlip_shard*.json and relaxed_<potential>/ go (default RESULTS_DIR)")
    ap.add_argument("--steps", type=int, default=int(env.get("STEPS", "300")))
    ap.add_argument("--fmax", type=float, default=0.05)
    ap.add_argument("--shard", type=int, default=int(env.get("SHARD", "0")))
    ap.add_argument("--nshards", type=int, default=int(env.get("NSHARDS", "1")))
    ap.add_argument("--subset", type=int, default=int(env["SUBSET"]) if env.get("SUBSET") else None,
                    help="at most this many candidates per shard (round-robin assignment keeps every target represented)")
    ap.add_argument("--potentials", nargs="+", default=list(POTENTIALS), choices=list(POTENTIALS))
    a = ap.parse_args()
    cands = a.candidates or os.path.join(a.results_dir, "candidates.csv")
    cifs_dir = a.cifs_dir or a.results_dir
    out_dir = a.out_dir or a.results_dir
    os.makedirs(out_dir, exist_ok=True)

    df = pd.read_csv(cands)
    rows = [r for i, r in enumerate(df.to_dict("records")) if i % a.nshards == a.shard]
    if a.subset:
        rows = rows[: a.subset]
    dst = os.path.join(out_dir, f"mlip_shard{a.shard}.json")
    print(f"shard {a.shard}/{a.nshards}: {len(rows)} candidates, {a.steps} max steps, potentials {a.potentials}", flush=True)
    out = []
    for r in rows:
        s0 = Structure.from_file(os.path.join(cifs_dir, r["file"]))
        rec = {"file": r["file"], "formula": r.get("formula"), "target": r.get("target"), "natoms": len(s0),
               "spacegroup_designed": spacegroup(s0)}
        for name in a.potentials:
            try:
                s1, part = relax_one(s0, name, a.steps, a.fmax)
                rec.update(part)
                folder = os.path.join(out_dir, f"relaxed_{name}")
                os.makedirs(folder, exist_ok=True)
                s1.to(filename=os.path.join(folder, os.path.basename(r["file"])))
            except Exception as e:
                rec[f"{name}_ok"] = False
                rec[f"{name}_error"] = f"{type(e).__name__}: {str(e)[:70]}"
        if all(rec.get(f"{n}_ok") for n in a.potentials) and len(a.potentials) >= 2:
            e = [rec[f"{n}_energy_per_atom"] for n in a.potentials]
            rec["potential_disagreement"] = round(float(max(e) - min(e)), 4)
        out.append(rec)
        print(f"  {str(r.get('formula')):22s} " + " ".join(f"{n}:{'ok' if rec.get(f'{n}_ok') else 'FAIL'}" for n in a.potentials), flush=True)
        json.dump(out, open(dst, "w"), indent=1)          # after every candidate, so a wall-clock kill keeps the results
    print(f"wrote {dst} ({len(out)} candidates)")


if __name__ == "__main__":
    main()
