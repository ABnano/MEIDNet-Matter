"""Stage 09 of discover.py: one report for a run, every number traceable to the stage that produced it.

Reads only what the stages wrote into the run folder (stage cards, hold-out metrics, proposals, novelty lookups,
validation tables) and writes <run>/report/report.md plus <run>/report/shortlist.csv.  Nothing is recomputed except
the two checks that need the relaxed cells: whether the relaxed ground state is still a corner-sharing perovskite, and,
on the hold-out set, how well the validation funnel itself (ML-potential hull, judges) agrees with DFT.
Usage: python final_report.py <run_dir> [--gap Eg] [--stability Es] [--es-max 0.1] [--window 0.3]
"""
import argparse, glob, json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)


def load(path, kind="csv"):
    if not os.path.exists(path):
        return None
    return pd.read_csv(path) if kind == "csv" else json.load(open(path))


def md_table(df, cols=None, floatfmt="{:.3g}"):
    if df is None or len(df) == 0:
        return "_none_\n"
    cols = cols or list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df[cols].itertuples(index=False):
        out.append("| " + " | ".join(floatfmt.format(v) if isinstance(v, (float, np.floating)) and not pd.isna(v)
                                     else ("" if (isinstance(v, float) and pd.isna(v)) else str(v)) for v in r) + " |")
    return "\n".join(out) + "\n"


def relaxed_is_perovskite(cells_dir, formula):
    from pymatgen.core import Structure
    try:
        from meidnet_eval.perovskite_geometry import is_perovskite
    except ImportError:          # run as a plain script from eval/
        from perovskite_geometry import is_perovskite
    p = os.path.join(cells_dir, "tensornet", f"{formula}.cif")
    return bool(is_perovskite(Structure.from_file(p))) if os.path.exists(p) else None


