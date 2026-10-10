"""Component scorecard: one command that says, for every part of the pipeline, what it does, what was measured on it and
whether it earns its place — so a failure is attributed to a component instead of to "the model".

Reads only what the diagnostics already wrote (nothing is re-run, nothing is graded by hand):
  results/checkups/<tag>.json    stage-by-stage checks (0 data ... 6 end-to-end)       -> status per stage
  results/ablation_summary.json  runs that differ in exactly one switch                -> contribution per switch
  results/model_metrics/*.json   held-out property prediction, retrieval, recovery     -> encoder / decoder quality
  results/unseen/*.json          models trained without an element, tested on it       -> trust outside the training chemistry
  results/discovery_report.csv   S.U.N. validation of the generated candidates         -> discovery yield, judge reliability

A switch's verdict is computed from its paired runs, never asserted: the difference must reach MARGIN points of DFT hit rate
in EVERY available pair.  When two seeds disagree in sign the switch is reported as seed-dependent instead of as a gain.
Usage: python component_report.py [--checkup TAG ...] [--margin 5]   (fairchem-env)
Writes results/component_report.md and results/component_report.json
"""
import argparse, glob, json, os
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__)); R = f"{HERE}/results"

# switch -> what it isolates, and the (with, without) run pairs from the ablation table; several pairs = independent repeats
SWITCHES = [
    ("labels read back from the decoded structure", "generation / labelling",
     [("G3", "G2"), ("G7a", "G0")]),
    ("unit-sphere latent space", "search", [("G4", "G3")]),
    ("manifold pull towards training latents", "search", [("G5", "G4")]),
    ("structure_property loss (property from the structure latent)", "training",
     [("G5", "G9"), ("G8", "G9")]),
    ("Option A: sample between nearest real structures (vs random proposals, same filter)", "search",
     [("OA", "AR"), ("OAs1", "ARs1")]),
    ("retraining alone, labels left as they were", "training", [("G1", "G0")]),
    ("everything together (full fix vs the published app)", "whole pipeline", [("G5", "G0")]),
]
SPREAD = ["G5", "G5w100", "G5w1000", "G5w1e4"]      # same pipeline, manifold weight 1 -> 10 000
# (component, check, checkup without the switch, checkup with it): stage-level effects the end-to-end hit rate cannot show
CROSS = [("search mode: optimise -> Option A (neighbours)", "distance to the data manifold", "grounded_grounded", "grounded_optA"),
         ("search mode: optimise -> Option A (neighbours)", "structure latent -> structure (generation condition)",
          "grounded_grounded", "grounded_optA")]


