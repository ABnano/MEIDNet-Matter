"""SUN, MSUN and a continuous SUN, with structure-level uniqueness and novelty — the metrics the field actually uses.

Why this file exists.  What this project has been reporting as "S.U.N." is **MSUN** by the standard naming: it used the
near-hull threshold (E_hull <= 0.1 eV/atom) and judged uniqueness and novelty by **composition**.  That is too weak once a
generator can return several polymorphs of one formula, because two different structures with the same formula are one
composition but two materials.  The definitions below follow the literature:

  stability   strict SUN uses on-hull (E_hull <= 0); metastable MSUN uses the near-hull E_hull <= 0.1 eV/atom.
              MatterGen reports the near-hull form; both are reported here, separately and labelled.
  uniqueness  no match against the rest of the generated set, compared among structures of the same reduced formula
              (MatterGen uses pymatgen's StructureMatcher for this).
  novelty     no match in the reference dataset.
  cSUN        the binary form is sensitive to its thresholds and to small coordinate perturbations, which motivated a
              continuous SUN (arXiv:2510.12405).  The continuous score here is in that spirit but is OUR OWN weighting,
              not a reproduction of theirs, and is labelled as such wherever it is printed.

AMD (average minimum distance, Widdowson & Kurlin) is implemented here rather than imported, since the `amd` package is
not installed.  For each atom in the cell, the distances to its k nearest neighbours in the infinite periodic structure
are sorted; AMD_k is the average of those vectors over the atoms.  It is invariant to the choice of unit cell and to
permuting the atoms, and it changes smoothly when coordinates move — which is exactly what a continuous metric needs and
what a formula-based comparison cannot give.

Usage:
  python metrics_sun.py <validated.csv> --cif-dir DIR --reference-intake INTAKE [--k 10] [--out report.json]
    validated.csv   one row per candidate, with columns: formula, e_hull, and either `file` or `cif`
    --cif-dir       where the relaxed structures live (the AMD comparison needs structures, not formulas)
"""
import argparse, glob, json, os, sys

import numpy as np
import pandas as pd
from pymatgen.core import Composition, Structure

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)


# ───────────────────────────── AMD ─────────────────────────────
def amd(structure: Structure, k: int = 10) -> np.ndarray:
    """AMD_k: for every atom, the sorted distances to its k nearest neighbours, averaged over the atoms.

    Isometry invariant (independent of the cell chosen and of atom order) and continuous in the coordinates, so two
    structures that differ by a small distortion get a small distance — unlike a formula or a space-group label.
    """
    n = len(structure)
    cutoff = max(6.0, 2.2 * float(np.max(structure.lattice.abc)))
    for _ in range(4):                                    # grow the cutoff until every atom really has k neighbours
        rows, enough = [], True
        for nbrs in structure.get_all_neighbors(cutoff):
            d = np.sort([x.nn_distance for x in nbrs])
            if len(d) < k:
                enough = False
                break
            rows.append(d[:k])
        if enough and len(rows) == n:
            return np.asarray(rows).mean(axis=0)
        cutoff *= 1.8
    raise ValueError("could not find k neighbours for every atom")


def amd_distance(a: np.ndarray, b: np.ndarray) -> float:
    """L-infinity between two AMD vectors, the distance used with these descriptors."""
    return float(np.max(np.abs(a - b)))


def safe_amd(s, k):
    try:
        return amd(s, k)
    except Exception:
        return None


# ───────────────────────────── structure matching ─────────────────────────────
def matcher():
    from pymatgen.analysis.structure_matcher import StructureMatcher
    return StructureMatcher(ltol=0.2, stol=0.3, angle_tol=5)      # pymatgen defaults, as used for these metrics


