"""D1, the symmetry geometry path: targets in, loss, and predictions out as real crystals.

The free-coordinate decoder has to place every atom independently and cannot: on MP-20 the cells it emits have a median
volume per atom of 0.0 A^3 and 81% contain atoms closer than 0.7 A.  A conventional cell holds a median of 16 atoms but
only a median of 4 sites that symmetry does not relate, so this path predicts the space group and those few sites and
lets the symmetry operations generate the rest.

Two things this module is careful about:
* **Symmetry does not by itself prevent atoms colliding.**  It guarantees crystallographic consistency; a badly placed
  representative site is then faithfully replicated into several badly placed atoms.  So `min_distance_penalty` is part
  of the loss, not an afterthought.
* **No prototype is predicted as a class.**  Space group, species and free coordinates are separate predictions, so a
  combination that never occurred in training can still come out.  Classifying into known prototypes would guarantee
  valid cells while making novel structure types impossible.
"""
from __future__ import annotations

import gzip
import json
import math
import os

import numpy as np
import torch
import torch.nn.functional as F

from meidnet.chem import ELEMENT_INDEX, ELEMENTS

MAX_ORBITS = 16
N_SPACEGROUPS = 230


def load_targets(intake: str, split: str) -> dict:
    """The side-car targets written by eval/wyckoff_targets.py, keeping only the rows that rebuild correctly."""
    path = f"{intake}/wyckoff_{split}.json.gz"
    if not os.path.exists(path):
        raise SystemExit(f"{path} is missing: run  python -m meidnet_eval.wyckoff_targets {intake}  first "
                         "(meidnet train does this itself when the intake folder is writable)")
    with gzip.open(path, "rt") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if v.get("roundtrip")}


def encode_targets(targets: dict, ids: list[str], max_orbits: int = MAX_ORBITS):
    """Pack the targets of a batch into tensors; `mask` marks the rows that have a usable target at all."""
    n = len(ids)
    sg = torch.zeros(n, dtype=torch.long)
    occ = torch.zeros(n, max_orbits)
    spc = torch.zeros(n, max_orbits, dtype=torch.long)
    crd = torch.zeros(n, max_orbits, 3)
    lat = torch.zeros(n, 6)
    mask = torch.zeros(n, dtype=torch.bool)
    for i, mid in enumerate(ids):
        t = targets.get(str(mid))
        if t is None:
            continue
        k = min(len(t["species"]), max_orbits)
        sg[i] = int(t["spacegroup"]) - 1                       # space groups are 1..230, classes are 0..229
        occ[i, :k] = 1.0
        for j in range(k):
            spc[i, j] = ELEMENT_INDEX.get(t["species"][j], 0)
            crd[i, j] = torch.tensor(t["coords"][j], dtype=torch.float32)
        a, b, c, al, be, ga = t["lattice"]
        lat[i] = torch.tensor([a / 20.0, b / 20.0, c / 20.0, al / 180.0, be / 180.0, ga / 180.0])
        mask[i] = True
    return dict(sg=sg, occ=occ, spc=spc, crd=crd, lat=lat, mask=mask)


def min_distance_penalty(coords: torch.Tensor, occ: torch.Tensor, lat: torch.Tensor, floor: float = 0.08):
    """Penalise representative sites that sit on top of each other, in fractional space.

    Symmetry replicates whatever it is given, so two representative sites placed at nearly the same point become many
    overlapping atoms.  A fractional floor is used rather than an Angstrom one because the lattice is being predicted at
    the same time; `floor` of 0.08 at a typical 8 A cell is about 0.6 A.
    """
    B, K, _ = coords.shape
    d = coords.unsqueeze(2) - coords.unsqueeze(1)              # (B, K, K, 3)
    d = d - d.round()                                          # periodic: nearest image in fractional coordinates
    dist = d.norm(dim=-1) + torch.eye(K, device=coords.device).unsqueeze(0) * 9.0
    pair = (occ.unsqueeze(2) * occ.unsqueeze(1))
    viol = F.relu(floor - dist) * pair
    return viol.sum() / pair.sum().clamp_min(1.0)


