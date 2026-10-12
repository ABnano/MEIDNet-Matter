"""MEIDNet discovery pipeline: one command from a user's perovskite table to a validated, interpretable S.U.N. shortlist.

It is the pipeline validated on Perov-5, driven by the dataset instead of by Perov-5's file names: every stage is a
separate component with its own check, everything lands in ONE run folder, and every stage leaves a stage card
(journey.py) from which the MEIDNet Matter interface is designed.  Rerunning the same command resumes after the last
finished stage; --from / --until run a slice.

  00 structures    the upload; a table without CIFs gets them from OQMD by id, verified against its labels  login node
  01 intake        audit, prototypes, composition-grouped split (intake.py)                                 CPU job
  02 models        MEIDNet main + seed replicate + ablation control; independent CGCNN judges              GPU job
  03 diagnosis     stage checkup per model, decoder autopsy -> generation/screening rule, reliability map  CPU job
  04 design space  polymorph templates learned from the data (auto_family.py), novelty frontier             login node
  05 proposals     polymorph-aware screening at every target, novel against the whole dataset             CPU job
  06 hold-out      the same screen with the test split hidden, every number checked against its DFT        CPU job
  07 novelty       Materials Project and OQMD lookups for the proposals (free DFT where it exists)       login node
  08 validation    two ML potentials, hull, formability, judges on the relaxed cells                       CPU job
  09 report        one report from the stage cards and the evidence tables (final_report.py)               login node

Usage (login node, e.g. under nohup setsid; compute stages are submitted with sbatch --wait):
  python discover.py --table oqmd_data.csv --run RUN_DIR --id-col entry_id --formula-col name --vol-col vol --sg-col sg \
         --props Ef Eg Es --gap Eg --stability Es --energy Ef --anion O --targets 0.5 1 1.5 2 2.5 3 4
  --smoke      tiny training, for plumbing tests;  --offline   structures from the OQMD cache only (no network)
"""
import argparse, datetime, glob, json, os, re, shutil, subprocess, sys, time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
try:
    import meidnet_eval.journey as journey
except ImportError:          # run as a plain script from eval/
    import journey
try:
    from meidnet_eval.stages import ALL_METRICS, BY_ID, STAGES as STAGE_SPECS
except ImportError:          # run as a plain script from eval/
    from stages import ALL_METRICS, BY_ID, STAGES as STAGE_SPECS

FC = os.environ.get("MEIDNET_PYTHON", sys.executable)        # MEIDNet, CGCNN, analysis
MG = os.environ.get("MEIDNET_PYTHON_JUDGE", FC)             # matgl: the ML potentials and MEGNet
FID = os.environ.get("MEIDNET_FIDELITY_DIR", "")  # cgcnn_judge.py and its saved judges
STAGES = ["00_structures", "01_intake", "02_models", "03_diagnosis", "04_design_space", "05_proposals",
          "06_holdout", "07_novelty", "08_validation", "09_report"]
MODELS = {"main": (0, 1.0), "seed1": (1, 1.0), "control": (0, 0.0)}   # name: (seed, weight of the structure-only losses)


class Run:
    def __init__(self, a):
        self.a = a
        self.dir = os.path.abspath(a.run)
        self.name = re.sub(r"[^A-Za-z0-9]+", "_", os.path.basename(self.dir)).strip("_")
        for sub in ("done", "logs", "jobs", "cards"):
            os.makedirs(self.path(sub), exist_ok=True)

    def path(self, *p):
        return os.path.join(self.dir, *p)

    def is_done(self, stage):
        return os.path.exists(self.path("done", stage))

    def mark(self, stage, info):
        json.dump(info, open(self.path("done", stage), "w"), indent=1, default=str)

    def env(self, **extra):
        e = dict(os.environ, PYTHONPATH=ROOT, PYTHONUNBUFFERED="1", DGLBACKEND="pytorch")
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run(self, cmd, log, **env):
        """A short step on the login node; its output goes to logs/<log>."""
        with open(self.path("logs", log), "a") as f:
            f.write(f"\n$ {' '.join(map(str, cmd))}\n"); f.flush()
            subprocess.run([str(c) for c in cmd], cwd=HERE, env=self.env(**env), stdout=f, stderr=subprocess.STDOUT,
                           check=True)

    def sbatch(self, name, body, partition="debug", gres=None, cpus=32, mem="64G", hours="01:55:00"):
        """A compute stage as its own job script (kept in jobs/ so the run is reproducible), waited for."""
        lines = ["#!/bin/bash", f"#SBATCH --job-name=md-{name}", "#SBATCH --account=catalys",
                 f"#SBATCH --partition={partition}", f"#SBATCH --cpus-per-task={cpus}", f"#SBATCH --mem={mem}",
                 f"#SBATCH --time={hours}", f"#SBATCH --output={self.path('logs', name + '-%j.out')}"]
        if gres:
            lines.append(f"#SBATCH --gres={gres}")
        lines += ["set -u", f"cd {HERE}",
                  f"export PYTHONPATH={ROOT} PYTHONUNBUFFERED=1 DGLBACKEND=pytorch OMP_NUM_THREADS=8", body]
        script = self.path("jobs", f"{name}.sbatch")
        open(script, "w").write("\n".join(lines) + "\n")
        r = subprocess.run(["sbatch", "--wait", script], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"job {name} failed (exit {r.returncode}): {r.stdout.strip()} {r.stderr.strip()} "
                               f"-- see {self.path('logs')}")

    def card(self, nn, key, **kw):
        journey.write_card(self.dir, nn, key, run_tag=self.name, **kw)


