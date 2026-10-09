"""Check candidate structures the way the target-following chain does, whatever produced them.

Generation (conditional_generate), screening (screen_local) and family generation (meidnet generate) all end with a
table of structures and the band gap each was asked for.  This command gives every one of them the same evidence:

  1 label     the model's own label, read from each returned cell (re-encoded), never from the search
  2 judge     the independent judge (MEGNet), qualified on the held-out split first; two-model consensus in the window
  3 relax     the consensus cells relaxed by two potentials of different architecture (TensorNet, CHGNet); a relaxed cell
              whose closest atoms sit nearer than 0.6 of their radii is collapsed, not a crystal, and goes no further;
              nor does one with an empty layer thicker than 6 A or a packing fraction below 0.12 (a slab or a sparse cell)
  4 re-judge  both readings again on the relaxed cells; the consensus on those is the deliverable
  5 stable    optional: energy above the convex hull, one potential for every phase (hull_mlip.py --reference ...)
  6 novel     AMD distance to the nearest structure of the data; known compositions carry the data's own values
  7 report    REPORT.md, report.json and the instrument sheet (requested in, delivered out)

Usage: python check_candidates.py TABLE --ckpt MODEL.pt --intake INTAKE --gap COLUMN --out DIR
       [--cifs-dir DIR] [--target-col COL] [--label-col COL] [--window 0.5] [--relax tensornet|none] [--relax-steps 150]
       [--hull-reference jarvis:PATH|mp] [--hull-cache DIR] [--workers 4] [--stability-col COL] [--test-csv PATH]
TABLE needs a `file` column (a CIF per row, relative to --cifs-dir, default the table's folder) and the requested value
(--target-col; default `target_<gap>` when present, else `target`).  The layout of DIR is the one generate_to_target
writes, so every route reads the same way: candidates.csv + cifs/, calibration.json, candidates_consensus.csv,
relax/ (mlip_shard0.json, relaxed_<potential>/), relaxed/ (candidates.csv, calibration.json, candidates_consensus.csv,
hull.json, sun.json), instrument/, REPORT.md, report.json.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def run(python, script, *args, env_extra=None, log=print, check=True):
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
    log("\n".join(keep[-30:]))
    if r.returncode:
        log(r.stderr[-1500:])
        if check:
            raise SystemExit(f"{mod} failed")
    return r.returncode


def standard_pool(table, cifs_dir, out, gap, target_col=None, label_col=None, log=print):
    """OUT/candidates.csv (target, formula, file, natoms, label_gap, then the table's own columns) and OUT/cifs/.
    Nothing is copied when the table already is OUT/candidates.csv in this layout (generate_to_target)."""
    from pymatgen.core import Structure
    df = pd.read_csv(table)
    if "file" not in df.columns:
        raise SystemExit(f"{table} has no `file` column naming the structures")
    tc = target_col or (f"target_{gap}" if f"target_{gap}" in df.columns else "target")
    if tc not in df.columns:
        raise SystemExit(f"{table} has no target column ({tc}); name it with --target-col")
    lc = label_col or next((c for c in ("label_gap", "label_structure", f"pred_{gap}") if c in df.columns), None)
    in_place = (os.path.abspath(table) == os.path.abspath(os.path.join(out, "candidates.csv"))
                and os.path.abspath(cifs_dir) == os.path.abspath(out) and tc == "target" and lc == "label_gap")
    if in_place:
        return df
    os.makedirs(os.path.join(out, "cifs"), exist_ok=True)
    rows, used = [], set()
    for i, r in df.iterrows():
        src = os.path.join(cifs_dir, str(r["file"]))
        name = os.path.basename(str(r["file"]))
        if name in used:
            name = f"{i:03d}_{name}"
        used.add(name)
        shutil.copyfile(src, os.path.join(out, "cifs", name))
        s = Structure.from_file(src)
        row = {"target": float(r[tc]), "formula": r.get("formula", s.composition.reduced_formula) or s.composition.reduced_formula,
               "file": f"cifs/{name}", "natoms": len(s),
               "label_gap": float(r[lc]) if lc and r[lc] == r[lc] else float("nan"), "source_file": str(r["file"])}
        for c in df.columns:                              # the table's own evidence travels with the row
            if c not in row and c not in ("file", tc, lc):
                row[c] = r[c]
        rows.append(row)
    pool = pd.DataFrame(rows)
    pool.to_csv(os.path.join(out, "candidates.csv"), index=False)
    log(f"{len(pool)} structures -> {out}/candidates.csv (target from `{tc}`, model label from `{lc or 'the structure, re-encoded'}`)")
    return pool


def known_values(intake, gap, stability_col=None):
    """reduced formula -> (the data's gap, the data's hull energy or None) over every split of the intake."""
    from pymatgen.core import Composition
    out = {}
    for split in ("train", "val", "test"):
        p = os.path.join(intake, f"{split}.csv")
        if not os.path.exists(p):
            continue
        cols = ["formula", gap] + ([stability_col] if stability_col else [])
        t = pd.read_csv(p, usecols=lambda c: c in cols)
        for _, r in t.iterrows():
            try:
                k = Composition(r["formula"]).reduced_formula
            except Exception:
                continue
            out.setdefault(k, (float(r[gap]), float(r[stability_col]) if stability_col and r.get(stability_col) == r.get(stability_col) else None))
    return out


def check(out, ckpt, intake, gap, window=0.5, test_csv=None, relax="tensornet", relax_steps=150, hull_reference=None,
          hull_cache=None, workers=4, stability_col=None, py_model=sys.executable, py_judge=None, log=print):
    """Stages 1-7 on OUT/candidates.csv (standard layout).  Returns the report dict."""
    py_judge = py_judge or py_model
    test_csv = test_csv or os.path.join(intake, "test.csv")
    gen = pd.read_csv(os.path.join(out, "candidates.csv"))
    report = {"targets": sorted(float(t) for t in gen["target"].unique()), "window_eV": window, "stages": {"1_candidates": int(len(gen))}}
    # 1 the label read from each returned cell; 2 the qualified judge and the two-model consensus
    run(py_model, "target_calibration.py", out, "--judge", "reencode", "--ckpt", ckpt, "--gap-col", gap, log=log)
    run(py_judge, "target_calibration.py", out, "--test-csv", test_csv, "--gap-col", gap, "--judge", "megnet",
        "--qualify-n", 80, "--select", window, log=log)
    cal = json.load(open(os.path.join(out, "calibration.json")))
    report["judge"] = cal.get("judge_qualification")
    cons = os.path.join(out, "candidates_consensus.csv")
    c0 = pd.read_csv(cons) if os.path.exists(cons) else pd.DataFrame()
    report["stages"]["2_two_model_consensus"] = int(len(c0))
    final = pd.DataFrame()
    if len(c0) and relax != "none":
        # 3 relax the consensus cells with two potentials (the CIFs stay where they are; the relaxer is told where they live)
        rdir = os.path.join(out, "relax"); os.makedirs(rdir, exist_ok=True)
        c0.to_csv(os.path.join(rdir, "candidates.csv"), index=False)
        run(py_judge, "d1_mlip_check.py", rdir, "--cifs-dir", out, "--steps", relax_steps, "--potentials", "tensornet", "chgnet", log=log)
        # 4 both readings again on the relaxed cells
        rel = os.path.join(out, "relaxed"); os.makedirs(os.path.join(rel, "cifs"), exist_ok=True)
        from pymatgen.core import Structure
        try:
            from meidnet_eval.d1_mlip_check import COLLAPSED, bulk_problem, contact_ratio, empty_layer, packing_fraction
        except ImportError:
            sys.path.insert(0, HERE)
            from d1_mlip_check import COLLAPSED, bulk_problem, contact_ratio, empty_layer, packing_fraction
        kept, collapsed, not_bulk = [], [], []
        for _, r in c0.iterrows():
            src = os.path.join(rdir, "relaxed_tensornet", os.path.basename(r["file"]))
            if os.path.exists(src):
                # a potential can drive atoms into each other and still report a low energy: such a cell is not judged again
                s_rel = Structure.from_file(src)
                ratio = contact_ratio(s_rel)
                if ratio < COLLAPSED:
                    collapsed.append({"file": os.path.basename(r["file"]), "formula": r.get("formula"), "target": float(r["target"]),
                                      "contact_ratio": round(ratio, 2)})
                    continue
                # nor is a slab or a sparse cage a bulk crystal: its band gap is not one
                why = bulk_problem(s_rel)
                if why:
                    not_bulk.append({"file": os.path.basename(r["file"]), "formula": r.get("formula"), "target": float(r["target"]),
                                     "reason": why, "empty_layer": round(empty_layer(s_rel), 2), "packing": round(packing_fraction(s_rel), 3)})
                    continue
                shutil.copyfile(src, os.path.join(rel, "cifs", os.path.basename(r["file"])))
                r = dict(r); r["file"] = "cifs/" + os.path.basename(r["file"]); kept.append(r)
        c1 = pd.DataFrame(kept, columns=list(c0.columns))
        c1.to_csv(os.path.join(rel, "candidates.csv"), index=False)
        report["stages"]["3_relaxed"] = int(len(c1))
        report["collapsed_on_relaxation"] = collapsed
        report["not_bulk_on_relaxation"] = not_bulk
        if len(c1):
            run(py_model, "target_calibration.py", rel, "--judge", "reencode", "--ckpt", ckpt, "--gap-col", gap, log=log)
            run(py_judge, "target_calibration.py", rel, "--test-csv", test_csv, "--gap-col", gap, "--judge", "megnet",
                "--qualify-n", 80, "--select", window, log=log)
            fin = os.path.join(rel, "candidates_consensus.csv")
            final = pd.read_csv(fin) if os.path.exists(fin) else pd.DataFrame()
            # the input of Prism's `meidnet score`: every relaxed cell, the window that was asked for, the judge's value
            rc = json.load(open(os.path.join(rel, "calibration.json")))
            q1 = rc.get("judge_qualification") or {}
            trows = [{"file": os.path.basename(r["file"]), f"{gap}_target": float(r["target"]),
                      f"{gap}_min": max(0.0, float(r["target"]) - window), f"{gap}_max": float(r["target"]) + window,
                      f"{gap}_value": rc.get("per_candidate", {}).get(r["file"], {}).get("independent_gap"),
                      "source": f"MEGNet fidelity {q1.get('fidelity')} judge on the relaxed cell"} for _, r in c1.iterrows()]
            pd.DataFrame(trows).to_csv(os.path.join(rel, "targets.csv"), index=False)
            # 5 stability, one potential for every phase (all relaxed cells, so the stable share is measured, not just the winners')
            if hull_reference:
                args = [rel, "--reference", hull_reference, "--workers", workers]
                if hull_cache:
                    args += ["--cache", hull_cache]
                if stability_col:
                    args += ["--validate", intake, "--stability-col", stability_col]
                if run(py_judge, "hull_mlip.py", *args, log=log, check=False) == 0 and os.path.exists(fin):
                    final = pd.read_csv(fin)
                    report["hull"] = {k: v for k, v in json.load(open(os.path.join(rel, "hull.json"))).items() if k != "candidates"}
            # 6 novelty against the data's own structures (with e_hull when it was computed, SUN becomes a measurement)
            run(py_model, "metrics_sun.py", os.path.join(rel, "candidates.csv"), "--cif-dir", rel, "--reference-intake", intake,
                "--out", os.path.join(rel, "sun.json"), log=log, check=False)
        report["stages"]["4_consensus_after_relaxation"] = int(len(final))
    # 7 report
    known = known_values(intake, gap, stability_col)
    mlip = [r for f in glob.glob(os.path.join(out, "relax", "mlip_shard*.json")) for r in json.load(open(f))]
    by_file = {os.path.basename(r["file"]): r for r in mlip}
    sunp = os.path.join(out, "relaxed", "sun_per_candidate.csv")
    amd = dict(zip(*pd.read_csv(sunp)[["formula", "amd_nearest"]].T.values)) if os.path.exists(sunp) else {}
    rows = []
    from pymatgen.core import Composition
    for _, r in final.iterrows():
        m = by_file.get(os.path.basename(r["file"]), {})
        k = Composition(r["formula"]).reduced_formula
        kv = known.get(k)
        # the data's own DFT value outranks two machine-learned readings: a known compound whose value lies outside the
        # window is not a hit, however well the models agree
        rid = r.get("reference_id") if "reference_id" in r else None
        rgap = r.get("reference_gap") if "reference_gap" in r else None
        has_ref = isinstance(rid, str) and rid
        def verdict(value, where):
            ok = abs(float(value) - float(r["target"])) <= window
            return f"known in {where}: its DFT value " + ("confirms (rediscovery)" if ok else "contradicts both models")
        if kv is not None:
            cls = verdict(kv[0], "the data")
        elif has_ref and rgap is not None and rgap == rgap:
            # absent from the user's data, present in the hull's reference set: that set's own DFT value decides the same way
            cls = verdict(rgap, "the reference set")
            kv = (float(rgap), None)
        elif has_ref:
            cls = "known in the reference set (no gap recorded)"
        else:
            cls = "new composition" + (" (absent from the data and the reference set)" if "reference_id" in r else "")
        rows.append(dict(target=float(r["target"]), formula=r["formula"], cls=cls,
                         label=float(r.get("label_structure_gap", r.get("label_gap"))), judge=float(r["independent_gap"]),
                         drop_tensornet=m.get("tensornet_drop_per_atom"), drop_chgnet=m.get("chgnet_drop_per_atom"),
                         spacegroup=f"{m.get('spacegroup_designed')}->{m.get('tensornet_spacegroup_relaxed')}/{m.get('chgnet_spacegroup_relaxed')}",
                         charge_balanced=r.get("charge_balanced"), e_hull=r.get("e_hull"), reference_id=rid if has_ref else None,
                         e_hull_note=r.get("e_hull_note") if isinstance(r.get("e_hull_note"), str) else "",
                         e_hull_assessed=bool(r.get("e_hull_assessed")) if "e_hull_assessed" in r else None,
                         known=(("yes" if known.get(k) else f"in the reference set ({rid})" if has_ref else "new")
                                + (f" (DFT {kv[0]:.2f} eV" + (f", hull {kv[1]:.3f}" if kv and kv[1] is not None else "") + ")" if kv else "")),
                         amd_nearest=amd.get(k)))
    report["final"] = rows
    report["classes"] = {}
    for r in rows:
        report["classes"][r["cls"]] = report["classes"].get(r["cls"], 0) + 1
    L = [f"# Candidate check: {len(gen)} structures, window {window} eV", "", "| stage | structures |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in report["stages"].items()]
    if rows:
        L += ["", "Of the accepted: " + "; ".join(f"{v} {k}" for k, v in report["classes"].items()) + "."]
    if report.get("collapsed_on_relaxation"):
        L += ["", "Collapsed on relaxation, not judged again (closest atoms as a share of their two radii; a sound crystal is near 1): "
              + ", ".join(f"{c['formula']} at {c['target']:g} eV ({c['contact_ratio']:.2f})" for c in report["collapsed_on_relaxation"]) + "."]
    if report.get("not_bulk_on_relaxation"):
        L += ["", "Not a bulk crystal after relaxation, not judged again: "
              + ", ".join(f"{c['formula']} at {c['target']:g} eV ({c['reason']})" for c in report["not_bulk_on_relaxation"]) + "."]
    q = report.get("judge") or {}
    if q:
        L += ["", f"Judge: MEGNet fidelity {q.get('fidelity')}, qualified on {q.get('split')}: MAE {q.get('mae', float('nan')):.2f} eV, "
                  f"Spearman {q.get('spearman', float('nan')):.2f} (n = {q.get('n')})."]
    h = report.get("hull") or {}
    if h:
        v = h.get("validation") or {}
        L += [f"Stability: energy above the hull with {h.get('potential')} for every phase, competing phases from {h.get('reference')}"
              + (f"; checked on {v['n']} known materials of the data: MAE {v['mae_eV']:.3f} eV/atom (median {v.get('median_abs_error_eV', float('nan')):.3f}), "
                 f"agreement on 'within 0.1 eV/atom' {100 * v['agreement_within_stable_line']:.0f}%" if v else "")
              + (f"; reference outliers {', '.join(v['reference_outliers'])}, without them MAE {v['mae_eV_without_outliers']:.3f} eV/atom"
                 if v and v.get("reference_outliers") else "")
              + (f"; {h['not_assessed']} value(s) not read as stability (marked †)" if h.get("not_assessed") else "") + "."]
    else:
        L += ["Stability: not assessed (pass --hull-reference to compute the energy above the hull)."]
    L += ["", "| target | formula | what it is | label (structure) | judge | drop TensorNet / CHGNet (eV/atom) | space group designed->relaxed | "
              "charge balanced | e_hull (eV/atom) | in the data | AMD |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    def f2(v, d=2):
        return "" if v is None or (isinstance(v, float) and v != v) else f"{v:.{d}f}"
    for r in rows:
        eh = f2(r["e_hull"], 3) + (" †" if r["e_hull_note"] else "")
        L.append(f"| {r['target']:.1f} | {r['formula']} | {r['cls']} | {r['label']:.2f} | {r['judge']:.2f} | {f2(r['drop_tensornet'])} / {f2(r['drop_chgnet'])} | "
                 f"{r['spacegroup']} | {r['charge_balanced']} | {eh} | {r['known']} | {f2(r['amd_nearest'], 3)} |")
    noted = [r for r in rows if r["e_hull_note"]]
    if noted:
        L += [""] + [f"† {r['formula']}: {r['e_hull_note']}" for r in noted]
    with open(os.path.join(out, "REPORT.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1, default=float)
    if os.path.isdir(os.path.join(out, "relaxed")) and os.path.exists(os.path.join(out, "relaxed", "candidates.csv")):
        run(py_model, "instrument_sheet.py", "--pool", out, "--relaxed", os.path.join(out, "relaxed"), "--consensus",
            os.path.join(out, "relax"), "--out", os.path.join(out, "instrument"), log=log, check=False)
    log("\n".join(L[:8])); log(f"\nreport: {out}/REPORT.md")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", help="candidates table with a `file` column (screen_local, meidnet generate or conditional_generate output)")
    ap.add_argument("--ckpt", required=True); ap.add_argument("--intake", required=True); ap.add_argument("--gap", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cifs-dir", default=None, help="folder the `file` column is relative to (default: the table's folder)")
    ap.add_argument("--target-col", default=None); ap.add_argument("--label-col", default=None)
    ap.add_argument("--window", type=float, default=0.5)
    ap.add_argument("--test-csv", default=None, help="held-out table that qualifies the judge (default INTAKE/test.csv)")
    ap.add_argument("--relax", choices=["tensornet", "none"], default="tensornet")
    ap.add_argument("--relax-steps", type=int, default=150)
    ap.add_argument("--hull-reference", default=None, help="jarvis:PATH or mp: compute the energy above the hull (hull_mlip.py)")
    ap.add_argument("--hull-cache", default=None, help="shared cache of relaxed competing phases")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    ap.add_argument("--stability-col", default=None, help="the data's DFT hull column: known materials then calibrate the hull estimate")
    ap.add_argument("--python", default=sys.executable); ap.add_argument("--python-judge", default=None)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    standard_pool(a.table, a.cifs_dir or os.path.dirname(os.path.abspath(a.table)), a.out, a.gap, a.target_col, a.label_col)
    check(a.out, a.ckpt, a.intake, a.gap, a.window, a.test_csv, a.relax, a.relax_steps, a.hull_reference, a.hull_cache,
          a.workers, a.stability_col, a.python, a.python_judge)
    return 0


if __name__ == "__main__":
    sys.exit(main())
