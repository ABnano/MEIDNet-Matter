"""The staged scorecard for a trained model: blocks S1-S4, S8 and S9, graded by the central definition.

This is the screen a user sees after training and before asking for any candidate: every block with its verdict, each
number next to the band it was judged against, and for anything short of PASS the plain-language meaning and the remedy.
It runs the diagnostics that need a model but no generation, so it answers "is this model worth generating with?" without
spending a search.

It also runs the two comparisons that single-number reports hide:
  ablation     main vs the control model (structure-only losses off) — what those losses actually bought on THIS data
  replicate    main vs a second seed — whether the numbers are reproducible at all

Everything is graded through stages.py, so the verdicts match STAGE_EVALUATION.md and the app exactly.

Usage:
  python scorecard.py <intake_dir> --models main=<ckpt> [control=<ckpt> seed1=<ckpt>] --gap COL --cost COL \
         --out <dir> [--targets 1 2 3] [--judge-tag TAG] [--skip-run]
  --skip-run reuses the diagnostics already in <out> instead of recomputing them.
"""
import argparse, json, os, subprocess, sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
try:
    from meidnet_eval.stages import BY_ID, CONFIGS
except ImportError:          # run as a plain script from eval/
    from stages import BY_ID, CONFIGS

FID = os.environ.get("MEIDNET_FIDELITY_DIR", "")   # the CGCNN judge checkout, when available
PY = sys.executable


def run(cmd, env, log, cwd):
    """One component, from a work folder inside --out (never the package's own folder) by its absolute path; its exit
    status is returned and recorded in the log."""
    if cmd[1].endswith(".py") and not os.path.isabs(cmd[1]):
        cmd = [cmd[0], os.path.join(HERE, cmd[1]), *cmd[2:]]
    os.makedirs(cwd, exist_ok=True)
    with open(log, "a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n"); f.flush()
        r = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
        f.write(f"[exit {r.returncode}]\n")
    return r.returncode


