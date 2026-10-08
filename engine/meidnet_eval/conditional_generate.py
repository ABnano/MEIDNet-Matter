"""Conditional generation WITHOUT a family: ask for a band gap, get whole structures, then check them independently.

Every generation path in this project so far needed a family — a prototype whose slots the decoder fills — which is why
blocks S5-S7 could not run on MP-20 and its 4,885 prototypes.  But the decoder already emits everything a structure
needs: `SE3Decoder` returns the lattice, the per-site element scores AND the per-site coordinates.  Generation threw the
lattice and the coordinates away and used the family template instead.  This path keeps them, so a structure comes out of
the model itself and no family is required.

How a target becomes a structure
  1. the requested property vector is normalised and encoded -> z_p, the point the target names in latent space;
  2. optional refinement: steps of gradient on the sphere that move z so the property decoder reads the target back,
     which is the same objective the family-based search uses, minus the family;
  3. the crystal decoder reads z once: lattice (6 scaled parameters), species scores per slot, coordinates per slot;
  4. the first `--atoms` slots are taken as the cell.  The decoder cannot say how many sites a structure has — padding
     slots were masked out of the training loss, so it was never taught to signal "empty" — therefore the cell size is an
     input here, not a prediction.  That limitation is stated here rather than hidden.

What it does NOT do: judge its own output.  The structures are written as CIFs for `candidate_cells.py` (two independent
ML potentials) and a trained CGCNN judge to score, so "the gap is near the target" is never the model's own claim.

Usage: python conditional_generate.py --tag T --ckpt model.pt --data INTAKE --gap band_gap \
           --targets 0.5 1 2 3 4 --atoms 4 6 8 --per-target 8 [--steps 300] [--sigma 0.3]
Writes results/<tag>/candidates.csv and cifs/, in the layout the validation components already read.
"""
import argparse, csv, json, os, sys, time

import numpy as np
import torch
import torch.nn.functional as F
from pymatgen.core import Lattice, Structure
from pymatgen.io.cif import CifWriter

from meidnet.chem import ELEMENTS                                  # noqa: E402
from meidnet.checkpoint import load_checkpoint                      # noqa: E402


def anchor(lm, gap_col, value, cols):
    """The latent the target names: the property vector with the target in its column, normalised, then encoded."""
    vec = torch.zeros(1, len(cols))
    for j, c in enumerate(cols):
        v = float(value) if c == gap_col else float(lm.stats.mean[j])
        vec[0, j] = (v - lm.stats.mean[j]) / lm.stats.std[j]
    with torch.no_grad():
        z = lm.model.encode_properties(vec)
    return F.normalize(z, dim=1)


def refine(lm, z, gap_col, value, cols, steps, lr=0.05):
    """Move z on the unit sphere until the property decoder reads the target back: the family-based search's objective."""
    j = cols.index(gap_col)
    want = torch.tensor([(float(value) - lm.stats.mean[j]) / lm.stats.std[j]], dtype=torch.float32)
    if steps <= 0:                                   # anchor only: no refinement, nothing to report as residual
        return z.detach(), float("nan")
    z = z.clone().requires_grad_(True)
    opt = torch.optim.Adam([z], lr=lr)
    for _ in range(steps):
        opt.zero_grad()
        loss = F.mse_loss(lm.model.property_decoder(z)[:, j], want)
        loss.backward(); opt.step()
        with torch.no_grad():
            z.data = F.normalize(z.data, dim=1)
    return z.detach(), float(loss)


def decode_structure(lm, z, n_atoms):
    """One latent -> one crystal: the decoder's own lattice, species and coordinates, read at `n_atoms` slots."""
    ms = lm.model.max_sites
    with torch.no_grad():
        lat, _adj, spc, crd = lm.model.crystal_decoder(z, input_coords=torch.zeros(1, ms, 3), center=torch.zeros(1, 3))
        props = lm.stats.denormalize_tensor(lm.model.property_decoder(z))[0]
    p = lat[0].numpy()
    a, b, c = (np.clip(p[:3], 0.05, 1.0) * 20.0)                   # scale_lattice divides lengths by 20, angles by 180
    al, be, ga = np.clip(p[3:], 0.1, 0.95) * 180.0
    species = [ELEMENTS[int(i)] for i in spc[0, :n_atoms].argmax(-1).numpy()]
    coords = (crd[0, :n_atoms].numpy() % 1.0)
    s = Structure(Lattice.from_parameters(float(a), float(b), float(c), float(al), float(be), float(ga)),
                  species, coords, coords_are_cartesian=False)
    return s, {c: float(props[j]) for j, c in enumerate(lm.stats.columns)}