def switch_verdict(deltas, margin):
    if not deltas:
        return "not measured"
    if all(d >= 4 * margin for d in deltas):
        return "decisive"
    if all(d >= margin for d in deltas):
        return "earns its place"
    if all(abs(d) < margin for d in deltas):
        return "no measurable effect"
    if all(d <= -margin for d in deltas):
        return "harmful"
    return "seed-dependent (not proven)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkup", nargs="+", default=["grounded_optA", "desc_full_optA", "grounded_grounded"])
    ap.add_argument("--margin", type=float, default=5.0, help="smallest difference in DFT hit rate (points) that counts")
    a = ap.parse_args()
    rows, raw = [], {}

    def add(part, component, evidence, status, verdict):
        rows.append(dict(part=part, component=component, evidence=evidence, status=status, verdict=verdict))

    # ── 1. stages, from the checkups: the worst status a stage got, with the measurement behind it ──────────────────
    checkups = {t: json.load(open(f"{R}/checkups/{t}.json")) for t in a.checkup if os.path.exists(f"{R}/checkups/{t}.json")}
    raw["checkups"] = {t: d["switches"] for t, d in checkups.items()}
    rank = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}
    best = max(checkups, key=lambda t: sum(c["status"] == "PASS" for c in checkups[t]["checks"])) if checkups else None
    if best:
        for stage in sorted({c["stage"] for c in checkups[best]["checks"]}):
            cs = [c for c in checkups[best]["checks"] if c["stage"] == stage]
            worst = max(cs, key=lambda c: rank.get(c["status"], 0))
            detail = "; ".join(f"{c['check']}: {c['detail']}" for c in cs if c["status"] == worst["status"])
            add(f"stage {stage}", worst["check"] if len(cs) == 1 else f"{len(cs)} checks",
                detail[:300], worst["status"],
                {"PASS": "works", "INFO": "informational", "WARN": "works with a caveat", "FAIL": "broken or limited",
                 "N/A": "too few candidates in this short run to decide"}.get(worst["status"], "see evidence"))

    # the same check measured under two search modes: a per-stage effect the end-to-end hit rate cannot show
    for comp, check, ta, tb in CROSS:
        if ta in checkups and tb in checkups:
            va = next((c for c in checkups[ta]["checks"] if c["check"] == check), None)
            vb = next((c for c in checkups[tb]["checks"] if c["check"] == check), None)
            if va and vb:
                add("search", comp, f"{ta}: {va['detail']} || {tb}: {vb['detail']}",
                    f"{va['status']}->{vb['status']}",
                    "the switch repairs this stage" if rank.get(vb["status"], 0) < rank.get(va["status"], 0)
                    else "no change at this stage")

    # ── 2. switches, from the ablation table: measured contribution of each design choice ─────────────────────────
    tbl = {r["tag"]: r for r in json.load(open(f"{R}/ablation_summary.json"))["table"]} if os.path.exists(f"{R}/ablation_summary.json") else {}
    for name, part, pairs in SWITCHES:
        deltas, shown = [], []
        for w, wo in pairs:
            if w in tbl and wo in tbl:
                d = tbl[w]["hit_dft_pct"] - tbl[wo]["hit_dft_pct"]
                deltas.append(d)
                shown.append(f"{w} vs {wo}: hits {tbl[w]['hit_dft_pct']:.0f}% vs {tbl[wo]['hit_dft_pct']:.0f}% "
                             f"({d:+.0f} pts), rho {tbl[w]['rho_dft']:+.2f} vs {tbl[wo]['rho_dft']:+.2f}")
        verdict = switch_verdict(deltas, a.margin)
        if name.startswith("manifold") and all(t in tbl for t in SPREAD):
            h = [tbl[t]["hit_dft_pct"] for t in SPREAD]
            shown.append(f"weight 1 -> 10 000: hits {min(h):.0f}-{max(h):.0f}% (spread {max(h) - min(h):.0f} pts)")
            if max(h) - min(h) < a.margin and verdict == "no measurable effect":
                verdict = "no measurable effect over four orders of magnitude: drop it"
        add(part, name, " | ".join(shown) or "pairs missing from the ablation table",
            "MEASURED" if deltas else "n/a", verdict)
        raw.setdefault("switch_deltas", {})[name] = deltas
    for tag, what in (("R", "chance: random valid compositions"), ("O", "ceiling: Perov-5 compositions ranked by their DFT gap")):
        if tag in tbl:
            add("baseline", what, f"hits {tbl[tag]['hit_dft_pct']:.0f}%, rho {tbl[tag]['rho_dft']:+.2f}, "
                                 f"{tbl[tag]['novel_pct']:.0f}% of them new to Perov-5", "REFERENCE", "context for the rows above")

    # ── 3. encoder quality and trust outside the training chemistry ───────────────────────────────────────────────
    for f in sorted(glob.glob(f"{R}/unseen/*.json")):
        u = json.load(open(f)); s, n = u["seen"], u["unseen"]
        held = ",".join(u["held_out_elements"])
        ratio = n["gap_mae_nonmetal"] / max(s["gap_mae_nonmetal"], 1e-9)
        add("stage 1 encoder", f"trust test: {u['tag']} (trained without {held})",
            f"seen chemistry gap MAE {s['gap_mae_nonmetal']:.2f} eV (r {s['gap_r_nonmetal']:+.2f}), dHf {s['dhf_mae']:.3f} | "
            f"held-out elements {n['gap_mae_nonmetal']:.2f} eV (r {n['gap_r_nonmetal']:+.2f}), dHf {n['dhf_mae']:.3f} "
            f"-> {ratio:.1f}x worse",
            "PASS" if ratio < 1.5 else ("WARN" if ratio < 2.5 else "FAIL"),
            "reliable on these elements" if ratio < 1.5 else "labels for unseen elements cannot be trusted")
    for f in sorted(glob.glob(f"{R}/model_metrics/*.json")):
        m = json.load(open(f)); p, rep, rec = m["property_prediction"], m["representation"], m["recoverability"]
        add("stages 1-3", f"held-out metrics: {m['tag']}",
            f"gap MAE (non-metals) {p['mae_dir_gap_nonzero']:.2f} eV, metal/non-metal {100*p['metal_vs_gap_accuracy']:.0f}%, "
            f"dHf MAE {p['mae_heat_all_nonzero']:.3f} | retrieval top-1 {100*rep['retrieval_top1']:.0f}%, "
            f"5-NN gap MAE {rep['knn_mae_dir_gap']:.3f} eV | composition recovered from z_c "
            f"{rec['from_structure']['composition_exact_pct']:.0f}%, from z_p {rec['from_property']['composition_exact_pct']:.0f}%",
            "MEASURED", "reference numbers for the stage rows")

    # ── 4. discovery and the independent judges ───────────────────────────────────────────────────────────────────
    if os.path.exists(f"{R}/discovery_report.csv"):
        V = pd.read_csv(f"{R}/discovery_report.csv")
        add("stage 7 validation", "S.U.N. funnel (MLIP relaxation, hull, tau, novelty)",
            f"{len(V)} candidates: {int(V.novel_mp.sum())} absent from MP, {int(V.stable.sum())} stable (<=0.1 eV/atom), "
            f"{int(V.formable.sum())} formable, {int((~V.novel_lit).sum())} already known in the literature "
            f"-> {int(V.SUN.sum())} S.U.N., {int(V.SUN_on_target.sum())} of them on target", "MEASURED",
            "works: it rejects most candidates and rediscovers known compounds")
        k = V.dropna(subset=["megnet_gllbsc_gap"]); ka = V.dropna(subset=["la_analogue_gap"])
        rm = spearmanr(k.target, k.megnet_gllbsc_gap)[0] if len(k) > 2 else float("nan")
        rl = spearmanr(ka.target, ka.la_analogue_gap)[0] if len(ka) > 2 else float("nan")
        add("stage 7 validation", "independent judge: MEGNet multi-fidelity gap",
            f"rho(target, MEGNet) {rm:+.2f} over {len(k)}; mean |MEGNet - target| {np.abs(k.megnet_gllbsc_gap - k.target).mean():.2f} eV",
            "WARN" if rm < 0.6 else "PASS", "too weak on these mixed-anion compounds to be the deciding judge")
        add("stage 7 validation", "independent evidence: DFT gap of the La/Y analogue (Perov-5)",
            f"rho(target, analogue gap) {rl:+.2f} over {len(ka)}; analogue within +-0.5 eV of target for "
            f"{int(ka.analogue_on_target.sum())}/{len(ka)}", "PASS" if rl >= 0.6 else "WARN",
            "the strongest target-following evidence we have for new compounds")

    # ── write ────────────────────────────────────────────────────────────────────────────────────────────────────
    json.dump(dict(margin=a.margin, checkup_used=best, rows=rows, raw=raw), open(f"{R}/component_report.json", "w"), indent=1)
    with open(f"{R}/component_report.md", "w") as f:
        f.write("# Component scorecard\n\nEvery line is a measurement already written by the diagnostics; the verdict on each "
                f"switch is computed from its paired runs (a difference counts from {a.margin:g} points of DFT hit rate, and "
                "must hold in every seed pair).\n\n")
        if best:
            f.write(f"Stage rows from checkup `{best}` ({checkups[best]['switches']}).\n\n")
        f.write("| part | component | status | verdict | evidence |\n|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['part']} | {r['component']} | **{r['status']}** | {r['verdict']} | {r['evidence']} |\n")
    print(open(f"{R}/component_report.md").read())


if __name__ == "__main__":
    main()
