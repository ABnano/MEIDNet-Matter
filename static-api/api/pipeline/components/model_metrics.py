"""Held-out diagnostics of a MEIDNet checkpoint (Perov-5 test split) for the interpretability part of the ablation.

  python model_metrics.py <tag> <checkpoint> [out.json]

Reports
  property_prediction  structure-only predictions (structure -> z_c -> property decoder): MAE/R2, MAE on gap > 0,
                       Pearson r on gap > 0, metal/non-metal accuracy (gap < 0.5 eV called metallic)
  representation       retrieval z_c <-> z_p among distinct property profiles, latent 5-NN property error, cosines
  recoverability       species decoded (argmax per site, zero start coordinates as at generation time) from the joint,
                       property-only and structure-only latents: exact composition %, site accuracy %
"""
import json, os, sys
import numpy as np
import torch
from torch.utils.data import DataLoader

from meidnet.benchmark import evaluate_checkpoint
from meidnet.checkpoint import load_checkpoint
from meidnet.benchmark import load_split
from meidnet.data import MaterialsDataset, split_dense

DATA = os.environ.get("EVAL_DATA")   # required: the dataset folder


def recoverability(lm, test):
    model, ms = lm.model.eval(), lm.model.max_sites
    acc = {p: [0, 0, 0, 0] for p in ("from_joint", "from_property", "from_structure")}  # n, comp_exact, sites_ok, sites
    with torch.no_grad():
        for b in DataLoader(MaterialsDataset(test, lm.stats), batch_size=256, shuffle=False):
            cv, props = b["crystal_vec"], b["props"]
            true = split_dense(cv, ms)
            n_sites = (true["species"].sum(-1) > 0).sum(1).numpy()
            zc, zp, zj, *_ = model.encode_modalities(cv, props)
            zeros, c0 = torch.zeros(len(cv), ms, 3), torch.zeros(len(cv), 3)
            for path, z in (("from_joint", zj), ("from_property", zp), ("from_structure", zc)):
                _, _, spc, _ = model.crystal_decoder(z, input_coords=zeros, center=c0)
                a = acc[path]
                for i in range(len(cv)):
                    n = int(n_sites[i])
                    t = true["species"][i].argmax(-1).numpy()[:n]
                    p = spc[i].argmax(-1).numpy()[:n]
                    a[0] += 1; a[1] += int(np.array_equal(np.sort(t), np.sort(p))); a[2] += int((t == p).sum()); a[3] += n
    return {k: {"composition_exact_pct": 100.0 * a[1] / a[0], "site_accuracy_pct": 100.0 * a[2] / a[3], "n": a[0]}
            for k, a in acc.items()}


def main(tag, ckpt, out=None, data=None):
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    data = data or DATA                      # any intake directory with train/val/test.csv works, not only Perov-5
    try:
        from meidnet_eval.stages import announce_dataset
    except ImportError:          # run as a plain script from eval/
        from stages import announce_dataset
    announce_dataset("model_metrics", data or DATA)
    lm = load_checkpoint(ckpt, device="cpu")
    ev = evaluate_checkpoint(lm, data)
    cols = list(lm.stats.columns)
    gap_col = os.environ.get("EVAL_GAP") or next((c for c in cols if "gap" in c.lower() or c == "Eg"), None)
    pred = ev.predictions
    extra = {}
    for c in cols:
        y = np.array([p[f"true_{c}"] for p in pred]); q = np.array([p[f"pred_{c}"] for p in pred])
        nz = y != 0
        extra[f"pearson_{c}_nonzero"] = float(np.corrcoef(y[nz], q[nz])[0, 1]) if nz.sum() > 2 else float("nan")
        if c == gap_col:
            extra["metal_vs_gap_accuracy"] = float(((q < 0.5) == (y == 0)).mean())
    test, _ = load_split(data, "test", cols, lm.model.max_sites)
    rec = recoverability(lm, test)
    res = {"tag": tag, "checkpoint": ckpt, "data": data, "property_prediction": {**ev.property_prediction, **extra},
           "representation": ev.representation, "recoverability": rec}
    out = out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "model_metrics", f"{tag}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "w"), indent=1)
    pp, rp = res["property_prediction"], res["representation"]
    other = [c for c in cols if c != gap_col]
    print(f"{tag}: {gap_col} MAE {pp[f'mae_{gap_col}']:.3f} (>0 {pp.get(f'mae_{gap_col}_nonzero', float('nan')):.2f}, "
          f"r {pp[f'pearson_{gap_col}_nonzero']:+.2f}, metal acc {100 * pp['metal_vs_gap_accuracy']:.0f}%) | "
          + " ".join(f"{c} MAE {pp[f'mae_{c}']:.3f} r2 {pp[f'r2_{c}']:.2f}" for c in other)
          + f" | retrieval@1 {rp['retrieval_top1']:.2f} @5 {rp['retrieval_top5']:.2f} | "
          f"kNN {gap_col} {rp[f'knn_mae_{gap_col}']:.3f} | "
          + " ".join(f"{k}: comp {v['composition_exact_pct']:.0f}% sites {v['site_accuracy_pct']:.0f}%" for k, v in rec.items()), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
