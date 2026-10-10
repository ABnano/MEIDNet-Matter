"""Ablation summary for the grounded-generation study.

Joins every results/<tag>/candidates.csv with the Perov-5 DFT values (by A|B|X site assignment) and with the CGCNN
judge trained on Perov-5 (on the MLIP-relaxed cell, results/judged_cache.csv), adds a random and an oracle baseline
over the family's valid compositions, and writes results/ablation_table.{csv,md}, results/per_target.csv,
results/ablation_summary.json and results/ablation_chart.png.
"""
import glob, json, os, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
RES = f"{HERE}/results"
MATERIALS = os.environ.get("EVAL_MATERIALS")   # the published materials table; required
TARGETS = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
REQUESTED = len(TARGETS) * 3 * 6

PLAN = {  # tag: (model, label source, latent space, manifold, what it isolates)
    "R":   ("-", "-", "-", "-", "chance: random valid compositions"),
    "O":   ("DFT", "-", "-", "-", "ceiling: valid Perov-5 compositions ranked by their DFT gap"),
    "G0":  ("A0 published", "latent", "clip", "0", "current behaviour (local)"),
    "G7a": ("A0 published", "structure", "clip", "0", "labels read from the structure, on the published model"),
    "G7":  ("A0 published", "structure", "sphere", "1", "full search on the published model"),
    "S0":  ("A0 published", "screen", "-", "-", "screening with the published structure predictions"),
    "G1":  ("A1 control", "latent", "clip", "0", "retraining alone"),
    "G6":  ("A1 control", "structure", "sphere", "1", "full search without the new losses"),
    "S1":  ("A1 control", "screen", "-", "-", "screening with the control model"),
    "G2":  ("A2 grounded", "latent", "clip", "0", "new model, old search and labels"),
    "G3":  ("A2 grounded", "structure", "clip", "0", "+ labels read from the structure"),
    "G4":  ("A2 grounded", "structure", "sphere", "0", "+ unit sphere"),
    "G5":  ("A2 grounded", "structure", "sphere", "1", "full fix"),
    "G5w100": ("A2 grounded", "structure", "sphere", "100", "full fix, manifold pull x100"),
    "G5w1000": ("A2 grounded", "structure", "sphere", "1000", "full fix, manifold pull x1000"),
    "G5w1e4": ("A2 grounded", "structure", "sphere", "10000", "full fix, manifold pull x10000 (on the scale of the objectives)"),
    "S2":  ("A2 grounded", "screen", "-", "-", "screening with the grounded model"),
    "G8":  ("A3 prop_only", "structure", "sphere", "1", "loss ablation: structure_property only"),
    "G9":  ("A4 recon_only", "structure", "sphere", "1", "loss ablation: structure_reconstruction only"),
    "G10": ("A2' grounded seed 1", "structure", "sphere", "1", "replicate of the full fix"),
    "V2C": ("v2 (site order + periodic)", "structure", "sphere", "1", "v2 model, current grounded search"),
    "V2R": ("v2 (site order + periodic)", "structure", "random", "-", "v2 model, random proposals + filter (no optimisation)"),
    "V2S": ("v2 (site order + periodic)", "structure", "sphere", "1000 top5", "v2 model, steered search + filter"),
    "V2S1R": ("v2 seed 1", "structure", "random", "-", "v2 seed 1, random proposals + filter"),
    "V2S1S": ("v2 seed 1", "structure", "sphere", "1000 top5", "v2 seed 1, steered search + filter"),
    "OA": ("A2 grounded", "structure", "neighbours", "family", "Option A: aim with alignment, sample between nearest real structures"),
    "OAs1": ("A2' grounded seed 1", "structure", "neighbours", "family", "Option A, replicate model"),
    "OAall": ("A2 grounded", "structure", "neighbours", "all", "Option A, neighbours from all training materials"),
    "AR": ("A2 grounded", "structure", "random", "-", "random proposals + filter, same decoding as Option A"),
    "ARs1": ("A2' grounded seed 1", "structure", "random", "-", "random proposals + filter, replicate model"),
}


