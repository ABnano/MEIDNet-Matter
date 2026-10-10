"""
Inverse design: from target properties to candidate crystals.

For every target (e.g. band gap 1.5 eV and formation enthalpy -0.1 eV/atom):

  round 1..R
    1. start a population of latents near the latent of the target properties
       (property encoder) plus a target-dependent random direction and noise;
    2. optimise them by gradient descent: predicted properties → targets,
       family search terms → decodable, chemically sensible outputs,
       diversity/history → spread out and avoid repeats;
    3. decode each latent: choose one element per site group from the decoder's
       scores (the last group only from charge-balancing elements), place them on
       the family prototype, and run the hard constraints;
    4. rank passing candidates by distance to the target and save new, unique ones.

Every attempt is logged, so the report can show where candidates are lost (the
"funnel") and why each saved candidate was accepted.  With the published
Perov-5 configuration this reproduces MEIDNet v1, with one change: element
iteration order is fixed, so results no longer depend on Python's hash seed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from pymatgen.io.cif import CifWriter

from meidnet.chem import ELEMENTS, NUM_SPECIES, element_index, ionic_radius
from meidnet.constraints import build_candidate, evaluate
from meidnet.data import featurize, fit_to_max_sites
from meidnet.terms import SearchContext, build_terms, build_transforms, softmax_temp


# ───────────────────────── small helpers (v1-identical) ─────────────────────────
def seed_from_target(base_seed: int, values) -> int:
    key = f"{base_seed}|" + "|".join(f"{v:.6f}" for v in values)
    h = hashlib.sha1(key.encode()).hexdigest()
    return int((base_seed ^ int(h[:8], 16)) % (2 ** 31 - 1))


def rff_target_offset(values, dim, nfreq=48, seed=0):
    rng = np.random.RandomState(seed)
    W = rng.normal(loc=0.0, scale=2.0, size=(len(values), nfreq))
    b = rng.uniform(0, 2 * np.pi, size=(nfreq,))
    x = np.array(values)[:, None]
    proj = (W.T @ x).reshape(-1) + b
    phi = np.concatenate([np.sin(proj), np.cos(proj)], axis=0)
    M = rng.normal(0, 1.0 / np.sqrt(2 * nfreq), size=(2 * nfreq, dim))
    return F.normalize(torch.tensor(phi @ M, dtype=torch.float32), dim=0)


def diversity_repulsion(Z, tau=0.25):
    Zn = F.normalize(Z, dim=1)
    S = Zn @ Zn.T
    S = S.masked_fill(torch.eye(Z.size(0), device=Z.device).bool(), -9.0)
    return torch.exp(S / max(tau, 1e-6)).mean()


def history_repulsion(Z, histZ, tau=0.25):
    if histZ is None or histZ.numel() == 0:
        return torch.tensor(0.0, device=Z.device)
    S = F.normalize(Z, dim=1) @ F.normalize(histZ, dim=1).T
    return torch.exp(S / max(tau, 1e-6)).mean()


def objective_loss(pred, target: float, kind: str, device):
    if kind == "l2":
        return F.mse_loss(pred, torch.tensor([[target]], device=device).expand_as(pred), reduction="none").mean(dim=1)
    if kind == "l1":
        return (pred - target).abs().mean(dim=1)
    if kind == "at_most":
        return F.relu(pred - target).mean(dim=1)
    if kind == "at_least":
        return F.relu(target - pred).mean(dim=1)
    raise ValueError(kind)


def objective_distance(pred: float, target: float, kind: str) -> float:
    if kind == "l2":
        return (pred - target) ** 2
    if kind == "l1":
        return abs(pred - target)
    if kind == "at_most":
        return max(0.0, pred - target)
    return max(0.0, target - pred)


def struct_signature(s, decimals=3) -> str:
    comp = "-".join(f"{el}{int(amt)}" for el, amt in sorted(s.composition.as_dict().items()))
    a, b, c = (round(x, decimals) for x in s.lattice.abc)
    fracs = sorted((sp.symbol, tuple(round(x, decimals) for x in f)) for sp, f in zip(s.species, s.frac_coords))
    return hashlib.sha1(f"{comp}|{a},{b},{c}|{fracs}".encode()).hexdigest()


# ───────────────────────── results ─────────────────────────
@dataclass
class SavedCandidate:
    target_index: int
    round: int
    file: str
    elements: dict
    formula: str
    lattice_a: float
    predictions: dict
    constraint_results: list
    score: float
    latent_norm: float
    flags: list = field(default_factory=list)

    def to_dict(self):
        return dict(self.__dict__)


@dataclass
class TargetLog:
    index: int
    values: dict
    rounds_used: int = 0
    attempts: int = 0
    latents_decoded: int = 0
    latents_passing: int = 0
    first_failure: Counter = field(default_factory=Counter)
    failures_any: Counter = field(default_factory=Counter)
    skipped_duplicate: int = 0
    skipped_similar: int = 0
    saved: list = field(default_factory=list)
    rejected_examples: list = field(default_factory=list)
    latent_start: list = field(default_factory=list)
    latent_final: list = field(default_factory=list)


@dataclass
class GenerationResult:
    out_dir: str
    targets: list[TargetLog]
    property_ranges: dict
    family: str
    variant: str | None
    settings: dict

    @property
    def saved(self) -> list[SavedCandidate]:
        return [c for t in self.targets for c in t.saved]


# ───────────────────────── the engine ─────────────────────────
class Designer:
    def __init__(self, loaded, family, gcfg, device=None, log=print, on_saved=None, on_step=None, should_stop=None,
                 reference_latents=None):
        """
        on_saved(candidate, target_log)  – called whenever a candidate is written (live views)
        on_step(step, steps, loss)       – called every 10 optimisation steps
        should_stop()                    – checked every 10 optimisation steps and between rounds;
                                           True ends the run early (candidates saved so far are kept)
        reference_latents                – structure latents of the training materials (grounded search with
                                           manifold_weight > 0)
        """
        self.lm = loaded
        self.model = loaded.model
        self.stats = loaded.stats
        self.family = family
        self.g = gcfg
        self.device = device or loaded.device
        self.log = log
        self.on_saved, self.on_step, self.should_stop = on_saved, on_step, should_stop
        self.objectives = []
        for o in gcfg.objectives:
            j = self.stats.index(o.property)
            self.objectives.append(dict(property=o.property, j=j, loss=o.loss, weight=o.weight,
                                        select_weight=o.select_weight, select_loss=o.select_loss or o.loss))
        for c in family.constraints:   # a window on a property the model does not predict would never reject
            if c["name"] == "property_window" and c.get("property") not in self.stats.columns:
                raise ValueError(f"property_window on '{c.get('property')}': this model predicts "
                                 f"{', '.join(self.stats.columns)}")
        self.terms = build_terms(family)
        self.transforms = build_transforms(family)
        self.mask = self._species_mask()
        ms = self.model.max_sites
        if family.n_sites > ms:
            raise ValueError(f"family has {family.n_sites} sites but the model handles at most {ms}")
        self.ar_group = gcfg.anti_repeat_group or family.sampling_order[0]
        coords = torch.zeros(ms, 3)
        if loaded.decoder_coordinate_input == "prototype":
            coords[:family.n_sites] = torch.tensor(family.frac_coords, dtype=torch.float32)
        self.decoder_coords = coords
        self.reference = None
        if reference_latents is not None and len(reference_latents):
            self.reference = F.normalize(torch.as_tensor(np.asarray(reference_latents), dtype=torch.float32), dim=1).to(self.device)
        self._struct_cache = {}
        # entries without a '|' are reduced formulas: a composition-level novelty rule that does not depend
        # on the family's group layout (a site key silently matches nothing when the layout differs)
        self._lat_cache = {}
        self._excluded = set(gcfg.exclude_compositions)
        # an entry without a '|' is a reduced formula: novelty judged on the COMPOSITION, which does not depend on the
        # family's group layout.  A site key assumes that layout, so an ABX3-shaped key matches nothing for an A2BB'X6
        # family and the rule then silently excludes nothing.
        self._excluded_formulas = {str(e) for e in self._excluded if "|" not in str(e)}

    # ── setup ────────────────────────────────────────────────────────────────
    def _species_mask(self):
        m = torch.zeros(self.model.max_sites, NUM_SPECIES, dtype=torch.bool)
        for grp in self.family.groups.values():
            for s in grp.slots:
                for el in grp.elements:
                    m[s, element_index(el)] = True
        return m

    def _norm_target(self, prop: str, value: float) -> float:
        j = self.stats.index(prop)
        return (value - self.stats.mean[j]) / self.stats.std[j]

    def _anchor_vector(self, target: dict) -> list[float]:
        vec = [0.0] * len(self.stats.columns)
        for o in self.objectives:
            value = self.g.query_values.get(o["property"], target[o["property"]])   # realistic value for bound-only goals
            vec[o["j"]] = float(self._norm_target(o["property"], value))
        return vec

    def _decoder_in(self, n):
        return (self.decoder_coords.to(self.device).unsqueeze(0).expand(n, -1, -1).contiguous()
                if self.lm.decoder_coordinate_input == "prototype"
                else torch.zeros(n, self.model.max_sites, 3, device=self.device)), torch.zeros(n, 3, device=self.device)

    def _physical(self, prop_norm: torch.Tensor) -> np.ndarray:
        return self.stats.denormalize_tensor(prop_norm).detach().cpu().numpy()

    # ── latent initialisation ────────────────────────────────────────────────
    def _randn(self, like: torch.Tensor) -> torch.Tensor:
        """Normal noise from this run's own generator: the same numbers as torch.manual_seed + randn_like,
        but untouched by other searches or trainings running in the same process (MEIDNet Studio)."""
        return torch.randn(like.shape, generator=self._gen, device=like.device, dtype=like.dtype)

    def make_population(self, pop, target, tvals, seed):
        g = self.g
        self._gen = torch.Generator(device=self.device).manual_seed(seed)
        dim = self.model.proj_crystal[-1].out_features
        x = torch.tensor([self._anchor_vector(target)], device=self.device, dtype=torch.float32)
        zs = []
        for i in range(pop):
            with torch.no_grad():
                z_seeded = self.model.encode_properties(x)
                rff_seed = seed_from_target(seed + i, tvals) % (2 ** 16)
                rff = rff_target_offset(tvals, dim, nfreq=g.rff_frequencies, seed=rff_seed).to(self.device).unsqueeze(0)
                z_noise = self._randn(z_seeded)
                z = F.normalize(g.init_anchor_mix * z_seeded + g.init_rff_mix * rff + g.init_noise_mix * z_noise, dim=1)
                z.add_(g.init_sigma * self._randn(z))
                if g.latent_space == "sphere":
                    z = F.normalize(z, dim=1)
            zs.append(z)
        Z0 = torch.cat(zs, dim=0)
        return Z0, nn.Parameter(Z0.clone())

    def _stop_requested(self) -> bool:
        return bool(self.should_stop and self.should_stop())

    # ── latent optimisation ──────────────────────────────────────────────────
    def optimise(self, pop, target, tvals, seed, hist):
        g, dev, model = self.g, self.device, self.model
        use_amp = g.amp and dev.type == "cuda"
        amp_dtype = torch.bfloat16 if (use_amp and torch.cuda.is_bf16_supported()) else torch.float16
        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
        Z0, Z = self.make_population(pop, target, tvals, seed)
        opt = optim.Adam([Z], lr=g.learning_rate)
        with torch.no_grad():
            anchor = model.encode_properties(
                torch.tensor([self._anchor_vector(target)], device=dev, dtype=torch.float32))
        norm_t = {o["property"]: float(self._norm_target(o["property"], target[o["property"]])) for o in self.objectives}
        best = torch.full((pop,), float("inf"), device=dev)
        since = torch.zeros(pop, dtype=torch.long, device=dev)
        coords_in, center_in = self._decoder_in(pop)
        mask = self.mask.to(dev)
        for step in range(g.steps):
            if step and step % 10 == 0 and self._stop_requested():
                break
            alpha = step / max(1, g.steps - 1)
            temp = g.temperature_start * (g.temperature_end / max(g.temperature_start, 1e-6)) ** alpha
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", dtype=amp_dtype, enabled=use_amp):
                prop = model.property_decoder(Z)
                lat_out, _, spc_raw, coords_out = model.crystal_decoder(Z, input_coords=coords_in, center=center_in,
                                                                         species_mask=mask)
                spc = spc_raw
                for _, fn, params in self.transforms:
                    spc = fn(spc, self.family, **params)
                xyz = torch.sigmoid(coords_out)
                occ = softmax_temp(spc, temp).max(dim=-1).values
                L = torch.zeros(pop, device=dev)
                for o in self.objectives:
                    L += o["weight"] * objective_loss(prop[:, o["j"]:o["j"] + 1], norm_t[o["property"]], o["loss"], dev)
                cos = F.cosine_similarity(F.normalize(Z, dim=1), anchor.expand_as(Z), dim=1)
                L += g.anchor_weight * (1.0 - cos)
                if g.manifold_weight > 0 and self.reference is not None:
                    sim = F.normalize(Z, dim=1).float() @ self.reference.T            # cosine to every training structure
                    if g.manifold_topk > 0:     # mean cosine to the k nearest training structures (sharp)
                        near = sim.topk(min(g.manifold_topk, sim.size(1)), dim=1).values.mean(dim=1)
                    else:                       # softmax over all of them (weak: saturates on many medium neighbours)
                        near = g.manifold_tau * torch.logsumexp(sim / g.manifold_tau, dim=1)
                    L += g.manifold_weight * (1.0 - near)
                if (not g.property_first) and g.geometry_scale > 0.0:
                    ctx = SearchContext(self.family, alpha, temp, spc, xyz, torch.sigmoid(lat_out), occ, dev)
                    L_geo = torch.zeros_like(L)
                    for _, fn, params in self.terms:
                        L_geo += fn(ctx, **params)
                    L += g.geometry_scale * L_geo
                L_mean = L.mean()
                L_div = g.diversity_weight * diversity_repulsion(Z, tau=g.diversity_tau)
                L_hist = g.history_weight * history_repulsion(Z, hist, tau=g.history_tau) if hist is not None else 0.0
                loss = L_mean + L_div + L_hist
            scaler.scale(loss).backward()
            torch.nn.utils.clip_grad_norm_([Z], g.grad_clip)
            scaler.step(opt)
            scaler.update()
            if self.on_step and step % 10 == 0:
                self.on_step(step, g.steps, float(loss.detach()))
            with torch.no_grad():
                if g.latent_space == "sphere":   # structure latents are unit vectors: never leave the sphere
                    Z.data = F.normalize(Z.data, dim=1)
                else:
                    Z.data.clamp_(-g.z_clip, g.z_clip)
                improved = L < best - 1e-6
                best = torch.minimum(best, L)
                since = torch.where(improved, torch.zeros_like(since), since + 1)
                need = since >= g.restart_patience
                if need.any():
                    idx = need.nonzero(as_tuple=False).view(-1)
                    Z[idx] = F.normalize(Z[idx] + g.restart_noise * self._randn(Z[idx]), dim=1)
                    since[idx] = 0
        return Z0.detach(), Z.detach()

    def propose(self, pop, target, tvals, seed, hist, rnd=1):
        """The latents to decode in one round: gradient search (v1) or neighbour sampling (aim with the alignment)."""
        if self.g.search_mode == "neighbours":
            return self.neighbour_samples(pop, target, seed, rnd)
        return self.optimise(pop, target, tvals, seed, hist)

    @torch.no_grad()
    def neighbour_samples(self, pop, target, seed, rnd=1):
        """Encode the target properties, find the k nearest REAL structure latents (reference_latents) and sample `pop`
        random convex mixes of them, projected to the unit sphere — every proposal stays where the decoder is faithful.
        Later rounds widen the neighbourhood (k x round)."""
        if self.reference is None:
            raise ValueError("search_mode 'neighbours' needs reference_latents (the training structures' latents)")
        x = torch.tensor([self._anchor_vector(target)], device=self.device, dtype=torch.float32)
        zp = self.model.encode_properties(x)[0]
        cos = self.reference @ zp.float()
        k = min(self.g.neighbour_k * rnd, cos.numel())
        idx = cos.topk(k).indices
        w = np.random.RandomState(seed % (2 ** 32 - 1)).dirichlet(np.full(k, self.g.mix_concentration), size=pop)
        Z = torch.tensor(w, dtype=torch.float32, device=self.device) @ self.reference[idx]
        Z = F.normalize(Z, dim=1)
        return Z.clone(), Z

    # ── decoding ─────────────────────────────────────────────────────────────
    @torch.no_grad()
    def decode(self, Z, rng, counts_global, counts_local, tlog: TargetLog):
        g, fam, dev, model = self.g, self.family, self.device, self.model
        prop_phys = self._physical(model.property_decoder(Z))
        coords_in, center_in = self._decoder_in(Z.size(0))
        lat_out, _, spc_logits, _ = model.crystal_decoder(Z, input_coords=coords_in, center=center_in,
                                                          species_mask=self.mask.to(dev))
        # lattice: the decoder's own head (property-conditioned, MAE 0.146 A against MLIP relaxation) or the radii rule
        # (0.182 A).  featurize/scale_lattice divides a, b, c by 20, so the head is read back by multiplying by 20.
        a_pred = (lat_out[:, 0] * 20.0).tolist() if g.lattice_source == "decoder_search" else [None] * Z.size(0)
        order = fam.sampling_order
        last = order[-1]
        out = []
        for i in range(Z.size(0)):
            logits_i = spc_logits[i]
            preds = {c: float(prop_phys[i, j]) for j, c in enumerate(self.stats.columns)}
            ok = None
            tlog.latents_decoded += 1
            for _try in range(g.decode_tries):
                chosen = {}
                failed_compat = False
                for gname in order:
                    grp = fam.groups[gname]
                    pool = list(grp.sample)
                    if gname == last:
                        pool = self._charge_compatible(grp, chosen)
                        if not pool:
                            failed_compat = True
                            break
                    idx = torch.tensor([element_index(e) for e in pool], device=dev)
                    if len(grp.slots) == 1:
                        v = logits_i[grp.slots[0], idx] / max(g.decode_temperature, 1e-6)
                    else:
                        v = logits_i[grp.slots][:, idx].sum(dim=0) / max(g.decode_temperature, 1e-6)
                    if gname == self.ar_group and g.anti_repeat_alpha:
                        w = [1.0 / ((1.0 + float(counts_global.get(e, 0) + counts_local.get(e, 0))) ** g.anti_repeat_alpha)
                             for e in pool]
                        v = v + torch.log(torch.tensor(w, device=dev, dtype=v.dtype).clamp_min(1e-6))
                    k = min(g.decode_topk, v.numel())
                    vv, ii = torch.topk(v, k=k)
                    p = F.softmax(vv, dim=-1).cpu().numpy()
                    chosen[gname] = pool[int(rng.choice(ii.cpu().numpy(), p=p))]
                tlog.attempts += 1
                if failed_compat:
                    tlog.first_failure["no charge-balancing element"] += 1
                    tlog.failures_any["no charge-balancing element"] += 1
                    continue
                if len(set(chosen.values())) < len(chosen):
                    tlog.first_failure["same element on two sites"] += 1
                    continue
                if self._excluded and self._is_known(chosen, fam):
                    tlog.first_failure["known composition (novelty rule)"] += 1
                    continue
                cand = build_candidate(fam, chosen, a_pred[i])
                if g.lattice_source == "decoder_structure":      # rebuild at the lattice the decoder reads off this cell
                    cand = build_candidate(fam, chosen, self._decoder_lattice(cand))
                cand.predictions = self._structure_predictions(cand) if g.label_source == "structure" else preds
                evaluate(cand, fam.constraints)
                if cand.passed:
                    ok = cand
                    break
                tlog.first_failure[cand.first_failure] += 1
                for r in cand.results:
                    if not r.passed:
                        tlog.failures_any[r.name] += 1
                if len(tlog.rejected_examples) < 40:
                    tlog.rejected_examples.append({"formula": cand.formula(), "first_failure": cand.first_failure,
                                                   "results": [r.to_dict() for r in cand.results]})
            if ok is not None:
                tlog.latents_passing += 1
            out.append((ok, ok.predictions if (ok is not None and g.label_source == "structure") else preds))
        return out

    @torch.no_grad()
    def _is_known(self, chosen, fam) -> bool:
        """Is this composition already in the reference data?  Checked as a site key (when the family layout matches the
        keys that were supplied) and as a reduced formula, which works for any family layout."""
        if "|".join(chosen[gn] for gn in fam.groups) in self._excluded:
            return True
        if not self._excluded_formulas:
            return False
        from pymatgen.core import Composition
        counts = {}
        for gname, el in chosen.items():
            counts[el] = counts.get(el, 0) + len(fam.groups[gname].slots)
        return Composition(counts).reduced_formula in self._excluded_formulas

    def _decoder_lattice(self, cand) -> float:
        """The decoder's lattice constant for a built cell, read at its structure latent (where that head is accurate)."""
        key = tuple(sorted(cand.elements.items()))
        if key not in self._lat_cache:
            x = torch.tensor(featurize(cand.raw, self.model.max_sites), dtype=torch.float32, device=self.device).unsqueeze(0)
            zc, _ = self.model.encode_crystal(x)
            lat, _, _, _ = self.model.crystal_decoder(zc, input_coords=torch.zeros(1, self.model.max_sites, 3, device=self.device),
                                                      center=torch.zeros(1, 3, device=self.device))
            self._lat_cache[key] = float(lat[0, 0]) * 20.0
        return self._lat_cache[key]

    def _structure_predictions(self, cand) -> dict:
        """Properties of the structure that is actually returned: featurise it, encode it to its structure latent
        and read the property decoder there (needs a model trained with structure_property > 0)."""
        # the lattice is part of the key: with lattice_source='decoder' the same composition can be returned at different
        # cell sizes, and the structure-read label must describe the cell actually returned
        key = (tuple(sorted(cand.elements.items())), round(float(cand.raw.lattice.a), 4))
        if key not in self._struct_cache:
            x = torch.tensor(featurize(cand.raw, self.model.max_sites), dtype=torch.float32, device=self.device).unsqueeze(0)
            zc, _ = self.model.encode_crystal(x)
            p = self._physical(self.model.property_decoder(zc))[0]
            self._struct_cache[key] = {c: float(p[j]) for j, c in enumerate(self.stats.columns)}
        return dict(self._struct_cache[key])

    def _charge_compatible(self, grp, chosen):
        fam = self.family
        partial = []
        for gname, el in chosen.items():
            og = fam.groups[gname]
            partial.append([q * len(og.slots) for q in og.oxidation_states.get(el, [2])])
        needed = set()

        def walk(i, s):
            if i == len(partial):
                q = -s / len(grp.slots)
                if float(q).is_integer():
                    needed.add(int(q))
                return
            for q in partial[i]:
                walk(i + 1, s + q)

        walk(0, 0)
        return [e for e in grp.sample if any(q in grp.oxidation_states.get(e, ()) for q in needed)]

    # ── main loop ────────────────────────────────────────────────────────────
    def run(self, out_dir: str, ranges: dict | None = None) -> GenerationResult:
        g, fam, dev = self.g, self.family, self.device
        os.makedirs(out_dir, exist_ok=True)
        cif_dir = os.path.join(out_dir, "cifs")
        os.makedirs(cif_dir, exist_ok=True)
        prefix = g.output_prefix or fam.variant or fam.name
        ranges = ranges or {}
        seen_structs, seen_formula = set(), set()
        saved_latents = []
        hist = None
        counts_global = Counter()
        targets = []
        for idx, target in enumerate(g.targets, start=1):
            tvals = [float(target[o["property"]]) for o in self.objectives]
            tlog = TargetLog(index=idx, values=dict(target))
            targets.append(tlog)
            label = ", ".join(f"{o['property']} {target[o['property']]:g}" for o in self.objectives)
            self.log(f"\n=== target {idx}/{len(g.targets)}: {label}  (family {fam.name}"
                     f"{' / ' + fam.variant if fam.variant else ''}) ===")
            rng = np.random.RandomState(seed_from_target(g.seed, tvals))
            counts_local = Counter()
            for rnd in range(1, g.rounds + 1):
                if self._stop_requested():
                    break
                seed_i = seed_from_target(g.seed + 9973 * idx + 31 * rnd, tvals)
                Z0, Zf = self.propose(g.population, target, tvals, seed_i, hist, rnd)
                if self._stop_requested():   # the round was cut short: do not decode a half-optimised population
                    break
                tlog.rounds_used = rnd
                tlog.latent_start.append(Z0.cpu().numpy())
                tlog.latent_final.append(Zf.cpu().numpy())
                decoded = self.decode(Zf, rng, counts_global, counts_local, tlog)
                cands = []
                for i, (cand, preds) in enumerate(decoded):
                    if cand is None:
                        continue
                    score = 0.0
                    for o in self.objectives:
                        score += o["select_weight"] * objective_distance(preds[o["property"]], target[o["property"]],
                                                                         o["select_loss"])
                    cands.append((score, i, cand, preds))
                cands.sort(key=lambda c: c[0])
                added = 0
                for score, i, cand, preds in cands:
                    if len(tlog.saved) >= g.per_target:
                        break
                    sig = struct_signature(cand.structure, decimals=g.unique_decimals)
                    if sig in seen_structs:
                        tlog.skipped_duplicate += 1
                        continue
                    key = tuple(cand.elements[gn] for gn in fam.groups)
                    if g.dedup_formula and key in seen_formula:
                        tlog.skipped_duplicate += 1
                        continue
                    z_i = Zf[i].detach().cpu().numpy()
                    if saved_latents:
                        cs = [float(np.dot(z_i, zp) / (np.linalg.norm(z_i) * np.linalg.norm(zp) + 1e-9))
                              for zp in saved_latents]
                        if max(cs) > g.min_cosine_sep:
                            tlog.skipped_similar += 1
                            continue
                    k = len(tlog.saved) + 1
                    path = os.path.join(cif_dir, f"{prefix}_T{idx}_R{rnd}_{k}.cif")
                    # the symmetry refinement returns the conventional cell, which for a double perovskite holds 40 atoms;
                    # the model reads at most max_sites, so the file carries the same crystal as its primitive cell
                    CifWriter(fit_to_max_sites(cand.structure, self.lm.model.max_sites)).write_file(path)
                    flags = self._flags(preds, z_i, ranges)
                    sc = SavedCandidate(idx, rnd, os.path.relpath(path, out_dir), dict(cand.elements), cand.formula(),
                                        float(cand.lattice_a), preds, [r.to_dict() for r in cand.results],
                                        float(score), float(np.linalg.norm(z_i)), flags)
                    tlog.saved.append(sc)
                    if self.on_saved:
                        self.on_saved(sc, tlog)
                    self.log(f"  saved {sc.formula:<10} " + "  ".join(
                        f"{o['property']}={preds[o['property']]:.3f}" for o in self.objectives)
                        + ("   ⚠ " + "; ".join(flags) if flags else ""))
                    seen_structs.add(sig)
                    if g.dedup_formula:
                        seen_formula.add(key)
                    saved_latents.append(z_i)
                    el = cand.elements[self.ar_group]
                    counts_global[el] += 1
                    counts_local[el] += 1
                    hist = (torch.tensor(np.array([z_i]), device=dev) if hist is None
                            else torch.cat([hist, Zf[i:i + 1].to(dev)], dim=0))
                    added += 1
                if len(tlog.saved) >= g.per_target:
                    self.log(f"  reached {g.per_target} candidates in {rnd} round(s)")
                    break
                self.log(f"  round {rnd}: +{added} saved, {len(tlog.saved)}/{g.per_target} so far")
            if self._stop_requested():
                self.log("  stopped by user")
                break
            if not tlog.saved:
                self.log("  no candidate passed every constraint for this target")
        res = GenerationResult(out_dir, targets, ranges, fam.name, fam.variant, self.g.model_dump())
        write_outputs(res, self.stats, self.objectives)
        return res

    def _flags(self, preds, z, ranges):
        flags = []
        for prop, (lo, hi) in ranges.items():
            v = preds.get(prop)
            if v is None:
                continue
            span = hi - lo
            if v < lo - 0.05 * span or v > hi + 0.05 * span:
                flags.append(f"predicted {prop} {v:.2f} is outside the training range [{lo:.2f}, {hi:.2f}] "
                             "- the model is extrapolating")
        # The search always lets latents grow past the unit length the model was trained on (typically 3-5), so a
        # per-candidate warning would fire on every candidate; the reports state it once per run instead
        # (latent_norm stays in candidates.csv). Only a latent pinned at the clip bound is singled out.
        nz = float(np.linalg.norm(z))
        if float(np.abs(z).max()) >= self.g.z_clip - 1e-6:
            flags.append(f"latent hit the search limit (z_clip {self.g.z_clip:g}, length {nz:.1f}) "
                         "- predictions are less reliable")
        return flags


