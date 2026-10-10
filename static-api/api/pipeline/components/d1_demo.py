"""The D0-vs-D1 demonstration: can the symmetry path emit real crystals where free coordinates cannot?

Three columns are reported, and the middle one is what makes this a controlled test rather than two anecdotes:

* **D0**            - the free-coordinate decoder of `mp20_main`, the published configuration and the current baseline.
* **D1 free path**  - the free-coordinate decoder *of the D1 model*.  The symmetry head was added alongside the old head,
                      not in place of it, so one model holds both and the SAME latent can be decoded through each.  Any
                      difference between this column and the next is the geometry path alone: same weights, same latent,
                      same data.
* **D1 symmetry**   - space group + the symmetry-distinct sites, expanded by the symmetry operations.

Comparing D0 with the D1 free path separately answers a different question: whether adding the symmetry objective
damaged the decoder that is already deployed.

Part 1 reconstructs held-out crystals (the ceiling: can the path represent a real material at all?).  Part 2 generates
from band-gap targets (the actual claim).  Defaults are deliberately small so this runs in minutes on a CPU.

Usage: python d1_demo.py --d0 <ckpt> --d1 <ckpt> --config <yaml> [--n 150] [--targets 0.5 1.5 3.0] [--per-target 10]
"""
import argparse, collections, json, os, sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pymatgen.core import Lattice, Structure                      # noqa: E402
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer         # noqa: E402

from meidnet.checkpoint import load_checkpoint                    # noqa: E402
from meidnet.config import load_config                            # noqa: E402
from meidnet.data import MaterialsDataset, load_records, read_table  # noqa: E402
from meidnet.symmetry import build_structure                      # noqa: E402
try:
    from meidnet_eval.conditional_generate import anchor, decode_structure, plausible, refine
except ImportError:          # run as a plain script from eval/
    from conditional_generate import anchor, decode_structure, plausible, refine


def spacegroup_of(s):
    try:
        return int(SpacegroupAnalyzer(s, symprec=0.1).get_space_group_number())
    except Exception:
        return 0


def describe(name, structures, truths=None):
    """Turn a list of (structure | None) into the row of the comparison table."""
    built = [s for s in structures if s is not None]
    row = {"attempted": len(structures), "built": len(built)}
    if not built:
        return row
    ok = [s for s in built if plausible(s)[0]]
    row["valid"] = len(ok)
    row["median_atoms"] = float(np.median([len(s) for s in built]))
    vols = []
    for s in built:
        try:
            vols.append(s.volume / len(s))
        except Exception:
            pass
    row["median_vol_per_atom"] = float(np.median(vols)) if vols else None
    mins = []
    for s in built:
        # A degenerate lattice -- D0's known failure mode -- makes pymatgen's periodic distance routine raise, so the
        # measurement has to survive it: that structure contributes no distance rather than killing the comparison.
        try:
            if len(s) > 1:
                d = s.distance_matrix + np.eye(len(s)) * 99
                mins.append(float(d.min()))
        except Exception:
            pass
    row["distance_failed"] = len([s for s in built if len(s) > 1]) - len(mins)
    row["median_min_distance"] = float(np.median(mins)) if mins else None
    row["distinct_spacegroups"] = len({spacegroup_of(s) for s in built})
    row["spacegroup_top"] = collections.Counter(spacegroup_of(s) for s in built).most_common(3)
    if truths is not None:
        from pymatgen.analysis.structure_matcher import StructureMatcher
        sm = StructureMatcher()
        hit = 0
        for s, t in zip(structures, truths):
            if s is None or t is None:
                continue
            try:
                hit += bool(sm.fit(s, t))
            except Exception:
                pass
        row["matches_truth"] = hit
    return row


def d1_structure(lm, z, species_mask=None):
    """Decode one latent through the symmetry head."""
    with torch.no_grad():
        pred = lm.model.crystal_decoder.symmetry_forward(z)
    try:
        s, _sg, _n = build_structure(*[p[0] for p in pred], species_mask=species_mask)
        return s
    except Exception:
        return None