def valid_compositions():
    """Every composition of the Pb-free oxide family that passes the chemistry rules (no property windows)."""
    from meidnet.designspace import enumerate_space
    from meidnet.pipeline import family_for
    try:
        from meidnet_eval.eval_generate import goal
    except ImportError:          # run as a plain script from eval/
        from eval_generate import goal
    fam = family_for(goal(2.0, 1, 6), need_variant=True)
    fam.constraints = [c for c in fam.constraints if c["name"] != "property_window"]
    sp = enumerate_space(fam, None)
    return [dict(formula=r["f"], **{f"site_{g}": e for g, e in r["e"].items()}) for r in sp["rows"] if all(r["ok"].values())], len(sp["rows"])


def main():
    mats = pd.read_csv(MATERIALS).dropna(subset=["site_key"]).drop_duplicates("site_key").set_index("site_key")
    cg = pd.read_csv(f"{RES}/judged_cache.csv")
    cg["formula_key"] = cg.file.str.replace(".cif", "", regex=False)
    cg = cg.set_index("formula_key")
    from pymatgen.core import Composition

    def enrich(d):
        d = d.copy()
        d["site_key"] = d.site_A + "|" + d.site_B + "|" + d.site_X
        d["dft_gap"] = d.site_key.map(mats.dir_gap); d["dft_dhf"] = d.site_key.map(mats.heat_all)
        d["split"] = d.site_key.map(mats.split).fillna("novel")
        d["formula_key"] = d.formula.map(lambda f: Composition(f).reduced_formula)
        d["cgcnn_gap"] = d.formula_key.map(cg.cgcnn_p5)
        return d

    frames, funnels = [], {}
    for path in sorted(glob.glob(f"{RES}/*/candidates.csv")):
        tag = os.path.basename(os.path.dirname(path))
        if tag not in PLAN:
            continue
        d = pd.read_csv(path)
        info = json.load(open(f"{os.path.dirname(path)}/run_info.json"))
        funnels[tag] = info.get("funnel", [])
        if len(d):
            frames.append(enrich(d).assign(tag=tag))
        else:
            frames.append(pd.DataFrame({"tag": [tag]}).iloc[:0])

    valid, n_all = valid_compositions()
    V = enrich(pd.DataFrame(valid).assign(label_gap=np.nan, label_dhf=np.nan))
    rnd = []
    for t in TARGETS:
        for seed in (101, 202, 303):
            pick = V.sample(6, random_state=seed * 100 + int(t * 10))
            rnd.append(pick.assign(target=t, seed=seed))
    frames.append(pd.concat(rnd).assign(tag="R"))
    ok = V.dropna(subset=["dft_gap"]); ok = ok[ok.dft_dhf <= 1.0]
    orc = [ok.assign(dist=(ok.dft_gap - t).abs()).nsmallest(18, "dist").assign(target=t, seed=0) for t in TARGETS]
    frames.append(pd.concat(orc).assign(tag="O"))
    allc = pd.concat(frames, ignore_index=True)
    allc.to_csv(f"{RES}/all_candidates_enriched.csv", index=False)
    print(f"design space: {n_all} compositions, {len(V)} pass the chemistry rules, {int(V.dft_gap.notna().sum())} of them in Perov-5 "
          f"({int((V.split == 'train').sum())} in its training split)")

    rows, per_target = [], []
    for tag in PLAN:
        d = allc[allc.tag == tag]
        if tag not in funnels and tag not in ("R", "O"):
            continue
        known = d.dropna(subset=["dft_gap"]); judged = d.dropna(subset=["cgcnn_gap"])
        def rho(x, y):
            if len(x) < 4 or pd.Series(x).nunique() < 2:
                return np.nan, np.nan
            r = spearmanr(x, y); return float(r[0]), float(r[1])
        r_dft, p_dft = rho(known.target, known.dft_gap); r_cg, p_cg = rho(judged.target, judged.cgcnn_gap)
        slope = float(np.polyfit(known.target, known.dft_gap, 1)[0]) if known.target.nunique() > 1 else np.nan
        sets = [set(g.formula) for _, g in d.groupby("target")]
        jac = [len(a & b) / len(a | b) for i, a in enumerate(sets) for b in sets[i + 1:] if a | b]
        fun = funnels.get(tag, [])
        ff = {}
        for f in fun:
            for k, v in (f.get("first_failure") or {}).items():
                ff[k] = ff.get(k, 0) + v
        top_fail = ", ".join(f"{k} {v}" for k, v in sorted(ff.items(), key=lambda kv: -kv[1])[:3])
        lab = known.dropna(subset=["label_gap"])
        model, ls, sp, mw, purpose = PLAN[tag]
        rows.append(dict(
            tag=tag, model=model, labels=ls, latent=sp, manifold=mw, isolates=purpose,
            returned=len(d), yield_pct=100 * len(d) / REQUESTED, distinct=d.formula.nunique(),
            novel_pct=100 * float((d.split == "novel").mean()) if len(d) else np.nan,
            rho_dft=r_dft, p_dft=p_dft, rho_cgcnn=r_cg, slope_dft=slope,
            hit_dft_pct=100 * float(((known.dft_gap - known.target).abs() <= 0.3 + 1e-9).mean()) if len(known) else np.nan,
            hit_dft_full_pct=100 * float((((known.dft_gap - known.target).abs() <= 0.3 + 1e-9) & (known.dft_dhf <= 1.0)).mean()) if len(known) else np.nan,
            hit_cgcnn_pct=100 * float(((judged.cgcnn_gap - judged.target).abs() <= 0.3 + 1e-9).mean()) if len(judged) else np.nan,
            metal_pct=100 * float((known.dft_gap == 0).mean()) if len(known) else np.nan,
            label_mae_dft=float((lab.label_gap - lab.dft_gap).abs().mean()) if len(lab) else np.nan,
            label_r_dft=float(np.corrcoef(lab.label_gap, lab.dft_gap)[0, 1]) if len(lab) > 2 and lab.label_gap.std() > 0 and lab.dft_gap.std() > 0 else np.nan,
            target_overlap_jaccard=float(np.mean(jac)) if jac else np.nan,
            rounds_mean=float(np.mean([f.get("rounds_used", 0) for f in fun])) if fun else np.nan,
            passing_latents_pct=100 * sum(f.get("latents_passing", 0) for f in fun) / max(1, sum(f.get("latents_decoded", 0) for f in fun)) if fun else np.nan,
            top_first_failures=top_fail))
        for t, g in d.groupby("target"):
            per_target.append(dict(tag=tag, target=t, n=len(g), label_mean=g.label_gap.mean(), dft_mean=g.dft_gap.mean(),
                                   cgcnn_mean=g.cgcnn_gap.mean(), n_known=int(g.dft_gap.notna().sum())))
    tab = pd.DataFrame(rows); pt = pd.DataFrame(per_target)
    tab.to_csv(f"{RES}/ablation_table.csv", index=False); pt.to_csv(f"{RES}/per_target.csv", index=False)
    cols = ["tag", "model", "labels", "latent", "manifold", "returned", "distinct", "novel_pct", "rho_dft", "p_dft", "rho_cgcnn",
            "slope_dft", "hit_dft_pct", "hit_cgcnn_pct", "metal_pct", "label_mae_dft", "target_overlap_jaccard", "isolates"]
    with open(f"{RES}/ablation_table.md", "w") as f:
        f.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for _, r in tab.iterrows():
            f.write("| " + " | ".join(f"{r[c]:.2f}" if isinstance(r[c], float) else str(r[c]) for c in cols) + " |\n")
    json.dump(dict(design_space=dict(compositions=n_all, valid=len(V), valid_in_perov5=int(V.dft_gap.notna().sum())),
                   table=rows, funnels=funnels), open(f"{RES}/ablation_summary.json", "w"), indent=1, default=float)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(tab[["tag", "model", "labels", "latent", "manifold", "returned", "distinct", "novel_pct", "rho_dft", "p_dft", "rho_cgcnn",
               "slope_dft", "hit_dft_pct", "hit_cgcnn_pct", "metal_pct", "label_mae_dft", "target_overlap_jaccard"]].round(2).to_string(index=False))
    print("\nwhere candidates are lost (first failing rule, summed over runs):")
    for _, r in tab.iterrows():
        if r.top_first_failures:
            print(f"   {r.tag:4s} passing latents {r.passing_latents_pct:5.1f}%  rounds {r.rounds_mean:.1f}  {r.top_first_failures}")


if __name__ == "__main__":
    main()