def decode_symmetry(lm, z, merge_distance=0.8, species_mask=None, max_atoms=0, require_elements=None, min_orbits=1):
    """One latent -> one crystal through the D1 symmetry head.

    Unlike the free path this needs no atom count: the occupancy head says how many symmetry-distinct sites there are
    and the space group's operations generate the rest, so the cell size is a prediction rather than a user input.
    """
    from meidnet.symmetry import build_structure
    with torch.no_grad():
        pred = lm.model.crystal_decoder.symmetry_forward(z)
        props = lm.stats.denormalize_tensor(lm.model.property_decoder(z))[0]
    try:
        s, sg, n_orbits = build_structure(*[p[0] for p in pred], merge_distance=merge_distance,
                                          species_mask=species_mask, max_atoms=max_atoms,
                                          require_elements=require_elements, min_orbits=min_orbits)
    except Exception:
        return None, {}, 0, 0
    return s, {c: float(props[j]) for j, c in enumerate(lm.stats.columns)}, sg, n_orbits


def structure_label(lm, s):
    """The properties of the structure that is actually returned, read at ITS OWN structure latent.

    This is the `label_source: structure` fix from the family-based engine (journal entry: "candidate properties =
    property decoder at the *search latent*; windows always pass").  Reading the property decoder at the search latent
    is circular -- the latent search drives that very output to the target, so it reports the request back and every
    target window passes.  Featurising the returned structure and encoding it again breaks the circle.

    Returns (labels, reason).  `reason` is set when no structure-read label exists: the encoder accepts at most `max_sites`
    atoms, and the symmetry path routinely predicts larger cells, so for those candidates the pipeline cannot check its
    own claim.  That is reported rather than quietly replaced by the latent label.
    """
    from meidnet.data import featurize
    try:
        x = torch.tensor(featurize(s, lm.model.max_sites), dtype=torch.float32).unsqueeze(0)
    except ValueError as e:
        return None, str(e)
    with torch.no_grad():
        zc, _ = lm.model.encode_crystal(x)
        v = lm.stats.denormalize_tensor(lm.model.property_decoder(zc))[0]
    return {c: float(v[j]) for j, c in enumerate(lm.stats.columns)}, ""


def plausible(s, min_d=0.7, max_vol_per_atom=200.0):
    """Reject cells that cannot be a material at all, so the judges are not asked to score nonsense."""
    try:
        if s.volume / len(s) > max_vol_per_atom or s.volume / len(s) < 2.0:
            return False, "implausible volume per atom"
        d = s.distance_matrix + np.eye(len(s)) * 99
        if len(s) > 1 and d.min() < min_d:
            return False, f"atoms {d.min():.2f} A apart"
        return True, ""
    except Exception as e:
        return False, type(e).__name__


REASON_NO_LABEL = "no structure-read label (cell larger than the encoder accepts)"


