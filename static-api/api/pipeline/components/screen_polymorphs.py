"""Stages 5 and 6 of discover.py: polymorph-aware screening, and the hold-out rediscovery test against DFT.

Why polymorph-aware: in the OQMD data the cubic and the ground-state band gap of the same composition differ by 1.8 eV on
average (Spearman 0.22), so a target has to be met by the structure the material actually adopts.  For every composition
of the design space this script builds the cell in each polymorph template (auto-families with minimal rules: charge and
distances only), predicts Ef, Eg and Es with MEIDNet from that structure, and takes as PREDICTED GROUND STATE the lowest
predicted formation energy over all templates and both site assignments (one composition has one hull reference, so this
is also the lowest predicted Es).  A composition is proposed for target T when its predicted ground state
  * is a corner-sharing perovskite (perovskite_geometry.py: an ilmenite template is a real competitor, never a candidate),
  * has a gap within T +- window and Es <= es_max,
  * and its composition is absent from the reference data: the whole dataset in discovery mode, the training split only
    in hold-out mode.
Hold-out mode (--truth test) then checks every number against the held-out DFT of the test split: polymorph identified,
ground-state gap, stability, and per target the precision and recall of the proposals against a blind draw (Wilson 95%
intervals), with the cubic-only screen as the ablation that shows what polymorph awareness buys.

  discover   python screen_polymorphs.py --tag OQ_screen  --ckpt M --data INTAKE --families F1.yaml F2.yaml ... --novel-against all
  hold-out   python screen_polymorphs.py --tag OQ_holdout --ckpt M --data INTAKE --families ... --novel-against train --truth test
Writes results/<tag>/: candidates.csv + cifs/ (standard layout, read unchanged by the validation stage), screen_table.csv
(every composition: predicted ground state, cubic prediction, novelty), screen_summary.json, and in hold-out mode
holdout_table.csv + holdout_metrics.json.
"""
import argparse, json, math, os, re, sys, time
import numpy as np
import pandas as pd
import torch
from pymatgen.core import Composition, Structure
from pymatgen.io.cif import CifWriter

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from meidnet.checkpoint import load_checkpoint            # noqa: E402
from meidnet.config import config_from_dict              # noqa: E402
from meidnet.constraints import build_candidate          # noqa: E402
from meidnet.designspace import enumerate_space           # noqa: E402
from meidnet.pipeline import family_for                   # noqa: E402
try:
    from meidnet_eval.perovskite_geometry import is_perovskite
except ImportError:          # run as a plain script from eval/
    from perovskite_geometry import is_perovskite

SG_SYMBOL = {221: "Pm-3m", 62: "Pnma", 148: "R-3", 167: "R-3c", 99: "P4mm", 140: "I4/mcm", 74: "Imma", 14: "P21/c",
             63: "Cmcm", 161: "R3c", 12: "C2/m", 194: "P63/mmc"}


def reduced(f):
    return Composition(f).reduced_formula


