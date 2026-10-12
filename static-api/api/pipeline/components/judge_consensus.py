"""Two-judge / two-potential consensus on the generated candidates, so no claim rests on a single model before DFT.

Band gap: four independent judges, none of them MEIDNet.  Each one's accuracy is known from the Perov-5 held-out test split
(meidnet_matter_fidelity_check/models/*_test_metrics.json), so the report states how much each judge deserves to be believed:
  CGCNN-P5     3-seed ensemble trained on the Perov-5 train split, GLLB-SC direct gap   (the quantity MEIDNet predicts)
  CGCNN-MP     pretrained CGCNN on Materials Project PBE gaps                           (different functional, runs low)
  MEGNet-mfi   multi-fidelity MEGNet read out at GLLB-SC                                (used by the first discovery report)
  La analogue  the DFT gap of the candidate's La analogue in Perov-5                    (not a model at all: real DFT)
Stability: the same cell relaxed by TWO potentials (TensorNet and CHGNet, see candidate_cells.py); agreement on the relaxed
space group and lattice constant is reported, because two potentials agreeing is the pre-DFT evidence we can actually get.
A candidate counts as "agreed on target" only when at least MIN_AGREE independent judges put it within TOL of the target.
Usage: python judge_consensus.py [--tol 0.75] [--min-agree 2] [--cells tensornet]   (fairchem-env)
Writes results/judge_consensus.csv and prints the revised shortlist.
"""
import argparse, glob, json, os
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__)); R = f"{HERE}/results"
FID = os.environ.get("MEIDNET_FIDELITY_DIR", "")   # the CGCNN judge checkout, when available
JUDGES = {"cgcnn_p5": "CGCNN-P5 (GLLB-SC, trained on Perov-5)", "megnet_gllbsc_gap": "MEGNet-mfi (GLLB-SC)",
          "cgcnn_mp_pbe": "CGCNN-MP (PBE, pretrained)", "la_analogue_gap": "La analogue, Perov-5 DFT"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=0.75, help="a judge 'agrees' within this many eV of the target")
    ap.add_argument("--min-agree", type=int, default=2, help="independent judges that must agree")
    ap.add_argument("--cells", default="tensornet", choices=["raw", "tensornet", "chgnet"])
    a = ap.parse_args()

    V = pd.read_csv(f"{R}/discovery_report.csv")
    M = pd.read_csv(f"{R}/mlip_compare.csv")[["formula", "a_tensornet", "a_chgnet", "da_mlip", "sg_tensornet", "sg_chgnet", "same_sg"]]
    V = V.merge(M, on="formula", how="left")
    for cells in ("raw", "tensornet", "chgnet"):
        f = f"{R}/cgcnn_{cells}.csv"
        if not os.path.exists(f):
            continue
        C = pd.read_csv(f)
        C["formula"] = C.file.str.replace(".cif", "", regex=False)
        C = C.rename(columns={"cgcnn_p5": f"cgcnn_p5_{cells}", "cgcnn_mp_pbe": f"cgcnn_mp_pbe_{cells}",
                              "cgcnn_p5_spread": f"cgcnn_p5_spread_{cells}"})
        V = V.merge(C.drop(columns=["file"]), on="formula", how="left")
    for k in ("cgcnn_p5", "cgcnn_mp_pbe"):                      # the chosen cell set is the judge of record
        V[k] = V[f"{k}_{a.cells}"]

    # how much each judge deserves to be believed, measured on the Perov-5 test split (no new computation)
    rel = {}
    for f in sorted(glob.glob(f"{FID}/models/*_test_metrics.json")):
        m = json.load(open(f))
        rel[os.path.basename(f).replace("_test_metrics.json", "")] = m
    print("Judge reliability on the Perov-5 held-out test split (3785 compounds, 151 with a gap > 0):")
    for k, m in sorted(rel.items(), key=lambda kv: kv[1]["mae_nonzero"]):
        print(f"  {m['model']:42s} MAE(gap>0) {m['mae_nonzero']:.2f} eV | r {m['pearson_nonzero']:+.2f} | "
              f"metal/non-metal {100 * m['metal_vs_gap_accuracy']:.0f}%")

    print(f"\nTarget following on the {len(V)} generated candidates (cells: {a.cells}-relaxed):")
    for k, name in JUDGES.items():
        d = V.dropna(subset=[k])
        if len(d) < 3:
            continue
        rho = spearmanr(d.target, d[k])[0]
        print(f"  {name:42s} rho(target, judge) {rho:+.2f} | mean |judge - target| {np.abs(d[k] - d.target).mean():.2f} eV | "
              f"within +-{a.tol:g} eV: {int((np.abs(d[k] - d.target) <= a.tol).sum())}/{len(d)}")
    print(f"  {'MEIDNet own label (not independent)':42s} rho(target, label) {spearmanr(V.target, V.label_gap)[0]:+.2f}")

    agree = pd.DataFrame({k: (V[k] - V.target).abs() <= a.tol for k in JUDGES})
    V["judges_agreeing"] = agree.sum(axis=1)
    V["judges_available"] = V[list(JUDGES)].notna().sum(axis=1)
    V["agreed_on_target"] = V.judges_agreeing >= a.min_agree
    V["mlip_agree"] = V.same_sg.fillna(False) & (V.da_mlip <= 0.1)
    V["SUN_consensus"] = V.SUN & V.formable & V.agreed_on_target & V.mlip_agree
    V.to_csv(f"{R}/judge_consensus.csv", index=False)

    print(f"\nTwo potentials on the same cells: same relaxed space group {int(V.same_sg.sum())}/{int(V.same_sg.notna().sum())}, "
          f"median |da| {V.da_mlip.median():.3f} A, worst {V.da_mlip.max():.3f} A")
    print(f"Candidates with >= {a.min_agree} independent judges within +-{a.tol:g} eV: {int(V.agreed_on_target.sum())}/{len(V)} "
          f"| S.U.N. {int(V.SUN.sum())} -> S.U.N. with judge AND potential consensus: {int(V.SUN_consensus.sum())}")
    cols = ["formula", "target", "label_gap", "cgcnn_p5", "megnet_gllbsc_gap", "cgcnn_mp_pbe", "la_analogue_gap",
            "judges_agreeing", "e_hull", "sg_tensornet", "da_mlip", "SUN", "SUN_consensus"]
    pd.set_option("display.width", 220)
    print("\nAll S.U.N. candidates (judges that agree, most first):")
    print(V[V.SUN].sort_values(["judges_agreeing", "e_hull"], ascending=[False, True])[cols].round(2).to_string(index=False))
    print(f"\nShortlist for DFT — S.U.N., formable, >= {a.min_agree} judges agree, both potentials agree:")
    for t, g in V[V.SUN_consensus].sort_values("e_hull").groupby("target"):
        print(f"  {t:g} eV: " + ", ".join(f"{r.formula} (E_hull {r.e_hull:.3f}, CGCNN-P5 {r.cgcnn_p5:.2f}, "
                                         f"analogue {r.la_analogue_gap:.1f}, {r.judges_agreeing} judges)" for r in g.itertuples()))


if __name__ == "__main__":
    main()
