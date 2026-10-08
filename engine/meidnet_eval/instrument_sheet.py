"""Instrument sheet for target-following generation: requested band gap in, delivered band gap out.

Stated the way a measuring device is specified: response curve, bias, precision, accuracy with a confidence interval,
linearity, resolution between adjacent requests, serviceable range, yield per stage, plus the stability proxy and the
novelty of the delivered cells.  Everything is read from the result folders a run leaves behind.  A relaxed cell that
collapsed (closest atoms nearer than 0.6 of their radii) describes no material: it is counted in the funnel and listed,
and its gap is left out of every number.

Usage: python instrument_sheet.py --pool DIR --relaxed DIR --consensus DIR --out DIR [--window 0.5] [--min-gap 0.1]
       [--sun FILE] [--sun-per-candidate FILE] [--known-formulas FILE]
"""
import argparse, glob, json, os

import numpy as np
import pandas as pd
from scipy.stats import linregress, spearmanr


def load(a):
    pool = pd.read_csv(f"{a.pool}/candidates.csv")
    pcal = json.load(open(f"{a.pool}/calibration.json"))
    pool["judge_generated"] = pool["file"].map(lambda f: pcal["per_candidate"].get(f, {}).get("independent_gap"))
    cons = pd.read_csv(f"{a.pool}/candidates_consensus.csv") if os.path.exists(f"{a.pool}/candidates_consensus.csv") else pool.iloc[0:0]
    if a.relaxed and os.path.exists(f"{a.relaxed}/candidates.csv"):
        rel = pd.read_csv(f"{a.relaxed}/candidates.csv")
        rcal = json.load(open(f"{a.relaxed}/calibration.json"))["per_candidate"]
        rel["label_structure"] = rel["file"].map(lambda f: rcal.get(f, {}).get("reencoded_gap"))
        rel["judge"] = rel["file"].map(lambda f: rcal.get(f, {}).get("independent_gap"))
        # a relaxed cell that collapsed (closest atoms nearer than 0.6 of their radii) describes no material: left out
        rel["contact_ratio"] = rel["file"].map(lambda f: _contact(a, f))
        collapsed = rel[rel["contact_ratio"] < _collapsed_line()]
        rel = rel.drop(collapsed.index)
    else:                                   # no relaxed folder: the sheet describes the generated (unrelaxed) cells and says so
        rel = cons.copy()
        rel["label_structure"] = rel.get("label_gap", rel.get("label_structure_gap"))
        rel["judge"] = rel["file"].map(lambda f: pcal["per_candidate"].get(f, {}).get("independent_gap"))
        collapsed = rel.iloc[0:0]
    mlip = [r for f in glob.glob(f"{a.consensus}/mlip_shard*.json") for r in json.load(open(f))] if a.consensus else []
    drop = {os.path.basename(r["file"]): r.get("tensornet_drop_per_atom") for r in mlip}
    kept = {os.path.basename(r["file"]): r.get("tensornet_spacegroup_relaxed") == r.get("spacegroup_designed") for r in mlip}
    rel["drop"] = rel["file"].map(lambda f: drop.get(os.path.basename(f)))
    rel["sg_kept"] = rel["file"].map(lambda f: kept.get(os.path.basename(f)))
    sun = None
    for cand in ([a.sun] if a.sun else []) + [f"{a.relaxed}/sun_relaxed_strict.json", f"{a.relaxed}/sun.json"]:
        if os.path.exists(cand):
            sun = json.load(open(cand))
            break
    return pool, pcal, cons, rel, sun, collapsed


def _collapsed_line():
    try:
        from meidnet_eval.d1_mlip_check import COLLAPSED
    except ImportError:
        from d1_mlip_check import COLLAPSED
    return COLLAPSED


