"""Reliability map: say IN ADVANCE which targets the pipeline can serve, and how wrong the label is likely to be.

Two things are known to control the error, and both are measurable before any candidate is validated:
  * distance to the training manifold in latent space.  Latent distance is an established, calibrated uncertainty metric:
    tightening a latent-distance cutoff drives predicted errors below training error and gives predictive error control
    (Janet et al., Chem. Sci. 2019, 10, 7913; arXiv:2406.05143 for the general applicability-domain view).
  * training density at the requested property value.  Conditional generators degrade exactly where labels are sparse
    (arXiv:2502.16984).  Perov-5 has 10,936 training materials at 0 eV and 7-22 above 4 eV.

Calibration uses the HELD-OUT TEST SPLIT (thousands of materials with DFT labels), not the handful of generated candidates:
  error(d) = mean |predicted - DFT| for test materials whose latent distance to the training set is d
Application: for a target value, report training density, the latent distance of the material the target's own latent points
at, and the expected label error from the calibration -> a servable / borderline / unreliable verdict per target.
Usage: python reliability_map.py [--ckpt ...] [--data INTAKE] [--gap Eg] [--stability Es] [--query Es=0] [--out DIR]
       (fairchem-env; --data/--gap default to EVAL_DATA/EVAL_GAP, else Perov-5).  With --stability the training density
       counts compositions by their GROUND-STATE gap (lowest stability value over their polymorphs), which is what a
       ground-state target asks for; without it every training record counts.
Writes <out>/reliability_map.csv, <out>/reliability_map.md, <out>/reliability_calibration.csv
"""
import argparse, os, sys
import numpy as np
import pandas as pd
import torch

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
R = f"{HERE}/results"
DATA = os.environ.get("EVAL_DATA")   # required: the dataset folder
from meidnet.benchmark import load_split                      # noqa: E402
from meidnet.checkpoint import load_checkpoint                 # noqa: E402
from meidnet.data import MaterialsDataset                      # noqa: E402
from torch.utils.data import DataLoader                        # noqa: E402