def generate_pool(lm, gap, targets, *, per_target=8, oversample=40, sigma=0.3, seed=0, steps=0, geometry="wyckoff", atoms=(4, 6, 8),
                  merge_distance=0.8, species_mask=None, anions=None, min_orbits=2, max_atoms=0, label_source="structure",
                  target_window=0.5, cifs_dir="cifs", tag="pool", on_progress=None, should_stop=None, log=print):
    """Draw candidates for each target and keep the ones that pass every check.  Returns (rows, rejected_counts).

    Each draw: a latent near the target's anchor -> a cell from the chosen geometry path -> plausibility -> a compound
    -> the label read from the returned cell -> inside the target window.  `on_progress(dict)` is called every ten
    draws and `should_stop()` is checked every draw, so a web server can report and interrupt the loop.
    """
    import torch.nn.functional as F
    torch.manual_seed(seed)
    cols = list(lm.stats.columns)
    os.makedirs(cifs_dir, exist_ok=True)
    rows, rejected = [], {}

    def reject(why):
        rejected[why] = rejected.get(why, 0) + 1

    for ti, target in enumerate(targets):
        z0 = anchor(lm, gap, target, cols)
        kept = 0
        # Over-sample until enough survive the filters.  With no refine step a draw costs a fraction of a second, so the
        # budget can be generous; the structure-read label window is strict at wide gaps, and that strictness is the point.
        for k in range(per_target * oversample):
            if kept >= per_target or (should_stop and should_stop()):
                break
            if on_progress and k % 10 == 0:
                on_progress(dict(target_index=ti, target=target, attempts=k, kept=kept, phase="generating"))
            z = F.normalize(z0 + sigma * torch.randn_like(z0), dim=1)
            z, resid = refine(lm, z, gap, target, cols, steps)
            n = atoms[k % len(atoms)]
            sg, n_orbits = 0, 0
            if geometry == "wyckoff":
                s, preds, sg, n_orbits = decode_symmetry(lm, z, merge_distance, species_mask=species_mask, max_atoms=max_atoms,
                                                        require_elements=anions, min_orbits=min_orbits)
                n = len(s) if s is not None else 0          # the cell size is predicted here, not requested
            else:
                s, preds = decode_structure(lm, z, n)
            if s is None:
                reject("symmetry build failed"); continue
            ok, why = plausible(s)
            if ok and len(s.composition.elements) < 2:
                ok, why = False, "a single element, not a compound"
            if not ok:
                reject(why); continue
            label_note = ""
            if label_source == "structure":
                label, label_note = structure_label(lm, s)
                if label is not None:
                    preds = label
                elif target_window is not None:
                    reject(REASON_NO_LABEL); continue           # a claim that cannot be checked is not made
            if target_window is not None and abs(preds[gap] - target) > target_window:
                reject(f"structure-read label off target by more than {target_window} eV"); continue
            name = f"T{target:g}_n{n}_{k}"
            CifWriter(s).write_file(os.path.join(cifs_dir, f"{name}.cif"))
            rows.append(dict(tag=tag, mode="conditional/no-family", target=target, seed=seed,
                             formula=s.composition.reduced_formula, natoms=len(s),
                             label_gap=preds[gap], label_dhf=preds[cols[0] if cols[0] != gap else cols[-1]],
                             latent_norm=float(z.norm()), round=0, file=f"cifs/{name}.cif",
                             lattice_a=round(s.lattice.a, 3), volume_per_atom=round(s.volume / len(s), 2),
                             target_residual=round(resid, 4) if resid == resid else None, geometry=geometry,
                             spacegroup=sg, n_orbits=n_orbits,
                             label_source=label_source if not label_note else "latent (no structure-read label)",
                             label_note=label_note))
            kept += 1
        log(f"  target {target:g} eV: {kept} structures kept")
    return rows, rejected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="pool", help="name of the run folder inside --out (default pool)"); ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", default=None, help="unused; kept so older commands still run")
    ap.add_argument("--gap", default=None, help="the target property column; default: the checkpoint's column whose name contains 'gap', else its first property")
    ap.add_argument("--targets", type=float, nargs="+", required=True)
    ap.add_argument("--atoms", type=int, nargs="+", default=[4, 6, 8])
    ap.add_argument("--geometry", choices=["free", "wyckoff"], default="free",
                    help="free = the original decoder, which needs --atoms because it cannot say how many sites a "
                         "structure has; wyckoff = the D1 symmetry head, which predicts the space group and the "
                         "symmetry-distinct sites and therefore predicts the cell size itself")
    ap.add_argument("--label-source", choices=["structure", "latent"], default="structure",
                    help="structure = read the properties back from the returned cell (the default); "
                         "latent = read them at the search latent, which reports the request back and makes every "
                         "target window pass. Kept only to reproduce older runs.")
    ap.add_argument("--target-window", type=float, default=None,
                    help="reject a candidate whose structure-read label misses the target by more than this many eV. This is "
                         "what makes generation target-following: the latent search alone does not.")
    ap.add_argument("--require-anion", nargs="*", default=["auto"],
                    help="force at least one site to be one of these elements (no value = F O Cl N Br I S Se Te). "
                         "Without it the species head returns the training set's dominant answer, which for MP-20 is a "
                         "zero-gap intermetallic regardless of the requested gap.")
    ap.add_argument("--exclude-elements", nargs="*", default=["Ac", "Np", "Pa", "Pm", "Pu", "Tc", "Th", "U"],
                    help="elements the decoder may not use (default: the radioactive ones)")
    ap.add_argument("--oversample", type=int, default=40,
                    help="draws attempted per structure kept (the structure-read label window rejects most draws at wide gaps)")
    ap.add_argument("--min-orbits", type=int, default=2,
                    help="least symmetry-distinct sites a cell may have; 2 means the result is always a compound "
                         "(with 1, forcing an anion onto a one-site cell gives a pure element, and 60% of draws were lost)")
    ap.add_argument("--max-atoms", type=int, default=0,
                    help="cap the predicted cell so every candidate can be re-encoded and labelled from its own structure "
                         "(0 = no cap; set it to the model's max_sites)")
    ap.add_argument("--merge-distance", type=float, default=0.8,
                    help="wyckoff only: merge a site's symmetry images closer than this many angstrom")
    ap.add_argument("--per-target", type=int, default=8)
    ap.add_argument("--steps", type=int, default=None,
                    help="gradient steps that move the latent until the property decoder reads the target back. "
                         "Default 300 for the free path, 0 for the symmetry path: measured on MP-20, those steps make "
                         "the property decoder SAY the right number while pushing the structure decoder into zero-gap "
                         "metals (semiconductor share 20% with them, 42-62% without), so the anchor alone is used.")
    ap.add_argument("--sigma", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="results", help="results folder; the run is written to OUT/TAG")
    a = ap.parse_args()
    # Defaults that depend on the geometry path.  Spelled out here so a reader of the log sees the recipe actually used.
    if a.steps is None:
        a.steps = 0 if a.geometry == "wyckoff" else 300
    if a.require_anion == ["auto"]:
        a.require_anion = [] if a.geometry == "wyckoff" else None       # [] = the standard anion list
    torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "4")))
    torch.manual_seed(a.seed)
    out = os.path.join(a.out, a.tag); os.makedirs(f"{out}/cifs", exist_ok=True)
    lm = load_checkpoint(a.ckpt, device="cpu")
    cols = list(lm.stats.columns)
    if a.gap is None:
        a.gap = next((c for c in cols if "gap" in c.lower()), cols[0])
        print(f"--gap not given: targeting '{a.gap}' (the checkpoint predicts {cols})", flush=True)
    if a.gap not in cols:
        raise SystemExit(f"the checkpoint predicts {cols}, not {a.gap}")
    if a.geometry == "wyckoff" and not a.max_atoms:
        a.max_atoms = lm.model.max_sites      # every candidate must be re-encodable, or it cannot carry a structure-read label
    if a.geometry == "wyckoff" and a.target_window is None:
        a.target_window = 0.5                 # this filter IS the target-following; without it windows are not applied
    if a.geometry == "wyckoff" and getattr(lm.model.crystal_decoder, "sym_trunk", None) is None:
        raise SystemExit(f"{a.ckpt} has no symmetry head: train with model.decoder_geometry: wyckoff, or use "
                         f"--geometry free")
    print(f"{a.tag}: conditional generation with no family, {a.geometry} geometry, from {a.ckpt}", flush=True)

    from meidnet.chem import ELEMENT_INDEX, ELEMENTS
    from meidnet.data import ANION_ELEMENTS
    anions = (list(ANION_ELEMENTS) if a.require_anion == [] else a.require_anion) if a.require_anion is not None else None
    mask = None
    if a.exclude_elements:
        mask = torch.ones(len(ELEMENTS), dtype=torch.bool)
        for e in a.exclude_elements:
            if e in ELEMENT_INDEX:
                mask[ELEMENT_INDEX[e]] = False
    print(f"  chemistry: anion required from {anions or 'nothing'}; excluded {a.exclude_elements}; "
          f"cell capped at {a.max_atoms or 'nothing'}", flush=True)

    t0 = time.time()
    rows, rejected = generate_pool(lm, a.gap, a.targets, per_target=a.per_target, oversample=a.oversample, sigma=a.sigma,
                                   seed=a.seed, steps=a.steps, geometry=a.geometry, atoms=a.atoms, merge_distance=a.merge_distance,
                                   species_mask=mask, anions=anions, min_orbits=a.min_orbits, max_atoms=a.max_atoms,
                                   label_source=a.label_source, target_window=a.target_window, cifs_dir=f"{out}/cifs", tag=a.tag)

    with open(f"{out}/candidates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["tag"]); w.writeheader(); w.writerows(rows)
    json.dump(dict(tag=a.tag, ckpt=a.ckpt, targets=a.targets, atoms=a.atoms, kept=len(rows), rejected=rejected,
                   seconds=round(time.time() - t0, 1),
                   geometry=a.geometry, label_source=a.label_source, target_window=a.target_window,
                   note=("the cell size is an input, not a prediction: padding slots were masked out of the training "
                         "loss, so the free decoder cannot signal how many sites a structure has")
                   if a.geometry == "free" else
                   ("the cell size is predicted: the occupancy head gives the number of symmetry-distinct sites and the "
                    "space group's operations generate the rest")),
              open(f"{out}/run_info.json", "w"), indent=1)
    print(f"\n{len(rows)} structures -> {out}; rejected as implausible: {rejected}")
    if rows:
        import collections
        print("formulas per target:")
        for t in a.targets:
            fs = [r["formula"] for r in rows if r["target"] == t]
            print(f"  {t:g} eV: {', '.join(list(dict.fromkeys(fs))[:8])}")
        print(f"distinct formulas overall: {len({r['formula'] for r in rows})} of {len(rows)}")


if __name__ == "__main__":
    main()
