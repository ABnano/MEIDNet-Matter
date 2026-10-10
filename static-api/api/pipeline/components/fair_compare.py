"""Fair comparison (answers the X-ray skeptics): metrics on DISTINCT (target, composition) pairs, and a matched oracle that
returns, per target, the same number of distinct compositions as the method, chosen by DFT closeness among the family's
valid known compositions (dHf <= 1).  Usage: python fair_compare.py TAG [TAG ...]   (needs results/all_candidates_enriched.csv)"""
import os
import sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr

R = os.environ.get("EVAL_ENRICHED", "results/all_candidates_enriched.csv")
def metrics(p):
    p = p.dropna(subset=["dft_gap"])
    rho = spearmanr(p.target, p.dft_gap)[0] if p.target.nunique() > 1 and len(p) > 3 else float("nan")
    hits = 100 * float(((p.dft_gap - p.target).abs() <= 0.3 + 1e-9).mean()) if len(p) else float("nan")
    nz = p[p.target > 0]
    hits_nz = 100 * float(((nz.dft_gap - nz.target).abs() <= 0.3 + 1e-9).mean()) if len(nz) else float("nan")
    return len(p), rho, hits, hits_nz

def main():
    """The script's work; nothing runs on import."""
    d = pd.read_csv(R)
    valid = d[d.tag == "R"].drop_duplicates("site_key")            # R samples valid compositions; use the full valid set below
    try:
        from meidnet_eval.eval_analyse import valid_compositions, MATERIALS
    except ImportError:          # run as a plain script from eval/
        from eval_analyse import valid_compositions, MATERIALS
    V, _ = valid_compositions()
    V = pd.DataFrame(V); V["site_key"] = V.site_A + "|" + V.site_B + "|" + V.site_X
    m = pd.read_csv(MATERIALS).dropna(subset=["site_key"]).drop_duplicates("site_key").set_index("site_key")
    V["dft_gap"] = V.site_key.map(m.dir_gap); V["dft_dhf"] = V.site_key.map(m.heat_all)
    K = V.dropna(subset=["dft_gap"]); K = K[K.dft_dhf <= 1.0]




    print(f"{'tag':7s} {'pairs':>5s} {'rho':>6s} {'hits':>6s} {'hits>0eV':>8s} | {'oracle rho':>10s} {'oracle hits':>11s} {'oracle >0':>9s}")
    for tag in sys.argv[1:]:
        g = d[d.tag == tag].drop_duplicates(["target", "site_key"])
        n, rho, hits, hnz = metrics(g)
        orc = []
        for t, gt in g.groupby("target"):
            k = gt.site_key.nunique()
            orc.append(K.assign(dist=(K.dft_gap - t).abs()).nsmallest(k, "dist").assign(target=t))
        o = pd.concat(orc) if orc else g.iloc[:0]
        _, orho, ohits, ohnz = metrics(o)
        print(f"{tag:7s} {n:5d} {rho:+6.2f} {hits:5.0f}% {hnz:7.0f}% | {orho:+10.2f} {ohits:10.0f}% {ohnz:8.0f}%")


if __name__ == "__main__":
    main()
