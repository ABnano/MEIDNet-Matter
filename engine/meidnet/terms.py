"""
Search terms: soft penalties on the decoder's outputs used while optimising latents.

They *steer* the latent search towards decodable, chemically sensible regions;
whether a candidate is finally accepted is decided by the hard constraints in
``meidnet.constraints``.  Each term is registered under the name used in family
files, receives a ``SearchContext`` and returns one penalty per latent.

The formulas (and the order in which a family lists them) reproduce MEIDNet v1
operation by operation, so the published search behaves identically.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
import torch
import torch.nn.functional as F

from meidnet.chem import ELEMENTS, NUM_SPECIES, element_index, ionic_radius
from meidnet.registry import Registry

SEARCH_TERMS = Registry("search term")
LOGIT_TRANSFORMS = Registry("logit transform")


@dataclass
class SearchContext:
    family: object
    alpha: float                 # progress through the round, 0 → 1
    temp: float                  # current softmax temperature
    spc_logits: torch.Tensor     # (pop, max_sites, 118) after logit transforms
    xyz: torch.Tensor            # sigmoid of decoded coordinates (pop, max_sites, 3)
    lat: torch.Tensor            # sigmoid of decoded lattice (pop, 6)
    occ: torch.Tensor            # most likely element probability per slot (pop, max_sites)
    device: torch.device

    def cell_lengths(self):
        ref = float(self.family.lattice.get("reference_a", 3.87))
        lat = torch.nan_to_num(self.lat)
        return tuple(lat[:, i] * ref * 0.4 + ref * 0.8 for i in range(3))


def softmax_temp(logits, temp):
    return F.softmax(logits / max(temp, 1e-6), dim=-1)


def _idx(elements) -> list[int]:
    return [element_index(e) for e in elements]


def _mean_charge_vector(group, states: dict[str, list[int]], device) -> torch.Tensor:
    vec = torch.zeros(NUM_SPECIES, device=device)
    for el in group.elements:
        qs = states.get(el)
        if qs:
            vec[element_index(el)] = float(np.mean(list(qs)))
    return vec


def _pairwise(coords):
    B, N, _ = coords.shape
    d = torch.norm(coords.unsqueeze(2) - coords.unsqueeze(1), dim=-1)
    return d, B, N


# ───────────────────────── geometry terms ─────────────────────────
@SEARCH_TERMS.register("site_separation", "Keeps decoded atoms from collapsing onto each other (1/distance).")
def site_separation(ctx: SearchContext, weight=200):
    d, B, N = _pairwise(ctx.xyz)
    d = d + torch.eye(N, device=ctx.device).unsqueeze(0)
    return weight * (1.0 / (d + 1e-6)).sum(dim=(1, 2))


@SEARCH_TERMS.register("site_repulsion", "Short-range exponential repulsion between decoded atoms.")
def site_repulsion(ctx: SearchContext, weight=8000):
    d, B, N = _pairwise(ctx.xyz)
    d = d + torch.eye(N, device=ctx.device).unsqueeze(0)
    return weight * torch.exp(-d).sum(dim=(1, 2))


@SEARCH_TERMS.register("cubic_cell", "Pulls the decoded cell towards a cube of the family's reference volume.")
def cubic_cell(ctx: SearchContext, volume_weight=1000, cubicity_weight=10000):
    a, b, c = ctx.cell_lengths()
    ref = float(ctx.family.lattice.get("reference_a", 3.87))
    vol_ref = ref ** 3
    vol_term = ((a * b * c - vol_ref) / vol_ref).pow(2)
    cub_term = (a - b).abs() + (b - c).abs()
    return volume_weight * vol_term + cubicity_weight * cub_term


@SEARCH_TERMS.register("prototype_alignment", "Pulls decoded positions onto the prototype's site positions.")
def prototype_alignment(ctx: SearchContext, weight=800):
    n = ctx.family.n_sites
    tpl = torch.tensor(ctx.family.frac_coords, dtype=torch.float32, device=ctx.device)
    d2 = torch.cdist(ctx.xyz[:, :n, :], tpl.expand(ctx.xyz.size(0), -1, -1)) ** 2
    m, _ = d2.min(-1)
    return weight * (ctx.occ[:, :n] * m).sum(dim=1)


@SEARCH_TERMS.register("short_distance_penalty", "Large penalty if any two decoded atoms come closer than `min`.")
def short_distance_penalty(ctx: SearchContext, min=0.8):  # noqa: A002  (name used in YAML)
    d, B, N = _pairwise(ctx.xyz)
    if N < 2:
        return torch.zeros(B, device=ctx.device)
    d = d + torch.eye(N, device=ctx.device).unsqueeze(0) * 99
    dmin = d.min(dim=2).values.min(dim=1).values
    return torch.where(dmin < min, 1e5 * (min - dmin) ** 2, torch.zeros_like(dmin))


# ───────────────────────── chemistry terms ─────────────────────────
def tolerance_window(family) -> tuple[float, float]:
    c = family.constraint_params("tolerance_factor") or {}
    return float(c.get("min", 0.78)), float(c.get("max", 1.05))


@SEARCH_TERMS.register("tolerance_penalty", "Soft version of the Goldschmidt tolerance-factor window, using the most likely elements.")
def tolerance_penalty(ctx: SearchContext, weight=1000, A="A", B="B", X="X"):
    fam = ctx.family
    top = ctx.spc_logits.argmax(dim=-1)
    radii = []
    for spec in (A, B, X):  # a list of groups averages their radii (double perovskites: B: [B1, B2])
        names = spec if isinstance(spec, (list, tuple)) else [spec]
        per = []
        for g in names:
            slot = fam.groups[g].slots[0]
            per.append(torch.tensor([ionic_radius(ELEMENTS[i]) for i in top[:, slot].tolist()], device=ctx.device))
        radii.append(torch.stack(per).mean(dim=0))
    rA, rB, rX = radii
    t = (rA + rX) / (math.sqrt(2) * (rB + rX))
    lo, hi = tolerance_window(fam)
    tmin = torch.tensor([lo] * len(t), device=ctx.device)
    tmax = torch.tensor([hi] * len(t), device=ctx.device)
    pen = torch.where(t < tmin, (t - tmin) ** 2, torch.where(t > tmax, (t - tmax) ** 2, torch.zeros_like(t)))
    return weight * pen


@SEARCH_TERMS.register("soft_charge", "Expected total charge of the most likely composition should be zero (ramps up during a round).")
def soft_charge(ctx: SearchContext, weight=3000, override_oxidation_states=None):
    fam = ctx.family
    w = weight * (0.2 + 0.8 * ctx.alpha) ** 2
    P = softmax_temp(torch.nan_to_num(ctx.spc_logits), ctx.temp)
    vec = {}
    for g in fam.groups.values():
        states = dict(g.oxidation_states_all)
        if override_oxidation_states and g.name in override_oxidation_states:
            states = {el: list(override_oxidation_states[g.name]) for el in g.elements}
        vec[g.name] = _mean_charge_vector(g, states, ctx.device)
    total = None
    for slot, (gname, _) in enumerate(fam.sites):
        q = (P[:, slot, :] * vec[gname]).sum(dim=1)
        total = q if total is None else total + q
    return w * total.pow(2)


@SEARCH_TERMS.register("group_consistency", "Sites of the same group should agree on their element (ramps up during a round).")
def group_consistency(ctx: SearchContext, weight=1500):
    fam = ctx.family
    w = weight * (0.5 + 0.5 * ctx.alpha)
    P = softmax_temp(torch.nan_to_num(ctx.spc_logits), ctx.temp)
    out = None
    for g in fam.groups.values():
        if len(g.slots) < 2:
            continue
        Psub = P[:, g.slots, :][:, :, _idx(g.elements)]
        Pm = Psub.mean(dim=1, keepdim=True)
        term = w * ((Psub - Pm) ** 2).sum(dim=(1, 2))
        out = term if out is None else out + term
    return out if out is not None else torch.zeros(P.size(0), device=ctx.device)


@SEARCH_TERMS.register("entropy_bonus", "Rewards uncertainty early in a round so the search explores (fades to zero).")
def entropy_bonus(ctx: SearchContext, weight=0.06):
    fam = ctx.family
    w = weight * (1.0 - ctx.alpha)
    if w <= 0:
        return torch.zeros(ctx.spc_logits.size(0), device=ctx.device)
    P = softmax_temp(ctx.spc_logits, ctx.temp)

    def H(slot, idx):
        p = P[:, slot, idx]
        return -(p * p.clamp_min(1e-8).log()).sum(dim=1)

    total = None
    multi = []
    for g in sorted(fam.groups.values(), key=lambda g: g.slots[0]):
        idx = _idx(g.elements)
        if len(g.slots) == 1:
            h = H(g.slots[0], idx)
            total = h if total is None else total + h
        else:
            multi.append((g, idx))
    for g, idx in multi:
        hx = 0
        for s in g.slots:
            hx += H(s, idx)
        total = hx / float(len(g.slots)) if total is None else total + hx / float(len(g.slots))
    return -w * total


# ───────────────────────── logit transforms ─────────────────────────
@LOGIT_TRANSFORMS.register("neutrality_bias", "Raises the scores of anions whose charge can neutralise the most likely cations.")
def neutrality_bias(spc_logits, family, group="X", bias=8.0, topk=5):
    if bias <= 0:
        return spc_logits
    L = spc_logits.clone()
    target = family.groups[group]
    others = [g for g in sorted(family.groups.values(), key=lambda g: g.slots[0]) if g.name != group]
    accept = {q for el in target.universe for q in target.oxidation_states_all.get(el, [])}
    first_q: dict[int, list[int]] = {}
    for el in target.elements:
        qs = target.oxidation_states_all.get(el)
        if qs:
            first_q.setdefault(int(qs[0]), []).append(element_index(el))
    n_target = float(len(target.slots))
    for b in range(L.size(0)):
        P = F.softmax(L[b], dim=-1)
        cands = []
        for g in others:
            idx = _idx(g.elements)
            for s in g.slots:
                top = torch.topk(P[s, idx], k=min(topk, len(idx))).indices.tolist()
                cands.append((g, [g.elements[i] for i in top]))
        ok = set()

        def walk(i, charge):
            if i == len(cands):
                q = -charge / n_target
                if q in accept:
                    ok.add(int(q))
                return
            g, els = cands[i]
            for el in els:
                for qq in g.oxidation_states_all.get(el, []):
                    walk(i + 1, charge + qq)

        walk(0, 0)
        if not ok:
            continue
        for s in target.slots:
            for q, idxs in first_q.items():
                delta = bias if q in ok else -0.5 * bias
                L[b, s, idxs] = L[b, s, idxs] + delta
    return L


TermFn = Callable[..., torch.Tensor]


def build_terms(family) -> list[tuple[str, TermFn, dict]]:
    out = []
    for spec in family.search_terms:
        params = {k: v for k, v in spec.items() if k != "name"}
        out.append((spec["name"], SEARCH_TERMS.get(spec["name"]), params))
    return out


def build_transforms(family) -> list[tuple[str, Callable, dict]]:
    out = []
    for spec in family.logit_transforms:
        params = {k: v for k, v in spec.items() if k != "name"}
        out.append((spec["name"], LOGIT_TRANSFORMS.get(spec["name"]), params))
    return out
