"""Evidence check for Option A ("aim with the alignment, sample between nearest REAL structure latents, decode, verify")
before building it.  No search, no training — measures the two assumptions directly from a trained model:

  AIM:    for each band-gap target t, the property latent z_p(t) is compared (cosine) with the structure latents z_c of the
          training materials.  Do the K nearest real structures have DFT gaps that follow t?  (all training materials, and
          only the demo family's valid Pb-free ABO3 compositions)
  DECODE: latents sampled BETWEEN those nearest family neighbours (random convex mixes on the unit sphere) are decoded
          greedily (family pools, last group charge-compatible).  Do the decoded compositions keep a gap that follows t?

  python feasibility_A.py <ckpt> [dHf_target ...]
"""
import csv, os, sys
import numpy as np, pandas as pd, torch, torch.nn.functional as F
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
try:
    from meidnet_eval.eval_generate import goal, reference_latents
except ImportError:          # run as a plain script from eval/
    from eval_generate import goal, reference_latents
try:
    from meidnet_eval.eval_analyse import valid_compositions, MATERIALS
except ImportError:          # run as a plain script from eval/
    from eval_analyse import valid_compositions, MATERIALS
from meidnet.checkpoint import load_checkpoint
from meidnet.chem import element_index
from meidnet.generate import Designer
from meidnet.pipeline import family_for

DATA = os.environ.get("EVAL_DATA")   # required: the dataset folder
csv.field_size_limit(10 ** 9)
TARGETS = [0, 1, 2, 3, 4, 5, 6]


def hits(dft, t):
    dft = np.asarray(dft, float)
    return 100 * float((np.abs(dft - t) <= 0.3 + 1e-9).mean()), 100 * float((np.abs(dft - t) < 0.3 - 1e-9).mean())


def main():
    ckpt = sys.argv[1]
    dhfs = [float(x) for x in sys.argv[2:]] or [1.0, 0.0]
    torch.set_num_threads(4)
    lm = load_checkpoint(ckpt, device="cpu"); M = lm.model.eval(); st = lm.stats
    Zc = reference_latents(lm, ckpt)                                   # training split, CSV order
    Zc = Zc / np.linalg.norm(Zc, axis=1, keepdims=True)
    ids = [r["material_id"] for r in csv.DictReader(open(f"{DATA}/train.csv"))]
    mats = pd.read_csv(MATERIALS).set_index("material_id")
    tr = mats.loc[[int(i) for i in ids]].reset_index()
    V, _ = valid_compositions()
    vkeys = {f"{v['site_A']}|{v['site_B']}|{v['site_X']}" for v in V}
    fam_mask = tr.site_key.isin(vkeys).values
    print(f"{ckpt.split('/')[-3]}: {len(tr)} training materials, {int(fam_mask.sum())} of them valid demo-family compositions")

    cfg = goal(2.0, 1, 6, label_source="structure", latent_space="sphere")
    fam = family_for(cfg, need_variant=True)
    d = Designer(lm, fam, cfg.generation, device=torch.device("cpu"), log=lambda *x: None)
    by_key = mats.dropna(subset=["site_key"]).drop_duplicates("site_key").set_index("site_key")

    def decode(Z):
        with torch.no_grad():
            coords, center = d._decoder_in(Z.shape[0])
            _, _, spc, _ = M.crystal_decoder(torch.as_tensor(Z, dtype=torch.float32), input_coords=coords, center=center,
                                             species_mask=d.mask)
        out = []
        for i in range(Z.shape[0]):
            chosen = {}
            for g in fam.sampling_order:
                grp = fam.groups[g]
                pool = list(grp.sample) if g != fam.sampling_order[-1] else d._charge_compatible(grp, chosen)
                if not pool:
                    break
                v = spc[i][grp.slots][:, [element_index(e) for e in pool]].sum(dim=0)
                chosen[g] = pool[int(v.argmax())]
            out.append(f"{chosen.get('A')}|{chosen.get('B')}|{chosen.get('X')}" if len(chosen) == 3 and len(set(chosen.values())) == 3 else None)
        return out

    rng = np.random.RandomState(0)
    for dhf in dhfs:
        print(f"\n--- property query: dHf target {dhf:g} eV/atom ---")
        rows_all, rows_fam, rows_dec = [], [], []
        for t in TARGETS:
            x = torch.tensor(st.normalize(np.array([[dhf if c == "heat_all" else t for c in st.columns]])), dtype=torch.float32)
            with torch.no_grad():
                zp = M.encode_properties(x)[0].numpy()
            cos = Zc @ zp
            top_all = np.argsort(-cos)[:20]
            fi = np.where(fam_mask)[0]; top_fam = fi[np.argsort(-cos[fi])[:5]]
            rows_all += [(t, tr.dir_gap[i]) for i in top_all]
            rows_fam += [(t, tr.dir_gap[i], tr.site_key[i]) for i in top_fam]
            # DECODE: 60 random convex mixes of the 5 nearest family structures, projected to the unit sphere
            w = rng.dirichlet(np.ones(len(top_fam)) * 0.5, size=60)
            Zs = w @ Zc[top_fam]; Zs /= np.linalg.norm(Zs, axis=1, keepdims=True)
            for k in decode(Zs):
                rows_dec.append((t, by_key.dir_gap.get(k, np.nan) if k else np.nan, k, k in set(tr.site_key[top_fam]) if k else False))
        A = pd.DataFrame(rows_all, columns=["t", "gap"]); Fm = pd.DataFrame(rows_fam, columns=["t", "gap", "key"])
        D = pd.DataFrame(rows_dec, columns=["t", "gap", "key", "is_neighbour"]); Dk = D.dropna(subset=["gap"])
        for name, df in (("AIM, 20 nearest of ALL training materials", A), ("AIM, 5 nearest demo-family compounds", Fm),
                         ("DECODE, 60 mixes of those 5 per target", Dk)):
            h_inc, h_str = hits(df.gap, df.t)
            nz = df[df.t > 0]; hn_inc, hn_str = hits(nz.gap, nz.t) if len(nz) else (np.nan, np.nan)
            print(f"{name:42s} rho {spearmanr(df.t, df.gap)[0]:+.2f} | hits {h_inc:4.0f}% (strict {h_str:3.0f}%) | "
                  f"targets>0: {hn_inc:4.0f}% (strict {hn_str:3.0f}%) | mean DFT gap per target: "
                  + " ".join(f"{g:.1f}" for g in df.groupby('t').gap.mean().reindex(TARGETS).values))
        print(f"   decode: {D.key.notna().mean()*100:.0f}% valid, {Dk.shape[0]/len(D)*100:.0f}% known, "
              f"{D.is_neighbour.mean()*100:.0f}% decode to one of the 5 neighbours, {D.key.nunique()} distinct compositions")
        print("   5 nearest family compounds per target: " + "; ".join(
            f"{t}: " + ",".join(f"{k.split('|')[0]}{k.split('|')[1]}({g:g})" for _, g, k in Fm[Fm.t == t].itertuples(index=False))
            for t in TARGETS))


if __name__ == "__main__":
    main()
