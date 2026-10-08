"""
Training the dual autoencoder.

Each step computes five losses (same as MEIDNet v1):

    total = w1 · rebuild crystal from the joint latent
          + w2 · predict properties from the joint latent
          + w3 · rebuild crystal from the PROPERTY latent alone   ← enables inverse design
          + w4 · predict properties from the property latent
          + λ(epoch) · contrastive alignment of z_c and z_p        (λ ramps up from 0)

plus, when their weights are > 0 (grounded generation), rebuilding the crystal and predicting the
properties from the STRUCTURE latent alone, so a decoded structure can be re-encoded and labelled,
and records validation metrics in physical units after every epoch so that the
report can say, in plain words, how good the model is.
"""
from __future__ import annotations

import os
import time

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from meidnet.chem import NUM_SPECIES
from meidnet.data import MaterialsDataset, PropertyStats, split_dense
from meidnet.model import DualAutoencoderModel


def reconstruction_loss(crystal_vec, lat_out, adj_logits, species_logits, coords_out, max_sites):
    """Lattice MSE + adjacency BCE + species cross-entropy + coordinate MSE (MEIDNet v1)."""
    B = crystal_vec.size(0)
    target_lat = crystal_vec[:, :6]
    target_adj = crystal_vec[:, 6:6 + max_sites * max_sites].view(B, max_sites, max_sites)
    target_species = crystal_vec[:, 6 + max_sites * max_sites:6 + max_sites * max_sites + max_sites * NUM_SPECIES].view(
        B, max_sites, NUM_SPECIES)
    target_coords = crystal_vec[:, 6 + max_sites * max_sites + max_sites * NUM_SPECIES:].view(B, max_sites, 3)
    # padding slots (cells smaller than max_sites) carry no atom: they are left out of the species, coordinate and adjacency
    # terms instead of being taught as "element 0 at the origin" (no effect when every cell fills max_sites, as in Perov-5)
    mask = target_species.sum(dim=-1) > 0                                           # (B, N) real atoms
    loss_lat = F.mse_loss(lat_out, target_lat)
    pair = (mask.unsqueeze(1) & mask.unsqueeze(2)).float()
    loss_adj = (F.binary_cross_entropy_with_logits(adj_logits, target_adj, reduction="none") * pair).sum() / pair.sum().clamp(min=1)
    ce = F.cross_entropy(species_logits.view(-1, NUM_SPECIES), target_species.argmax(dim=-1).view(-1), reduction="none")
    loss_species = (ce * mask.view(-1).float()).sum() / mask.sum().clamp(min=1)
    m3 = mask.unsqueeze(-1).float()
    loss_coords = (((coords_out - target_coords) ** 2) * m3).sum() / (3 * mask.sum().clamp(min=1))
    return loss_lat + loss_adj + loss_species + loss_coords


def contrastive_loss(z1, z2, temperature=0.01):
    """Symmetric InfoNCE: each structure should be closest to its own property latent."""
    logits = torch.matmul(z1, z2.t()) / temperature
    labels = torch.arange(z1.size(0), device=z1.device)
    return 0.5 * (F.cross_entropy(logits, labels) + F.cross_entropy(logits.t(), labels))


def decoder_inputs(mode: str, crystal_vec, center, max_sites, prototype_coords=None):
    """Starting positions given to the crystal decoder (see ModelSection.decoder_coordinate_input)."""
    if mode == "data":
        return split_dense(crystal_vec, max_sites)["coords"], center
    B = crystal_vec.size(0)
    zeros_c = torch.zeros(B, 3, device=crystal_vec.device)
    if mode == "zeros":
        return torch.zeros(B, max_sites, 3, device=crystal_vec.device), zeros_c
    if mode == "prototype":
        return prototype_coords.to(crystal_vec.device).unsqueeze(0).expand(B, -1, -1), zeros_c
    raise ValueError(f"unknown decoder_coordinate_input '{mode}'")