def graded(stage_id, values, context=None):
    """Grade measured values against the CENTRAL bands in stages.py and return (verdict, reason, per-metric rows).

    Every stage goes through here, so a run never invents its own pass/fail logic: the number a user sees, the band it is
    judged against and the remedy they are offered all come from the same definition as STAGE_EVALUATION.md and the app.
    """
    st = BY_ID[stage_id]
    verdict, grades = st.verdict(values, context=context if context is not None else values)
    rows, bad = {}, []
    for m in st.metrics:
        v = values.get(m.id)
        g = grades[m.id]
        if v is None:
            continue
        p, w, f = m.band_text()
        band = f"PASS {p}" + (f" / WARN {w}" if w else "")
        rows[f"{m.name} ({m.unit})"] = f"{v:.3g} \u2192 {g}" + ("" if m.info_only else f"  [{band}]")
        if g in ("WARN", "FAIL"):
            bad.append(f"{m.name}: {m.meaning_bad} Remedy: {m.remedy}")
    reason = (f"{st.question} \u2192 {verdict}. " + " | ".join(bad)) if bad else f"{st.question} \u2192 {verdict}."
    return verdict, reason, rows, bad


# ───────────────────────────── 00 structures ─────────────────────────────
def s00_structures(R, t0):
    a = R.a
    out = R.path("structures"); os.makedirs(out, exist_ok=True)
    header = list(pd.read_csv(a.table, nrows=1).columns)
    if a.cif_col in header:                                      # the upload already carries structures
        d = pd.read_csv(a.table)
        t = pd.DataFrame({"material_id": d[a.id_col], "cif": d[a.cif_col], "formula": d[a.formula_col],
                          **{p: d[p] for p in a.props}})
        t.to_csv(os.path.join(out, "table.csv"), index=False)
        rep = dict(input_rows=len(d), kept=len(t), kept_fraction=1.0, dropped={}, source="uploaded CIFs")
    else:                                                        # structure-less table: fetch from OQMD by id
        try:
            import meidnet_eval.fetch_oqmd_structures as F
        except ImportError:          # run as a plain script from eval/
            import fetch_oqmd_structures as F
        F.fetch(argparse.Namespace(table=a.table, out=out, anion=a.anion, props=a.props, id_col=a.id_col,
                                   formula_col=a.formula_col, vol_col=a.vol_col, sg_col=a.sg_col,
                                   max_atoms=a.max_sites, workers=a.workers, offline=a.offline))
        rep = json.load(open(os.path.join(out, "fetch_report.json")))
        rep["source"] = "OQMD REST API, matched by entry id" + (" (offline: cached formulas only)" if a.offline else "")
    frac = rep.get("kept_fraction", 0)
    verdict = "PASS" if frac >= 0.98 else ("WARN" if frac >= 0.9 else "FAIL")
    R.card(0, "structures", title="Structures for every row", matter="projects/{id}/dataset (upload)",
           matter_new="cif" not in header,
           purpose="Give every row of the upload a crystal structure that provably belongs to its labels.",
           verdict=verdict, reason=f"{100 * frac:.1f}% of the selected rows kept with a verified structure",
           inputs={"table": a.table, "rows": rep.get("input_rows"), "source": rep.get("source")},
           decisions=[dict(question="Which chemistry should this run cover?",
                           options=["oxides only", "all anions", "halides + chalcogenides"], default="oxides only",
                           chosen=f"anion {a.anion}" if a.anion else "all anions",
                           why="oxides are 92% of this dataset and the densest part, so target following is most "
                               "trustworthy")],
           metrics={"rows selected": rep.get("selected_rows", rep.get("input_rows")), "rows kept": rep.get("kept"),
                    "dropped by reason": rep.get("dropped"), "atoms per cell": rep.get("natoms"),
                    "experimentally reported (ICSD)": rep.get("experimental"), "seconds": rep.get("seconds")},
           warnings=[f"{k}: {v}" for k, v in (rep.get("dropped") or {}).items() if v],
           seconds=time.time() - t0, artefacts=[os.path.join(out, "table.csv")],
           ui_notes="Show the match/verify counts, not just 'uploaded'; the fetch is a resumable background job "
                    "(OQMD answers in 1 s to minutes per formula and rate-limits bursts with HTTP 429).")
    return rep


