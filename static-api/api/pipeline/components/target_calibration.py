"""Does a conditionally generated structure have the property that was asked for?  Three numbers per candidate:

* **requested**     - what the user asked for.
* **latent label**  - what the model's property decoder read off the latent it generated from.  Self-reported and not
  evidence: the same network chose the latent and graded it.
* **independent**   - MEGNet multi-fidelity band gap computed from the generated *structure* by a model that played no
  part in generation.  The judge is **qualified first** on the dataset's own test split, so its error is known rather
  than assumed; which of its fidelity heads matches this dataset is also decided by that measurement.

A fourth number, written by `--judge reencode`, is the model's own label **read from the returned structure** (featurise
the cell, encode it, read the property head there).  It is the label this pipeline reports, and the consensus rule
uses it when it exists for a folder's cells (after relaxation, that is the relaxed cell).

Both passes merge into one `calibration.json`, so each can run in whichever environment has its dependencies:
    python target_calibration.py RESULTS --test-csv INTAKE/test.csv --judge megnet [--select 0.5]
    python target_calibration.py RESULTS --judge reencode --ckpt MODEL.pt
Columns are parameters (`--gap-col`, `--id-col`, `--cif-col`), so any dataset's intake works, not only MP-20's.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
from pymatgen.core import Structure

_MEGNET = None


def megnet_gaps(structures, fidelity: int = 0) -> list:
    """MEGNet multi-fidelity band gaps for a list of structures (NaN where the model fails on a cell)."""
    global _MEGNET
    import torch
    if _MEGNET is None:
        import matgl
        _MEGNET = matgl.load_model("MEGNet-BandGap-mfi-MP-2019.4.1")
    out = []
    for s in structures:
        try:
            out.append(max(0.0, float(_MEGNET.predict_structure(s, state_attr=torch.tensor([fidelity])))))
        except Exception:
            out.append(float("nan"))
    return out


def qualify(test_csv: str, n: int, cache: dict, gap_col: str = "band_gap", cif_col: str = "cif",
            fidelities=(0, 1, 2, 3)) -> dict:
    """The judge's own error on this dataset's test split, measured before it is believed.  Every fidelity head is
    tried and the one with the lowest error is used, so the choice of functional is a measurement too."""
    if cache.get("judge_qualification", {}).get("n", 0) >= n:
        return cache["judge_qualification"]
    df = pd.read_csv(test_csv, usecols=lambda c: c in (cif_col, gap_col)).head(n)
    truth, structs = [], []
    for r in df.to_dict("records"):
        try:
            structs.append(Structure.from_str(r[cif_col], fmt="cif"))
            truth.append(float(r[gap_col]))
        except Exception:
            pass
    from scipy.stats import spearmanr
    t = np.array(truth)
    best, by_fidelity = None, {}
    for fid in fidelities:
        p = np.array(megnet_gaps(structs, fid))
        m = ~np.isnan(p)
        if not m.any():
            by_fidelity[fid] = None
            continue
        q = dict(fidelity=fid, n=int(m.sum()), mae=float(np.abs(p[m] - t[m]).mean()),
                 spearman=float(spearmanr(p[m], t[m]).statistic), share_zero_truth=float(np.mean(t[m] == 0)),
                 split=os.path.basename(test_csv), gap_column=gap_col)
        nz = m & (t > 0)
        q["mae_on_nonzero"] = float(np.abs(p[nz] - t[nz]).mean()) if nz.any() else None
        by_fidelity[fid] = q
        if best is None or q["mae"] < best["mae"]:
            best = q
    if best is None:
        raise SystemExit("MEGNet returned nothing for any fidelity")
    best["by_fidelity"] = {str(k): (v["mae"] if v else None) for k, v in by_fidelity.items()}
    return best


def structure_labels(lm, structures, gap_col: str = "band_gap") -> list:
    """The model's own label read from each structure: (value or None, note).  A cell the encoder cannot read (more
    atoms than its max_sites) gets None and the reason, never a value borrowed from the search latent."""
    import torch
    from meidnet.data import featurize, fit_to_max_sites
    cols = list(lm.stats.columns)
    if gap_col not in cols:
        raise SystemExit(f"the model predicts {cols}, not {gap_col}")
    j = cols.index(gap_col)
    out = []
    for s in structures:
        try:
            dense = featurize(fit_to_max_sites(s, lm.model.max_sites), lm.model.max_sites)
            with torch.no_grad():
                zc, _ = lm.model.encode_crystal(torch.from_numpy(dense).float().unsqueeze(0))
                v = lm.stats.denormalize_tensor(lm.model.property_decoder(zc))[0]
            out.append((float(v[j]), ""))
        except ValueError as e:                       # larger than the encoder accepts: recorded, not hidden
            out.append((None, str(e)[:60]))
        except Exception as e:
            out.append((None, type(e).__name__))
    return out


def select_label_only(df: pd.DataFrame, per: dict, window: float) -> pd.DataFrame:
    """Candidates whose structure-read label lies within `window` of the request, when no independent judge exists for
    the property.  One model's reading of its own output: weaker evidence than a consensus, and labelled as such."""
    keep = []
    for _, r in df.iterrows():
        label = per.get(r["file"], {}).get("reencoded_gap")
        if label is None or (isinstance(label, float) and np.isnan(label)):
            continue
        if abs(float(label) - float(r["target"])) <= window:
            row = dict(r)
            row["independent_gap"] = float("nan")
            row["label_structure_gap"] = round(float(label), 3)
            try:
                from pymatgen.core import Composition
                row["charge_balanced"] = bool(Composition(r["formula"]).oxi_state_guesses(max_sites=-1))
            except Exception:
                row["charge_balanced"] = None
            row["judge"] = "none: selected on the structure-read label alone"
            keep.append(row)
    return pd.DataFrame(keep, columns=list(df.columns) + ["independent_gap", "label_structure_gap", "charge_balanced", "judge"])


