"""
Stability screening of generated CIFs with the MACE-MP-0 universal potential.

For each structure: relax cell + positions, compute the formation energy per atom
against elemental reference phases, and report S/U/N:

    S — stable:  ΔH_f ≤ threshold (default 0.10 eV/atom, the Materials Project
                 "potentially synthesisable" criterion)
    U — unique:  no structural duplicate among the candidates (StructureMatcher)
    N — novel:   reduced formula absent from the training table

Requires ``pip install meidnet[stability]`` (ase + mace-torch; ~500 MB of weights
are downloaded on first use).  The elemental reference phases and the GGA-style
O/N corrections are those of MEIDNet v1 (scripts/screen_stability.py).
"""
from __future__ import annotations

import glob
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

GGA_CORRECTIONS = {"O": +0.35, "N": +0.35}
ARTEFACT_THRESHOLD = 5.0


def _element_structs():
    from ase.build import bulk, molecule
    return {
        "Ba": lambda: bulk("Ba", "bcc", a=5.023), "Sr": lambda: bulk("Sr", "fcc", a=6.084),
        "Ca": lambda: bulk("Ca", "fcc", a=5.588), "Na": lambda: bulk("Na", "bcc", a=4.225),
        "K": lambda: bulk("K", "bcc", a=5.332), "Rb": lambda: bulk("Rb", "bcc", a=5.703),
        "Cs": lambda: bulk("Cs", "bcc", a=6.141), "La": lambda: bulk("La", "fcc", a=5.303),
        "Ce": lambda: bulk("Ce", "fcc", a=5.160), "Pr": lambda: bulk("Pr", "fcc", a=5.170),
        "Nd": lambda: bulk("Nd", "fcc", a=5.160), "Sm": lambda: bulk("Sm", "fcc", a=5.124),
        "Eu": lambda: bulk("Eu", "bcc", a=4.583), "Gd": lambda: bulk("Gd", "hcp", a=3.636, c=5.783),
        "Tb": lambda: bulk("Tb", "hcp", a=3.601, c=5.694), "Dy": lambda: bulk("Dy", "hcp", a=3.591, c=5.651),
        "Ho": lambda: bulk("Ho", "hcp", a=3.577, c=5.617), "Er": lambda: bulk("Er", "hcp", a=3.559, c=5.587),
        "Tm": lambda: bulk("Tm", "hcp", a=3.538, c=5.555), "Yb": lambda: bulk("Yb", "fcc", a=5.485),
        "Lu": lambda: bulk("Lu", "hcp", a=3.505, c=5.551), "Ti": lambda: bulk("Ti", "hcp", a=2.951, c=4.684),
        "Zr": lambda: bulk("Zr", "hcp", a=3.232, c=5.148), "Hf": lambda: bulk("Hf", "hcp", a=3.196, c=5.051),
        "V": lambda: bulk("V", "bcc", a=3.024), "Nb": lambda: bulk("Nb", "bcc", a=3.301),
        "Ta": lambda: bulk("Ta", "bcc", a=3.303), "Cr": lambda: bulk("Cr", "bcc", a=2.884),
        "Mn": lambda: bulk("Mn", "bcc", a=2.910), "Fe": lambda: bulk("Fe", "bcc", a=2.867),
        "Co": lambda: bulk("Co", "hcp", a=2.507, c=4.069), "Ni": lambda: bulk("Ni", "fcc", a=3.524),
        "Cu": lambda: bulk("Cu", "fcc", a=3.615), "Zn": lambda: bulk("Zn", "hcp", a=2.664, c=4.947),
        "Sc": lambda: bulk("Sc", "hcp", a=3.309, c=5.273), "Y": lambda: bulk("Y", "hcp", a=3.648, c=5.731),
        "Al": lambda: bulk("Al", "fcc", a=4.046), "Ga": lambda: bulk("Ga", "fcc", a=4.510),
        "In": lambda: bulk("In", "fcc", a=4.590), "Ge": lambda: bulk("Ge", "diamond", a=5.658),
        "Sn": lambda: bulk("Sn", "diamond", a=6.489), "Pb": lambda: bulk("Pb", "fcc", a=4.951),
        "W": lambda: bulk("W", "bcc", a=3.165), "Mo": lambda: bulk("Mo", "bcc", a=3.147),
        "O": lambda: molecule("O2"), "F": lambda: molecule("F2"), "Cl": lambda: molecule("Cl2"),
        "Br": lambda: bulk("Br", "orthorhombic", a=6.67, b=4.48, c=8.72),
        "I": lambda: bulk("I", "orthorhombic", a=7.27, b=4.79, c=9.79),
        "S": lambda: bulk("S", "fcc", a=6.36), "Se": lambda: bulk("Se", "hcp", a=3.66, c=4.95),
        "Te": lambda: bulk("Te", "hcp", a=4.456, c=5.921), "N": lambda: molecule("N2"),
    }