def symmetry_loss(pred, tgt, w_sg=1.0, w_occ=1.0, w_spc=1.0, w_crd=10.0, w_lat=10.0, w_dist=5.0,
                  bin_logits=None, w_bin=2.0):
    """Cross-entropy on the space group and the species, BCE on occupancy, MSE on coordinates and lattice, plus the
    minimum-distance penalty.  Species and coordinates are scored only where an orbit is really occupied."""
    sg_logits, occ_logits, spc_logits, crd, lat = pred
    m = tgt["mask"]
    if not bool(m.any()):
        return torch.zeros((), device=sg_logits.device), {}
    sg_logits, occ_logits, spc_logits, crd, lat = (x[m] for x in (sg_logits, occ_logits, spc_logits, crd, lat))
    t_sg, t_occ, t_spc, t_crd, t_lat = (tgt[k][m] for k in ("sg", "occ", "spc", "crd", "lat"))
    occupied = t_occ > 0.5
    parts = {"sg": F.cross_entropy(sg_logits, t_sg),
             "occ": F.binary_cross_entropy_with_logits(occ_logits, t_occ),
             "lat": F.mse_loss(lat, t_lat)}
    if bool(occupied.any()):
        parts["spc"] = F.cross_entropy(spc_logits[occupied], t_spc[occupied])
        diff = crd[occupied] - t_crd[occupied]
        parts["crd"] = (diff - diff.round()).pow(2).mean()     # periodic: 0.99 and 0.01 are close
    else:
        parts["spc"] = torch.zeros((), device=crd.device); parts["crd"] = torch.zeros((), device=crd.device)
    parts["dist"] = min_distance_penalty(crd, t_occ, lat)
    total = (w_sg * parts["sg"] + w_occ * parts["occ"] + w_spc * parts["spc"] + w_crd * parts["crd"]
             + w_lat * parts["lat"] + w_dist * parts["dist"])
    if bin_logits is not None:
        # Cross-entropy over the discrete grid.  The regression term above is kept as well: it supplies a smooth signal
        # through the shared trunk, while this term is the one that can actually land on a special position.
        bl = bin_logits[m]
        nb = bl.shape[-1]
        tb = ((t_crd * nb).round().long()) % nb
        if bool(occupied.any()):
            parts["crd_bin"] = F.cross_entropy(bl[occupied].reshape(-1, nb), tb[occupied].reshape(-1))
        else:
            parts["crd_bin"] = torch.zeros((), device=crd.device)
        total = total + w_bin * parts["crd_bin"]
    return total, {k: float(v.detach()) for k, v in parts.items()}


def lattice_for_spacegroup(sg: int, abc, angles):
    """Force a predicted lattice to be consistent with a predicted space group.

    The head predicts the space group and six lattice parameters separately, and six free numbers will essentially never
    satisfy a constraint like Fm-3m's a=b=c -- pymatgen then refuses the build outright.  The crystal system says which
    parameters are actually free; the others are *derived* from the prediction (lengths that must be equal are averaged,
    fixed angles are set) rather than invented.  Nothing about which structures are reachable changes: every space group,
    every cell size and every coordinate is still available.
    """
    a, b, c = (float(x) for x in abc)
    al, be, ga = (float(x) for x in angles)
    if sg >= 195:                                            # cubic
        a = b = c = (a + b + c) / 3.0; al = be = ga = 90.0
    elif sg >= 168:                                          # hexagonal
        a = b = (a + b) / 2.0; al = be = 90.0; ga = 120.0
    elif sg >= 143:                                          # trigonal, incl. the R groups: pymatgen expects the
        a = b = (a + b) / 2.0; al = be = 90.0; ga = 120.0    # hexagonal setting, not the rhombohedral one (probed)
    elif sg >= 75:                                           # tetragonal
        a = b = (a + b) / 2.0; al = be = ga = 90.0
    elif sg >= 16:                                           # orthorhombic
        al = be = ga = 90.0
    elif sg >= 3:                                            # monoclinic, b unique
        al = ga = 90.0
    return a, b, c, al, be, ga


_SPACEGROUPS: dict = {}


def expand_orbits(sg: int, lattice, species, coords, merge_distance: float = 0.8):
    """Build the full cell from the representative sites, merging each site's near-coincident symmetry images.

    A representative site sitting a little off its special position has symmetry images a short distance away, and
    `Structure.from_spacegroup` keeps every one of them as a separate atom -- which is why a 0.01 fractional coordinate
    error inflated a 16-atom cell to 42 atoms.  Merging images closer together than `merge_distance` angstrom repairs
    it.  Measured on real MP-20 cells with noise added to their coordinates, the correct atom count is recovered for
    100% of structures at 0.01 fractional error and 91% at 0.02, against 4% with no merging.  The per-component
    fractional tolerance that `from_spacegroup` offers peaks at 14% however it is set, because it scales wrongly with
    cell size and anisotropy; a distance in angstrom is the physically meaningful criterion, since no two distinct atoms
    sit 0.8 A apart.

    Each orbit is expanded on its own so that only images of the *same* site can ever merge: pymatgen's `merge_sites`
    clusters by distance regardless of species, and a global merge would quietly fuse two different elements and change
    the composition.  Two *different* sites landing on top of each other therefore stays visible, which is what the
    overlap check exists to catch.
    """
    from pymatgen.core import Structure
    from pymatgen.symmetry.groups import SpaceGroup
    if sg not in _SPACEGROUPS:
        _SPACEGROUPS[sg] = SpaceGroup.from_int_number(sg)
    g = _SPACEGROUPS[sg]
    sp_out, fc_out = [], []
    for sp, c in zip(species, coords):
        orbit = g.get_orbit(np.asarray(c, dtype=float) % 1.0, tol=1e-5)
        sub = Structure(lattice, [sp] * len(orbit), orbit)
        if merge_distance > 0 and len(sub) > 1:
            sub.merge_sites(tol=merge_distance, mode="average")
        sp_out += [site.specie for site in sub]
        fc_out += [site.frac_coords for site in sub]
    return Structure(lattice, sp_out, fc_out)


