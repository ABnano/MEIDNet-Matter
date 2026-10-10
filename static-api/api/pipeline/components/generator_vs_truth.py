"""Score the generative path against exact ground truth, which is only possible because this design space is enumerable.

The novel-anion space is small enough to enumerate completely (exhaustive_truth.py builds all of it), so for each target we
can ask the two questions a conditioned sampler must answer, with no sampling uncertainty in the reference:
  recall     of the compositions that are REALLY on target, how many does the generator return?
  precision  of what it returns, how many are really on target?
"Really on target" is decided by the independent CGCNN judge on the relaxed cell, never by the model that proposed the
candidate, and the random baseline is the precision a blind draw from the same rule-valid space would reach.
Scope: this measures target attainment, not stability; stability needs the hull and is applied afterwards.
Usage: python generator_vs_truth.py [--space EX_anion] [--tags AN_x3S ...] [--tol 0.75]    (fairchem-env)
Writes results/generator_vs_truth.csv
"""
import argparse, glob, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); R = f"{HERE}/results"


def load(tag):
    path = f"{R}/{tag}/candidates.csv"
    return pd.read_csv(path) if os.path.exists(path) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default="EX_anion")
    ap.add_argument("--tags", nargs="+", default=["AN_x3S", "AN_OS2", "AN_FS2", "AN_ONS", "AN_OFS", "AN_x3S_s1"])
    ap.add_argument("--tol", type=float, default=0.75, help="a composition is on target within this many eV (judge)")
    ap.add_argument("--cells", default="tensornet")
    a = ap.parse_args()

    space = load(a.space)
    if space is None:
        raise SystemExit(f"no enumerated space at {R}/{a.space}: run exhaustive_truth.py first")
    judge = pd.read_csv(f"{R}/cgcnn_{a.cells}.csv")
    judge["formula"] = judge.file.str.replace(".cif", "", regex=False)
    mlip = pd.read_csv(f"{R}/mlip_compare.csv")[["formula", "same_sg", "da_mlip"]]
    S = space.merge(judge[["formula", "cgcnn_p5"]], on="formula", how="left").merge(mlip, on="formula", how="left")
    S = S.drop_duplicates("formula")
    judged = S.dropna(subset=["cgcnn_p5"])
    print(f"complete space: {len(S)} compositions, {len(judged)} with an independent judge value "
          f"({len(S) - len(judged)} missing a relaxed cell)")

    gen = {}
    for t in a.tags:
        d = load(t)
        if d is not None:
            gen[t] = d

    rows = []
    for target in sorted({float(x) for d in gen.values() for x in d.target.dropna().unique()}):
        truth = set(judged[(judged.cgcnn_p5 - target).abs() <= a.tol].formula)
        if not truth:
            continue
        base = len(truth) / max(len(judged), 1)
        for tag, d in gen.items():
            got = set(d[d.target == target].formula)
            if not got:
                continue
            hit = got & truth
            # only the part of the space this family actually covers is a fair denominator for recall
            fam_space = set(judged[judged.formula.isin(set(d.formula))].formula) | truth
            rows.append(dict(target=target, tag=tag, space_judged=len(judged), truth=len(truth), returned=len(got),
                             on_target=len(hit), precision=len(hit) / len(got), recall=len(hit) / len(truth),
                             random_precision=base))
    V = pd.DataFrame(rows)
    if V.empty:
        raise SystemExit("nothing to compare: no generated candidates carry a judged counterpart")
    V.to_csv(f"{R}/generator_vs_truth.csv", index=False)
    pd.set_option("display.width", 200)
    print("\nPer target and family (truth = the independent judge within "
          f"+-{a.tol:g} eV over the complete enumerated space):")
    print(V.round(3).to_string(index=False))
    print("\nPooled over families, per target:")
    agg = V.groupby("target").apply(lambda g: pd.Series({
        "truth": g.truth.iloc[0], "returned": g.returned.sum(), "precision": np.average(g.precision, weights=g.returned),
        "recall_best_family": g.recall.max(), "random_precision": g.random_precision.iloc[0]}), include_groups=False)
    print(agg.round(3).to_string())
    print(f"\noverall: precision {np.average(V.precision, weights=V.returned):.2f} vs a blind draw "
          f"{V.random_precision.mean():.2f}; best-family recall per target {V.groupby('target').recall.max().mean():.2f}")


if __name__ == "__main__":
    main()
