"""Block S0, the preview gate: what an upload can and cannot support, before a minute of training is spent.

Every number here is computed from the data alone — no model — so the answer arrives in seconds, and each one predicts
something about the run that follows:
  shared property profile   whether property -> structure has a unique answer at all
  compositions per element  whether the DECODER can work, hence generation vs screening
                            (measured: 12 -> 0.1%, 30 -> 0.7%, 80 -> 5.4%, 218 -> 64% composition recovery)
  support per target        the label error to expect there (validated: servable 0.59 eV vs unreliable 0.95 eV)
  polymorph spread         whether a target must mean the GROUND-STATE property rather than one polymorph's
  novelty frontier         whether anything new is reachable from this chemistry (needs a family, so optional)
Grades come from stages.py, the single definition shared with the checkup, the report and the app.

Usage: python preview.py <intake_dir> --gap Band_gap_DSH_SOC [--stability Es] [--targets 2 3 4] [--family fam.yaml]
Writes <intake_dir>/preview.json and prints the gate.
"""
import argparse, collections, csv, json, os, sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
try:
    from meidnet_eval.stages import BY_ID
except ImportError:          # run as a plain script from eval/
    from stages import BY_ID
csv.field_size_limit(10 ** 9)


def compositions_per_element(formulas):
    """Mean number of distinct compositions each element appears in — the quantity the density rule is stated in."""
    from pymatgen.core import Composition
    seen = collections.defaultdict(set)
    for f in set(formulas):
        try:
            for el in Composition(f).elements:
                seen[el.symbol].add(f)
        except Exception:
            continue
    counts = {e: len(v) for e, v in seen.items()}
    return (float(np.mean(list(counts.values()))) if counts else 0.0), counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("intake"); ap.add_argument("--gap", required=True)
    ap.add_argument("--stability", default=None, help="column that ranks polymorphs of one composition (lower = better)")
    ap.add_argument("--targets", type=float, nargs="+", default=None)
    ap.add_argument("--window", type=float, default=0.25)
    ap.add_argument("--family", default=None, help="family yaml, to measure the novelty frontier as well")
    ap.add_argument("--out", default=None, help="where preview.json is written (default INTAKE/preview.json)")
    a = ap.parse_args()

    audit = json.load(open(f"{a.intake}/audit.json"))
    tr = pd.read_csv(f"{a.intake}/train.csv", usecols=lambda c: c in ("formula", "prototype", a.gap, a.stability))
    full = pd.concat([pd.read_csv(f"{a.intake}/{s}.csv", usecols=lambda c: c in ("formula", "prototype", a.gap))
                      for s in ("train", "val", "test") if os.path.exists(f"{a.intake}/{s}.csv")], ignore_index=True)

    density, per_el = compositions_per_element(tr.formula)
    y = tr[a.gap].to_numpy(dtype=float)
    targets = a.targets or [round(q, 1) for q in np.quantile(y, [0.1, 0.3, 0.5, 0.7, 0.9])]
    support = {float(t): int((np.abs(y - t) <= a.window).sum()) for t in targets}
    poly = collections.Counter(full.formula)
    multi = {f: n for f, n in poly.items() if n > 1}

    values = {"shared_profile": audit.get("materials_sharing_profile_with_>=10"),
              "zero_share": audit["properties"][a.gap]["zero_share"],
              "density": density}
    if a.family:
        try:
            try:
                from meidnet_eval.screen_polymorphs import load_template
            except ImportError:          # run as a plain script from eval/
                from screen_polymorphs import load_template
            from meidnet.designspace import enumerate_space
            from pymatgen.core import Composition
            fam = load_template(a.family, a.intake, [a.gap])
            sp = enumerate_space(fam, None)
            space = {Composition(r["f"]).reduced_composition for r in sp["rows"] if all(r["ok"].values())}
            have = {Composition(f).reduced_composition for f in full.formula}
            values["novelty_frontier"] = (len(space - have) / len(space)) if space else 0.0
        except Exception as e:                                  # a family is optional: never block the gate on it
            print(f"  (novelty frontier not measured: {e})")

    S0 = BY_ID["S0"]
    verdict, grades = S0.verdict(values, context=values)
    # the support metric is graded per target, not once
    sup_metric = S0.by_id("target_support")
    sup_grades = {t: sup_metric.grade(n) for t, n in support.items()}
    servable = [t for t, g in sup_grades.items() if g == "PASS"]
    borderline = [t for t, g in sup_grades.items() if g == "WARN"]

    dens_metric = S0.by_id("density")
    mode = "generation" if dens_metric.grade(density) == "PASS" else "screening"

    print(f"\n{'=' * 78}\nS0 PREVIEW — {a.intake}\n{'=' * 78}")
    print(f"{audit['parsed']} of {audit['rows']} structures parsed, {audit['elements']} elements, "
          f"{audit['prototypes']} prototypes, {audit['duplicates']} duplicate(s); split {audit['split_sizes']}")
    print(f"atoms per cell: {audit['atoms_per_cell']}")
    print(f"\n{'metric':34s} {'value':>10s}  {'band':>22s}  grade")
    for m in S0.metrics:
        if m.id not in values or values[m.id] is None:
            continue
        p, w, f = m.band_text()
        band = f"PASS {p}" + (f" / WARN {w}" if w else "")
        print(f"{m.name:34s} {values[m.id]:10.3g}  {band:>22s}  {grades[m.id]}")
    print(f"\nsupport per target (+-{a.window:g}):")
    for t in sorted(support):
        print(f"   {t:6.2f} {a.gap}: {support[t]:4d} materials  -> {sup_grades[t]}")
    print(f"\npolymorphs: {len(multi)} compositions have more than one structure "
          f"(max {max(multi.values()) if multi else 0})")

    gate = []
    gate.append(f"BLOCK S0 VERDICT: {verdict}")
    gate.append(f"PREDICTED MODE: {mode}  (compositions per element {density:.0f}; "
                f"the decoder needs >= {dens_metric.pass_at:g} to generate, >= {dens_metric.warn_at:g} to be marginal)")
    if servable or borderline:
        gate.append(f"TARGETS this data can serve: {sorted(servable)} well supported"
                    + (f", {sorted(borderline)} borderline" if borderline else ""))
    else:
        gate.append("TARGETS: none of the tested targets has enough support; expect extrapolation everywhere")
    if multi:
        gate.append(f"GROUND-STATE TARGET recommended: {len(multi)} compositions have several polymorphs with different "
                    f"properties, so a target must mean the property of the polymorph the material actually adopts"
                    + ("" if a.stability else " — no stability/energy column was given, so the pipeline cannot rank them"))
    for m in S0.metrics:
        if m.id in values and grades.get(m.id) in ("WARN", "FAIL"):
            gate.append(f"{m.name} is {grades[m.id]}: {m.meaning_bad} Remedy: {m.remedy}")
    print("\n" + "\n".join("* " + g for g in gate))

    json.dump(dict(intake=a.intake, gap=a.gap, values=values, grades=grades, verdict=verdict, mode=mode,
                   support=support, support_grades={str(k): v for k, v in sup_grades.items()},
                   servable=servable, borderline=borderline, polymorph_compositions=len(multi),
                   compositions_per_element=per_el, gate=gate),
              open(a.out or f"{a.intake}/preview.json", "w"), indent=1, default=float)
    print(f"\nwrote {a.out or f'{a.intake}/preview.json'}")


if __name__ == "__main__":
    main()
