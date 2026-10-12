"""Trust test for elements never seen in training: models trained WITHOUT any La or Y compound predict the properties of all
Perov-5 compounds that contain La or Y (none seen in training), from their structure alone; compared with DFT, and with the
same model's error on ordinary held-out test compounds.  Usage: python unseen_element_test.py <ckpt> [<ckpt> ...]"""
import csv, os, re, sys
import numpy as np, torch
from meidnet.checkpoint import load_checkpoint
from meidnet.data import parse_structure, order_perovskite_sites, featurize

DATA = os.environ.get("EVAL_DATA")   # required: the dataset folder
csv.field_size_limit(10 ** 9)
UNSEEN = set(os.environ.get("UNSEEN", "La,Y").split(","))   # elements absent from the tested model's training data


def rows(split, laY):
    out = []
    for r in csv.DictReader(open(f"{DATA}/{split}.csv")):
        has = bool(UNSEEN & set(re.findall(r"[A-Z][a-z]?", r["formula"])))
        if has == laY:
            out.append(r)
    return out


def predict(lm, rs):
    site_order = lm.raw_config.get("data", {}).get("site_order", "file") if hasattr(lm, "raw_config") else "perovskite"
    X = []
    for r in rs:
        s = parse_structure(cif_text=r["cif"])
        s = order_perovskite_sites(s, r["formula"])
        X.append(featurize(s, lm.model.max_sites))
    with torch.no_grad():
        zc, _ = lm.model.encode_crystal(torch.tensor(np.stack(X), dtype=torch.float32))
        P = lm.stats.denormalize_tensor(lm.model.property_decoder(zc)).numpy()
    return P


def report(name, P, rs, cols):
    gi, hi = cols.index("dir_gap"), cols.index("heat_all")
    y = np.array([float(r["dir_gap"]) for r in rs]); h = np.array([float(r["heat_all"]) for r in rs])
    nz = y > 0
    gap_nz = np.abs(P[nz, gi] - y[nz]).mean() if nz.any() else float("nan")
    r_nz = np.corrcoef(P[nz, gi], y[nz])[0, 1] if nz.sum() > 2 else float("nan")
    metal = ((P[:, gi] < 0.5) == (y == 0)).mean()
    print(f"   {name:34s} n={len(rs):5d} (non-metals {int(nz.sum()):3d}) | gap MAE non-metals {gap_nz:.2f} eV, r {r_nz:+.2f} | "
          f"metal/non-metal {100*metal:.0f}% | dHf MAE {np.abs(P[:, hi] - h).mean():.3f} eV/atom")
    return dict(n=len(rs), n_nonmetal=int(nz.sum()), gap_mae_nonmetal=float(gap_nz), gap_r_nonmetal=float(r_nz),
                metal_accuracy=float(metal), dhf_mae=float(np.abs(P[:, hi] - h).mean()))


OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "unseen")
os.makedirs(OUT, exist_ok=True)
for ck in sys.argv[1:]:
    lm = load_checkpoint(ck, device="cpu"); cols = list(lm.stats.columns)
    laY = rows("train", True) + rows("val", True) + rows("test", True)
    test = rows("test", False)
    tag = ck.split("/")[-3]
    print(tag)
    seen = report("ordinary test compounds (no La/Y)", predict(lm, test), test, cols)
    unseen = report("UNSEEN-element compounds (La or Y)", predict(lm, laY), laY, cols)
    import json
    json.dump(dict(tag=tag, checkpoint=ck, held_out_elements=sorted(UNSEEN), seen=seen, unseen=unseen),
              open(f"{OUT}/{tag}_{'-'.join(sorted(UNSEEN))}.json", "w"), indent=1)
