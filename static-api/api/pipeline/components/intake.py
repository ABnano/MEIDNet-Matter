"""Bring-your-own-dataset intake (step 1 of the general pipeline): audit + prototype detection + fair split.

Input: a CSV with an id column, a CIF column and property columns (as a user would upload).
Output (out_dir): audit.json, audit.md (diagnosis stage 0), prototypes.csv, train.csv / val.csv / test.csv (MEIDNet format).
  * audit: parse failures, atoms per cell, element coverage, per-property statistics (range, zero share, distinct values and
    grid step, shared property profiles), duplicate structures (same composition + space group + Wyckoff letters)
  * prototype: anonymised formula + space group + occupied Wyckoff letters (symprec 0.1), e.g. "ABC3|221|a,b,c"
  * split: grouped by the multiset of elements and their amounts, so compositional twins (e.g. A/B swapped) never straddle splits
Usage: python intake.py <table.csv> <out_dir> --id material_id --cif cif --props band_gap formation_energy_per_atom"""
import argparse, csv, hashlib, json, os, sys
from collections import Counter
import numpy as np
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

csv.field_size_limit(10 ** 9)


def prototype(s):
    try:
        ds = SpacegroupAnalyzer(s, symprec=0.1).get_symmetry_dataset()
        sg = ds.number if hasattr(ds, "number") else ds["number"]
        wy = ds.wyckoffs if hasattr(ds, "wyckoffs") else ds["wyckoffs"]
        eq = ds.equivalent_atoms if hasattr(ds, "equivalent_atoms") else ds["equivalent_atoms"]
        letters = sorted({wy[i] for i in set(eq)})
        occupancy = ",".join(sorted(f"{s[i].specie.symbol}@{wy[i]}" for i in set(eq)))   # which element on which Wyckoff site
        return f"{s.composition.anonymized_formula}|{sg}|{','.join(letters)}", sg, occupancy
    except Exception:
        return f"{s.composition.anonymized_formula}|?|?", 0, "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("table"); ap.add_argument("out")   # table is ignored when --presplit is given
    ap.add_argument("--id", default="material_id"); ap.add_argument("--cif", default="cif"); ap.add_argument("--props", nargs="+", required=True)
    ap.add_argument("--fractions", nargs=3, type=float, default=[0.7, 0.15, 0.15])
    ap.add_argument("--presplit", nargs=3, metavar=("TRAIN", "VAL", "TEST"),
                    help="the dataset already carries its own splits (a benchmark protocol): keep them instead of "
                         "re-splitting, so results stay comparable with published numbers")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.presplit:
        rows, given = [], {}
        for name, path in zip(("train", "val", "test"), a.presplit):
            part = list(csv.DictReader(open(path)))
            for r in part:
                given[r[a.id]] = name
            rows += part
        print(f"using the dataset's own splits: " + ", ".join(f"{n} {sum(1 for v in given.values() if v == n)}"
                                                              for n in ("train", "val", "test")))
    else:
        rows, given = list(csv.DictReader(open(a.table))), None
    ok, fail, protos, dup_keys = [], 0, Counter(), Counter()
    for r in rows:
        try:
            s = Structure.from_str(r[a.cif], fmt="cif")
            props = [float(r[p]) for p in a.props]
        except Exception:
            fail += 1; continue
        proto, sg, occupancy = prototype(s)
        comp = s.composition.reduced_composition
        group = hashlib.md5(str(sorted((e.symbol, float(n)) for e, n in comp.items())).encode()).hexdigest()
        ok.append(dict(id=r[a.id], s=s, props=props, proto=proto, group=group, formula=s.composition.reduced_formula))
        protos[proto] += 1; dup_keys[(s.composition.reduced_formula, proto, occupancy)] += 1
    P = np.array([o["props"] for o in ok])
    audit = {"rows": len(rows), "parsed": len(ok), "failed": fail,
             "atoms_per_cell": dict(Counter(len(o["s"]) for o in ok).most_common()),
             "elements": len({e.symbol for o in ok for e in o["s"].composition.elements}),
             "element_counts": dict(Counter(e.symbol for o in ok for e in o["s"].composition.elements).most_common()),
             "duplicates": int(sum(c - 1 for c in dup_keys.values() if c > 1)),
             "prototypes": len(protos), "top_prototypes": dict(protos.most_common(12)), "properties": {}}
    for j, p in enumerate(a.props):
        v = P[:, j]; vals = np.unique(np.round(v, 6)); steps = np.diff(vals)
        audit["properties"][p] = {"min": float(v.min()), "max": float(v.max()), "mean": float(v.mean()), "median": float(np.median(v)),
                                  "zero_share": float((v == 0).mean()), "distinct": int(len(vals)),
                                  "typical_grid_step": float(np.median(steps)) if len(steps) else None}
    prof = Counter(tuple(np.round(x, 6)) for x in P)
    audit["materials_sharing_profile_with_>=10"] = float(np.mean([prof[tuple(np.round(x, 6))] >= 10 for x in P]))
    # twin-aware split by composition group (deterministic)
    if given:
        which = None                                  # the dataset decides; no composition grouping is imposed on it
    else:
        groups = sorted({o["group"] for o in ok})
        rng = np.random.RandomState(0); rng.shuffle(groups)
        n1, n2 = int(a.fractions[0] * len(groups)), int((a.fractions[0] + a.fractions[1]) * len(groups))
        which = {g: ("train" if i < n1 else "val" if i < n2 else "test") for i, g in enumerate(groups)}
    for split in ("train", "val", "test"):
        with open(f"{a.out}/{split}.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["material_id", "cif", "formula", "prototype", *a.props])
            for o in ok:
                if (given[o["id"]] if given else which[o["group"]]) == split:
                    w.writerow([o["id"], o["s"].to(fmt="cif"), o["formula"], o["proto"], *o["props"]])
    audit["split_sizes"] = dict(Counter((given[o["id"]] if given else which[o["group"]]) for o in ok))
    audit["split_source"] = "the dataset's own splits" if given else "composition-grouped, generated here"
    with open(f"{a.out}/prototypes.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["prototype", "count"]); w.writerows(protos.most_common())
    json.dump(audit, open(f"{a.out}/audit.json", "w"), indent=1)
    with open(f"{a.out}/audit.md", "w") as f:
        f.write(f"# Data audit\n\n{audit['parsed']} of {audit['rows']} structures parsed ({fail} failed); {audit['elements']} elements; "
                f"{audit['prototypes']} prototypes; {audit['duplicates']} duplicates; split {audit['split_sizes']} (composition-grouped).\n\n")
        f.write("| property | min | max | median | zero share | distinct values | grid step |\n|---|---|---|---|---|---|---|\n")
        for p, st in audit["properties"].items():
            f.write(f"| {p} | {st['min']:.3g} | {st['max']:.3g} | {st['median']:.3g} | {100*st['zero_share']:.0f} % | {st['distinct']} | {st['typical_grid_step']} |\n")
        f.write(f"\n{100*audit['materials_sharing_profile_with_>=10']:.0f} % of materials share their property profile with ≥ 9 others "
                f"(property → structure is one-to-many when high).\n\nTop prototypes: {audit['top_prototypes']}\n")
    print(open(f"{a.out}/audit.md").read())


if __name__ == "__main__":
    main()