# ───────────────────────────── 01 intake ─────────────────────────────
def s01_intake(R, t0):
    a = R.a
    body = (f"{FC} intake.py {R.path('structures', 'table.csv')} {R.path('intake')} --id material_id --cif cif "
            f"--props {' '.join(a.props)}\ntest -s {R.path('intake', 'train.csv')}")
    R.sbatch("01_intake", body, cpus=8, mem="48G", hours="01:00:00")
    au = json.load(open(R.path("intake", "audit.json")))
    gp = au["properties"].get(a.gap, {})
    vals = {"shared_profile": au.get("materials_sharing_profile_with_>=10"),
            "zero_share": gp.get("zero_share"),
            "density": au.get("compositions_per_element")}          # written by intake.py; None until the preview lands
    verdict, reason, rows, bad = graded("S0", {k: v for k, v in vals.items() if v is not None})
    R.card(1, "intake", title="Is the data usable?", matter="projects/{id}/dataset (summary, ambiguity grid)",
           purpose=BY_ID["S0"].purpose, verdict=verdict, reason=reason,
           metrics={**rows, "structures parsed": f"{au['parsed']} of {au['rows']}", "elements": au["elements"],
                    "prototypes": au["prototypes"], "duplicates": au["duplicates"], "split": au["split_sizes"],
                    **{f"{p} range": f"{v['min']:.3g} to {v['max']:.3g} (zero share {100 * v['zero_share']:.0f}%)"
                       for p, v in au["properties"].items()}},
           warnings=bad, seconds=time.time() - t0, artefacts=[R.path("intake", "audit.md")],
           ui_notes="Graded against the central bands in stages.py (block S0). The split is by composition: every "
                    "polymorph and both site assignments of a formula stay together.")
    return au


# ───────────────────────────── 02 models ─────────────────────────────
def model_yaml(R, name, seed, w):
    a = R.a
    epochs = 3 if a.smoke else a.epochs
    props = "\n".join(f"    - {{column: {p}, normalize: true}}" for p in a.props)
    return f"""# Written by discover.py for run {R.name}: {name} (seed {seed}, structure-only losses {w}).
name: {R.name}_{name}
description: "{R.name} {name}: all polymorphs <= {a.max_sites} atoms, site_order roles, cgcnn descriptors, periodic encoder"
output_dir: {R.path('models', name, 'out')}
data:
  table: {R.path('intake', 'train.csv')}
  val_table: {R.path('intake', 'val.csv')}
  id_column: material_id
  cif_column: cif
  properties:
{props}
  max_sites: {a.max_sites}
  site_order: roles
  align_to_prototype: false
model:
  decoder_coordinate_input: zeros
  periodic_encoder: true
  element_features: cgcnn
training:
  epochs: {epochs}
  batch_size: 64
  learning_rate: 0.001
  seed: {seed}
  device: cuda
  save_every: 50
  loss_weights: {{structure_reconstruction: {w}, structure_property: {w}}}
"""


def last_val_line(log):
    lines = [l for l in open(log) if "val MAE" in l] if os.path.exists(log) else []
    return lines[-1].strip() if lines else ""


def s02_models(R, t0):
    a = R.a
    body = []
    for g, (name, (seed, w)) in enumerate(MODELS.items()):
        os.makedirs(R.path("models", name), exist_ok=True)
        open(R.path("models", name, "meidnet.yaml"), "w").write(model_yaml(R, name, seed, w))
        body.append(f"CUDA_VISIBLE_DEVICES={g} {FC} -m meidnet.cli train {R.path('models', name, 'meidnet.yaml')} "
                    f"> {R.path('logs', f'train_{name}.log')} 2>&1 &")
    judges = [] if a.smoke else [a.gap, a.stability]
    if judges:
        loop = "; ".join(f"CUDA_VISIBLE_DEVICES=3 JUDGE_DATA={R.path('intake')} JUDGE_TARGET={c} JUDGE_TAG={R.name}_{c} "
                         f"{FC} {FID}/cgcnn_judge.py train > {R.path('logs', f'judge_{c}.log')} 2>&1" for c in judges)
        body.append(f"( {loop} ) &")
    body.append("wait")
    body += [f"test -s {R.path('models', n, 'out', 'model.pt')}" for n in MODELS]
    R.sbatch("02_models", "\n".join(body), partition="debug-gpu", gres="gpu:4", cpus=32, mem="128G")
    metrics = {n: last_val_line(R.path("logs", f"train_{n}.log"))[-160:] for n in MODELS}
    jm = {}
    for c in judges:
        p = os.path.join(FID, "models", f"{R.name}_{c}_test_metrics.json")
        if os.path.exists(p):
            j = json.load(open(p))
            jm[f"judge {c} (CGCNN, 3 seeds)"] = (f"MAE {j.get('mae_all', float('nan')):.3f}, MAE on >0 "
                                                 f"{j.get('mae_nonzero', float('nan')):.3f}, r {j.get('pearson_nonzero', float('nan')):+.2f}")
    R.card(2, "models", title="Train on the user's data", matter="models/{id}", matter_new=False,
           purpose="Train the main model, a seed replicate and an ablation control, plus independent judges that "
                   "share no code with MEIDNet.",
           verdict="PASS" if all(os.path.exists(R.path("models", n, "out", "model.pt")) for n in MODELS) else "FAIL",
           reason="all three models and the judges trained" if jm or a.smoke else "models trained",
           metrics={**{f"{n} (last validation line)": v for n, v in metrics.items()}, **jm},
           seconds=time.time() - t0, artefacts=[R.path("models")],
           ui_notes="The control model (structure-only losses off) is what makes the ablation verdict in stage 3 "
                    "possible; the seed replicate shows run-to-run spread.")
    return dict(models=metrics, judges=jm)