def train_step(model: DualAutoencoderModel, batch, epoch, tcfg, coord_mode="data", prototype_coords=None):
    """One optimisation step's losses.  Mirrors scripts/train.py of MEIDNet v1 operation by operation."""
    cv, props = batch["crystal_vec"], batch["props"]
    w = tcfg.loss_weights
    if coord_mode == "data":
        zc, zp, lat, adj, spc, crd, prop_out = model(cv, props)
    else:
        z_c0, center0 = model.encode_crystal(cv)
        coords, center = decoder_inputs(coord_mode, cv, center0, model.max_sites, prototype_coords)
        zc, zp, lat, adj, spc, crd, prop_out = model(cv, props, coords=coords, center=center)
    l_rj = reconstruction_loss(cv, lat, adj, spc, crd, model.max_sites)
    l_pj = F.mse_loss(prop_out, props)
    # property-only branch (encodings recomputed exactly as in v1)
    zc2, zp2, _, center, _, data_coords = model.encode_modalities(cv, props)
    coords, center = (data_coords, center) if coord_mode == "data" else decoder_inputs(
        coord_mode, cv, center, model.max_sites, prototype_coords)
    lat_p, adj_p, spc_p, crd_p = model.crystal_decoder(zp2, input_coords=coords, center=center)
    l_rp = reconstruction_loss(cv, lat_p, adj_p, spc_p, crd_p, model.max_sites)
    l_pp = F.mse_loss(model.property_decoder(zp2), props)
    l_ct = contrastive_loss(zc, zp, temperature=tcfg.temperature)
    lam = min(epoch / float(tcfg.warmup()), 1.0) * tcfg.contrastive_weight
    loss = (w.joint_reconstruction * l_rj + w.joint_property * l_pj
            + w.property_reconstruction * l_rp + w.property_property * l_pp + lam * l_ct)
    parts = {"total": loss, "recon_joint": l_rj, "prop_joint": l_pj, "recon_from_prop": l_rp,
             "prop_from_prop": l_pp, "contrastive": l_ct}
    # structure-only branch (grounded generation): decode and predict from z_c alone
    if w.structure_reconstruction > 0:
        lat_c, adj_c, spc_c, crd_c = model.crystal_decoder(zc2, input_coords=coords, center=center)
        l_rc = reconstruction_loss(cv, lat_c, adj_c, spc_c, crd_c, model.max_sites)
        loss = loss + w.structure_reconstruction * l_rc
        parts["recon_from_struct"] = l_rc
    if w.structure_property > 0:
        l_pc = F.mse_loss(model.property_decoder(zc2), props)
        loss = loss + w.structure_property * l_pc
        parts["prop_from_struct"] = l_pc
    if w.symmetry > 0 and getattr(model.crystal_decoder, "sym_trunk", None) is not None and "sym_targets" in batch:
        from meidnet.symmetry import symmetry_loss
        pred = model.crystal_decoder.symmetry_forward(zc2)
        bins = (model.crystal_decoder.coordinate_bin_logits(zc2)
                if getattr(model.crystal_decoder, "fc_orbit_coord_bins", None) is not None else None)
        l_sym, sym_parts = symmetry_loss(pred, batch["sym_targets"], bin_logits=bins)
        loss = loss + w.symmetry * l_sym
        parts["symmetry"] = l_sym
        for k, v in sym_parts.items():
            parts[f"sym_{k}"] = v
    parts["total"] = loss
    return loss, parts, (zc, zp)


@torch.no_grad()
def evaluate(model: DualAutoencoderModel, dataset: MaterialsDataset, stats: PropertyStats, batch_size=64) -> dict:
    """Validation metrics in physical units: MAE/R² of the property predictors and latent retrieval accuracy."""
    model.eval()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    preds_joint, preds_struct, preds_prop, truth, zcs, zps = [], [], [], [], [], []
    for b in loader:
        cv, props = b["crystal_vec"].to(next(model.parameters()).device), b["props"].to(next(model.parameters()).device)
        zc, zp, zj, *_ = model.encode_modalities(cv, props)
        preds_joint.append(stats.denormalize_tensor(model.property_decoder(zj)).cpu())
        preds_struct.append(stats.denormalize_tensor(model.property_decoder(zc)).cpu())
        truth.append(stats.denormalize_tensor(props).cpu())
        zcs.append(zc.cpu()); zps.append(zp.cpu())
    Y = torch.cat(truth).numpy()
    out = {"n": int(len(Y))}
    for key, P in (("joint", preds_joint), ("structure_only", preds_struct)):
        P = torch.cat(P).numpy()
        mae = np.abs(P - Y).mean(0)
        ss_res = ((P - Y) ** 2).sum(0)
        ss_tot = ((Y - Y.mean(0)) ** 2).sum(0)
        r2 = 1 - ss_res / np.where(ss_tot > 0, ss_tot, 1)
        out[f"mae_{key}"] = {c: float(m) for c, m in zip(stats.columns, mae)}
        out[f"r2_{key}"] = {c: float(r) for c, r in zip(stats.columns, r2)}
    out["mae"] = out["mae_structure_only"]
    zc = torch.cat(zcs); zp = torch.cat(zps)
    sims = zc @ zp.t()
    k = min(5, sims.size(1))
    topk = sims.topk(k, dim=1).indices
    target = torch.arange(len(zc)).unsqueeze(1)
    out["retrieval_top1"] = float((topk[:, :1] == target).any(1).float().mean())
    out["retrieval_top5"] = float((topk == target).any(1).float().mean())
    out["cosine_matched"] = float((zc * zp).sum(1).mean())
    return out