def write_outputs(res: GenerationResult, stats, objectives) -> None:
    rows = []
    for c in res.saved:
        row = {"target": c.target_index}
        for o in objectives:
            row[f"target_{o['property']}"] = res.targets[c.target_index - 1].values[o["property"]]
        for col in stats.columns:
            row[f"pred_{col}"] = c.predictions[col]
        row.update({f"site_{g}": e for g, e in c.elements.items()})
        row["formula"] = c.formula
        row["lattice_a"] = c.lattice_a
        for r in c.constraint_results:
            if r["value"] is not None:
                row[r["name"]] = r["value"]
        row.update({"score": c.score, "latent_norm": c.latent_norm, "round": c.round, "file": c.file,
                    "warnings": " | ".join(c.flags)})
        rows.append(row)
    path = os.path.join(res.out_dir, "candidates.csv")
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys or ["target"])
        w.writeheader()
        w.writerows(rows)
    summary = {
        "family": res.family, "variant": res.variant,
        "targets": [{"index": t.index, "values": t.values, "rounds_used": t.rounds_used, "attempts": t.attempts,
                     "latents_decoded": t.latents_decoded, "latents_passing": t.latents_passing,
                     "first_failure": dict(t.first_failure), "failures_any": dict(t.failures_any),
                     "skipped_duplicate": t.skipped_duplicate, "skipped_similar": t.skipped_similar,
                     "saved": [c.to_dict() for c in t.saved], "rejected_examples": t.rejected_examples}
                    for t in res.targets],
        "property_ranges": res.property_ranges, "settings": res.settings,
    }
    with open(os.path.join(res.out_dir, "generation.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, default=float)


__all__ = ["Designer", "GenerationResult", "seed_from_target", "rff_target_offset", "ELEMENTS", "ionic_radius"]