# ───────────────────────────── 03 diagnosis ─────────────────────────────
def s03_diagnosis(R, t0):
    a = R.a
    env = (f"export EVAL_DATA={R.path('intake')} EVAL_GAP={a.gap} EVAL_COST={a.stability} EVAL_COST_MAX={a.es_max} "
           f"EVAL_STABILITY={a.stability} CHECKUP_MATERIALS=/nonexistent")
    os.makedirs(R.path("diagnosis"), exist_ok=True)
    body = [env]
    for n in MODELS:
        ck = R.path("models", n, "out", "model.pt")
        body += [f"{FC} pipeline_checkup.py {R.name}_{n} {ck} --label-source structure --latent-space sphere "
                 f"--skip-search --family none > {R.path('logs', f'checkup_{n}.log')} 2>&1",
                 f"{FC} model_metrics.py {R.name}_{n} {ck} {R.path('diagnosis', f'metrics_{n}.json')} {R.path('intake')} "
                 f"> {R.path('logs', f'metrics_{n}.log')} 2>&1"]
    main = R.path("models", "main", "out", "model.pt")
    body += [f"{FC} decoder_autopsy.py {main} --data {R.path('intake')} --json {R.path('diagnosis', 'decoder.json')} "
             f"> {R.path('logs', 'decoder_autopsy.log')} 2>&1",
             f"{FC} reliability_map.py --ckpt {main} --data {R.path('intake')} --gap {a.gap} --stability {a.stability} "
             f"--query {a.stability}=0 --out {R.path('diagnosis')} --targets {' '.join(map(str, a.targets))} "
             f"> {R.path('logs', 'reliability_map.log')} 2>&1",
             f"test -s {R.path('diagnosis', 'reliability_map.csv')}"]
    R.sbatch("03_diagnosis", "\n".join(body), cpus=16, mem="64G")
    for n in MODELS:                                           # keep the checkup JSONs with the run
        src = os.path.join(HERE, "results", "checkups", f"{R.name}_{n}.json")
        if os.path.exists(src):
            shutil.copy(src, R.path("diagnosis", f"checkup_{n}.json"))
    ck = {n: json.load(open(R.path("diagnosis", f"checkup_{n}.json"))) for n in MODELS
          if os.path.exists(R.path("diagnosis", f"checkup_{n}.json"))}
    mm = {n: json.load(open(R.path("diagnosis", f"metrics_{n}.json"))) for n in MODELS
          if os.path.exists(R.path("diagnosis", f"metrics_{n}.json"))}
    dec = json.load(open(R.path("diagnosis", "decoder.json")))
    rel = pd.read_csv(R.path("diagnosis", "reliability_map.csv"))
    # the generation/screening decision comes from the CENTRAL S3 band, not from a number chosen here
    s3 = BY_ID["S3"].by_id("comp_exact_gen")
    rule_pct = a.generation_rule * 100 if a.generation_rule <= 1 else a.generation_rule
    gen_ok = 100 * dec["exact_composition"] >= min(rule_pct, s3.warn_at)
    # ablation: main vs control on the measurements that the structure-only losses are meant to move
    def pp(n, k):
        return mm.get(n, {}).get("property_prediction", {}).get(k, float("nan"))
    abl = {"metal/non-metal accuracy": (pp("main", "metal_vs_gap_accuracy"), pp("control", "metal_vs_gap_accuracy")),
           f"{a.gap} MAE": (pp("main", f"mae_{a.gap}"), pp("control", f"mae_{a.gap}")),
           f"{a.stability} MAE": (pp("main", f"mae_{a.stability}"), pp("control", f"mae_{a.stability}")),
           f"{a.energy} MAE": (pp("main", f"mae_{a.energy}"), pp("control", f"mae_{a.energy}"))}
    stage_rows = {}
    for c in ck.get("main", {}).get("checks", []):
        stage_rows[f"{c['stage']}: {c['check']}"] = f"{c['status']} — {c['detail'][:110]}"
    # the blocks this stage is responsible for, graded against the central bands
    meas = {"gap_rel_mae": pp("main", f"mae_{a.gap}_rel"), "metal_accuracy": pp("main", "metal_vs_gap_accuracy"),
            "comp_exact_gen": 100 * dec["exact_composition"],
            "servable_targets": len(servable)}
    for sid in ("S1", "S3", "S9"):
        v, why, rows_c, _ = graded(sid, {k: x for k, x in meas.items() if k in {m.id for m in BY_ID[sid].metrics}
                                         and x is not None and x == x})
        stage_rows[f"{sid} {BY_ID[sid].name} (central bands)"] = f"{v} — " + "; ".join(f"{k} {x}" for k, x in rows_c.items())
    servable = rel[rel.verdict == "servable"].target.tolist()
    R.card(3, "diagnosis", title="Can I trust each part?", matter="models/{id} held-out evaluation; readiness",
           matter_new=True,
           purpose="Check every component separately, decide between generation and screening by a measured rule, "
                   "and say in advance which targets the data can serve.",
           verdict="PASS" if servable else "WARN",
           reason=(f"decoder recovers {100 * dec['exact_composition']:.0f}% of compositions "
                   f"(central S3 band: WARN at {s3.warn_at:g}%, PASS at {s3.pass_at:g}%) -> "
                   f"{'generation allowed' if gen_ok else 'screening mode'}; servable targets {servable}"),
           decisions=[dict(question="Generation or screening?", options=["generation", "screening"],
                           default="decided by the measured rule", chosen="generation" if gen_ok else "screening",
                           why=f"composition recovery from the structure latent is {100 * dec['exact_composition']:.1f}%; "
                               "the density experiment showed generation needs about 200 compositions per element")],
           metrics={**stage_rows,
                    **{f"ablation {k} (main vs control)": f"{m:.3f} vs {c:.3f}" for k, (m, c) in abl.items()},
                    f"seed replicate {a.gap} MAE": f"{pp('main', f'mae_{a.gap}'):.3f} vs {pp('seed1', f'mae_{a.gap}'):.3f}",
                    "reliability per target": "; ".join(f"{r.target:g} eV: {r.verdict.split(' (')[0]} "
                                                        f"(support {r.train_within_0p25})" for r in rel.itertuples())},
           seconds=time.time() - t0,
           artefacts=[R.path("diagnosis"), R.path("diagnosis", "reliability_map.md")],
           ui_notes="Render as a scorecard: one row per component with its verdict, plus the mode decision.")
    return dict(generation_allowed=gen_ok, decoder=dec, servable=servable, ablation=abl)


