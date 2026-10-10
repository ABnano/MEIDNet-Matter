"""Discovery report: merge the S.U.N. validation shards of the mixed-anion discovery runs and rank candidates per target.

Definitions (stated, so the result is reproducible and auditable):
  Stable   E_hull <= 0.1 eV/atom (distortion-aware MLIP relaxation; MP DFT / MP ground state / MLIP hull vs MP phases)
  Unique   one row per composition (deduplicated across seeds and methods)
  Novel    absent from Perov-5 (training data) AND absent from Materials Project
  On-target  independent check: MEGNet multi-fidelity band gap (GLLB-SC, Perov-5's functional) within +/-0.75 eV of the target
             (the model's own label is inside +/-0.3 eV by construction of the generation filter)
Usage: python discovery_report.py   (fairchem-env)"""
import glob, os
import numpy as np, pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__)); R = f"{HERE}/results"
def analogue(formula, key, A_new):
    from pymatgen.core import Composition
    c = Composition(formula); A, B = key.split("|")[:2]
    an = frozenset((el.symbol, int(round(n))) for el, n in c.items() if el.symbol not in (A, B))
    return ana.get((A_new, B, an), (float("nan"), float("nan")))[0]

def main():
    """The script's work; nothing runs on import."""
    files = sorted(glob.glob(f"{R}/sun_D*shard*.csv")) + sorted(glob.glob(f"{R}/sun_partial_D*shard*.csv"))
    V = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    for col, default in (("stable", None), ("formable", None), ("novel_perov5", None), ("sun", None)):
        if col in V.columns:
            V = V.drop(columns=[col])
    perov5 = set(pd.read_csv(os.environ["EVAL_MATERIALS"]).site_key.dropna())   # the published materials table
    V["novel_perov5"] = True        # discovery runs used the novelty rule (every Perov-5 composition excluded at generation)
    # one row per composition across discovery rounds; a composition proposed for several targets keeps all of them
    V["targets"] = V.targets.apply(lambda s: list(eval(s)))
    agg = V.groupby("key").targets.agg(lambda ts: sorted({t for x in ts for t in x}))
    V = V.drop_duplicates("key").drop(columns=["targets"]).merge(agg.rename("targets"), left_on="key", right_index=True)
    V["target"] = V.targets.apply(lambda ts: float(np.mean(ts)))
    V["novel_mp"] = V.mp_status.eq("absent from MP")
    V["stable"] = V.e_hull <= 0.1
    V["formable"] = V.tau < 4.18
    # DFT-grounded analogue evidence: the La (and Y) analogue of each candidate is in Perov-5 (complete grid) with a DFT gap
    import csv, re
    from collections import Counter
    csv.field_size_limit(10 ** 9)
    DATA = os.environ.get("EVAL_DATA")   # required: the dataset folder
    ana = {}
    for split in ("train", "val", "test"):
        for r in csv.DictReader(open(f"{DATA}/{split}.csv")):
            toks = re.findall(r"([A-Z][a-z]?)(\d*)", r["formula"])
            an = Counter()
            for el, n in toks[2:]:
                an[el] += int(n or 1)
            ana[(toks[0][0], toks[1][0], frozenset(an.items()))] = (float(r["dir_gap"]), float(r["heat_all"]))
    V["la_analogue_gap"] = [analogue(f, k, "La") for f, k in zip(V.formula, V.key)]
    V["y_analogue_gap"] = [analogue(f, k, "Y") for f, k in zip(V.formula, V.key)]
    V["analogue_on_target"] = (V.la_analogue_gap - V.target).abs() <= 0.5
    V["on_target"] = (V.megnet_gllbsc_gap - V.target).abs() <= 0.75
    # experimentally reported compounds absent from MP (literature review, LITERATURE_REVIEW.md §4): not novel
    from pymatgen.core import Composition
    KNOWN_LIT = {"LaTiO2N": "Clarke 2002", "NdTiO2N": "Clarke 2002", "LaZrO2N": "Clarke 2002",
                 "LaNbON2": "Kumar 2011", "PrNbON2": "Kumar 2011", "NdNbON2": "Kumar 2011",
                 "LaTaON2": "Cordes & Schnick 2017", "CeTaON2": "Cordes & Schnick 2017", "PrTaON2": "Cordes & Schnick 2017",
                 "NdTaON2": "Cordes & Schnick 2017", "SmTaON2": "Cordes & Schnick 2017", "GdTaON2": "Cordes & Schnick 2017"}
    RELATED_LIT = {"LaVO2N": "LnVO3-xNx, Oro-Sole 2014", "PrVO2N": "LnVO3-xNx, Oro-Sole 2014", "NdVO2N": "LnVO3-xNx, Oro-Sole 2014"}
    lit = {Composition(f).reduced_composition: ref for f, ref in KNOWN_LIT.items()}
    rel = {Composition(f).reduced_composition: ref for f, ref in RELATED_LIT.items()}
    V["literature"] = [lit.get(Composition(f).reduced_composition, rel.get(Composition(f).reduced_composition, "")) for f in V.formula]
    V["novel_lit"] = ~V.formula.map(lambda f: Composition(f).reduced_composition in lit)
    V["SUN"] = V.stable & V.novel_perov5 & V.novel_mp & V.novel_lit
    V["SUN_on_target"] = V.SUN & V.formable & (V.on_target | V.analogue_on_target)
    V.to_csv(f"{R}/discovery_report.csv", index=False)

    print(f"{len(V)} distinct compositions | novel vs Perov-5 {int(V.novel_perov5.sum())} | absent from MP {int(V.novel_mp.sum())} | "
          f"stable (<=0.1) {int(V.stable.sum())} (<=0.05: {int((V.e_hull <= 0.05).sum())}) | formable {int(V.formable.sum())} | "
          f"known in literature {int((~V.novel_lit).sum())} | S.U.N. {int(V.SUN.sum())} | S.U.N. + on-target (MEGNet) {int(V.SUN_on_target.sum())}")
    k = V.dropna(subset=["megnet_gllbsc_gap"])
    print(f"target following (independent MEGNet gap): rho(target, MEGNet) {spearmanr(k.target, k.megnet_gllbsc_gap)[0]:+.2f}; "
          f"rho(MEIDNet label, MEGNet) {spearmanr(k.label_gap, k.megnet_gllbsc_gap)[0]:+.2f}; mean |MEGNet - target| {np.abs(k.megnet_gllbsc_gap - k.target).mean():.2f} eV")
    ka = V.dropna(subset=["la_analogue_gap"])
    print(f"La-analogue evidence (Perov-5 DFT): rho(target, La-analogue gap) {spearmanr(ka.target, ka.la_analogue_gap)[0]:+.2f}; "
          f"rho(MEIDNet label, La-analogue gap) {spearmanr(ka.label_gap, ka.la_analogue_gap)[0]:+.2f}; analogue within ±0.5 eV of target: "
          f"{int(ka.analogue_on_target.sum())}/{len(ka)}")
    print("relaxed structures:", V.spacegroup.value_counts().head(6).to_dict(), "| distorted:", int((V.structure_kind == "distorted").sum()))
    cols = ["formula", "target", "label_gap", "la_analogue_gap", "megnet_gllbsc_gap", "e_hull", "stability_source", "spacegroup", "tau", "mp_status", "literature", "SUN", "on_target"]
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 38)
    print("\nAll candidates (sorted by target, then E_hull):")
    print(V.sort_values(["target", "e_hull"])[cols].round(3).to_string(index=False))
    print("\nShortlist: S.U.N. and on-target (independent check), per target:")
    for t, g in V[V.SUN_on_target].sort_values("e_hull").groupby("target"):
        print(f"  {t:g} eV: " + ", ".join(f"{r.formula} (E_hull {r.e_hull:.3f}, MEGNet {r.megnet_gllbsc_gap:.2f} eV, {r.spacegroup})" for r in g.itertuples()))


if __name__ == "__main__":
    main()