def select_consensus(df: pd.DataFrame, per: dict, window: float, min_gap: float, judge_text: str) -> pd.DataFrame:
    """Candidates that BOTH the model's structure-read label and the independent judge place within `window` eV of the
    request.  A judged metal (gap below `min_gap`) never satisfies a non-zero request, even when the window arithmetic
    would admit it (0.5 ± 0.5 includes 0).  Two models of different lineage agreeing is the evidence standard here."""
    keep = []
    for _, r in df.iterrows():
        d = per.get(r["file"], {})
        g_ind = d.get("independent_gap")
        if g_ind is None or (isinstance(g_ind, float) and np.isnan(g_ind)):
            continue
        label = d.get("reencoded_gap")                # the label read from THIS folder's cells when it exists
        if label is None or (isinstance(label, float) and np.isnan(label)):
            label = float(r["label_gap"])
        if min_gap and float(r["target"]) > 0 and g_ind < min_gap:
            continue
        if abs(float(label) - float(r["target"])) <= window and abs(g_ind - float(r["target"])) <= window:
            row = dict(r)
            row["independent_gap"] = round(float(g_ind), 3)
            row["label_structure_gap"] = round(float(label), 3)
            # An interpretable flag, not a filter: does a charge-balanced oxidation-state assignment exist?  It has false
            # negatives (peroxides such as Na2O2), so it is shown rather than used to drop candidates.
            try:
                from pymatgen.core import Composition
                row["charge_balanced"] = bool(Composition(r["formula"]).oxi_state_guesses(max_sites=-1))
            except Exception:
                row["charge_balanced"] = None
            row["judge"] = judge_text
            keep.append(row)
    cols = list(df.columns) + ["independent_gap", "label_structure_gap", "charge_balanced", "judge"]
    return pd.DataFrame(keep, columns=cols if not keep else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="folder with candidates.csv and the CIFs it names")
    ap.add_argument("--intake", help="intake folder; its test.csv qualifies the judge unless --test-csv is given")
    ap.add_argument("--test-csv", help="held-out table with CIFs and the true property (default INTAKE/test.csv)")
    ap.add_argument("--gap-col", default="band_gap"); ap.add_argument("--id-col", default="material_id")
    ap.add_argument("--cif-col", default="cif")
    ap.add_argument("--judge", choices=["megnet", "reencode"], required=True)
    ap.add_argument("--ckpt", help="reencode only: the model whose label is read from the returned cells")
    ap.add_argument("--qualify-n", type=int, default=300)
    ap.add_argument("--min-gap", type=float, default=0.1,
                    help="consensus only: a judged metal (gap below this) never satisfies a non-zero request")
    ap.add_argument("--select", type=float, default=None,
                    help="write candidates_consensus.csv: candidates that BOTH the structure-read label and the judge "
                         "place within this many eV of the request")
    a = ap.parse_args()

    path = os.path.join(a.results, "calibration.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    df = pd.read_csv(os.path.join(a.results, "candidates.csv"))
    files = list(df["file"])
    structs = [Structure.from_file(os.path.join(a.results, f)) for f in files]
    per = cache.setdefault("per_candidate", {})
    for f, t, lab in zip(files, df["target"], df["label_gap"]):
        per.setdefault(f, {})["requested"] = float(t)
        per[f]["model_label"] = float(lab)

    if a.judge == "megnet":
        test_csv = a.test_csv or (os.path.join(a.intake, "test.csv") if a.intake else None)
        if not test_csv:
            raise SystemExit("--judge megnet needs --test-csv or --intake to qualify the judge")
        cache["judge_qualification"] = qualify(test_csv, a.qualify_n, cache, a.gap_col, a.cif_col)
        q = cache["judge_qualification"]
        print(f"judge qualification on the test split: n={q['n']}, MAE {q['mae']:.3f} eV, Spearman {q['spearman']:.2f}  "
              f"(of the truth, {100 * q['share_zero_truth']:.0f}% are zero-gap metals; MAE on the non-zero ones "
              f"{q['mae_on_nonzero']:.3f} eV)")
        print(f"  MAE by fidelity index: {q['by_fidelity']}  -> using {q['fidelity']}")
        for f, g in zip(files, megnet_gaps(structs, q["fidelity"])):
            per[f]["independent_gap"] = g
    else:
        if not a.ckpt:
            raise SystemExit("--judge reencode needs --ckpt")
        from meidnet.checkpoint import load_checkpoint
        lm = load_checkpoint(a.ckpt)
        for f, (v, note) in zip(files, structure_labels(lm, structs, a.gap_col)):
            per[f]["reencoded_gap"] = v
            if note:
                per[f]["reencode_error"] = note
    json.dump(cache, open(path, "w"), indent=1)

    t = pd.DataFrame(list(per.values()))
    key = "independent_gap" if "independent_gap" in t else "reencoded_gap"
    if key not in t:
        print("nothing to tabulate yet")
        return
    t = t.dropna(subset=[key])
    print(f"\n{'requested':>10s} {'n':>4s} {'latent label':>13s} {key:>18s} {'|err| vs request':>18s}")
    for req, g in t.groupby("requested"):
        print(f"{req:10.1f} {len(g):4d} {g['model_label'].mean():13.2f} {g[key].mean():18.2f} {np.abs(g[key] - req).mean():18.2f}")
    print(f"\nMAE of the {key.replace('_', ' ')} against what was requested: {np.abs(t[key] - t['requested']).mean():.2f} eV "
          f"over {len(t)} candidates")
    print(f"candidates whose {key.replace('_', ' ')} is within 0.5 eV of the request: "
          f"{int((np.abs(t[key] - t['requested']) <= 0.5).sum())} of {len(t)}")
    if key == "independent_gap":
        print(f"candidates the independent judge calls zero-gap (metal): {int((t[key] <= 0.05).sum())} of {len(t)}")
    print(f"\nwrote {path}")

    if a.select is not None and "independent_gap" in t:
        q = cache.get("judge_qualification", {})
        judge_text = f"MEGNet-mfi fidelity {q.get('fidelity')} (test MAE {q.get('mae', float('nan')):.2f} eV)"
        out = select_consensus(df, per, a.select, a.min_gap, judge_text)
        out.to_csv(os.path.join(a.results, "candidates_consensus.csv"), index=False)   # header even when empty
        print(f"CONSENSUS ({a.select} eV, both judges): {len(out)} of {len(df)} candidates")
        for tgt, g in out.groupby("target") if len(out) else []:
            print(f"   {tgt:4.1f} eV: {len(g):2d}  " + ", ".join(list(g['formula'])[:8]))
    elif a.select is not None and a.judge == "reencode":
        # no independent judge (a property MEGNet cannot read): the selection rests on the structure-read label alone,
        # and the file says so in its `judge` column, so a reader never mistakes it for a two-model consensus
        out = select_label_only(df, per, a.select)
        out.to_csv(os.path.join(a.results, "candidates_consensus.csv"), index=False)
        print(f"SELECTED ({a.select} {a.gap_col}, structure-read label only, no independent judge): {len(out)} of {len(df)} candidates")
        for tgt, g in out.groupby("target") if len(out) else []:
            print(f"   {tgt:6.2f}: {len(g):2d}  " + ", ".join(list(g['formula'])[:8]))


if __name__ == "__main__":
    main()
