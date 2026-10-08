"""Screening mode on a laptop: enumerate a family, label every composition from its template structure, judge independently.

The mode block S0 recommends when a dataset is too small for the decoder to generate (fewer than ~200 compositions per
element).  Nothing is decoded: every composition the family allows is built on the family's prototype cell, read by the
trained model's STRUCTURE encoder (the same label a generated structure would get), and the ones inside the requested
window are judged by an independent, qualified model.  Compositions already in the data are marked, with the data's own
value next to the model's.  Any family file works (any number of cation groups, any anion); property roles are
arguments, not fixed column names.

Usage: python screen_local.py <intake> --ckpt MODEL.pt --family NAME_OR_YAML[:variant] --gap COLUMN --targets 1 2 3
       [--window 0.5] [--per-target 10] [--judge megnet|none] [--test-csv INTAKE/test.csv] [--relax none|tensornet]
       [--exclude-elements Pb Tl] [--out DIR]
Writes OUT/shortlist.csv (one row per kept composition: elements per site, model label, judge value, known/new with the
data's value, consensus), OUT/space.csv (every composition with its predictions), OUT/cifs/ (template cells) and
OUT/report.md.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

try:
    from meidnet_eval.screen_polymorphs import load_template
    from meidnet_eval.target_calibration import megnet_gaps, qualify
except ImportError:
    from screen_polymorphs import load_template
    from target_calibration import megnet_gaps, qualify


def known_values(intake, gap):
    """reduced formula -> the data's gap value, over every split of the intake."""
    from pymatgen.core import Composition
    out = {}
    for split in ("train", "val", "test"):
        p = os.path.join(intake, f"{split}.csv")
        if os.path.exists(p):
            t = pd.read_csv(p, usecols=lambda c: c in ("formula", gap))
            for f, v in zip(t["formula"], t[gap]):
                try:
                    out.setdefault(Composition(f).reduced_formula, float(v))
                except Exception:
                    pass
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("intake"); ap.add_argument("--ckpt", required=True)
    ap.add_argument("--family", required=True, help="a shipped family name or yaml path, optionally with :variant")
    ap.add_argument("--variant", default=None)
    ap.add_argument("--gap", required=True, help="the target property column of the model")
    ap.add_argument("--targets", type=float, nargs="+", required=True)
    ap.add_argument("--window", type=float, default=0.5)
    ap.add_argument("--per-target", type=int, default=10, help="compositions kept per target, closest model label first")
    ap.add_argument("--judge", choices=["megnet", "none"], default="megnet")
    ap.add_argument("--test-csv", default=None, help="held-out table that qualifies the judge (default INTAKE/test.csv)")
    ap.add_argument("--qualify-n", type=int, default=80)
    ap.add_argument("--relax", choices=["none", "tensornet"], default="none", help="relax the kept cells and re-judge them (needs matgl)")
    ap.add_argument("--exclude-elements", nargs="*", default=[])
    ap.add_argument("--max-compositions", type=int, default=60000)
    ap.add_argument("--out", default="screening")
    a = ap.parse_args(argv)

    import torch
    from meidnet.checkpoint import load_checkpoint
    from meidnet.designspace import enumerate_space
    from pymatgen.core import Composition
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    os.makedirs(os.path.join(a.out, "cifs"), exist_ok=True)
    lm = load_checkpoint(a.ckpt, device="cpu")
    cols = list(lm.stats.columns)
    if a.gap not in cols:
        raise SystemExit(f"the checkpoint predicts {cols}, not {a.gap}")
    fam = load_template(a.family, a.intake, [a.gap], variant=a.variant)
    if a.exclude_elements:
        for g in fam.groups.values():
            g.sample = [e for e in g.sample if e not in set(a.exclude_elements)]
    print(f"family {fam.name}{' / ' + fam.variant if fam.variant else ''}: groups {list(fam.groups)}; "
          f"enumerating up to {a.max_compositions} compositions ...", flush=True)
    space = enumerate_space(fam, lm, max_compositions=a.max_compositions,
                            progress=lambda i, n, *w: print(f"  {w[0] if w else 'building'} {i}/{n}", flush=True) if i % 2000 == 0 else None)
    rows = space["rows"]
    print(f"{len(rows)} compositions ({'a sample of ' + str(space['total']) if space['sampled'] else 'the whole space'}); "
          f"{sum(all(r['ok'].values()) for r in rows)} pass every rule of the family", flush=True)
    known = known_values(a.intake, a.gap)

    # the whole space, for the user's own analysis
    full = []
    for r in rows:
        rf = Composition(r["f"]).reduced_formula
        full.append({"formula": r["f"], **{f"site_{g}": e for g, e in r["e"].items()}, "lattice_a": r["a"],
                     **{f"label_{c}": r["p"].get(c) for c in cols}, "rules_passed": all(r["ok"].values()),
                     "known_in_data": rf in known, f"data_{a.gap}": known.get(rf)})
    pd.DataFrame(full).to_csv(os.path.join(a.out, "space.csv"), index=False)

    # the shortlist: per target, the rule-passing compositions whose model label lies in the window, closest first
    short = []
    for t in a.targets:
        ok = [r for r in rows if all(r["ok"].values()) and r["p"].get(a.gap) is not None and abs(r["p"][a.gap] - t) <= a.window]
        ok.sort(key=lambda r: abs(r["p"][a.gap] - t))
        for r in ok[:a.per_target]:
            rf = Composition(r["f"]).reduced_formula
            short.append({"target": t, "formula": r["f"], **{f"site_{g}": e for g, e in r["e"].items()},
                          "label_structure": float(r["p"][a.gap]), "known_in_data": rf in known, f"data_{a.gap}": known.get(rf),
                          "row": r})
        print(f"target {t}: {len(ok)} compositions inside ±{a.window}, {min(len(ok), a.per_target)} kept", flush=True)
    if not short:
        raise SystemExit("no composition of this family lands inside a window: widen --window, change the targets or the family")

    # template cells on disk
    from meidnet.constraints import build_candidate
    structs = []
    for i, s in enumerate(short):
        cand = build_candidate(fam, s["row"]["e"])
        st = cand.raw
        fn = f"{s['formula']}_{i:03d}.cif"
        st.to(filename=os.path.join(a.out, "cifs", fn))
        s["file"] = os.path.join("cifs", fn); s["natoms"] = len(st); structs.append(st)
        del s["row"]

    # the independent judge, qualified on the held-out split first
    judge_info = None
    if a.judge == "megnet":
        test_csv = a.test_csv or os.path.join(a.intake, "test.csv")
        try:
            judge_info = qualify(test_csv, a.qualify_n, {}, a.gap, "cif")
            json.dump(judge_info, open(os.path.join(a.out, "judge_qualification.json"), "w"), indent=1, default=float)
            fid = int(judge_info.get("fidelity", 0))
            print(f"judge qualification on {os.path.basename(test_csv)}: MAE {judge_info['mae']:.2f} eV, Spearman {judge_info['spearman']:.2f} (fidelity {fid})", flush=True)
            gaps = megnet_gaps(structs, fid)
            for s, g in zip(short, gaps):
                s["judge"] = None if g is None or g != g else float(g)
        except Exception as e:
            print(f"independent judge not run: {e}", flush=True)
            for s in short:
                s["judge"] = None
    else:
        for s in short:
            s["judge"] = None
    for s in short:
        s["label_in_window"] = abs(s["label_structure"] - s["target"]) <= a.window
        s["judge_in_window"] = (abs(s["judge"] - s["target"]) <= a.window) if s["judge"] is not None else None
        s["consensus"] = bool(s["label_in_window"] and s["judge_in_window"])
        s["data_in_window"] = (abs(s[f"data_{a.gap}"] - s["target"]) <= a.window) if s[f"data_{a.gap}"] is not None else None

    if a.relax != "none":
        try:
            try:
                from meidnet_eval.d1_mlip_check import relax_one
            except ImportError:
                from d1_mlip_check import relax_one
            os.makedirs(os.path.join(a.out, "relaxed"), exist_ok=True)
            for s, st in zip(short, structs):
                s1, rec = relax_one(st, a.relax, 150)
                s["relax_drop_eV_atom"] = rec.get(f"{a.relax}_drop_per_atom"); s["relaxed_spacegroup"] = rec.get(f"{a.relax}_spacegroup_relaxed")
                s1.to(filename=os.path.join(a.out, "relaxed", os.path.basename(s["file"])))
        except Exception as e:
            print(f"relaxation not run: {e}", flush=True)

    df = pd.DataFrame(short)
    df.to_csv(os.path.join(a.out, "shortlist.csv"), index=False)
    n_cons = int(df["consensus"].sum()); n_known = int(df["known_in_data"].sum())
    lines = [f"# Screening of {fam.name}{' / ' + fam.variant if fam.variant else ''} for {a.gap} at {a.targets} (window ±{a.window} eV)", "",
             f"{len(rows)} compositions enumerated, {len(df)} kept by the model's structure label, {n_cons} also inside the window for the independent judge; "
             f"{n_known} of the kept compositions are already in the data.", ""]
    if judge_info:
        lines.append(f"Judge: MEGNet, qualified on the held-out split: MAE {judge_info['mae']:.2f} eV, Spearman {judge_info['spearman']:.2f}. "
                     f"Values are model estimates on template cells; relaxation and stability are not assessed here unless --relax was given.")
        lines.append("")
    lines += ["| target | formula | model label | judge | known in data (its value) | both in window |", "|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        dv = r[f"data_{a.gap}"]
        kv = ("yes (%.2f)" % dv) if r["known_in_data"] and pd.notna(dv) else ("yes" if r["known_in_data"] else "new")
        jv = "" if r["judge"] is None or pd.isna(r["judge"]) else "%.2f" % r["judge"]
        lines.append("| %.1f | %s | %.2f | %s | %s | %s |" % (r["target"], r["formula"], r["label_structure"], jv, kv, "yes" if r["consensus"] else "no"))
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    json.dump({"family": fam.name, "variant": fam.variant, "gap": a.gap, "targets": a.targets, "window": a.window,
               "enumerated": len(rows), "kept": len(df), "consensus": n_cons, "known": n_known, "judge": judge_info},
              open(os.path.join(a.out, "summary.json"), "w"), indent=1, default=float)
    print("\n".join(lines[:4]))
    print(f"\nwrote {a.out}/shortlist.csv, space.csv, report.md, cifs/", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