# ───────────────────────────── 04 design space ─────────────────────────────
def pick_templates(R):
    """Prototype per space group, enough space groups to cover >= coverage of the training ground states."""
    a = R.a
    tr = pd.read_csv(R.path("intake", "train.csv"), usecols=["formula", "prototype", a.stability])
    from pymatgen.core import Composition
    tr["f"] = tr.formula.map(lambda f: Composition(f).reduced_formula)
    tr["sg"] = tr.prototype.astype(str).str.split("|").str[1]
    gs = tr.loc[tr.groupby("f")[a.stability].idxmin()]
    share = gs.sg.value_counts(normalize=True)
    chosen, cum = [], 0.0
    for sg, s in share.items():
        if sg in ("?", "") or len(chosen) >= a.max_templates:
            continue
        proto = tr[tr.sg == sg].prototype.value_counts().index[0]      # its most common prototype string
        chosen.append(dict(sg=int(sg), prototype=proto, ground_state_share=float(s)))
        cum += s
        if cum >= a.template_coverage:
            break
    if not any(c["sg"] == 221 for c in chosen) and (tr.sg == "221").any():   # cubic: needed for the cubic-only ablation
        chosen.append(dict(sg=221, prototype=tr[tr.sg == "221"].prototype.value_counts().index[0],
                           ground_state_share=float(share.get("221", 0))))
    return chosen, cum, len(gs)


def s04_design_space(R, t0):
    a = R.a
    fam_dir = R.path("families"); os.makedirs(fam_dir, exist_ok=True)
    chosen, cum, n_gs = pick_templates(R)
    made = []
    for c in chosen:
        out = os.path.join(fam_dir, f"{R.name}_sg{c['sg']}.yaml")
        try:
            R.run([FC, "auto_family.py", R.path("intake"), out, "--prototype", c["prototype"], "--rules", "minimal"],
                  "04_design_space.log")
            made.append(dict(c, family=out))
        except subprocess.CalledProcessError:
            c["error"] = "auto_family failed (see logs/04_design_space.log)"
    # novelty frontier: charge-balanced compositions of the templates that the dataset does not contain
    from pymatgen.core import Composition
    sys.path.insert(0, HERE)
    try:
        from meidnet_eval.screen_polymorphs import load_template
    except ImportError:          # run as a plain script from eval/
        from screen_polymorphs import load_template
    from meidnet.designspace import enumerate_space
    data_f = set()
    for sp in ("train", "val", "test"):
        data_f |= {Composition(f).reduced_formula for f in pd.read_csv(R.path("intake", f"{sp}.csv"), usecols=["formula"]).formula}
    comp = set()
    for m in made:
        fam = load_template(m["family"], R.path("intake"), a.props)
        sp = enumerate_space(fam, None)
        comp |= {Composition(r["f"]).reduced_formula for r in sp["rows"] if all(r["ok"].values())}
        m["compositions"] = len({Composition(r["f"]).reduced_formula for r in sp["rows"] if all(r["ok"].values())})
        m["excluded_cations"] = None
    novel = sorted(comp - data_f)
    info = dict(templates=made, coverage_of_ground_states=cum, ground_states=n_gs, compositions=len(comp),
                in_dataset=len(comp & data_f), novel=len(novel), novel_examples=novel[:40])
    json.dump(info, open(R.path("families", "design_space.json"), "w"), indent=1)
    exhausted = len(novel) <= max(5, 0.01 * len(comp))
    R.card(4, "design_space", title="What could be made?", matter="families/{name}", matter_new=True,
           purpose="Learn the polymorph templates, site chemistries and charges from the user's own data, and measure "
                   "how much of that space is still unexplored.",
           verdict="WARN" if exhausted else "PASS",
           reason=(f"{len(made)} polymorph templates cover {100 * cum:.0f}% of the training ground states; "
                   f"{len(comp)} charge-balanced compositions, {len(novel)} absent from the dataset"
                   + (" — the dataset has already explored this space" if exhausted else "")),
           metrics={"templates": "; ".join(f"sg {m['sg']} ({m['prototype']}): {100 * m['ground_state_share']:.0f}% of "
                                           f"ground states, {m.get('compositions', '?')} compositions" for m in made),
                    "design space (charge-balanced compositions)": len(comp),
                    "already in the dataset": len(comp & data_f), "novel (absent from the dataset)": len(novel),
                    "novel examples": ", ".join(novel[:20])},
           warnings=[c.get("error") for c in chosen if c.get("error")],
           seconds=time.time() - t0, artefacts=[fam_dir],
           ui_notes="Show the novelty frontier BEFORE the user asks for new materials; say plainly when the design "
                    "space is exhausted. Radioactive elements and oxyanion formers (P, S, N, C...) are excluded "
                    "from cation sites by default.")
    return info


