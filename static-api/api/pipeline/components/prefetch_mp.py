"""Prefetch Materials Project data for every generated composition (login node, internet), so that the heavy validation can
run on compute nodes from the cache: the composition's entries, and for compositions absent from MP the competing phases of
their chemical system (all sub-systems).  Usage: python prefetch_mp.py TAG [TAG ...]   (megnet-env or fairchem-env)"""
import glob, os, sys, importlib.util
import pandas as pd
from pymatgen.core import Structure
HERE = os.path.dirname(os.path.abspath(__file__))
def main():
    """The script's work; nothing runs on import."""
    spec = importlib.util.spec_from_file_location("sv", f"{HERE}/sun_validate.py"); sv = importlib.util.module_from_spec(spec)
    sys_argv = sys.argv; sys.argv = ["x"]; spec.loader.exec_module(sv); sys.argv = sys_argv
    n_abs = 0; seen = set()
    for tag in sys.argv[1:]:
        d = pd.read_csv(f"{HERE}/results/{tag}/candidates.csv")
        for f in d.file:
            s = Structure.from_file(f"{HERE}/results/{tag}/{f}")
            formula = s.composition.reduced_formula
            if formula in seen:
                continue
            seen.add(formula)
            if not sv.mp_entries(formula):
                n_abs += 1
                sv.mp_chemsys_entries(sorted({el.symbol for el in s.composition.elements}))
    print(f"prefetched {len(seen)} compositions; {n_abs} absent from MP (competing phases fetched)")


if __name__ == "__main__":
    main()
