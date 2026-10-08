"""The one command behind "give me materials with band gap X": family-free, target-following, with its evidence attached.

Each stage is a component that already exists and is registered in stages.py; this file only runs them in order and
stops when a stage leaves nothing to continue with.  Stages run as subprocesses of the same interpreter by default
(`--python`, `--python-judge` let two environments be used when the potentials live in a different one).

  1 generate   conditional_generate.py --geometry wyckoff : symmetry decoder, target anchor (no latent refinement), one
               anion required, radioactive elements excluded, cell capped at the encoder's max_sites, label read from
               the returned cell, label window.                                                       (~1-3 min)
  2-7 check    check_candidates.py, the same for every route: the label read from each cell, the qualified independent
               judge and the two-model consensus, relaxation by two potentials (TensorNet, CHGNet), both readings again
               on the RELAXED cells (the consensus on those is the deliverable: a gap judged on a cell that then moves by
               an angstrom describes no material), optionally the energy above the hull, novelty, REPORT.md, report.json
               and the instrument sheet.

Usage: python generate_to_target.py --ckpt MODEL.pt --intake DIR --gap band_gap --targets 1.5 2.0 3.0 --tag mytag
       [--out results] [--test-csv PATH] [--per-target 25] [--window 0.5] [--relax tensornet|none] [--relax-steps 150]
       [--hull-reference jarvis:PATH|mp] [--stability-col COL] [--workers 4]
"""
import argparse
import json
import os
import sys

try:
    from meidnet_eval.check_candidates import check, run
except ImportError:                    # run as a plain script from eval/
    from check_candidates import check, run


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
    ap.add_argument("--hull-reference", default=None, help="jarvis:PATH or mp: also the energy above the hull (hull_mlip.py)")
    ap.add_argument("--hull-cache", default=None)
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    ap.add_argument("--stability-col", default=None, help="the data's DFT hull column, to calibrate the hull estimate")
    ap.add_argument("--python", default=sys.executable, help="interpreter for the model steps")
    ap.add_argument("--python-judge", default=None, help="interpreter for the judge and potentials (default: --python)")
    a = ap.parse_args()
    py_model, py_judge = a.python, a.python_judge or a.python
    out = os.path.abspath(os.path.join(a.out, a.tag))
    test_csv = a.test_csv or os.path.join(a.intake, "test.csv")
    # S0's verdict, when the preview ran: family-free generation on data it graded for screening is a measured dead end
    preview = os.path.join(a.intake, "preview.json")
    if os.path.exists(preview):
        try:
            import json as _json
            pv = _json.load(open(preview, encoding="utf-8"))
            mode = pv.get("predicted_mode") or pv.get("mode")
            dens = (pv.get("values") or {}).get("density")
            if mode == "screening":
                print("=" * 78 + f"\nWARNING: block S0 graded this intake for SCREENING, not generation"
                      + (f" ({dens:.0f} compositions per element; generation needs about 200)" if isinstance(dens, (int, float)) else "")
                      + ".\nFamily-free generation will return structures outside your family and the independent judge will reject most of them."
                      "\nThe local screening path is:  python -m meidnet_eval.screen_local <intake> --ckpt MODEL --family FAMILY[:variant] --gap COLUMN --targets ... --check\n"
                      + "=" * 78, flush=True)
        except Exception as e:                                   # the warning must never stop a run
            print(f"(preview.json not read: {e})", flush=True)

    # 1 generate (the window here is looser than the final one: the judge and relaxation still have to act)
    run(py_model, "conditional_generate.py", "--tag", a.tag, "--ckpt", a.ckpt, "--gap", a.gap, "--geometry", "wyckoff",
        "--targets", *a.targets, "--per-target", a.per_target, "--target-window", a.window + 0.25, "--out", a.out)
    # 2-7 the same check every route gets: label from the structure, qualified judge, consensus, two potentials,
    # re-judge, optional hull, novelty, report and instrument sheet
    report = check(out, a.ckpt, a.intake, a.gap, a.window, test_csv, a.relax, a.relax_steps, a.hull_reference, a.hull_cache,
                   a.workers, a.stability_col, py_model, py_judge)
    report["tag"] = a.tag
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1, default=float)
    if report["stages"].get("2_two_model_consensus", 0) == 0:
        raise SystemExit("no candidate passed both judges: the target is outside what this model and data can serve")


if __name__ == "__main__":
    main()