def wilson(k, n, z=1.96):
    """95% Wilson interval of a proportion k/n (well behaved for small n, unlike the normal approximation)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def load_template(path, intake, props, variant=None):
    """Family object for one polymorph template, built the way auto_family.verify builds it.  `path` may be a shipped
    family name or a yaml path, optionally with the variant after a colon (double_perovskite_a2bbx6:halide)."""
    if variant is None and ":" in path and not os.path.exists(path):
        path, variant = path.rsplit(":", 1)
    g = dict(family=os.path.abspath(path) if os.path.exists(path) else path, seed=0, per_target=1, variant=variant,
             objectives=[dict(property=props[0], loss="l2", weight=1.0)], targets=[{props[0]: 0.0}])
    cfg = config_from_dict({"name": "screen", "output_dir": "unused",
                            "data": {"table": f"{intake}/train.csv", "properties": [{"column": p} for p in props]},
                            "generation": g}, base_dir=".")
    return family_for(cfg, need_variant=True)


def template_spacegroup(path):
    """Space-group number from the '# prototype ABC3|221|...' header auto_family writes."""
    for line in open(path):
        m = re.search(r"prototype \S+?\|(\d+)\|", line)
        if m:
            return int(m.group(1))
    return 0


def template_is_perovskite(fam):
    """Build the template once with a reference A/B pair and apply the corner-sharing test to it."""
    groups = list(fam.groups)
    cat = [g for g in groups if "O" not in fam.groups[g].elements]
    an = [g for g in groups if g not in cat]
    pick = {}
    for g, pref in zip(cat, (["Sr", "Ba", "Ca", "La"], ["Ti", "Zr", "Al", "Fe"])):
        pool = list(fam.groups[g].elements)
        pick[g] = next((e for e in pref if e in pool), pool[0])
    for g in an:
        pick[g] = "O"
    try:
        return is_perovskite(build_candidate(fam, pick).raw)
    except Exception:
        return False


def screen(lm, templates, intake, props):
    """Predicted Ef/Eg/Es of every composition in every template, then the predicted ground state per composition."""
    rows = []
    for path in templates:
        fam = load_template(path, intake, props)
        sg = template_spacegroup(path)
        label = SG_SYMBOL.get(sg, f"sg{sg}")
        perov = template_is_perovskite(fam)
        t0 = time.time()
        space = enumerate_space(fam, lm)
        n_ok = 0
        for r in space["rows"]:
            if not all(r["ok"].values()):
                continue
            n_ok += 1
            rows.append(dict(formula=reduced(r["f"]), polymorph=label, sg=sg, template_perovskite=perov,
                             A=r["e"].get("A"), B=r["e"].get("B"), X=r["e"].get("X"), template=path,
                             elements=json.dumps(r["e"]), **{p: r["p"][p] for p in props}))
        print(f"  template {label:6s} (perovskite: {perov}): {len(space['rows'])} cells, {n_ok} pass charge and distance, "
              f"{time.time() - t0:.0f}s", flush=True)
    P = pd.DataFrame(rows)
    gs = P.loc[P.groupby("formula").Ef.idxmin()].set_index("formula")
    cub = P[P.polymorph == "Pm-3m"]
    cub = cub.loc[cub.groupby("formula").Ef.idxmin()].set_index("formula") if len(cub) else None
    return P, gs, cub


def reference_formulas(intake, which):
    splits = ("train", "val", "test") if which == "all" else ("train",)
    out = set()
    for s in splits:
        out |= {reduced(f) for f in pd.read_csv(f"{intake}/{s}.csv", usecols=["formula"]).formula}
    return out


def dft_truth(intake, split):
    """DFT ground state per held-out composition (lowest Es over its polymorphs), with its corner-sharing flag."""
    d = pd.read_csv(f"{intake}/{split}.csv")
    d["formula_r"] = d.formula.map(reduced)
    d["sg"] = d.prototype.astype(str).str.split("|").str[1].apply(lambda x: int(x) if str(x).isdigit() else 0)
    gs = d.loc[d.groupby("formula_r").Es.idxmin()].copy()
    gs["perovskite"] = [is_perovskite(Structure.from_str(c, fmt="cif")) for c in gs.cif]
    cub = d[d.sg == 221]
    cub = cub.loc[cub.groupby("formula_r").Es.idxmin()].set_index("formula_r")
    T = gs.set_index("formula_r")[["sg", "Ef", "Eg", "Es", "perovskite"]].rename(columns=lambda c: f"dft_{c}")
    T["dft_Eg_cubic"] = cub.Eg.reindex(T.index)
    return T


def select(table, T, window, es_max, need_perov=True):
    m = ((table.Eg - T).abs() <= window) & (table.Es <= es_max)
    if need_perov:
        m &= table.template_perovskite.astype(bool)
    return table[m]


def holdout(gs, cub, truth, targets, window, es_max, out_dir):
    """Every proposal of the screen checked against held-out DFT; returns the metrics written to holdout_metrics.json."""
    H = gs.join(truth, how="inner")
    covered = len(H)
    m = {"test_compositions": len(truth), "covered_by_design_space": covered}
    m["polymorph_identified"] = float((H.sg == H.dft_sg).mean())
    m["perovskite_call_accuracy"] = float((H.template_perovskite.astype(bool) == H.dft_perovskite.astype(bool)).mean())
    from scipy.stats import spearmanr
    m["gs_gap_mae"] = float((H.Eg - H.dft_Eg).abs().mean())
    m["gs_gap_spearman"] = float(spearmanr(H.Eg, H.dft_Eg)[0])
    m["es_mae"] = float((H.Es - H.dft_Es).abs().mean())
    m["es_spearman"] = float(spearmanr(H.Es, H.dft_Es)[0])
    stab_pred, stab_dft = H.Es <= es_max, H.dft_Es <= es_max
    m["stable_call_accuracy"] = float((stab_pred == stab_dft).mean())
    m["stable_call_precision"] = float(stab_dft[stab_pred].mean()) if stab_pred.any() else float("nan")
    if cub is not None:
        C = cub.join(truth, how="inner")
        m["cubic_only_gap_mae_vs_gs"] = float((C.Eg - C.dft_Eg).abs().mean())
        m["cubic_only_gap_spearman_vs_gs"] = float(spearmanr(C.Eg, C.dft_Eg)[0])
    per = []
    for T in targets:
        truth_T = set(H.index[((H.dft_Eg - T).abs() <= window) & (H.dft_Es <= es_max) & H.dft_perovskite.astype(bool)])
        gap_T = set(H.index[(H.dft_Eg - T).abs() <= window])
        for name, tab in (("polymorph-aware", H), ("cubic-only", None if cub is None else cub.join(truth, how="inner"))):
            if tab is None:
                continue
            S = set(select(tab, T, window, es_max).index)
            k_full, k_gap = len(S & truth_T), len(S & gap_T)
            lo, hi = wilson(k_full, len(S))
            blo, bhi = wilson(len(truth_T), covered)
            per.append(dict(target=T, screen=name, proposed=len(S), on_target_and_stable_dft=k_full,
                            precision=k_full / len(S) if S else float("nan"), precision_lo=lo, precision_hi=hi,
                            gap_only_precision=k_gap / len(S) if S else float("nan"),
                            recall=k_full / len(truth_T) if truth_T else float("nan"), truth=len(truth_T),
                            blind_draw=len(truth_T) / covered if covered else float("nan"), blind_lo=blo, blind_hi=bhi,
                            beats_blind_draw=bool(S) and lo > bhi))
    P = pd.DataFrame(per)
    m["per_target"] = P.to_dict("records")
    H.to_csv(os.path.join(out_dir, "holdout_table.csv"))
    json.dump(m, open(os.path.join(out_dir, "holdout_metrics.json"), "w"), indent=1, default=float)
    return m, P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True); ap.add_argument("--ckpt", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--families", nargs="+", required=True, help="polymorph template YAMLs (auto_family --rules minimal)")
    ap.add_argument("--targets", type=float, nargs="+", default=[0.5, 1, 1.5, 2, 2.5, 3, 4])
    ap.add_argument("--window", type=float, default=0.3)
    ap.add_argument("--es-max", type=float, default=0.1)
    ap.add_argument("--per-target", type=int, default=12)
    ap.add_argument("--novel-against", choices=["all", "train"], default="all")
    ap.add_argument("--truth", choices=["test", "none"], default="none")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    a = ap.parse_args()
    out = os.path.join(a.out, a.tag); os.makedirs(os.path.join(out, "cifs"), exist_ok=True)
    t0 = time.time()
    lm = load_checkpoint(a.ckpt, device=a.device)
    props = list(lm.stats.columns)
    for need in ("Ef", "Eg", "Es"):
        if need not in props:
            raise SystemExit(f"the checkpoint predicts {props}; polymorph-aware screening needs Ef, Eg and Es")
    print(f"{a.tag}: {len(a.families)} polymorph templates, model {a.ckpt}", flush=True)
    P, gs, cub = screen(lm, a.families, a.data, props)
    known = reference_formulas(a.data, a.novel_against)
    gs["novel"] = ~gs.index.isin(known)
    if cub is not None:
        gs["Eg_cubic"] = cub.Eg.reindex(gs.index)
    gs.to_csv(os.path.join(out, "screen_table.csv"))
    summary = dict(tag=a.tag, templates=a.families, compositions=len(gs), novel=int(gs.novel.sum()),
                   novel_perovskite_gs=int((gs.novel & gs.template_perovskite.astype(bool)).sum()),
                   gs_polymorphs=gs.polymorph.value_counts().to_dict(), novel_against=a.novel_against,
                   window=a.window, es_max=a.es_max, seconds=None)
    print(f"{len(gs)} compositions; predicted ground states {summary['gs_polymorphs']}; "
          f"{summary['novel']} absent from the {a.novel_against} reference ({summary['novel_perovskite_gs']} with a "
          f"perovskite ground state)", flush=True)

    # proposals: novel compositions whose predicted ground state is a perovskite at the target
    rows, per_target = [], {}
    pool = gs[gs.novel]
    for T in a.targets:
        S = select(pool, T, a.window, a.es_max)
        S = S.assign(dist=(S.Eg - T).abs()).sort_values(["Es", "dist"]).head(a.per_target)
        per_target[T] = len(select(pool, T, a.window, a.es_max))
        for k, (f, r) in enumerate(S.iterrows(), 1):
            fam = load_template(r.template, a.data, props)
            cand = build_candidate(fam, json.loads(r.elements))
            path = os.path.join(out, "cifs", f"T{T:g}_{k}_{f}_{r.polymorph.replace('/', '')}.cif")
            CifWriter(cand.raw).write_file(path)
            rows.append(dict(tag=a.tag, mode=f"polymorph-screen/{a.novel_against}", target=T, seed=0, formula=f,
                             site_A=r.A, site_B=r.B, site_X=r.X, label_gap=r.Eg, label_dhf=r.Es, latent_norm=float("nan"),
                             round=0, file=os.path.relpath(path, out), polymorph=r.polymorph, label_Ef=r.Ef,
                             Eg_cubic=r.get("Eg_cubic", float("nan"))))
    pd.DataFrame(rows, columns=["tag", "mode", "target", "seed", "formula", "site_A", "site_B", "site_X", "label_gap",
                                "label_dhf", "latent_norm", "round", "file", "polymorph", "label_Ef", "Eg_cubic"]
                 ).to_csv(os.path.join(out, "candidates.csv"), index=False)
    summary["proposals_per_target"] = per_target
    summary["returned"] = len(rows)
    print("proposals per target (novel, perovskite ground state, in window, Es <= es_max): "
          + ", ".join(f"{T:g} eV: {n}" for T, n in per_target.items()), flush=True)

    if a.truth == "test":
        truth = dft_truth(a.data, "test")
        m, Ptab = holdout(gs, cub, truth, a.targets, a.window, a.es_max, out)
        summary["holdout"] = {k: v for k, v in m.items() if k != "per_target"}
        pd.set_option("display.width", 220)
        print(f"\nHOLD-OUT against DFT ({m['covered_by_design_space']} of {m['test_compositions']} test compositions in the "
              f"design space): polymorph identified {100 * m['polymorph_identified']:.0f}%, perovskite call "
              f"{100 * m['perovskite_call_accuracy']:.0f}%, ground-state gap MAE {m['gs_gap_mae']:.2f} eV "
              f"(Spearman {m['gs_gap_spearman']:+.2f}), Es MAE {m['es_mae']:.3f} (Spearman {m['es_spearman']:+.2f}), "
              f"stable call {100 * m['stable_call_accuracy']:.0f}%")
        if "cubic_only_gap_mae_vs_gs" in m:
            print(f"cubic-only screen vs the real ground-state gap: MAE {m['cubic_only_gap_mae_vs_gs']:.2f} eV "
                  f"(Spearman {m['cubic_only_gap_spearman_vs_gs']:+.2f})")
        print(Ptab.round(3).to_string(index=False))
    summary["seconds"] = round(time.time() - t0, 1)
    json.dump(summary, open(os.path.join(out, "screen_summary.json"), "w"), indent=1, default=float)
    print(f"\n{a.tag}: {len(rows)} proposals in {summary['seconds']:.0f}s -> {out}", flush=True)


if __name__ == "__main__":
    main()
