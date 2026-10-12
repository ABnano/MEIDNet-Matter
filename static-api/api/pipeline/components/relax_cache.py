"""Relax every distinct composition returned by the ablation runs once (TensorNet-PES-MatPES-PBE-2025.2), cached by
reduced formula in results/relaxed_cache/<formula>.cif, so the band-gap judges see physically sized cells.
Seeds the cache with the relaxations of the fidelity check.  Run in the megnet-env (matgl)."""
import glob, json, os, warnings
def main():
    """The script's work; nothing runs on import."""
    warnings.filterwarnings("ignore")
    import pandas as pd
    from pymatgen.core import Structure

    HERE = os.path.dirname(os.path.abspath(__file__))
    CACHE = f"{HERE}/results/relaxed_cache"
    FID = os.environ.get("MEIDNET_FIDELITY_DIR", "")   # the CGCNN judge checkout, when available
    os.makedirs(CACHE, exist_ok=True)

    # seed from the fidelity check (same potential, same settings)
    judged = pd.read_csv(f"{FID}/candidates_judged.csv")
    for f, formula in zip(judged.file, judged.formula):
        dst = f"{CACHE}/{Structure.from_file(f'{FID}/space_runs/{f}').composition.reduced_formula}.cif"
        if not os.path.exists(dst):
            Structure.from_file(f"{FID}/space_runs_relaxed/{f}").to(filename=dst)

    todo = {}
    for csv_path in glob.glob(f"{HERE}/results/*/candidates.csv"):
        if "smoke" in csv_path:
            continue
        d = pd.read_csv(csv_path)
        if not len(d):
            continue
        base = os.path.dirname(csv_path)
        for f in d.file:
            s = Structure.from_file(f"{base}/{f}")
            key = s.composition.reduced_formula
            if not os.path.exists(f"{CACHE}/{key}.cif"):
                todo.setdefault(key, s)
    print(f"{len(glob.glob(f'{CACHE}/*.cif'))} cached, {len(todo)} to relax", flush=True)
    if todo:
        import matgl
        from matgl.ext.ase import Relaxer
        relaxer = Relaxer(potential=matgl.load_model("TensorNet-PES-MatPES-PBE-2025.2"), relax_cell=True)
        log_path = f"{CACHE}/relaxation_log.json"
        log = json.load(open(log_path)) if os.path.exists(log_path) else {}
        for key, s in sorted(todo.items()):
            r = relaxer.relax(s, fmax=0.01, steps=300)
            rs = r["final_structure"]
            rs.to(filename=f"{CACHE}/{key}.cif")
            log[key] = dict(a_generated=round(s.lattice.a, 4), a_relaxed=round(rs.lattice.a, 4))
            print(f"{key:10s} a {s.lattice.a:.3f} -> {rs.lattice.a:.3f}", flush=True)
        json.dump(log, open(log_path, "w"), indent=1)
    print("relax cache complete")


if __name__ == "__main__":
    main()