def fit(model: DualAutoencoderModel, train_set: MaterialsDataset, val_set: MaterialsDataset | None, tcfg,
        coord_mode="data", prototype_coords=None, device="cpu", on_epoch=None, checkpoint_fn=None,
        log=print, should_stop=None) -> dict:
    """
    Train for tcfg.epochs.  Returns the history dict stored in the checkpoint and report.
    Seed the RNGs *before* building the model (see ``seed_everything``) so that weight
    initialisation and batch shuffling are both reproducible.
    ``should_stop()`` is checked after every epoch; True ends training early with the history so far
    (``history["stopped"] = True``).
    """
    model.to(device)
    # CPU threads: on graphs of 10-20 atoms more threads only spin (measured 142 s versus 4 s per epoch with 16 versus 4
    # threads on one dataset), so cap them unless the user chose a count (OMP_NUM_THREADS or training.threads)
    if str(device) == "cpu" and not os.environ.get("OMP_NUM_THREADS"):
        torch.set_num_threads(int(getattr(tcfg, "threads", 0) or min(4, os.cpu_count() or 4)))
        log(f"CPU threads: {torch.get_num_threads()} (set OMP_NUM_THREADS or training.threads to change)")
    loader = DataLoader(train_set, batch_size=tcfg.batch_size, shuffle=True, drop_last=True)
    if len(loader) == 0:
        raise ValueError(f"Only {len(train_set)} training materials: need at least batch_size={tcfg.batch_size}.")
    # D1 only: the side-car symmetry targets that pipeline.train() stashes on the config.  None on the free path,
    # so the per-batch block below is skipped and training is exactly what it was.
    sym_targets = getattr(tcfg, "_sym_targets", None)
    opt = torch.optim.Adam(model.parameters(), lr=tcfg.learning_rate)
    history = {"train": [], "val": [], "warmup_epochs": tcfg.warmup(), "seconds": 0.0}
    t0 = time.time()
    for ep in range(1, tcfg.epochs + 1):
        model.train()
        sums = {}
        cos = n = 0.0
        for batch in loader:
            batch = {k: (v.to(device) if torch.is_tensor(v) else v) for k, v in batch.items()}
            if sym_targets is not None:
                from meidnet.symmetry import encode_targets
                batch["sym_targets"] = {k: v.to(device) for k, v in
                                        encode_targets(sym_targets, list(batch["material_id"])).items()}
            loss, parts, (zc, zp) = train_step(model, batch, ep, tcfg, coord_mode, prototype_coords)
            opt.zero_grad()
            loss.backward()
            opt.step()
            for k, v in parts.items():                 # loss terms are tensors; diagnostic sub-parts are plain floats
                sums[k] = sums.get(k, 0.0) + (v.item() if torch.is_tensor(v) else float(v))
            cos += torch.mean(torch.sum(zc * zp, dim=1)).item()
            n += 1
        rec = {k: v / n for k, v in sums.items()}
        rec["epoch"] = ep
        rec["cosine"] = cos / n
        rec["contrastive_strength"] = min(ep / float(tcfg.warmup()), 1.0) * tcfg.contrastive_weight
        history["train"].append(rec)
        msg = f"epoch {ep:4d}/{tcfg.epochs}  loss {rec['total']:.4f}  align cos {rec['cosine']:.3f}"
        if val_set is not None and len(val_set) and (ep == tcfg.epochs or ep % max(1, tcfg.epochs // 20) == 0 or ep <= 2):
            ev = evaluate(model, val_set, train_set.stats)
            ev["epoch"] = ep
            history["val"].append(ev)
            msg += "  val MAE " + ", ".join(f"{k} {v:.3g}" for k, v in ev["mae"].items())
            msg += f"  retrieval@1 {ev['retrieval_top1']:.2f}"
        log(msg)
        if ep == 2:                                   # the measured pace, so a slow run is recognised at once
            per_epoch = (time.time() - t0) / 2
            log(f"measured: {per_epoch:.1f} s per epoch -> about {per_epoch * (tcfg.epochs - 2) / 60:.0f} min for the remaining {tcfg.epochs - 2} epochs")
        if on_epoch:
            on_epoch(ep, rec)
        if checkpoint_fn and (ep % tcfg.save_every == 0 or ep == tcfg.epochs):
            history["seconds"] = time.time() - t0
            checkpoint_fn(history)
        if should_stop and should_stop():
            history["stopped"] = True
            log(f"stopped after epoch {ep}")
            break
    history["seconds"] = time.time() - t0
    return history


def seed_everything(seed: int) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)


def pick_device(name: str) -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if name == "cuda" and not torch.cuda.is_available():
        raise SystemExit("device 'cuda' requested but no CUDA GPU is available to PyTorch. Use device: auto or cpu.")
    return torch.device(name)


def human_time(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def estimate_epoch_seconds(n_samples: int, device: torch.device) -> float:
    """Rough guide from the published model: ~21 s per 11k samples on a laptop RTX GPU, ~10x slower on CPU."""
    per_sample = 21.0 / 11356
    return n_samples * per_sample * (1.0 if device.type == "cuda" else 10.0)


__all__ = ["fit", "evaluate", "train_step", "reconstruction_loss", "contrastive_loss", "pick_device",
           "seed_everything", "human_time", "estimate_epoch_seconds"]
