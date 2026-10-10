"""Prepare the generated candidate cells for the independent judges, and cross-check the two MLIPs on the same cells.

For every distinct composition of the discovery runs (same keying as sun_validate.py) this writes the 5-atom generated cell
and its relaxation under TWO independent machine-learning potentials, so a stability claim never rests on one potential:
  results/cells/raw/<formula>.cif         the cell the generator produced (what CGCNN-P5 was trained on: 5-atom perovskites)
  results/cells/tensornet/<formula>.cif   relaxed with TensorNet-PES-MatPES-PBE-2025.2
  results/cells/chgnet/<formula>.cif      relaxed with CHGNet-PES-MatPES-PBE-2025.2.10
  results/mlip_compare.csv                per composition: energy/atom, lattice a and space group from each potential,
                                          and their difference (agreement = both potentials see the same relaxed structure)
Absolute energies of two potentials are not comparable (different references); the lattice constant, the space group and the
energy DIFFERENCE between cells of the same composition are.
Usage: DGLBACKEND=pytorch python candidate_cells.py <TAG> [<TAG> ...]    (megnet-env)
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
import pandas as pd
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

HERE = os.path.dirname(os.path.abspath(__file__)); RES = f"{HERE}/results"
CELLS = os.environ.get("CELLS_DIR", f"{RES}/cells")          # a run folder keeps its own cells (no cross-dataset overwrite)
CMP = os.environ.get("MLIP_COMPARE_DIR", RES)
POTENTIALS = {"tensornet": "TensorNet-PES-MatPES-PBE-2025.2", "chgnet": "CHGNet-PES-MatPES-PBE-2025.2.10"}
_cache = {}


def relaxer(name):
    if name not in _cache:
        import matgl
        from matgl.ext.ase import Relaxer
        _cache[name] = Relaxer(potential=matgl.load_model(POTENTIALS[name]), relax_cell=True)
    return _cache[name]


def sg(s):
    try:
        return SpacegroupAnalyzer(s, symprec=0.1).get_space_group_symbol()
    except Exception:
        return "?"


def main():
    tags = sys.argv[1:]
    rows = []
    for tag in tags:
        d = pd.read_csv(f"{RES}/{tag}/candidates.csv")
        sites = [c for c in ("site_A", "site_B", "site_X", "site_X1", "site_X2") if c in d.columns]
        for r in d.to_dict("records"):
            rows.append(dict(key="|".join(str(r[c]) for c in sites), target=r["target"], label_gap=r["label_gap"],
                             file=f"{RES}/{tag}/{r['file']}"))
    C = pd.DataFrame(rows)
    for sub in ("raw", *POTENTIALS):
        os.makedirs(f"{CELLS}/{sub}", exist_ok=True)
    shard, nshards = int(os.environ.get("SHARD", "0")), int(os.environ.get("NSHARDS", "1"))
    out, done = [], set()
    part = f"{CMP}/mlip_compare_shard{shard}.csv" if nshards > 1 else f"{CMP}/mlip_compare.csv"
    if os.path.exists(part):                                  # resume: whole compositions already finished
        done = set(pd.read_csv(part).key)
        out = pd.read_csv(part).to_dict("records")
    for i_key, (key, g) in enumerate(C.groupby("key")):
        if i_key % nshards != shard or key in done:
            continue
        s0 = Structure.from_file(g.file.iloc[0])
        formula = s0.composition.reduced_formula
        s0.to(filename=f"{CELLS}/raw/{formula}.cif")
        rec = dict(key=key, formula=formula, targets=sorted(set(g.target)), label_gap=float(g.label_gap.mean()),
                   a_raw=s0.lattice.a)
        for name in POTENTIALS:
            r = relaxer(name).relax(s0, fmax=0.02, steps=400)
            s = r["final_structure"]
            s.to(filename=f"{CELLS}/{name}/{formula}.cif")
            rec[f"e_{name}"] = float(r["trajectory"].energies[-1]) / len(s)
            rec[f"a_{name}"] = s.lattice.a
            rec[f"sg_{name}"] = sg(s)
        rec["da_mlip"] = abs(rec["a_tensornet"] - rec["a_chgnet"])
        rec["same_sg"] = rec["sg_tensornet"] == rec["sg_chgnet"]
        out.append(rec)
        pd.DataFrame(out).to_csv(part, index=False)          # incremental: the job can be stopped and resumed
        print(f"{formula:9s} a {rec['a_tensornet']:.3f}/{rec['a_chgnet']:.3f} (d {rec['da_mlip']:.3f}) | "
              f"sg {rec['sg_tensornet']}/{rec['sg_chgnet']} | agree {rec['same_sg']}", flush=True)
    V = pd.DataFrame(out)
    print(f"\n{len(V)} compositions | the two potentials agree on the space group for {int(V.same_sg.sum())} "
          f"| median |da| {V.da_mlip.median():.3f} A, 90th percentile {V.da_mlip.quantile(0.9):.3f} A")


if __name__ == "__main__":
    main()
