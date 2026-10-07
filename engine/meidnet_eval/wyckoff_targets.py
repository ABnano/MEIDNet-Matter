"""Side-car training targets for the symmetry decoder (D1): space group, conventional lattice, symmetry-distinct sites.

The free-coordinate decoder has to predict every atom's position and fails: on MP-20 the cells it emits have a median
volume per atom of 0.0 A^3 and 81% contain atoms closer than 0.7 A.  A crystal is far more compactly described by its
space group plus the few sites that are not related by symmetry — median **4** such sites against a median of 16 atoms in
the conventional cell — and the symmetry operations generate the rest.  That is the representation D1 learns.

This script precomputes those targets as a SIDE-CAR file keyed by material_id, so the data pipeline, `featurize` and the
encoder are untouched: the targets are loaded only when `model.decoder_geometry: wyckoff` is set.

Verified before use: rebuilding with `Structure.from_spacegroup(sg, refined lattice, representative sites)` returns a
StructureMatcher-identical crystal.  Rows that do not rebuild are written with `roundtrip: false` and excluded from
training rather than silently learned as wrong.  Equal atom counts implied structural identity in all 298 structures
checked with StructureMatcher, so the cheap count test is used for the full dataset.

Usage: python wyckoff_targets.py <intake_dir> [--splits train val test] [--symprec 0.1] [--max-sites 16]
Writes <intake_dir>/wyckoff_<split>.json.gz and prints how many structures are usable.
"""
import argparse, gzip, json, os

import numpy as np
import pandas as pd
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer


def targets_for(cif: str, symprec: float, max_sites: int):
    """(space group, lattice parameters, representative species and coordinates) for one structure, or None."""
    s = Structure.from_str(cif, fmt="cif")
    sga = SpacegroupAnalyzer(s, symprec=symprec)
    # get_refined_structure (spglib's idealised cell), NOT get_conventional_standard_structure: the latter's extra
    # Setyawan-Curtarolo transformation leaves coordinates a shade off their special positions, so a site on a mirror
    # plane is read as a general position and symmetry generates twice the atoms.  That silently threw away 48% of all
    # orthorhombic structures, including 408 of the Pnma ones -- the distorted-perovskite space group.  Measured on the
    # structures that had failed: refining rescues 98 of 100, and on 200 that already passed it changes nothing
    # (StructureMatcher-identical in both cases).
    conv = sga.get_refined_structure()
    sga2 = SpacegroupAnalyzer(conv, symprec=symprec)
    sg = int(sga2.get_space_group_number())
    ds = sga2.get_symmetry_dataset()
    eq = list(ds.equivalent_atoms if hasattr(ds, "equivalent_atoms") else ds["equivalent_atoms"])
    reps = sorted(set(eq))
    if len(reps) > max_sites:
        return None, "more symmetry-distinct sites than the head can emit"
    species = [conv[i].specie.symbol for i in reps]
    coords = [list(map(float, conv[i].frac_coords % 1.0)) for i in reps]
    lat = conv.lattice
    try:
        rebuilt = Structure.from_spacegroup(sg, lat, species, coords)
        roundtrip = len(rebuilt) == len(conv)
    except Exception:
        roundtrip = False
    return dict(spacegroup=sg, lattice=[lat.a, lat.b, lat.c, *lat.angles], species=species, coords=coords,
                n_conventional=len(conv), n_reps=len(reps), roundtrip=bool(roundtrip)), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("intake"); ap.add_argument("--splits", nargs="+", default=["train", "val", "test"])
    ap.add_argument("--symprec", type=float, default=0.1); ap.add_argument("--max-sites", type=int, default=16)
    a = ap.parse_args()
    summary = {}
    for split in a.splits:
        path = f"{a.intake}/{split}.csv"
        if not os.path.exists(path):
            continue
        d = pd.read_csv(path, usecols=lambda c: c in ("material_id", "cif"))
        out, skipped = {}, {}
        for r in d.to_dict("records"):
            try:
                t, why = targets_for(r["cif"], a.symprec, a.max_sites)
            except Exception as e:
                t, why = None, type(e).__name__
            if t is None:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            out[str(r["material_id"])] = t
        usable = {k: v for k, v in out.items() if v["roundtrip"]}
        dst = f"{a.intake}/wyckoff_{split}.json.gz"
        with gzip.open(dst, "wt") as f:
            json.dump(out, f)
        reps = [v["n_reps"] for v in usable.values()]
        sgs = len({v["spacegroup"] for v in usable.values()})
        summary[split] = dict(rows=len(d), described=len(out), usable=len(usable), skipped=skipped,
                              distinct_spacegroups=sgs,
                              reps_median=int(np.median(reps)) if reps else 0, reps_max=max(reps) if reps else 0)
        print(f"{split:6s} {len(d):6d} rows -> {len(out):6d} described, {len(usable):6d} round-trip "
              f"({100*len(usable)/max(len(d),1):.0f}%); {sgs} space groups; "
              f"symmetry-distinct sites median {summary[split]['reps_median']}, max {summary[split]['reps_max']}"
              + (f"; skipped {skipped}" if skipped else ""), flush=True)
    json.dump(summary, open(f"{a.intake}/wyckoff_summary.json", "w"), indent=1)
    print(f"\nwrote {a.intake}/wyckoff_<split>.json.gz  (training uses only the round-trip rows)")


if __name__ == "__main__":
    main()