def collect(out, name, intake, ckpt, gap, cost, targets, env, skip):
    """Run (or reuse) the per-model diagnostics and return the measured values keyed by central metric id."""
    cj = os.path.join(out, f"checkup_{name}.json")
    mj = os.path.join(out, f"metrics_{name}.json")
    dj = os.path.join(out, f"decoder_{name}.json")
    log = os.path.join(out, "diagnostics.log")
    work = os.path.join(out, "_work")
    failed = []
    if not skip:
        # results of an earlier run (another model, perhaps) must never stand in for this one: clear them first
        src = os.path.join(work, "checkups", f"sc_{name}.json")
        for stale in (cj, mj, dj, src):
            if os.path.exists(stale):
                os.remove(stale)
        rc = run([PY, "pipeline_checkup.py", f"sc_{name}", ckpt, "--label-source", "structure", "--latent-space", "sphere",
                  "--skip-search", "--family", "none", "--out-dir", os.path.join(work, "checkups")], env, log, work)
        if rc == 0 and os.path.exists(src):
            json.dump(json.load(open(src)), open(cj, "w"), indent=1)
        else:
            failed.append(f"pipeline_checkup.py (exit {rc})")
        rc = run([PY, "model_metrics.py", f"sc_{name}", ckpt, mj, intake], env, log, work)
        if rc != 0 or not os.path.exists(mj):
            failed.append(f"model_metrics.py (exit {rc})")
        rc = run([PY, "decoder_autopsy.py", ckpt, "--data", intake, "--json", dj], env, log, work)
        if rc != 0 or not os.path.exists(dj):
            failed.append(f"decoder_autopsy.py (exit {rc})")

    v, raw = {}, {}
    if os.path.exists(mj):
        m = json.load(open(mj)); raw["model_metrics"] = m
        pp, rep, rec = m["property_prediction"], m["representation"], m["recoverability"]
        spread = m.get("spreads", {})
        v["metal_accuracy"] = pp.get("metal_vs_gap_accuracy")
        v["gap_r"] = pp.get(f"pearson_{gap}_nonzero")
        v["retrieval_vs_chance"] = None          # filled from the checkup, which knows the number of profiles
        v["comp_exact_gen"] = rec["from_structure"]["composition_exact_pct"]
        v["comp_exact_from_property"] = rec["from_property"]["composition_exact_pct"]
    if os.path.exists(cj):
        c = json.load(open(cj)); raw["checkup"] = c
        for ch in c["checks"]:
            k, val = ch["check"], ch.get("value")
            if k.startswith("structure -> ") and gap.lower() in k.lower() or k == "structure -> band gap":
                v["gap_rel_mae"] = val
            elif k == "structure -> metal or not":
                v["metal_accuracy"] = val
            elif k.startswith("structure -> ") and cost and cost.lower() in k.lower():
                v["cost_rel_mae"] = val
            elif k.startswith("latent organised"):
                v["knn_rel_mae"] = val
            elif k.startswith("structure <-> property retrieval"):
                v["retrieval_vs_chance"] = val
            elif k.startswith("structure latent -> structure"):
                v["comp_exact_gen"] = val
            elif k.startswith("train/generation mismatch"):
                v["condition_drop"] = val
            elif k.startswith("property latent -> structure"):
                v["comp_exact_from_property"] = val
            elif k.startswith("sensitivity to latent length"):
                v["head_length_sensitivity"] = val
    if os.path.exists(dj):
        raw["decoder"] = json.load(open(dj))
    raw["failed"] = failed
    return {k: x for k, x in v.items() if x is not None}, raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("intake"); ap.add_argument("--models", nargs="+", required=True, help="name=checkpoint")
    ap.add_argument("--gap", required=True); ap.add_argument("--cost", default=None)
    ap.add_argument("--targets", type=float, nargs="+", default=None)
    ap.add_argument("--judge-tag", default=None, help="a CGCNN judge in MEIDNET_FIDELITY_DIR (research setup)")
    ap.add_argument("--judge", choices=["megnet", "none"], default="none",
                    help="block S8: qualify the MEGNet band-gap judge on INTAKE/test.csv (needs matgl)")
    ap.add_argument("--judge-n", type=int, default=80)
    ap.add_argument("--out", required=True); ap.add_argument("--skip-run", action="store_true")
    a = ap.parse_args()
    # absolute paths: the components run from a work folder, and a relative path must mean what the user meant
    a.intake, a.out = os.path.abspath(a.intake), os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    models = {k: os.path.abspath(v) for k, v in (m.split("=", 1) for m in a.models)}
    if not a.cost:                                 # the second property, when the intake has an obvious one
        try:
            cols = [c for c in pd.read_csv(os.path.join(a.intake, "train.csv"), nrows=1).columns if c != a.gap]
            cands = [c for c in cols if any(w in c.lower() for w in ("formation", "heat", "e_form", "dhf"))]
            if len(cands) == 1:
                a.cost = cands[0]
                print(f"--cost not given: using the intake's {a.cost}", flush=True)
        except Exception:
            pass
    if "main" not in models:                       # the first model named is the one every block is computed for
        first = next(iter(models))
        print(f"no model is named 'main': treating '{first}' as the main model (control= and seed1= are the comparisons)", flush=True)
        models = {"main": models[first], **{k: v for k, v in models.items() if k != first}}
    env = dict(os.environ, PYTHONPATH=os.path.dirname(HERE), EVAL_DATA=a.intake, EVAL_GAP=a.gap,
               CHECKUP_MATERIALS="/nonexistent", PYTHONUNBUFFERED="1")
    if a.cost:
        env["EVAL_COST"] = a.cost

    measured, raws = {}, {}
    for name, ckpt in models.items():
        if not os.path.exists(ckpt):
            print(f"  {name}: checkpoint missing ({ckpt}) — skipped", flush=True); continue
        print(f"running diagnostics for {name} ...", flush=True)
        measured[name], raws[name] = collect(a.out, name, a.intake, ckpt, a.gap, a.cost, a.targets, env, a.skip_run)
    if "main" not in measured:
        raise SystemExit(f"the main model's checkpoint was not found: {models['main']}")

    # block S9 needs the reliability map, which is a separate script
    rel = os.path.join(a.out, "reliability_map.csv")
    if not a.skip_run and "main" in models and os.path.exists(models["main"]):
        cmd = [PY, "reliability_map.py", "--ckpt", models["main"], "--data", a.intake, "--gap", a.gap,
               "--out", a.out]
        if a.targets:
            cmd += ["--targets"] + [str(t) for t in a.targets]
        if os.path.exists(rel):
            os.remove(rel)
        if run(cmd, env, os.path.join(a.out, "diagnostics.log"), os.path.join(a.out, "_work")) != 0 or not os.path.exists(rel):
            raws.setdefault("main", {}).setdefault("failed", []).append("reliability_map.py")
    if os.path.exists(rel):
        R = pd.read_csv(rel)
        measured.setdefault("main", {})["servable_targets"] = int((R.verdict == "servable").sum())

    # block S9: the MEASURED held-out label error, which supersedes the support count as soon as a model exists
    if "main" in models and os.path.exists(models["main"]):
        try:
            import torch
            from meidnet.benchmark import load_split
            from meidnet.checkpoint import load_checkpoint
            from meidnet.data import MaterialsDataset
            from torch.utils.data import DataLoader
            lm = load_checkpoint(models["main"], device="cpu"); cols = list(lm.stats.columns); gi = cols.index(a.gap)
            te, _ = load_split(a.intake, "test", cols, lm.model.max_sites)
            yte = np.array([r.properties[gi] for r in te]); P = []
            with torch.no_grad():
                for b in DataLoader(MaterialsDataset(te, lm.stats), batch_size=64, shuffle=False):
                    zc, _ = lm.model.encode_crystal(b["crystal_vec"])
                    P.append(lm.stats.denormalize_tensor(lm.model.property_decoder(zc)).numpy())
            P = np.concatenate(P)
            sd = float(yte.std())
            if sd > 0:
                measured.setdefault("main", {})["holdout_label_error"] = float(np.abs(P[:, gi] - yte).mean() / sd)
        except Exception as e:
            print(f"  (held-out label error not measured: {e})")

    # block S8: the judge must qualify on its own held-out split before its verdict counts
    judge = {}
    if a.judge == "megnet":
        try:
            try:
                from meidnet_eval.target_calibration import qualify
            except ImportError:
                from target_calibration import qualify
            q = qualify(os.path.join(a.intake, "test.csv"), a.judge_n, {}, a.gap, "cif")
            te = pd.read_csv(os.path.join(a.intake, "test.csv"), usecols=[a.gap])
            sd = float(te[a.gap].std())
            judge = dict(name=f"MEGNet band gap, fidelity {q['fidelity']}", mae_all=q["mae"], mae_nonzero=q.get("mae_on_nonzero"),
                         corr=q.get("spearman"), corr_name="Spearman", n=q["n"], by_fidelity=q.get("by_fidelity"))
            if sd > 0 and q.get("mae_on_nonzero") is not None:
                measured.setdefault("main", {})["judge_qualification"] = q["mae_on_nonzero"] / sd
            print(f"judge (S8): MEGNet fidelity {q['fidelity']} on the test split: MAE {q['mae']:.3f} eV, Spearman {q['spearman']:.2f} (n = {q['n']})", flush=True)
        except Exception as e:
            print(f"  (judge not qualified: {e})")
    if a.judge_tag:
        jp = os.path.join(FID, "models", f"{a.judge_tag}_test_metrics.json")
        if os.path.exists(jp):
            j = json.load(open(jp)); judge = j
            tr = pd.read_csv(os.path.join(a.intake, "test.csv"), usecols=[a.gap])
            sd = float(tr[a.gap].std())
            if sd > 0 and j.get("mae_nonzero") is not None:
                measured.setdefault("main", {})["judge_qualification"] = j["mae_nonzero"] / sd

    # ── grade every block through the central definition ──
    # a remedy that says "switch the structure losses on" is empty advice when the configuration already has them on:
    # read the main checkpoint's training configuration once and condition the wording on it
    lw = {}
    try:
        from meidnet.checkpoint import load_checkpoint as _lc
        lw = (_lc(models["main"], device="cpu").meta.get("config", {}).get("training", {}) or {}).get("loss_weights", {}) or {}
    except Exception:
        lw = {}
    def remedy_for(m):
        text = m.remedy
        if "structure losses" in text.lower() and float(lw.get("structure_reconstruction", 0) or 0) > 0:
            text += " In this configuration the structure losses are already on, so the limit is the data (block S0's density), not the losses."
        return text
    report = {}
    failures = {name: (raws.get(name) or {}).get("failed", []) for name in measured}
    for name, vals in measured.items():
        blocks = {}
        model_failed = [f for f in failures.get(name, []) if not f.startswith("reliability_map")]
        for sid in ("S1", "S2", "S3", "S4", "S8", "S9"):
            st = BY_ID[sid]
            sub = {m.id: vals[m.id] for m in st.metrics if m.id in vals}
            if sid in ("S1", "S2", "S3", "S4") and model_failed:
                # a block whose diagnostics failed is not graded: neither from partial values nor from an earlier run
                blocks[sid] = dict(name=st.name, question=st.question, verdict="NOT COMPUTED", metrics=[],
                                   reason="failed: " + ", ".join(model_failed) + " (see diagnostics.log)")
                continue
            if not sub:
                continue
            verdict, grades = st.verdict(sub, context=vals)
            rows = []
            for m in st.metrics:
                if m.id not in sub:
                    continue
                p, w, f = m.band_text()
                rows.append(dict(metric=m.name, id=m.id, value=sub[m.id], unit=m.unit,
                                 band=("context only" if m.info_only else f"PASS {p}" + (f" / WARN {w}" if w else "")),
                                 grade=grades[m.id],
                                 note=("" if grades[m.id] in ("PASS", "INFO") or m.info_only else
                                       f"{m.meaning_bad} Remedy: {remedy_for(m)}")))
            blocks[sid] = dict(name=st.name, question=st.question, verdict=verdict, metrics=rows)
        report[name] = blocks

    # ── the two comparisons a single number hides ──
    comparisons = {}
    if "main" in measured and "control" in measured:
        comparisons["ablation (main vs control: what the structure-only losses bought)"] = {
            k: f"{measured['main'].get(k)} vs {measured['control'].get(k)}"
            for k in ("gap_rel_mae", "metal_accuracy", "comp_exact_gen", "knn_rel_mae")
            if k in measured["main"] and k in measured["control"]}
    if "main" in measured and "seed1" in measured:
        comparisons["replicate (main vs seed 1: is it reproducible)"] = {
            k: f"{measured['main'].get(k)} vs {measured['seed1'].get(k)}"
            for k in ("gap_rel_mae", "metal_accuracy", "comp_exact_gen")
            if k in measured["main"] and k in measured["seed1"]}

    json.dump(dict(intake=a.intake, gap=a.gap, cost=a.cost, models=models, measured=measured, report=report,
                   comparisons=comparisons, judge=judge, failures=failures), open(os.path.join(a.out, "scorecard.json"), "w"),
              indent=1, default=float)

    # ── render ──
    ds = os.path.basename(os.path.normpath(a.intake))
    if ds in ("intake", "data"):
        ds = os.path.basename(os.path.dirname(os.path.normpath(a.intake)))
    L = [f"# Staged scorecard — {ds}", "",
         f"Target property `{a.gap}`" + (f"; second property `{a.cost}`" if a.cost else "") +
         ". Blocks S1-S4, S8 and S9: everything that needs a trained model but no generation. "
         "Bands and remedies come from `stages.py`, the same definition as the reference document.", ""]
    main = report.get("main", {})
    L += ["| block | question | verdict |", "|---|---|---|"]
    for sid, b in main.items():
        L.append(f"| **{sid}** {b['name']} | {b['question']} | **{b['verdict']}** |")
    L.append("")
    for sid, b in main.items():
        L += [f"## {sid} — {b['name']}: **{b['verdict']}**", "",
              "| metric | value | band | grade |", "|---|---|---|---|"]
        if b["verdict"] == "NOT COMPUTED":
            L += [f"Not computed: {b['reason']}.", ""]
            continue
        for r in b["metrics"]:
            L.append(f"| {r['metric']} ({r['unit']}) | {r['value']:.4g} | {r['band']} | **{r['grade']}** |")
        L.append("")
        for r in b["metrics"]:
            if r["note"]:
                L.append(f"- **{r['metric']} is {r['grade']}.** {r['note']}")
            elif r["grade"] == "INFO" and r["band"] != "context only":
                L.append(f"- *{r['metric']}*: not applicable to this run (the hazard it measures cannot arise here), "
                         f"value {r['value']:.4g} recorded for the record.")
        L.append("")
    if comparisons:
        L += ["## Comparisons", ""]
        for title, d in comparisons.items():
            L += [f"**{title}**", "", "| metric | values |", "|---|---|"]
            L += [f"| {k} | {v} |" for k, v in d.items()]
            L.append("")
    if judge:
        name = judge.get("name") or a.judge_tag
        corr = judge.get("corr", judge.get("pearson_nonzero", float("nan")))
        L += ["## Judge qualification (block S8)", "",
              f"`{name}` on the held-out split: MAE {judge.get('mae_all', float('nan')):.3f}, "
              f"MAE on non-zero {judge.get('mae_nonzero', float('nan')):.3f}, {judge.get('corr_name', 'r')} {corr:+.3f}, "
              f"n = {judge.get('n')}. A judge is believed only if it qualifies here first.", ""]
    open(os.path.join(a.out, "scorecard.md"), "w").write("\n".join(L))
    print("\n".join(L))
    print(f"\nwrote {a.out}/scorecard.md and scorecard.json")
    failed = {k: v for k, v in failures.items() if v}
    if failed:
        print("\nNOT COMPUTED: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in failed.items()) + f" (log: {a.out}/diagnostics.log)", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