# ───────────────────────────── 05 proposals / 06 hold-out ─────────────────────────────
def screen_job(R, tag, extra):
    a = R.a
    fams = " ".join(m["family"] for m in json.load(open(R.path("families", "design_space.json")))["templates"])
    return (f"{FC} screen_polymorphs.py --tag {tag} --ckpt {R.path('models', 'main', 'out', 'model.pt')} "
            f"--data {R.path('intake')} --families {fams} --targets {' '.join(map(str, a.targets))} "
            f"--window {a.window} --es-max {a.es_max} --per-target {a.per_target} --device cpu {extra} "
            f"> {R.path('logs', tag + '.log')} 2>&1\ntest -s {os.path.join(HERE, 'results', tag, 'screen_summary.json')}")


def s05_proposals(R, t0):
    tag = f"{R.name}_screen"
    R.sbatch("05_proposals", screen_job(R, tag, "--novel-against all"), cpus=16, mem="64G")
    res = os.path.join(HERE, "results", tag)
    shutil.copytree(res, R.path("proposals"), dirs_exist_ok=True)
    sm = json.load(open(os.path.join(res, "screen_summary.json")))
    n = sm.get("returned", 0)
    R.card(5, "proposals", title="Find materials at my targets", matter="goals/validate, runs", matter_new=True,
           purpose="For every composition, predict each polymorph, keep the predicted ground state, and propose novel "
                   "compositions whose ground state is a perovskite at the target gap and predicted stable.",
           verdict="PASS" if n else "WARN",
           reason=f"{n} proposals; per target: {sm.get('proposals_per_target')}",
           decisions=[dict(question="What should 'target band gap' mean?", options=["ground-state gap", "cubic-polymorph gap"],
                           default="ground-state gap", chosen="ground-state gap",
                           why="cubic and ground-state gaps of the same composition differ by 1.8 eV on average in this "
                               "data (Spearman 0.22)"),
                      dict(question="Which targets?", options=["broad 0.5-4 eV", "solar 1-2 eV", "wide gap 3-5 eV"],
                           default="broad 0.5-4 eV", chosen=" / ".join(f"{t:g}" for t in R.a.targets) + " eV",
                           why="every target has hundreds of training materials nearby")],
           metrics={"compositions screened": sm.get("compositions"), "predicted ground states": sm.get("gs_polymorphs"),
                    "novel": sm.get("novel"), "novel with a perovskite ground state": sm.get("novel_perovskite_gs"),
                    "proposals per target": sm.get("proposals_per_target")},
           seconds=time.time() - t0, artefacts=[R.path("proposals")],
           ui_notes="Every candidate is shown with its predicted ground-state polymorph and whether that is a perovskite.")
    return sm


