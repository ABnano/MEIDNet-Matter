"""Enumerate a design space completely, so the generator can be scored against exact ground truth.

The novel-anion families are small enough to enumerate (a few hundred rule-valid compositions), which makes a measurement
possible that the old design space never allowed: of the candidates that are REALLY on target, what fraction does the
generative path find (recall), and of what it returns, what fraction is really on target (precision)?

This script writes the complete space: every rule-valid composition of the given families, its cell (lattice from the
decoder's structure-latent head, the same way generation now builds cells) and the model's label read back from the structure.
The independent ground truth is added afterwards by the usual components -- candidate_cells.py for the two MLIPs and
cgcnn_judge.py for the gap -- so nothing here is judged by the model that proposed it.

Usage: python exhaustive_truth.py <out_tag> <family:variant> [<family:variant> ...] [--ckpt ...]    (fairchem-env)
Writes results/<out_tag>/candidates.csv and the CIFs, in the same layout as eval_generate.py so every later stage
(candidate_cells.py, sun_validate.py, cgcnn_judge.py) accepts it unchanged.
"""
import argparse, csv, os, sys
import torch
from pymatgen.io.cif import CifWriter

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
R = f"{HERE}/results"
from meidnet.checkpoint import load_checkpoint                 # noqa: E402
from meidnet.constraints import build_candidate, evaluate       # noqa: E402
from meidnet.data import featurize                             # noqa: E402
from meidnet.designspace import enumerate_space                 # noqa: E402
from meidnet.pipeline import family_for                         # noqa: E402
try:
    from meidnet_eval.eval_generate import COST, GAP, goal
except ImportError:          # run as a plain script from eval/
    from eval_generate import COST, GAP, goal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag"); ap.add_argument("spaces", nargs="+", help="family:variant, e.g. perovskite_ab_x3:sulfide")
    ap.add_argument("--ckpt", required=True)
    a = ap.parse_args()
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    lm = load_checkpoint(a.ckpt, device="cpu")
    out_dir = f"{R}/{a.tag}"; os.makedirs(f"{out_dir}/cifs", exist_ok=True)
    rows = []

    def predict(cand):
        x = torch.tensor(featurize(cand.raw, lm.model.max_sites), dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            zc, _ = lm.model.encode_crystal(x)
            lat, _, _, _ = lm.model.crystal_decoder(zc, input_coords=torch.zeros(1, lm.model.max_sites, 3),
                                                    center=torch.zeros(1, 3))
            p = lm.stats.denormalize_tensor(lm.model.property_decoder(zc))[0]
        return {c: float(p[j]) for j, c in enumerate(lm.stats.columns)}, float(lat[0, 0]) * 20.0

    for space in a.spaces:
        fam_name, variant = space.split(":")
        fam = family_for(goal(2.0, 1, 6, family=fam_name, variant=variant), need_variant=True)
        rules = [c for c in fam.constraints if c["name"] != "property_window"]
        fam_rules = family_for(goal(2.0, 1, 6, family=fam_name, variant=variant), need_variant=True)
        fam_rules.constraints = rules
        sp = enumerate_space(fam_rules, None)
        valid = [r for r in sp["rows"] if all(r["ok"].values())]
        kept = 0
        for r in valid:
            elements = dict(r["e"])
            cand = build_candidate(fam_rules, elements)
            _, a_dec = predict(cand)                      # the decoder's lattice for this cell, then rebuild on it
            cand = build_candidate(fam_rules, elements, a_dec)
            preds, _ = predict(cand)
            evaluate(cand, rules)
            if not cand.passed:                           # the rebuilt cell must still satisfy the chemistry rules
                continue
            name = f"{cand.raw.composition.reduced_formula}_{variant}.cif"
            CifWriter(cand.raw).write_file(f"{out_dir}/cifs/{name}")
            sites = {f"site_{g}": elements[g] for g in fam_rules.groups}
            rows.append(dict(tag=a.tag, mode=f"exhaustive/{fam_name}:{variant}", target=float("nan"), seed=0,
                             formula=cand.raw.composition.reduced_formula, **sites,
                             label_gap=preds[GAP], label_dhf=preds[COST], latent_norm=float("nan"), round=0,
                             file=f"cifs/{name}", a=cand.raw.lattice.a))
            kept += 1
        print(f"{space:38s} {len(sp['rows']):4d} enumerated, {len(valid):4d} rule-valid, {kept:4d} built and still valid",
              flush=True)

    cols = sorted({k for r in rows for k in r})
    order = [c for c in ("tag", "mode", "target", "seed", "formula") if c in cols] + \
            sorted(c for c in cols if c.startswith("site_")) + \
            [c for c in ("label_gap", "label_dhf", "latent_norm", "round", "file", "a") if c in cols]
    with open(f"{out_dir}/candidates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=order, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\n{len(rows)} compositions -> {out_dir}/candidates.csv "
          f"(label gap range {min(r['label_gap'] for r in rows):.2f}-{max(r['label_gap'] for r in rows):.2f} eV)")


if __name__ == "__main__":
    main()
