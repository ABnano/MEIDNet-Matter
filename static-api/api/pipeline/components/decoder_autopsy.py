"""Why does the decoder recover 64% of compositions on Perov-5 and 1% on a multi-prototype dataset?

Three candidate causes, each measured rather than argued:
  collapse     the decoder predicts the majority species everywhere.  Site accuracy is only meaningful against the
               majority-species baseline (predict the commonest element in every slot), so both are reported.
  cell size    a fixed slot count has to serve 5-, 10-, 20- and 40-atom cells; recovery is therefore split by cell size.
  prototype    73 prototypes share one decoder; recovery is split by prototype as well.
Usage: python decoder_autopsy.py <ckpt> --data <intake dir> [--split test]    (fairchem-env)
"""
import argparse, collections, os, sys
import numpy as np
import pandas as pd
import torch

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from meidnet.benchmark import load_split                       # noqa: E402
from meidnet.checkpoint import load_checkpoint                  # noqa: E402
from meidnet.data import MaterialsDataset, split_dense          # noqa: E402
from torch.utils.data import DataLoader                         # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt"); ap.add_argument("--data", required=True); ap.add_argument("--split", default="test")
    ap.add_argument("--json", help="also write the numbers here (used by discover.py for the generation/screening rule)")
    a = ap.parse_args()
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    lm = load_checkpoint(a.ckpt, device="cpu")
    cols = list(lm.stats.columns)
    recs, _ = load_split(a.data, a.split, cols, lm.model.max_sites)
    proto = {}
    path = f"{a.data}/{a.split}.csv"
    if os.path.exists(path):
        d = pd.read_csv(path, usecols=lambda c: c in ("material_id", "prototype"))
        if "prototype" in d.columns:
            proto = dict(zip(d.material_id.astype(str), d.prototype))

    ms = lm.model.max_sites
    rows, slot_true, slot_pred = [], [], []
    with torch.no_grad():
        for b in DataLoader(MaterialsDataset(recs, lm.stats), batch_size=128, shuffle=False):
            cv = b["crystal_vec"]
            true = split_dense(cv, ms)
            zc, _ = lm.model.encode_crystal(cv)
            _, _, spc, _ = lm.model.crystal_decoder(zc, input_coords=torch.zeros(len(cv), ms, 3),
                                                    center=torch.zeros(len(cv), 3))
            n_sites = (true["species"].sum(-1) > 0).sum(1).numpy()
            for i in range(len(cv)):
                n = int(n_sites[i])
                t = true["species"][i].argmax(-1).numpy()[:n]
                p = spc[i].argmax(-1).numpy()[:n]
                slot_true += list(t); slot_pred += list(p)
                rows.append(dict(n=n, exact=int(np.array_equal(np.sort(t), np.sort(p))),
                                 sites=float((t == p).mean()), n_pred_distinct=len(set(p.tolist()))))
    V = pd.DataFrame(rows)
    for k, r in enumerate(recs):
        V.loc[k, "prototype"] = proto.get(str(r.material_id), "?")
    st, sp = np.array(slot_true), np.array(slot_pred)
    majority = collections.Counter(st.tolist()).most_common(1)[0]
    base = (st == majority[0]).mean()

    print(f"{len(V)} structures, max_sites {ms}, {len(st)} real slots\n")
    print("1) COLLAPSE — is the decoder doing better than predicting the commonest element everywhere?")
    print(f"   majority-species baseline (always predict the commonest element): {100*base:.0f}% of slots")
    print(f"   decoder site accuracy:                                           {100*(st == sp).mean():.0f}% of slots")
    print(f"   distinct elements in the data {len(set(st.tolist())):3d} | distinct elements the decoder ever predicts "
          f"{len(set(sp.tolist())):3d} | predicted per structure, median {V.n_pred_distinct.median():.0f}")
    print(f"   verdict: {'COLLAPSED towards the majority species' if (st == sp).mean() < base + 0.05 else 'genuinely better than the majority baseline'}\n")
    print("2) CELL SIZE — a fixed slot count serving several cell sizes")
    g = V.groupby("n").agg(structures=("exact", "size"), exact_pct=("exact", lambda x: 100 * x.mean()),
                           site_pct=("sites", lambda x: 100 * x.mean()))
    print(g.round(1).to_string())
    print()
    print("3) PROTOTYPE — one decoder shared by many prototypes")
    p = V.groupby("prototype").agg(structures=("exact", "size"), exact_pct=("exact", lambda x: 100 * x.mean()),
                                   site_pct=("sites", lambda x: 100 * x.mean())).sort_values("structures", ascending=False)
    print(p.head(8).round(1).to_string())
    print(f"\noverall: {100*V.exact.mean():.1f}% exact compositions, {100*V.sites.mean():.0f}% sites")
    single = V[V.n == V.n.mode()[0]]
    if a.json:
        import json
        json.dump(dict(structures=len(V), majority_baseline=float(base), site_accuracy=float((st == sp).mean()),
                       exact_composition=float(V.exact.mean()), distinct_elements_data=len(set(st.tolist())),
                       distinct_elements_predicted=len(set(sp.tolist())),
                       by_cell_size={int(k): float(v) for k, v in V.groupby("n").exact.mean().items()}),
                  open(a.json, "w"), indent=1)
    print(f"restricted to the commonest cell size ({int(V.n.mode()[0])} atoms, {len(single)} structures): "
          f"{100*single.exact.mean():.1f}% exact, {100*single.sites.mean():.0f}% sites")


if __name__ == "__main__":
    main()