def s06_holdout(R, t0):
    tag = f"{R.name}_holdout"
    R.sbatch("06_holdout", screen_job(R, tag, "--novel-against train --truth test"), cpus=16, mem="64G")
    res = os.path.join(HERE, "results", tag)
    shutil.copytree(res, R.path("holdout"), dirs_exist_ok=True)
    m = json.load(open(os.path.join(res, "holdout_metrics.json")))
    per = pd.DataFrame(m["per_target"])
    pa = per[per.screen == "polymorph-aware"]
    cu = per[per.screen == "cubic-only"]
    beats = int(pa.beats_blind_draw.sum())
    R.card(6, "holdout", title="Would it have found real materials?", matter="readiness", matter_new=True,
           purpose="Hide the test compositions, run the same screen, and check every proposal against their DFT.",
           verdict="PASS" if beats >= max(1, len(pa) // 2) else "WARN",
           reason=f"precision beats a blind draw (95% intervals not overlapping) at {beats} of {len(pa)} targets",
           metrics={"test compositions in the design space": f"{m['covered_by_design_space']} of {m['test_compositions']}",
                    "ground-state polymorph identified": f"{100 * m['polymorph_identified']:.0f}%",
                    "perovskite / not called correctly": f"{100 * m['perovskite_call_accuracy']:.0f}%",
                    "ground-state gap MAE (Spearman)": f"{m['gs_gap_mae']:.2f} eV ({m['gs_gap_spearman']:+.2f})",
                    "cubic-only gap vs real ground state (ablation)": (f"{m.get('cubic_only_gap_mae_vs_gs', float('nan')):.2f} eV "
                                                                      f"({m.get('cubic_only_gap_spearman_vs_gs', float('nan')):+.2f})"),
                    "stability MAE (Spearman)": f"{m['es_mae']:.3f} ({m['es_spearman']:+.2f})",
                    "stable / unstable called correctly": f"{100 * m['stable_call_accuracy']:.0f}%",
                    **{f"target {r.target:g} eV": (f"{r.on_target_and_stable_dft}/{r.proposed} correct "
                                                   f"(precision {r.precision:.2f} [{r.precision_lo:.2f}-{r.precision_hi:.2f}] "
                                                   f"vs blind {r.blind_draw:.2f}; recall {r.recall:.2f})")
                       for r in pa.itertuples()},
                    **{f"cubic-only, target {r.target:g} eV": f"precision {r.precision:.2f} vs polymorph-aware above"
                       for r in cu.itertuples()}},
           seconds=time.time() - t0, artefacts=[R.path("holdout")],
           ui_notes="This is the trust card: real DFT, not a model judging a model.")
    return m


# ───────────────────────────── 07 novelty ─────────────────────────────
def s07_novelty(R, t0):
    tags = [f"{R.name}_screen", f"{R.name}_holdout"]
    os.makedirs(R.path("novelty"), exist_ok=True)
    R.run([FC, "prefetch_mp.py", *tags], "07_novelty.log")
    look = {}
    for t in tags:
        cands = os.path.join(HERE, "results", t, "candidates.csv")
        if os.path.exists(cands) and len(pd.read_csv(cands)):
            out = R.path("novelty", f"oqmd_{t}.csv")
            R.run([FC, "fetch_oqmd_structures.py", "lookup", cands, out], "07_novelty.log")
            look[t] = pd.read_csv(out)
    sc = look.get(f"{R.name}_screen")
    n_in = int((sc.oqmd_status == "in OQMD").sum()) if sc is not None else 0
    R.card(7, "novelty", title="Is it really new?", matter="runs/{id}/candidates/{id} (novelty)", matter_new=False,
           purpose="Look every proposal up in Materials Project and in the full OQMD; where it exists, its DFT values "
                   "become a free check of the prediction.",
           verdict="INFO", reason=f"{n_in} of the discovery proposals already exist in OQMD (DFT available)",
           metrics={t: f"{int((d.oqmd_status == 'in OQMD').sum())} in OQMD, {int((d.oqmd_status == 'absent from OQMD').sum())} absent"
                    for t, d in look.items()},
           seconds=time.time() - t0, artefacts=[R.path("novelty")])
    return {t: len(d) for t, d in look.items()}


# ───────────────────────────── 08 validation ─────────────────────────────
def s08_validation(R, t0):
    a = R.a
    v = R.path("validation"); os.makedirs(v, exist_ok=True)
    disc, hold = f"{R.name}_screen", f"{R.name}_holdout"
    tags = [t for t in (disc, hold) if os.path.exists(os.path.join(HERE, "results", t, "candidates.csv"))
            and len(pd.read_csv(os.path.join(HERE, "results", t, "candidates.csv")))]
    if not tags:
        R.card(8, "validation", title="Is it stable, is it a perovskite?", matter="runs/{id}/candidates/{id} (evidence)",
               purpose="Relax every proposal with two independent ML potentials and validate it.", verdict="WARN",
               reason="nothing to validate: no proposals", seconds=time.time() - t0)
        return {}
    cells = os.path.join(v, "cells")
    body = [f"export CELLS_DIR={cells} MLIP_COMPARE_DIR={v} NSHARDS=8"]
    body.append(" ".join(f"SHARD={i} {MG} candidate_cells.py {' '.join(tags)} > {R.path('logs', f'cells_{i}.log')} 2>&1 &"
                         for i in range(8)) + " wait")
    for t, splits in ((disc, "train,val,test"), (hold, "train")):
        if t in tags:
            body.append(f"export SUN_REFERENCE={R.path('intake')} SUN_REFERENCE_SPLITS={splits} DISTORT=1 NSHARDS=8")
            body.append(" ".join(f"SHARD={i} {MG} sun_validate.py {t} > {R.path('logs', f'sun_{t}_{i}.log')} 2>&1 &"
                                 for i in range(8)) + " wait")
    for c in ([] if a.smoke else [a.gap, a.stability]):
        body.append(f"JUDGE_TAG={R.name}_{c} {FC} {FID}/cgcnn_judge.py judge {cells}/tensornet {v}/judge_{c}.csv "
                    f"> {R.path('logs', f'judge_apply_{c}.log')} 2>&1")
    R.sbatch("08_validation", "\n".join(body), cpus=64, mem="128G")
    sun = []
    for t in tags:
        for f in glob.glob(os.path.join(HERE, "results", f"sun_{t}_shard*.csv")):
            d = pd.read_csv(f); d["set"] = "discovery" if t == disc else "hold-out"; sun.append(d)
    S = pd.concat(sun, ignore_index=True).drop_duplicates(["set", "key"]) if sun else pd.DataFrame()
    S.to_csv(os.path.join(v, "sun_validated.csv"), index=False)
    cmp = sorted(glob.glob(os.path.join(v, "mlip_compare_shard*.csv")))
    M = pd.concat([pd.read_csv(f) for f in cmp], ignore_index=True).drop_duplicates("key") if cmp else pd.DataFrame()
    M.to_csv(os.path.join(v, "mlip_compare.csv"), index=False)
    agree = f"{int(M.same_sg.sum())}/{len(M)}" if len(M) else "n/a"
    R.card(8, "validation", title="Is it stable, is it a perovskite?", matter="runs/{id}/candidates/{id} (evidence)",
           matter_new=True,
           purpose="Relax every proposal with two independent ML potentials, compute its hull distance against Materials "
                   "Project phases, its formability, and judge its gap and stability with models trained on the user's data.",
           verdict="PASS" if len(S) else "WARN",
           reason=f"{len(S)} compositions validated; the two potentials agree on the relaxed space group for {agree}",
           metrics={"validated (discovery / hold-out)": f"{int((S.get('set') == 'discovery').sum()) if len(S) else 0} / "
                                                        f"{int((S.get('set') == 'hold-out').sum()) if len(S) else 0}",
                    "two potentials agree (space group)": agree,
                    "stable (MLIP hull <= es_max)": int((S.e_hull <= a.es_max).sum()) if len(S) else 0},
           seconds=time.time() - t0, artefacts=[v])
    return dict(validated=len(S))


# ───────────────────────────── 09 report ─────────────────────────────
def s09_report(R, t0):
    R.run([FC, "final_report.py", R.dir, "--gap", R.a.gap, "--stability", R.a.stability, "--es-max", str(R.a.es_max),
           "--window", str(R.a.window)], "09_report.log")
    R.card(9, "report", title="Give me the answer", matter="export/bundle.zip, schema/candidate-record",
           purpose="One report: every stage verdict, the trust numbers, the funnel, and the shortlist with the source of "
                   "every number.", verdict="INFO", reason="report written", seconds=time.time() - t0,
           artefacts=[R.path("report", "report.md")])
    return {}


FUNCS = dict(zip(STAGES, [s00_structures, s01_intake, s02_models, s03_diagnosis, s04_design_space, s05_proposals,
                          s06_holdout, s07_novelty, s08_validation, s09_report]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", required=True); ap.add_argument("--run", required=True)
    ap.add_argument("--id-col", default="material_id"); ap.add_argument("--formula-col", default="formula")
    ap.add_argument("--cif-col", default="cif"); ap.add_argument("--vol-col", default="vol"); ap.add_argument("--sg-col", default="sg")
    ap.add_argument("--props", nargs="+", required=True, help="property columns to train on")
    ap.add_argument("--gap", required=True, help="the target property (band gap)")
    ap.add_argument("--stability", required=True, help="energy above hull column (lower = more stable)")
    ap.add_argument("--energy", required=True, help="formation energy column (ranks the polymorphs of one composition)")
    ap.add_argument("--anion", default="O", help="restrict to A B X3 with this anion ('' = all)")
    ap.add_argument("--targets", type=float, nargs="+", default=[0.5, 1, 1.5, 2, 2.5, 3, 4])
    ap.add_argument("--window", type=float, default=0.3); ap.add_argument("--es-max", type=float, default=0.1)
    ap.add_argument("--per-target", type=int, default=12)
    ap.add_argument("--epochs", type=int, default=200); ap.add_argument("--max-sites", type=int, default=20)
    ap.add_argument("--generation-rule", type=float, default=0.30,
                    help="composition recovery from z_c above which the generative engine may be used")
    ap.add_argument("--template-coverage", type=float, default=0.90); ap.add_argument("--max-templates", type=int, default=6)
    ap.add_argument("--workers", type=int, default=3, help="concurrent OQMD requests (it rate-limits bursts)")
    ap.add_argument("--from", dest="start", default=STAGES[0]); ap.add_argument("--until", default=STAGES[-1])
    ap.add_argument("--smoke", action="store_true"); ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    R = Run(a)
    json.dump(vars(a), open(R.path("settings.json"), "w"), indent=1)
    i0 = next(i for i, s in enumerate(STAGES) if s.startswith(a.start) or s == a.start)
    i1 = next(i for i, s in enumerate(STAGES) if s.startswith(a.until) or s == a.until)
    for stage in STAGES[i0:i1 + 1]:
        if R.is_done(stage):
            print(f"[{stage}] already done, skipped", flush=True)
            continue
        print(f"[{stage}] started {datetime.datetime.now():%H:%M:%S}", flush=True)
        t0 = time.time()
        info = FUNCS[stage](R, t0)
        R.mark(stage, dict(seconds=round(time.time() - t0, 1), info=info))
        print(f"[{stage}] done in {time.time() - t0:.0f}s", flush=True)
    print(f"run {R.name}: stages {STAGES[i0]}..{STAGES[i1]} complete -> {R.dir}", flush=True)


if __name__ == "__main__":
    main()