def judge_table(vdir, col):
    j = load(os.path.join(vdir, f"judge_{col}.csv"))
    if j is None:
        return {}
    j["formula"] = j.file.str.replace(".cif", "", regex=False).str.split("/").str[-1]
    return dict(zip(j.formula, j.cgcnn_p5))          # the ensemble column is named cgcnn_p5 whatever the judge's tag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run"); ap.add_argument("--gap", default="Eg"); ap.add_argument("--stability", default="Es")
    ap.add_argument("--es-max", type=float, default=0.1); ap.add_argument("--window", type=float, default=0.3)
    a = ap.parse_args()
    R = os.path.abspath(a.run); out = os.path.join(R, "report"); os.makedirs(out, exist_ok=True)
    cards = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(R, "cards", "*.json")))]
    settings = load(os.path.join(R, "settings.json"), "json") or {}
    ds = load(os.path.join(R, "families", "design_space.json"), "json") or {}
    hm = load(os.path.join(R, "holdout", "holdout_metrics.json"), "json")
    props = load(os.path.join(R, "proposals", "candidates.csv"))
    vdir = os.path.join(R, "validation")
    S = load(os.path.join(vdir, "sun_validated.csv"))
    M = load(os.path.join(vdir, "mlip_compare.csv"))
    jg, js = judge_table(vdir, a.gap), judge_table(vdir, a.stability)
    oq = load(os.path.join(R, "novelty", f"oqmd_{os.path.basename(R).replace('-', '_')}_screen.csv"))
    if oq is None:
        cand = glob.glob(os.path.join(R, "novelty", "oqmd_*_screen.csv"))
        oq = load(cand[0]) if cand else None

    L = [f"# Discovery report — {os.path.basename(R)}", "",
         f"Dataset `{settings.get('table', '?')}`; targets {settings.get('targets')} eV ({a.gap}, ground state), "
         f"window +-{a.window} eV, stable = {a.stability} / hull <= {a.es_max} eV/atom.  All gaps are those of the "
         "dataset's functional (OQMD: PBE).", ""]

    # 1. stage verdicts
    L += ["## 1. Stage verdicts", "", "| # | stage | verdict | reason |", "|---|---|---|---|"]
    for c in cards:
        L.append(f"| {c['nn']:02d} | {c['title']} | **{c['verdict']}** | {c['reason']} |")
    L.append("")

    # 2. trust: hold-out against DFT
    L += ["## 2. Trust: would it have found real materials? (hold-out against DFT)", ""]
    if hm:
        per = pd.DataFrame(hm["per_target"])
        L += [f"{hm['covered_by_design_space']} of {hm['test_compositions']} held-out compositions lie in the design space. "
              f"Ground-state polymorph identified for {100 * hm['polymorph_identified']:.0f}%; perovskite / not called "
              f"correctly for {100 * hm['perovskite_call_accuracy']:.0f}%; ground-state gap MAE {hm['gs_gap_mae']:.2f} eV "
              f"(Spearman {hm['gs_gap_spearman']:+.2f}); stability MAE {hm['es_mae']:.3f} (Spearman {hm['es_spearman']:+.2f}), "
              f"stable / unstable called correctly for {100 * hm['stable_call_accuracy']:.0f}%.", ""]
        if "cubic_only_gap_mae_vs_gs" in hm:
            L += [f"Ablation — screening only the cubic polymorph, as for Perov-5: gap MAE against the real ground state "
                  f"{hm['cubic_only_gap_mae_vs_gs']:.2f} eV (Spearman {hm['cubic_only_gap_spearman_vs_gs']:+.2f}).", ""]
        per = per.assign(precision_95=per.apply(lambda r: f"{r.precision:.2f} [{r.precision_lo:.2f}-{r.precision_hi:.2f}]"
                                                if r.proposed else "-", axis=1),
                         blind=per.apply(lambda r: f"{r.blind_draw:.2f} [{r.blind_lo:.2f}-{r.blind_hi:.2f}]", axis=1))
        L += [md_table(per, ["target", "screen", "proposed", "on_target_and_stable_dft", "precision_95", "blind", "recall",
                             "gap_only_precision", "beats_blind_draw"]), ""]
    else:
        L += ["_hold-out not run_", ""]

    # 3. the validation funnel itself, checked on the hold-out set
    L += ["## 3. Is the validation itself trustworthy? (hold-out compositions have DFT)", ""]
    ht = load(os.path.join(R, "holdout", "holdout_table.csv"))
    if S is not None and len(S) and ht is not None:
        H = S[S["set"] == "hold-out"].merge(ht.rename(columns={ht.columns[0]: "formula"})[["formula", "dft_Es", "dft_Eg"]],
                                            on="formula", how="inner")
        if len(H):
            from scipy.stats import spearmanr
            agree = ((H.e_hull <= a.es_max) == (H.dft_Es <= a.es_max)).mean()
            rho = spearmanr(H.e_hull, H.dft_Es)[0] if len(H) > 2 else float("nan")
            L.append(f"On {len(H)} held-out compositions: ML-potential hull vs DFT {a.stability}: Spearman {rho:+.2f}, "
                     f"stable / unstable agreement {100 * agree:.0f}%.")
            if jg:
                g = H.formula.map(jg)
                ok = g.notna()
                if ok.sum() > 2:
                    L.append(f"Independent {a.gap} judge on the relaxed cells vs DFT: MAE {np.abs(g[ok] - H.dft_Eg[ok]).mean():.2f} eV "
                             f"(Spearman {spearmanr(g[ok], H.dft_Eg[ok])[0]:+.2f}, n={int(ok.sum())}).")
        else:
            L.append("_no hold-out composition was validated_")
    else:
        L.append("_validation not run_")
    L.append("")

    # 4. novelty frontier
    L += ["## 4. Novelty frontier", ""]
    if ds:
        L += [f"{ds.get('compositions')} charge-balanced compositions in the learned design space; "
              f"{ds.get('in_dataset')} are already in the dataset, **{ds.get('novel')} are not**"
              + (f": {', '.join(ds.get('novel_examples', [])[:30])}" if ds.get("novel") else "") + ".", ""]

    # 5. funnel and shortlist (discovery set)
    L += ["## 5. S.U.N. funnel and shortlist (discovery)", ""]
    short = pd.DataFrame()
    if S is not None and len(S):
        D = S[S["set"] == "discovery"].copy()
        if len(D):
            D["relaxed_perovskite"] = [relaxed_is_perovskite(os.path.join(vdir, "cells"), f) for f in D.formula]
            D["judge_gap"] = D.formula.map(jg) if jg else np.nan
            D["judge_stability"] = D.formula.map(js) if js else np.nan
            if M is not None and len(M):
                D = D.merge(M[["formula", "same_sg", "da_mlip"]], on="formula", how="left")
            if oq is not None:
                D = D.merge(oq, on="formula", how="left")
            D["target"] = D.targets.apply(lambda s: float(np.mean(eval(s))) if isinstance(s, str) else np.nan)
            steps = [("proposed", pd.Series(True, index=D.index)),
                     ("absent from Materials Project", D.mp_status.eq("absent from MP")),
                     ("absent from OQMD", D.get("oqmd_status", pd.Series("?", index=D.index)).ne("in OQMD")),
                     (f"stable (ML-potential hull <= {a.es_max})", D.e_hull <= a.es_max),
                     ("formable (Bartel tau < 4.18)", D.tau < 4.18),
                     ("relaxed ground state is a perovskite", D.relaxed_perovskite.fillna(False).astype(bool)),
                     (f"on target by the independent judge (+-{a.window + 0.2:g} eV)",
                      (D.judge_gap - D.target).abs() <= a.window + 0.2 if jg else pd.Series(True, index=D.index))]
            keep = pd.Series(True, index=D.index)
            L += ["| step | remaining |", "|---|---|"]
            for name, m in steps:
                keep &= m.fillna(False).astype(bool)
                L.append(f"| {name} | {int(keep.sum())} |")
            L.append("")
            D["shortlist"] = keep
            cols = [c for c in ["formula", "target", "label_gap", "judge_gap", "e_hull", "judge_stability", "spacegroup",
                                "relaxed_perovskite", "tau", "same_sg", "mp_status", "oqmd_status", "oqmd_gs_band_gap",
                                "oqmd_gs_stability", "shortlist"] if c in D.columns]
            short = D.sort_values(["shortlist", "target", "e_hull"], ascending=[False, True, True])
            L += [md_table(short, cols), ""]
            short.to_csv(os.path.join(out, "shortlist.csv"), index=False)
    else:
        L += ["_no discovery proposals were validated_", ""]

    L += ["## 6. Definitions and caveats", "",
          f"- **Stable**: hull distance <= {a.es_max} eV/atom from two independent ML potentials' relaxations against "
          "Materials Project phases (no DFT run here). **Unique**: one row per formula. **Novel**: absent from the "
          "dataset, Materials Project and OQMD. A candidate also has to keep a corner-sharing perovskite structure "
          "after relaxation.",
          "- The ground-state polymorph is the lowest predicted formation energy over the polymorph templates learned "
          "from the data; compositions whose true ground state is another structure type are a known blind spot "
          "(measured above as 'polymorph identified').",
          "- Where a proposal already exists in OQMD, its DFT values are shown: a free check of the prediction, but the "
          "composition is then not novel.", ""]
    open(os.path.join(out, "report.md"), "w").write("\n".join(L))
    print("\n".join(L[:60]))
    print(f"\nwrote {out}/report.md" + (f" and shortlist.csv ({int(short.shortlist.sum())} shortlisted)" if len(short) else ""))


if __name__ == "__main__":
    main()