def latents_for(lm, dataset, idx):
    """z_c for a held-out crystal, exactly as the structure-only training branch computes it."""
    batch = torch.stack([dataset[i]["crystal_vec"] for i in idx])
    props = torch.stack([dataset[i]["props"] for i in idx])
    with torch.no_grad():
        zc, _zp, _a, _center, _b, _coords = lm.model.encode_modalities(batch, props)
    return zc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--d0", required=True, help="baseline checkpoint (free decoder)")
    ap.add_argument("--d1", required=True, help="D1 checkpoint (carries both heads)")
    ap.add_argument("--config", required=True, help="a config naming the val table and columns")
    ap.add_argument("--n", type=int, default=150, help="held-out structures for part 1")
    ap.add_argument("--targets", type=float, nargs="+", default=[0.5, 1.5, 3.0])
    ap.add_argument("--per-target", type=int, default=10)
    ap.add_argument("--gap-column", default="band_gap")
    ap.add_argument("--json", help="write the table here")
    a = ap.parse_args()

    cfg = load_config(a.config)
    d0 = load_checkpoint(a.d0)
    d1 = load_checkpoint(a.d1)
    has_head = getattr(d1.model.crystal_decoder, "sym_trunk", None) is not None
    print(f"D0 {os.path.basename(a.d0)} | D1 {os.path.basename(a.d1)} (symmetry head: {has_head})")
    if not has_head:
        raise SystemExit("the --d1 checkpoint has no symmetry head; train with decoder_geometry: wyckoff")

    df = read_table(cfg.resolve(cfg.data.val_table)).head(a.n)
    records, rep = load_records(df, cfg.data, cfg.resolve, None, source="demo", keep_structures=True)
    print(f"part 1: {len(records)} held-out crystals ({rep.rows} read)")
    ds0, ds1 = MaterialsDataset(records, d0.stats), MaterialsDataset(records, d1.stats)
    truths = [getattr(r, "structure", None) for r in records]
    idx = list(range(len(records)))

    table = {}
    z0 = latents_for(d0, ds0, idx)
    z1 = latents_for(d1, ds1, idx)
    n_atoms = [len(t) if t is not None else 8 for t in truths]

    def free_path(lm, z, counts):
        out = []
        for i in range(z.shape[0]):
            try:
                s, _ = decode_structure(lm, z[i:i + 1], min(counts[i], lm.model.max_sites))
                out.append(s)
            except Exception:
                out.append(None)
        return out

    table["recon_D0"] = describe("D0", free_path(d0, z0, n_atoms), truths)
    table["recon_D1_free"] = describe("D1 free", free_path(d1, z1, n_atoms), truths)
    table["recon_D1_sym"] = describe("D1 sym", [d1_structure(d1, z1[i:i + 1]) for i in idx], truths)

    # ── part 2: generation from band-gap targets ────────────────────────────
    print(f"part 2: {len(a.targets)} targets x {a.per_target} draws")
    gen = {k: [] for k in ("D0", "D1_free", "D1_sym")}
    for t in a.targets:
        for lm, keys in ((d0, ("D0",)), (d1, ("D1_free", "D1_sym"))):
            cols = list(lm.stats.columns)
            if a.gap_column not in cols:
                print(f"  {a.gap_column} is not a property of this model ({cols})")
                continue
            zt = anchor(lm, a.gap_column, t, cols)
            for k in range(a.per_target):
                z = zt + 0.3 * torch.randn_like(zt)
                z = torch.nn.functional.normalize(z, dim=1)
                z, _ = refine(lm, z, a.gap_column, t, cols, steps=200)
                if "D0" in keys or "D1_free" in keys:
                    try:
                        s, _ = decode_structure(lm, z, 8)
                    except Exception:
                        s = None
                    gen[keys[0]].append(s)
                if "D1_sym" in keys:
                    gen["D1_sym"].append(d1_structure(d1, z))
    for k, v in gen.items():
        if v:
            table[f"gen_{k}"] = describe(k, v)

    print()
    hdr = ["attempted", "built", "valid", "median_atoms", "median_vol_per_atom",
           "median_min_distance", "distance_failed", "distinct_spacegroups", "matches_truth"]
    print(f"{'row':16s}" + "".join(f"{h[:11]:>13s}" for h in hdr))
    for name, row in table.items():
        print(f"{name:16s}" + "".join(
            f"{(f'{row[h]:.2f}' if isinstance(row.get(h), float) else str(row.get(h, '-'))):>13s}" for h in hdr))
    print()
    for name, row in table.items():
        if "spacegroup_top" in row:
            print(f"  {name:16s} most common space groups: {row['spacegroup_top']}")
    if a.json:
        json.dump(table, open(a.json, "w"), indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
