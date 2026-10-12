"""Does the latent search itself steer towards the target (generation), or do only the filters do the work (screening)?

For each target and seed: run the engine's latent optimisation (Designer.optimise), then decode EVERY final latent
greedily (most likely element per site within the family pools, last group charge-compatible) with NO property window,
NO ranking and NO dedup.  If the raw proposals' band gaps (DFT where Perov-5 has the composition, else the model's
structure prediction) rise with the target, the search steers.  Compared with random proposals (no optimisation,
random start) under identical decoding.

  python steer_test.py <tag> <ckpt> [--set key=value ...]
"""
import argparse, json, os, sys
import numpy as np, pandas as pd, torch
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from meidnet_eval.eval_generate import goal, reference_latents, reference_pool
except ImportError:          # run as a plain script from eval/
    from eval_generate import goal, reference_latents, reference_pool
from meidnet.checkpoint import load_checkpoint
from meidnet.constraints import build_candidate
from meidnet.generate import Designer
from meidnet.chem import element_index
from meidnet.pipeline import family_for

MATERIALS = os.environ.get("EVAL_MATERIALS")   # the published materials table; required



def _value(v):
    """--set values: true/false, int, float, else the string itself (e.g. label_source=structure)."""
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag"); ap.add_argument("ckpt")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--query", action="append", default=[])
    ap.add_argument("--pool", choices=["all", "family"], default="all")
    ap.add_argument("--targets", type=float, nargs="+", default=[0, 1, 2, 3, 4, 5, 6])
    ap.add_argument("--seeds", type=int, nargs="+", default=[101, 202, 303])
    a = ap.parse_args()
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    lm = load_checkpoint(a.ckpt, device="cpu")
    sw = {}
    for kv in a.set:
        k, v = kv.split("=", 1)
        sw[k] = _value(v)
    if a.query:
        sw["query_values"] = {kv.split("=")[0]: float(kv.split("=")[1]) for kv in a.query}
    need_ref = sw.get("manifold_weight", 0) > 0 or sw.get("search_mode") == "neighbours"
    ref = reference_pool(lm, a.ckpt, a.pool) if need_ref else None
    mats = pd.read_csv(MATERIALS).dropna(subset=["site_key"]).drop_duplicates("site_key").set_index("site_key")
    rows = []
    for t in a.targets:
        for seed in a.seeds:
            cfg = goal(t, seed, 6, **sw)
            fam = family_for(cfg, need_variant=True)
            d = Designer(lm, fam, cfg.generation, device=torch.device("cpu"), log=lambda *x: None, reference_latents=ref)
            tvals = [float(cfg.generation.targets[0][o["property"]]) for o in d.objectives]
            _, Z = d.propose(cfg.generation.population, cfg.generation.targets[0], tvals, seed, None, 1)
            coords, center = d._decoder_in(Z.size(0))
            with torch.no_grad():
                _, _, spc, _ = lm.model.crystal_decoder(Z, input_coords=coords, center=center, species_mask=d.mask)
            for i in range(Z.size(0)):
                chosen = {}
                for g in fam.sampling_order:
                    grp = fam.groups[g]
                    pool = list(grp.sample) if g != fam.sampling_order[-1] else d._charge_compatible(grp, chosen)
                    if not pool:
                        break
                    idx = [element_index(e) for e in pool]
                    v = spc[i][grp.slots][:, idx].sum(dim=0)
                    chosen[g] = pool[int(v.argmax())]
                if len(chosen) < len(fam.groups) or len(set(chosen.values())) < len(chosen):
                    rows.append(dict(target=t, seed=seed, valid=False)); continue
                cand = build_candidate(fam, chosen)
                lab = d._structure_predictions(cand)
                key = f"{chosen['A']}|{chosen['B']}|{chosen['X']}"
                dft = mats.dir_gap.get(key, np.nan)
                rows.append(dict(target=t, seed=seed, valid=True, formula=cand.formula(), key=key, label_gap=lab["dir_gap"],
                                 dft_gap=dft, split=mats.split.get(key, "novel"), z_norm=float(Z[i].norm())))
    df = pd.DataFrame(rows)
    out = os.path.join(HERE, "results", "steer", a.tag); os.makedirs(out, exist_ok=True)
    df.to_csv(f"{out}/proposals.csv", index=False)
    v = df[df.valid]
    known = v.dropna(subset=["dft_gap"])
    rho_dft = spearmanr(known.target, known.dft_gap)[0] if len(known) > 3 else float("nan")
    rho_lab = spearmanr(v.target, v.label_gap)[0] if len(v) > 3 else float("nan")
    per = v.groupby("target").agg(n=("formula", "size"), distinct=("formula", "nunique"), label=("label_gap", "mean"),
                                  dft=("dft_gap", "mean"), known=("dft_gap", lambda s: int(s.notna().sum())))
    hits = float(((known.dft_gap - known.target).abs() <= 0.3 + 1e-9).mean() * 100) if len(known) else float("nan")
    summary = dict(tag=a.tag, settings=a.set, proposals=len(df), valid=int(v.shape[0]), known=int(len(known)),
                   distinct=int(v.formula.nunique()), rho_target_dft=float(rho_dft), rho_target_label=float(rho_lab),
                   raw_hit_pct=hits, per_target=per.round(2).reset_index().to_dict(orient="records"))
    json.dump(summary, open(f"{out}/summary.json", "w"), indent=1)
    print(f"{a.tag}: {len(df)} raw proposals, {len(v)} valid, {v.formula.nunique()} distinct, {len(known)} known | "
          f"rho(target, DFT of raw proposals) {rho_dft:+.2f} | rho(target, structure label) {rho_lab:+.2f} | raw DFT hits {hits:.0f}%")
    print(per.round(2).to_string())


if __name__ == "__main__":
    main()
