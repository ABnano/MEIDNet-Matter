"""Is the lattice constant better predicted by the property-conditioned decoder or by the radii rule the template uses?

Generation currently throws the decoder's lattice away: `decode()` keeps only the species logits and builds the cell from the
family prototype with the bond_sum radii rule.  So "property -> structure" is today "property -> composition".  This script
asks whether that is justified, against ground truth we already own: the MLIP-relaxed lattice constant of all the generated
candidates, where TensorNet and CHGNet agree to ~0.02 A (results/mlip_compare.csv).

For every validated composition it compares three lattice constants with the relaxed one:
  a_rule      the radii rule used by the template (what generation uses today)
  a_decoder   the crystal decoder's own lattice head, read from the structure latent z_c
  a_mean      the mean of the two, as a trivial baseline
Usage: python lattice_source.py [--ckpt ...] [--family perovskite_ab_o2x]    (fairchem-env)
Writes results/lattice_source.csv and prints MAE against the relaxed lattice.
"""
import argparse, os, sys
import numpy as np
import pandas as pd
import torch

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
R = f"{HERE}/results"
from meidnet.checkpoint import load_checkpoint                     # noqa: E402
from meidnet.data import featurize                                 # noqa: E402
from meidnet.designspace import build_candidate                    # noqa: E402
from meidnet.pipeline import family_for                            # noqa: E402
try:
    from meidnet_eval.eval_generate import goal
except ImportError:          # run as a plain script from eval/
    from eval_generate import goal

FAMILIES = {4: ("perovskite_ab_o2x", ("oxynitride", "oxyfluoride")),   # key length -> family and variants to try
            3: ("perovskite_abx3", ("oxide",))}


def unscale_lattice(lat):
    """The decoder emits the scaled lattice used by featurize/scale_lattice; invert the a, b, c part."""
    from meidnet.data import scale_lattice
    probe = scale_lattice(10.0, 10.0, 10.0, 90.0, 90.0, 90.0)       # recover the linear factor from a known cell
    factor = float(probe.flatten()[0]) / 10.0
    return np.asarray(lat).flatten()[:3] / factor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    a = ap.parse_args()
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    lm = load_checkpoint(a.ckpt, device="cpu")
    M = pd.read_csv(f"{R}/mlip_compare.csv")
    rows = []
    for r in M.itertuples():
        parts = str(r.key).split("|")
        fam_name, variants = FAMILIES.get(len(parts), (None, ()))
        if not fam_name:
            continue
        cand = None
        for v in variants:                                          # the variant that accepts this composition
            fam = family_for(goal(2.0, 1, 6, family=fam_name, variant=v), need_variant=True)
            try:
                cand = build_candidate(fam, dict(zip(fam.groups, parts)))
                break
            except Exception:
                continue
        if cand is None:
            continue
        a_rule = cand.raw.lattice.a
        with torch.no_grad():
            X = torch.from_numpy(featurize(cand.raw, lm.model.max_sites)[None]).float()
            zc, _ = lm.model.encode_crystal(X)
            lat_out, _, _, _ = lm.model.crystal_decoder(zc, input_coords=torch.zeros(1, lm.model.max_sites, 3),
                                                        center=torch.zeros(1, 3))
        a_dec = float(unscale_lattice(lat_out.numpy())[0])
        rows.append(dict(formula=r.formula, key=r.key, a_rule=a_rule, a_decoder=a_dec,
                         a_mean=0.5 * (a_rule + a_dec), a_relaxed=r.a_tensornet, a_chgnet=r.a_chgnet))
    V = pd.DataFrame(rows)
    V.to_csv(f"{R}/lattice_source.csv", index=False)
    print(f"{len(V)} compositions with a relaxed lattice to compare against "
          f"(the two potentials differ by only {np.abs(V.a_relaxed - V.a_chgnet).mean():.3f} A on average)\n")
    print(f"{'lattice source':34s} {'MAE':>7s} {'median':>8s} {'bias':>8s} {'worst':>7s}")
    for col, name in (("a_rule", "radii rule (used by generation)"), ("a_decoder", "crystal decoder lattice head"),
                      ("a_mean", "mean of the two")):
        d = V[col] - V.a_relaxed
        print(f"{name:34s} {np.abs(d).mean():7.3f} {np.abs(d).median():8.3f} {d.mean():+8.3f} {np.abs(d).max():7.3f}")
    better = int((np.abs(V.a_decoder - V.a_relaxed) < np.abs(V.a_rule - V.a_relaxed)).sum())
    print(f"\ndecoder closer than the radii rule for {better}/{len(V)} compositions")
    print("verdict:", "use the decoder's lattice at generation" if better > 0.6 * len(V)
          else ("keep the radii rule and do not claim the lattice is generated" if better < 0.4 * len(V)
                else "no clear winner: keep the radii rule, state that the lattice is not property-conditioned"))


if __name__ == "__main__":
    main()