def groups_by_formula(items):
    out = {}
    for it in items:
        out.setdefault(Composition(it["formula"]).reduced_formula, []).append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("table"); ap.add_argument("--cif-dir", required=True)
    ap.add_argument("--reference-intake", default=None, help="intake directory whose structures count as 'known'")
    ap.add_argument("--reference-sample", type=int, default=4000, help="reference structures to compare against (AMD)")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--stable", type=float, default=0.0, help="E_hull for strict SUN")
    ap.add_argument("--metastable", type=float, default=0.1, help="E_hull for MSUN")
    ap.add_argument("--amd-novel", type=float, default=0.3, help="AMD distance beyond which a structure counts as new")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    V = pd.read_csv(a.table)
    items = []
    for r in V.to_dict("records"):
        f = Composition(r["formula"]).reduced_formula
        path = None
        for cand in (os.path.join(a.cif_dir, f"{f}.cif"), os.path.join(a.cif_dir, str(r.get("file", "")))):
            if cand and os.path.exists(cand):
                path = cand; break
        if path is None:
            hit = glob.glob(os.path.join(a.cif_dir, "**", f"{f}.cif"), recursive=True)
            path = hit[0] if hit else None
        if path is None:
            continue
        try:
            s = Structure.from_file(path)
        except Exception:
            continue
        items.append(dict(formula=f, e_hull=float(r.get("e_hull", np.nan)), struct=s, path=path))
    print(f"{len(items)} of {len(V)} candidates have a structure on disk in {a.cif_dir}", flush=True)
    if not items:
        raise SystemExit("no structures found: metrics need structures, not formulas")

    # ── uniqueness: no match against the others, compared within the same reduced formula ──
    sm = matcher()
    for it in items:
        it["amd"] = safe_amd(it["struct"], a.k)
    uniq = []
    for formula, group in groups_by_formula(items).items():
        for i, it in enumerate(group):
            dup = any(sm.fit(it["struct"], other["struct"]) for j, other in enumerate(group) if j < i)
            it["unique"] = not dup
        uniq += group
    n_unique = sum(1 for it in items if it["unique"])
    polymorphs = {f: len(g) for f, g in groups_by_formula(items).items() if len(g) > 1}

    # ── novelty: no match in the reference dataset (structure level, by AMD, and by the matcher where affordable) ──
    ref_amd, ref_struct_by_formula = [], {}
    if a.reference_intake:
        rows = []
        for sp in ("train", "val", "test"):
            p = f"{a.reference_intake}/{sp}.csv"
            if os.path.exists(p):
                rows.append(pd.read_csv(p, usecols=lambda c: c in ("formula", "cif")))
        if rows:
            R = pd.concat(rows, ignore_index=True)
            wanted = {it["formula"] for it in items}
            same = R[R.formula.map(lambda f: Composition(str(f)).reduced_formula).isin(wanted)]
            for r in same.to_dict("records"):                  # exact matcher only where the formula coincides
                try:
                    ref_struct_by_formula.setdefault(Composition(str(r["formula"])).reduced_formula, []).append(
                        Structure.from_str(r["cif"], fmt="cif"))
                except Exception:
                    continue
            samp = R.sample(min(a.reference_sample, len(R)), random_state=0)
            for r in samp.to_dict("records"):                  # AMD against a sample of the whole reference
                try:
                    v = safe_amd(Structure.from_str(r["cif"], fmt="cif"), a.k)
                    if v is not None:
                        ref_amd.append(v)
                except Exception:
                    continue
            print(f"reference: {len(ref_struct_by_formula)} formulas shared with the candidates, "
                  f"{len(ref_amd)} structures described by AMD", flush=True)
    ref_amd = np.asarray(ref_amd) if ref_amd else None

    for it in items:
        same_formula = ref_struct_by_formula.get(it["formula"], [])
        it["novel_matcher"] = not any(sm.fit(it["struct"], rs) for rs in same_formula)
        if it["amd"] is not None and ref_amd is not None and len(ref_amd):
            d = np.max(np.abs(ref_amd - it["amd"]), axis=1)
            it["amd_nearest"] = float(d.min())
        else:
            it["amd_nearest"] = float("nan")
        it["novel_amd"] = (it["amd_nearest"] > a.amd_novel) if it["amd_nearest"] == it["amd_nearest"] else None

    # ── the three metrics ──
    def rate(mask):
        return dict(n=int(sum(mask)), rate=float(np.mean(mask)) if items else 0.0)

    stable = [it["e_hull"] <= a.stable for it in items]
    meta = [it["e_hull"] <= a.metastable for it in items]
    uniqm = [bool(it["unique"]) for it in items]
    novm = [bool(it["novel_matcher"]) for it in items]
    sun = [s and u and n for s, u, n in zip(stable, uniqm, novm)]
    msun = [s and u and n for s, u, n in zip(meta, uniqm, novm)]

    # continuous score: our own weighting, in the spirit of arXiv:2510.12405, not a reproduction of it
    def cont(it, ok_stab):
        st = float(np.exp(-max(it["e_hull"], 0.0) / a.metastable)) if it["e_hull"] == it["e_hull"] else 0.0
        nov = min(it["amd_nearest"] / a.amd_novel, 1.0) if it["amd_nearest"] == it["amd_nearest"] else 0.0
        uni = 1.0 if it["unique"] else 0.0
        return float(st * nov * uni)
    csun = [cont(it, m) for it, m in zip(items, meta)]

    out = dict(candidates=len(items),
               thresholds=dict(stable=a.stable, metastable=a.metastable, amd_novel=a.amd_novel, amd_k=a.k),
               stable_on_hull=rate(stable), metastable_near_hull=rate(meta),
               unique_structure_level=rate(uniqm), novel_structure_level=rate(novm),
               SUN_strict_on_hull=rate(sun), MSUN_near_hull=rate(msun),
               cSUN_mean=float(np.mean(csun)), cSUN_max=float(np.max(csun)) if csun else 0.0,
               polymorph_groups=polymorphs,
               amd_nearest_reference=dict(median=float(np.nanmedian([it["amd_nearest"] for it in items])),
                                          min=float(np.nanmin([it["amd_nearest"] for it in items])),
                                          max=float(np.nanmax([it["amd_nearest"] for it in items]))))
    has_hull = any(it["e_hull"] == it["e_hull"] for it in items)
    out["stability_assessed"] = bool(has_hull)
    if not has_hull:                       # no hull energies given: stability is not a verdict here, it is not computed
        for key in ("stable_on_hull", "metastable_near_hull", "SUN_strict_on_hull", "MSUN_near_hull"):
            out[key] = dict(n=None, rate=None, note="not assessed: no hull energies given (an e_hull column)")
        out["cSUN_mean"] = out["cSUN_max"] = None
    print(f"\n{'metric':34s} {'count':>6s}  rate")
    for key in ("stable_on_hull", "metastable_near_hull", "unique_structure_level", "novel_structure_level",
                "SUN_strict_on_hull", "MSUN_near_hull"):
        if out[key]["n"] is None:
            print(f"{key:34s} {'':6s}  not assessed (no hull energies given)")
        else:
            print(f"{key:34s} {out[key]['n']:6d}  {100*out[key]['rate']:5.1f}%")
    if out["cSUN_mean"] is None:
        print(f"{'cSUN (our weighting, continuous)':34s} {'':6s}  not assessed (no hull energies given)")
    else:
        print(f"{'cSUN (our weighting, continuous)':34s} {'':6s}  mean {out['cSUN_mean']:.3f}, best {out['cSUN_max']:.3f}")
    print(f"\npolymorph groups (one formula, several structures): {len(polymorphs)}"
          + (f" -> {polymorphs}" if polymorphs else ""))
    print(f"AMD distance to the nearest reference structure: median {out['amd_nearest_reference']['median']:.3f}, "
          f"range {out['amd_nearest_reference']['min']:.3f}-{out['amd_nearest_reference']['max']:.3f} "
          f"(a structure counts as new beyond {a.amd_novel})")
    rows = [dict(formula=it["formula"], e_hull=it["e_hull"], unique=it["unique"], novel_matcher=it["novel_matcher"],
                 amd_nearest=it["amd_nearest"], novel_amd=it["novel_amd"], cSUN=c) for it, c in zip(items, csun)]
    pd.DataFrame(rows).to_csv((a.out or "metrics_sun").replace(".json", "") + "_per_candidate.csv", index=False)
    json.dump(out, open(a.out or "metrics_sun.json", "w"), indent=1, default=float)
    print(f"\nwrote {a.out or 'metrics_sun.json'} and the per-candidate table")


if __name__ == "__main__":
    main()