def _contact(a, f):
    """Contact ratio of the relaxed cell behind a candidates-table row (the relaxed folder's copy, else the relaxer's own)."""
    try:
        from meidnet_eval.d1_mlip_check import contact_ratio
    except ImportError:
        from d1_mlip_check import contact_ratio
    from pymatgen.core import Structure
    for p in ([os.path.join(a.relaxed, f)] if a.relaxed else []) + \
             ([os.path.join(a.consensus, "relaxed_tensornet", os.path.basename(f))] if a.consensus else []):
        if os.path.exists(p):
            try:
                return contact_ratio(Structure.from_file(p))
            except Exception:
                return np.nan
    return np.nan


def per_target(pool, cons, ok, final):
    rows = []
    for t in sorted(pool["target"].unique()):
        g = ok[ok["target"] == t]
        d = g["judge"].values.astype(float)
        rows.append(dict(
            requested=float(t),
            generated=int((pool["target"] == t).sum()),
            both_judges=int((cons["target"] == t).sum()),
            relaxed=int(len(g)),
            final=int((final["target"] == t).sum()),
            generated_judge_mean=float(pool.loc[pool["target"] == t, "judge_generated"].dropna().mean()),
            delivered_mean=float(d.mean()) if len(d) else None,
            delivered_sd=float(d.std(ddof=1)) if len(d) > 1 else None,
            delivered_min=float(d.min()) if len(d) else None,
            delivered_max=float(d.max()) if len(d) else None,
            bias=float(d.mean() - t) if len(d) else None,
            drop_median=float(g["drop"].dropna().median()) if g["drop"].notna().any() else None,
            spacegroup_kept=float(g["sg_kept"].dropna().mean()) if g["sg_kept"].notna().any() else None,
            final_formulas=final.loc[final["target"] == t, "formula"].tolist(),
        ))
    return rows


def classify(known: bool, amd: float | None) -> str:
    """What relaxation revealed: a known structure found again, a new polymorph of a known formula, or a new composition."""
    if known and amd is not None and amd < 0.3:
        return "rediscovered known structure"
    if known and amd is not None and amd < 0.35:
        return "rediscovered (borderline)"
    if known:
        return "new polymorph of known formula"
    return "new composition, new structure"