def latents(lm, records, bs=256):
    """Structure latents and the model's property predictions for a list of records."""
    Z, P = [], []
    with torch.no_grad():
        for b in DataLoader(MaterialsDataset(records, lm.stats), batch_size=bs, shuffle=False):
            zc, _ = lm.model.encode_crystal(b["crystal_vec"])
            Z.append(zc.numpy())
            P.append(lm.stats.denormalize_tensor(lm.model.property_decoder(zc)).numpy())
    return np.concatenate(Z), np.concatenate(P)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--targets", type=float, nargs="+", default=[0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6])
    ap.add_argument("--bins", type=int, default=6)
    ap.add_argument("--data", default=os.environ.get("EVAL_DATA", DATA))
    ap.add_argument("--gap", default=os.environ.get("EVAL_GAP"))
    ap.add_argument("--stability", default=os.environ.get("EVAL_STABILITY"),
                    help="stability column; when given, density counts compositions by their ground-state gap")
    ap.add_argument("--query", action="append", default=[], metavar="PROP=VALUE",
                    help="value of a non-target property in the anchor (others sit at the training mean)")
    ap.add_argument("--min-support", type=int, default=30, help="training support below which a target is unreliable")
    ap.add_argument("--out", default=R)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    try:
        from meidnet_eval.stages import announce_dataset
    except ImportError:          # run as a plain script from eval/
        from stages import announce_dataset
    announce_dataset("reliability_map", a.data, target=a.gap, stability=a.stability)
    lm = load_checkpoint(a.ckpt, device="cpu")
    cols = list(lm.stats.columns)
    gap = a.gap or next(c for c in cols if "gap" in c.lower() or c == "Eg"); gi = cols.index(gap)

    train, _ = load_split(a.data, "train", cols, lm.model.max_sites)
    test, _ = load_split(a.data, "test", cols, lm.model.max_sites)
    Ztr, _ = latents(lm, train)
    Zte, Pte = latents(lm, test)
    Ntr = Ztr / np.linalg.norm(Ztr, axis=1, keepdims=True)
    Nte = Zte / np.linalg.norm(Zte, axis=1, keepdims=True)
    y_tr = np.array([r.properties[gi] for r in train])
    y_te = np.array([r.properties[gi] for r in test])
    # latent distance of each test material to the training set (1 - max cosine: 0 = sits on a training point)
    d_te = 1.0 - (Nte @ Ntr.T).max(axis=1)
    err = np.abs(Pte[:, gi] - y_te)

    # ── calibration: error as a function of latent distance, on materials with a gap (the informative regime) ──
    nz = y_te > 0
    qs = np.quantile(d_te[nz], np.linspace(0, 1, a.bins + 1))
    rows = []
    for i in range(a.bins):
        m = nz & (d_te >= qs[i]) & (d_te <= qs[i + 1] if i == a.bins - 1 else d_te < qs[i + 1])
        if m.sum() < 5:
            continue
        rows.append(dict(bin=f"{qs[i]:.4f}-{qs[i+1]:.4f}", n=int(m.sum()), mean_latent_distance=float(d_te[m].mean()),
                         mae_gap=float(err[m].mean()), p90_gap=float(np.quantile(err[m], 0.9))))
    cal = pd.DataFrame(rows)
    cal.to_csv(f"{a.out}/reliability_calibration.csv", index=False)
    print(f"Calibration on the held-out test split ({int(nz.sum())} materials with a gap > 0), "
          f"error vs latent distance to the training set:")
    print(cal.to_string(index=False))
    slope = np.corrcoef(d_te[nz], err[nz])[0, 1]
    print(f"correlation(latent distance, |predicted - DFT|) = {slope:+.2f}  "
          f"({'usable as an uncertainty signal' if slope > 0.2 else 'NOT usable: distance does not predict error here'})")
    print(f"latent-distance range covered by the test split: {d_te[nz].min():.4f}-{d_te[nz].max():.4f} "
          f"(a complete grid leaves no room for this axis to vary: every test material almost touches a training one)")
    # how far the property latent of a target sits from the structure manifold, in the same units
    print(f"for comparison, structure-to-structure latent distances within the data span "
          f"{d_te.min():.4f}-{d_te.max():.4f}; the targets below sit much further out, which is the 0%-from-z_p problem "
          f"expressed as a distance")

    if a.stability:
        from pymatgen.core import Composition
        tr = pd.read_csv(f"{a.data}/train.csv", usecols=["formula", gap, a.stability])
        tr["f"] = tr.formula.map(lambda f: Composition(f).reduced_formula)
        y_density = tr.loc[tr.groupby("f")[a.stability].idxmin(), gap].to_numpy()
        print(f"density counts {len(y_density)} training compositions by their ground-state {gap} "
              f"(lowest {a.stability} over their polymorphs)")
    else:
        y_density = y_tr
    # ── per-target map: training density, where the target's latent points, expected error ──
    # the anchor latent exactly as Designer._anchor_vector builds it: normalised values, the other property at its query
    # value (0 for heat_all, matching the discovery runs), then the property encoder
    anchor = []
    with torch.no_grad():
        for t in a.targets:
            qv = {kv.split("=")[0]: float(kv.split("=")[1]) for kv in a.query}
            legacy = a.data == DATA      # Perov-5: the other property at 0, exactly as in its discovery runs
            vec = [((qv[c] if c in qv else (0.0 if legacy else lm.stats.mean[j])) - lm.stats.mean[j]) / lm.stats.std[j]
                   for j, c in enumerate(cols)]
            vec[gi] = (float(t) - lm.stats.mean[gi]) / lm.stats.std[gi]
            zp = lm.model.encode_properties(torch.tensor([vec], dtype=torch.float32))
            zp = torch.nn.functional.normalize(zp, dim=1)
            cos = (zp.numpy() @ Ntr.T)[0]
            k = int(np.argmax(cos))
            anchor.append(dict(target=t, train_within_0p25=int((np.abs(y_density - t) <= 0.25).sum()),
                               nearest_train_cosine=float(cos[k]), nearest_train_gap=float(y_tr[k]),
                               latent_distance=float(1.0 - cos[k])))
    M = pd.DataFrame(anchor)
    # expected error: the calibration bin the target's latent distance falls into (nearest bin centre)
    # only quote a calibrated error when the target's latent distance is inside the range the calibration covers
    lo, hi = float(cal.mean_latent_distance.min()), float(cal.mean_latent_distance.max())
    usable = slope > 0.2
    M["expected_label_error"] = [float(cal.iloc[int(np.argmin(np.abs(cal.mean_latent_distance - d)))].mae_gap)
                                 if (usable and lo <= d <= hi) else float("nan") for d in M.latent_distance]
    M["in_calibration_range"] = [bool(lo <= d <= hi) for d in M.latent_distance]

    def verdict(r):
        if r.train_within_0p25 < a.min_support:
            return "unreliable (too few training materials at this value)"
        if r.expected_label_error > 1.0:
            return "borderline (calibrated label error above 1 eV)"
        return "servable"
    M["verdict"] = M.apply(verdict, axis=1)
    M.to_csv(f"{a.out}/reliability_map.csv", index=False)
    print("\nPer-target map (decided before generating anything):")
    print(M.to_string(index=False))

    # ── validation: does the map agree with what we measured on the generated candidates? ──
    jc = f"{a.out}/judge_consensus.csv"
    if os.path.exists(jc):
        V = pd.read_csv(jc).dropna(subset=["cgcnn_p5"])
        V["err_vs_judge"] = (V.label_gap - V.cgcnn_p5).abs()
        V["servable"] = V.target.map(dict(zip(M.target, M.verdict == "servable"))).fillna(False)
        g = V.groupby(V.servable)
        print("\nCheck against the validated candidates (label error vs the strongest independent judge):")
        for ok, grp in g:
            print(f"   targets the map called {'servable' if ok else 'unreliable/borderline'}: "
                  f"n={len(grp):2d}, mean |label - CGCNN-P5| {grp.err_vs_judge.mean():.2f} eV, "
                  f"S.U.N. {int(grp.SUN.sum())}")
    with open(f"{a.out}/reliability_map.md", "w") as f:
        f.write("# Reliability map\n\nWhich band-gap targets this model can serve, decided before generation from training "
                "density and latent distance, and calibrated on the held-out test split.\n\n")
        f.write(cal.to_markdown(index=False) + "\n\n" + M.to_markdown(index=False) + "\n")
    print(f"\nwrote {a.out}/reliability_map.md")


if __name__ == "__main__":
    main()
