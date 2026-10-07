"""The one command behind "give me materials with band gap X": family-free, target-following, with its evidence attached.

Each stage is a component that already exists and is registered in stages.py; this file only runs them in order and
stops when a stage leaves nothing to continue with.  Stages run as subprocesses of the same interpreter by default
(`--python`, `--python-judge` let two environments be used when the potentials live in a different one).

  1 generate   conditional_generate.py --geometry wyckoff : symmetry decoder, target anchor (no latent refinement), one
               anion required, radioactive elements excluded, cell capped at the encoder's max_sites, label read from
               the returned cell, label window.                                                       (~1-3 min)
  2 judge      target_calibration.py --judge megnet --select : qualified independent judge; two-judge consensus.
  3 relax      d1_mlip_check.py : the consensus cells relaxed by the potentials, relaxed cells kept.      (minutes)
  4 re-judge   both judges again on the RELAXED cells; the consensus on those is the deliverable.  A gap judged on a
               cell that then moves by an angstrom describes no material.
  5 report     one JSON + one Markdown table: per target, what survived each stage and why the rest did not.

Usage: python generate_to_target.py --ckpt MODEL.pt --intake DIR --gap band_gap --targets 1.5 2.0 3.0 --tag mytag
       [--out results] [--test-csv PATH] [--per-target 25] [--window 0.5] [--relax tensornet|none] [--relax-steps 150]
"""
import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(python, script, *args, env_extra=None, log=print):
    """Run one component as `python -m meidnet_eval.<script>` when the package is installed, else as a file from eval/."""
    mod = script[:-3] if script.endswith(".py") else script
    try:
        import importlib.util
        installed = importlib.util.find_spec(f"meidnet_eval.{mod}") is not None
    except Exception:
        installed = False
    cmd = [python, "-W", "ignore"] + (["-m", f"meidnet_eval.{mod}"] if installed else [os.path.join(HERE, f"{mod}.py")]) + [str(x) for x in args]
    env = dict(os.environ, OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS", "4"))
    env.update(env_extra or {})
    log(f"\n$ {mod} {' '.join(str(x) for x in args)}")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    keep = [l for l in r.stdout.splitlines() if not l.lstrip().startswith("'atoms") and "Warning" not in l]
    log("\n".join(keep[-25:]))
    if r.returncode:
        log(r.stderr[-1500:])
        raise SystemExit(f"{mod} failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True); ap.add_argument("--intake", required=True)
    ap.add_argument("--gap", default="band_gap"); ap.add_argument("--targets", type=float, nargs="+", required=True)
    ap.add_argument("--tag", required=True); ap.add_argument("--per-target", type=int, default=25)
    ap.add_argument("--window", type=float, default=0.5)
    ap.add_argument("--out", default="results", help="results root; this run is written to OUT/TAG")
    ap.add_argument("--test-csv", default=None, help="held-out table that qualifies the judge (default INTAKE/test.csv)")
    ap.add_argument("--relax", choices=["tensornet", "none"], default="tensornet")
    ap.add_argument("--relax-steps", type=int, default=150)
    ap.add_argument("--python", default=sys.executable, help="interpreter for the model steps")
    ap.add_argument("--python-judge", default=None, help="interpreter for the judge and potentials (default: --python)")
    a = ap.parse_args()
    py_model, py_judge = a.python, a.python_judge or a.python
    out = os.path.abspath(os.path.join(a.out, a.tag))
    test_csv = a.test_csv or os.path.join(a.intake, "test.csv")

    # 1 generate (the window here is looser than the final one: the judge and relaxation still have to act)
    run(py_model, "conditional_generate.py", "--tag", a.tag, "--ckpt", a.ckpt, "--gap", a.gap, "--geometry", "wyckoff",
        "--targets", *a.targets, "--per-target", a.per_target, "--target-window", a.window + 0.25, "--out", a.out)
    # 2 judge + consensus on the generated cells
    run(py_judge, "target_calibration.py", out, "--test-csv", test_csv, "--gap-col", a.gap, "--judge", "megnet",
        "--qualify-n", 80, "--select", a.window)
    import pandas as pd
    cons = os.path.join(out, "candidates_consensus.csv")
    gen = pd.read_csv(os.path.join(out, "candidates.csv"))
    c0 = pd.read_csv(cons) if os.path.exists(cons) else pd.DataFrame()
    report = {"tag": a.tag, "targets": a.targets, "window_eV": a.window,
              "stages": {"1_generated": int(len(gen)), "2_two_judge_consensus": int(len(c0))}}
    if len(c0) == 0:
        json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
        raise SystemExit("no candidate passed both judges: the target is outside what this model and data can serve")
    if a.relax == "none":
        json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
        return
    # 3 relax the consensus cells (the CIFs stay where they are; the relaxer is told where they live)
    rdir = os.path.join(out, "relax"); os.makedirs(rdir, exist_ok=True)
    c0.to_csv(os.path.join(rdir, "candidates.csv"), index=False)
    run(py_judge, "d1_mlip_check.py", rdir, "--cifs-dir", out, "--steps", a.relax_steps, "--potentials", "tensornet", "chgnet")
    # 4 re-judge on the relaxed cells
    rel = os.path.join(out, "relaxed"); os.makedirs(os.path.join(rel, "cifs"), exist_ok=True)
    c1 = c0.copy()
    kept_rows = []
    for _, r in c1.iterrows():
        src = os.path.join(rdir, "relaxed_tensornet", os.path.basename(r["file"]))
        if os.path.exists(src):
            dst = os.path.join(rel, "cifs", os.path.basename(r["file"]))
            with open(src, "rb") as f_in, open(dst, "wb") as f_out:
                f_out.write(f_in.read())
            r = dict(r); r["file"] = "cifs/" + os.path.basename(r["file"]); kept_rows.append(r)
    c1 = pd.DataFrame(kept_rows, columns=list(c0.columns))
    c1.to_csv(os.path.join(rel, "candidates.csv"), index=False)
    run(py_model, "target_calibration.py", rel, "--judge", "reencode", "--ckpt", a.ckpt, "--gap-col", a.gap)
    run(py_judge, "target_calibration.py", rel, "--test-csv", test_csv, "--gap-col", a.gap, "--judge", "megnet",
        "--qualify-n", 80, "--select", a.window)
    fin = os.path.join(rel, "candidates_consensus.csv")
    try:
        final = pd.read_csv(fin)
    except Exception:
        final = pd.DataFrame()
    report["stages"]["3_relaxed"] = int(len(c1)); report["stages"]["4_consensus_after_relaxation"] = int(len(final))
    # 5 report
    mlip = [r for f in glob.glob(os.path.join(rdir, "mlip_shard*.json")) for r in json.load(open(f))]
    drop = {os.path.basename(r["file"]): r.get("tensornet_drop_per_atom") for r in mlip}
    lines = [f"# {a.tag}: target-following generation, window {a.window} eV", "", "| stage | candidates |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in report["stages"].items()]
    lines += ["", "| target | formula | label read from the structure | independent gap | relaxation drop (eV/atom) | charge-balanced |",
              "|---|---|---|---|---|---|"]
    for _, r in final.iterrows():
        label = r["label_structure_gap"] if "label_structure_gap" in r and r["label_structure_gap"] == r["label_structure_gap"] else r["label_gap"]
        lines.append(f"| {r['target']:.1f} | {r['formula']} | {label:.2f} | {r['independent_gap']:.2f} | "
                     f"{drop.get(os.path.basename(r['file']), float('nan')):.2f} | {r.get('charge_balanced', '')} |")
    lines += ["", "Stability: the energy lowered by relaxation is reported; a hull energy is not computed here. "
                  "Novelty: run metrics_sun.py on the relaxed folder for the AMD distance to the training structures."]
    with open(os.path.join(out, "REPORT.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
    print("\n".join(lines[:6])); print(f"\nreport: {out}/REPORT.md")


if __name__ == "__main__":
    main()