def reference_energies(elements, calc, log=print):
    structs = _element_structs()
    refs = {}
    for el in sorted(elements):
        if el not in structs:
            log(f"  [warn] no reference phase defined for {el}")
            refs[el] = float("nan")
            continue
        try:
            atoms = structs[el]()
            atoms.calc = calc
            refs[el] = atoms.get_potential_energy() / len(atoms) + GGA_CORRECTIONS.get(el, 0.0)
        except Exception as exc:
            log(f"  [warn] reference energy failed for {el}: {exc}")
            refs[el] = float("nan")
    return refs


def relax(atoms, calc, fmax=0.05, steps=500):
    from ase.filters import FrechetCellFilter
    from ase.optimize import BFGS
    atoms.calc = calc
    try:
        opt = BFGS(FrechetCellFilter(atoms), logfile=None)
        converged = opt.run(fmax=fmax, steps=steps)
        return bool(converged), atoms.get_potential_energy() / len(atoms)
    except Exception:
        return False, float("nan")


def screen(results_dir: str, train_csv: str | None = None, threshold: float = 0.10, device: str = "auto",
           model_path: str = "medium", fmax: float = 0.05, steps: int = 500, log=print) -> pd.DataFrame:
    try:
        from mace.calculators import mace_mp
    except ImportError:
        raise SystemExit("Stability screening needs the optional packages: pip install 'meidnet[stability]'")
    import torch
    from pymatgen.analysis.structure_matcher import StructureMatcher
    from pymatgen.core import Composition, Structure
    from pymatgen.io.ase import AseAtomsAdaptor

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"loading MACE-MP-0 ({model_path}) on {device} ...")
    calc = mace_mp(model=model_path, dispersion=False, default_dtype="float32", device=device)
    cifs = sorted(glob.glob(os.path.join(results_dir, "**", "*.cif"), recursive=True))
    if not cifs:
        raise SystemExit(f"no CIF files under {results_dir}")
    structs, elements = [], set()
    for f in cifs:
        try:
            s = Structure.from_file(f)
            structs.append((f, s))
            elements.update(str(e) for e in s.composition.elements)
        except Exception as e:
            log(f"  [warn] could not read {f}: {e}")
            structs.append((f, None))
    refs = reference_energies(elements, calc, log)
    train_formulas = set()
    if train_csv:
        df = pd.read_csv(train_csv)
        col = next((c for c in df.columns if "formula" in c.lower()), None)
        if col:
            for f in df[col].dropna():
                train_formulas.add(str(f).strip())
                try:
                    train_formulas.add(Composition(f).reduced_formula)
                except Exception:
                    pass
    rows = []
    for path, s in structs:
        rec = {"file": os.path.relpath(path, results_dir), "formula": "?", "dHf": float("nan"), "stable": False,
               "unique": None, "novel": None, "converged": False, "artefact": False}
        if s is None:
            rows.append(rec)
            continue
        rec["formula"] = s.composition.reduced_formula
        comp = {str(e): s.composition[e] for e in s.composition.elements}
        rec["novel"] = rec["formula"] not in train_formulas if train_formulas else None
        atoms = AseAtomsAdaptor.get_atoms(s)
        conv, e_pa = relax(atoms, calc, fmax, steps)
        rec["converged"] = conv
        if np.isnan(e_pa) or any(np.isnan(refs.get(el, float("nan"))) for el in comp):
            rec["artefact"] = True
        else:
            dHf = e_pa - sum(comp[el] * refs[el] for el in comp) / len(atoms)
            rec["dHf"] = dHf
            rec["artefact"] = abs(dHf) > ARTEFACT_THRESHOLD
            rec["stable"] = (not rec["artefact"]) and dHf <= threshold
        log(f"  {rec['file']:<40} {rec['formula']:<10} dHf {rec['dHf']:+.3f} eV/atom  "
            f"{'ARTEFACT' if rec['artefact'] else ('STABLE' if rec['stable'] else 'unstable')}")
        rows.append(rec)
    sm = StructureMatcher(ltol=0.20, stol=0.30, angle_tol=5.0, primitive_cell=True, allow_subset=False)
    kept = []
    for i, (path, s) in enumerate(structs):
        if s is None:
            rows[i]["unique"] = False
            continue
        uniq = True
        for j in kept:
            try:
                if sm.fit(s, structs[j][1]):
                    uniq = False
                    break
            except Exception:
                pass
        rows[i]["unique"] = uniq
        if uniq:
            kept.append(i)
    df = pd.DataFrame(rows)
    valid = df[~df.artefact]
    n = max(len(valid), 1)
    log(f"\nstable {int(valid.stable.sum())}/{n}  unique {int(valid.unique.sum())}/{n}  "
        + (f"novel {int(valid.novel.sum())}/{n}  " if train_formulas else "")
        + f"SUN {int((valid.stable & valid.unique & (valid.novel if train_formulas else True)).sum())}/{n}")
    out = os.path.join(results_dir, "stability.csv")
    df.to_csv(out, index=False)
    log(f"written {out}")
    return df