def accepted_table(final, a) -> pd.DataFrame:
    """One row per accepted material with the evidence a reader needs: both gaps on the relaxed cell, the AMD distance,
    whether the formula exists in the training data (and at which recorded gaps), the class, and a charge-balance flag."""
    amd, by_file = {}, False
    if a.sun_per_candidate and os.path.exists(a.sun_per_candidate):
        t = pd.read_csv(a.sun_per_candidate)
        col = [c for c in t.columns if "amd" in c.lower()]
        by_file = "file" in t.columns
        if col:
            amd = {(os.path.basename(str(k)) if by_file else k): v for k, v in zip(t["file" if by_file else "formula"], t[col[0]])}
    known = {}
    if a.known_formulas and os.path.exists(a.known_formulas):
        import gzip
        opener = gzip.open if a.known_formulas.endswith(".gz") else open
        known = json.load(opener(a.known_formulas, "rt"))
    rows = []
    for _, r in final.sort_values(["target", "formula"]).iterrows():
        d = amd.get(os.path.basename(str(r["file"]))) if by_file else amd.get(r["formula"])
        d = None if d is None or d != d else float(d)
        is_known = r["formula"] in known if known else None
        try:
            from pymatgen.core import Composition
            balanced = bool(Composition(r["formula"]).oxi_state_guesses(max_sites=-1))
        except Exception:
            balanced = None
        rows.append(dict(requested=float(r["target"]), formula=r["formula"], label_structure=round(float(r["label_structure"]), 3),
                         judge=round(float(r["judge"]), 3), amd_nearest=None if d is None else round(d, 3),
                         known_formula=is_known, recorded_gaps=",".join(f"{g:.2f}" for g in known.get(r["formula"], [])) if known else "",
                         cls=classify(bool(is_known), d) if is_known is not None else "",
                         charge_balanced=balanced, drop_eV_atom=r.get("drop"), spacegroup_kept=r.get("sg_kept"),
                         natoms=int(r["natoms"]) if "natoms" in r else None, file=r.get("file"),
                         flag="judges disagree" if abs(float(r["label_structure"]) - float(r["judge"])) > 0.5 else ""))
    return pd.DataFrame(rows).rename(columns={"cls": "class"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, help="the generation folder (candidates.csv, calibration.json, candidates_consensus.csv)")
    ap.add_argument("--relaxed", default=None, help="the relaxed folder re-judged by target_calibration (generate_to_target writes OUT/TAG/relaxed); "
                                                     "without it the sheet describes the unrelaxed cells")
    ap.add_argument("--consensus", "--relax", dest="consensus", default=None,
                    help="the folder holding the relaxation shards mlip_shard*.json (generate_to_target writes OUT/TAG/relax)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--window", type=float, default=0.5)
    ap.add_argument("--min-gap", type=float, default=0.1)
    ap.add_argument("--sun", default=None, help="metrics_sun JSON for the novelty line (default: the relaxed folder's sun_relaxed_strict.json or sun.json)")
    ap.add_argument("--sun-per-candidate", default=None, help="metrics_sun per-candidate CSV (adds the AMD distance per material)")
    ap.add_argument("--known-formulas", default=None, help="JSON {reduced formula: [gaps]} of the training data (adds known/new and the recorded gaps)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pool, pcal, cons, rel, sun, collapsed = load(a)

    ok = rel.dropna(subset=["label_structure", "judge"]).copy()
    in_window = (abs(ok["label_structure"] - ok["target"]) <= a.window) & (abs(ok["judge"] - ok["target"]) <= a.window)
    not_metal = ~((ok["target"] > 0) & (ok["judge"] < a.min_gap))
    final = ok[in_window & not_metal]
    rows = per_target(pool, cons, ok, final)

    x = ok["target"].values.astype(float)
    y = ok["judge"].values.astype(float)
    rng = np.random.default_rng(0)
    boots = [float(np.abs((y - x)[rng.integers(0, len(x), len(x))]).mean()) for _ in range(2000)]
    lr = linregress(x, y)
    resolution = []
    for p, q in zip(rows, rows[1:]):
        if p["delivered_sd"] and q["delivered_sd"]:
            pooled = float(np.sqrt((p["delivered_sd"] ** 2 + q["delivered_sd"] ** 2) / 2))
            delta = float(q["delivered_mean"] - p["delivered_mean"])
            resolution.append(dict(pair=[p["requested"], q["requested"]], delta_mean=delta, pooled_sd=pooled,
                                   separable=bool(abs(delta) > pooled)))
    served = [r["requested"] for r in rows if r["final"] > 0]
    sds = [r["delivered_sd"] for r in rows if r["delivered_sd"] is not None]

    sheet = dict(
        window_eV=a.window, metal_floor_eV=a.min_gap,
        funnel=dict(generated=int(len(pool)), both_judges=int(len(cons)), collapsed_on_relaxation=int(len(collapsed)),
                    relaxed=int(len(ok)), final=int(len(final))),
        collapsed_on_relaxation=[dict(formula=r["formula"], target=float(r["target"]), contact_ratio=round(float(r["contact_ratio"]), 2))
                                 for _, r in collapsed.iterrows()],
        judge=pcal.get("judge_qualification"),
        per_target=rows,
        accuracy=dict(mae_generated_cells=float(np.abs(pool["judge_generated"] - pool["target"]).mean()),
                      mae_relaxed_cells=float(np.abs(y - x).mean()),
                      mae_relaxed_ci95=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                      within_window=int((np.abs(y - x) <= a.window).sum()), of=int(len(x))),
        linearity=dict(slope=float(lr.slope), intercept=float(lr.intercept), r2=float(lr.rvalue ** 2),
                       spearman=float(spearmanr(x, y).statistic), ideal="slope 1, intercept 0"),
        precision=dict(within_target_sd_median=float(np.median(sds)) if sds else None),
        resolution=resolution,
        range=dict(requested=[r["requested"] for r in rows], served=served),
        novelty=None if sun is None else dict(amd_median=sun["amd_nearest_reference"]["median"],
                                              amd_min=sun["amd_nearest_reference"]["min"],
                                              novel_share=sun["novel_structure_level"]["rate"],
                                              unique_share=sun["unique_structure_level"]["rate"]),
        stability_note="energy drop on relaxation only; no hull energy, so stability is not claimed",
        cells=("relaxed" if a.relaxed and os.path.exists(f"{a.relaxed}/candidates.csv")
               else "unrelaxed: generated cells only; relax them and re-judge before quoting a gap"),
    )
    json.dump(sheet, open(f"{a.out}/instrument.json", "w"), indent=1)
    accepted_table(final, a).to_csv(f"{a.out}/accepted_materials.csv", index=False)

    print(f"funnel: {sheet['funnel']}")
    print(f"judge: MAE {sheet['judge']['mae']:.3f} eV, Spearman {sheet['judge']['spearman']:.2f} (n={sheet['judge']['n']})\n")
    print(f"{'request':>7s} {'gen':>4s} {'2j':>3s} {'rel':>4s} {'final':>5s} | {'delivered mean':>14s} {'sd':>5s} {'min':>5s} {'max':>5s} {'bias':>6s} | {'drop':>5s} {'sg kept':>7s}")
    for r in rows:
        f = lambda v, w=5, p=2: (f"{v:{w}.{p}f}" if v is not None else " " * (w - 1) + "-")
        print(f"{r['requested']:7.1f} {r['generated']:4d} {r['both_judges']:3d} {r['relaxed']:4d} {r['final']:5d} | "
              f"{f(r['delivered_mean'],14)} {f(r['delivered_sd'])} {f(r['delivered_min'])} {f(r['delivered_max'])} {f(r['bias'],6)} | "
              f"{f(r['drop_median'])} {f(r['spacegroup_kept'],7)}")
    acc, lin = sheet["accuracy"], sheet["linearity"]
    cells = sheet.get("cells", "relaxed")
    print(f"\ncells: {cells}")
    print(f"accuracy: MAE generated {acc['mae_generated_cells']:.2f} -> {'relaxed' if cells == 'relaxed' else 'kept (unrelaxed)'} {acc['mae_relaxed_cells']:.2f} eV "
          f"(95% CI {acc['mae_relaxed_ci95'][0]:.2f}-{acc['mae_relaxed_ci95'][1]:.2f}); within {a.window} eV: {acc['within_window']} of {acc['of']}")
    if len(x) >= 3 and lin["slope"] == lin["slope"]:
        print(f"linearity: delivered = {lin['intercept']:.2f} + {lin['slope']:.2f} x requested (R2 {lin['r2']:.2f}, Spearman {lin['spearman']:.2f}); ideal 0 + 1.00 x")
    else:
        print("linearity: not measurable with fewer than three accepted cells")
    psd = sheet["precision"]["within_target_sd_median"]
    print("precision: within-target sd median " + (f"{psd:.2f} eV" if psd is not None else "not measurable (one cell per request)"))
    print("resolution:", ", ".join(f"{p['pair'][0]:.1f}->{p['pair'][1]:.1f}: {'yes' if p['separable'] else 'no'}" for p in resolution))
    print(f"range: served {served} of {sheet['range']['requested']}")
    if sheet["novelty"]:
        print(f"novelty (relaxed final cells): AMD median {sheet['novelty']['amd_median']:.3f}, novel {100*sheet['novelty']['novel_share']:.0f}%")
    print(f"\nwrote {a.out}/instrument.json")


if __name__ == "__main__":
    main()