def _coords_for(keep, crd, bin_logits):
    """Fractional coordinates for the kept orbits: grid points when the discrete head is present, otherwise regressed."""
    if bin_logits is not None:
        nb = bin_logits.shape[-1]                 # grid point i/nb, so special-position fractions come out exactly
        return [(bin_logits[i].argmax(-1).detach().cpu().numpy() / float(nb)).tolist() for i in keep]
    return [(crd[i].detach().cpu().numpy() % 1.0).tolist() for i in keep]


def build_structure(sg_logits, occ_logits, spc_logits, crd, lat, species_mask=None, min_orbits=1,
                    merge_distance=0.8, bin_logits=None, max_atoms=0, require_elements=None):
    """One set of predictions -> a pymatgen Structure, with the symmetry operations generating the equivalent sites."""
    from pymatgen.core import Lattice
    sg = int(sg_logits.argmax().item()) + 1
    p = lat.detach().cpu().numpy()
    a, b, c = np.clip(p[:3], 0.15, 1.5) * 20.0
    al, be, ga = np.clip(p[3:], 0.15, 0.9) * 180.0
    a, b, c, al, be, ga = lattice_for_spacegroup(sg, (a, b, c), (al, be, ga))
    keep = (torch.sigmoid(occ_logits) > 0.5).nonzero(as_tuple=True)[0].tolist()
    if len(keep) < min_orbits:
        keep = torch.sigmoid(occ_logits).topk(min_orbits).indices.tolist()
    logits = spc_logits.clone()
    if species_mask is not None:
        logits = logits.masked_fill(~species_mask.to(torch.bool).unsqueeze(0), torch.finfo(logits.dtype).min)
    species = [ELEMENTS[int(logits[i].argmax().item())] for i in keep]
    coords = _coords_for(keep, crd, bin_logits)
    lattice = Lattice.from_parameters(float(a), float(b), float(c), float(al), float(be), float(ga))
    st = expand_orbits(sg, lattice, species, coords, merge_distance)
    # A high-symmetry space group times several occupied orbits can expand past anything the encoder will read back, and
    # a candidate the pipeline cannot re-encode cannot carry a label read from its own structure -- it would have to be reported on the
    # strength of the search latent alone, which is the circular labelling this project already rejected.  So the least
    # confident orbit is dropped until the cell fits, and the cell size stays a prediction rather than becoming a claim
    # that cannot be checked.
    if max_atoms and len(st) > max_atoms:
        conf = torch.sigmoid(occ_logits)
        order = sorted(keep, key=lambda i: float(conf[i]))        # least confident first
        while len(order) > min_orbits and len(st) > max_atoms:
            order.pop(0)
            kept = [i for i in keep if i in order]
            sub_species = [species[keep.index(i)] for i in kept]
            sub_coords = [coords[keep.index(i)] for i in kept]
            st = expand_orbits(sg, lattice, sub_species, sub_coords, merge_distance)
        keep = [i for i in keep if i in order]
        species = [ELEMENTS[int(logits[i].argmax().item())] for i in keep]
        coords = _coords_for(keep, crd, bin_logits)
    # MP-20 is 68% zero-gap metals, so the species head's most likely answer is an intermetallic whatever property was
    # asked for -- the latent search constrains the property decoder, never this head.  Requiring at least one anion
    # makes the result a compound, which is a precondition for having a band gap at all.  The orbit already most
    # inclined towards one of these elements is the one converted, so the decoder's own preference picks the site.
    # Applied AFTER the cell cap: the cap drops the least confident orbit, and a forced site is by construction not a
    # confident one, so doing this first had the cap delete the very anion it had just added.
    if require_elements and not (set(species) & set(require_elements)):
        want = [e for e in require_elements if e in ELEMENT_INDEX]
        if want:
            cols = [ELEMENT_INDEX[e] for e in want]
            sub = logits[:, cols]
            j = int(max(range(len(keep)), key=lambda q: float(sub[keep[q]].max())))
            species[j] = want[int(sub[keep[j]].argmax())]
            st = expand_orbits(sg, lattice, species, coords, merge_distance)
    return st, sg, len(keep)
