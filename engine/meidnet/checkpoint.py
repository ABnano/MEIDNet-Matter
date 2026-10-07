"""
Saving and loading trained models.

A MEIDNet 2 checkpoint is a single ``.pt`` file that carries everything needed to
use the model later: the weights, the architecture settings, the property names,
units and normalisation, the family it was trained for, the data summary and the
training history.  MEIDNet v1 ``.pth`` files load too; they are recognised and
described as the published Perov-5 model (properties heat_all and dir_gap, no
normalisation).
"""
from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass, field

import numpy as np
import torch

from meidnet import __version__
from meidnet.data import PropertyStats
from meidnet.model import DualAutoencoderModel

V1_PROPERTIES = [
    {"column": "heat_all", "label": "Formation enthalpy", "unit": "eV/atom", "mean": 0.0, "std": 1.0},
    {"column": "dir_gap", "label": "Direct band gap", "unit": "eV", "mean": 0.0, "std": 1.0},
]

# Renames used by the earliest v1 checkpoint (dual_autoencoder_clip_earlyfusion.pth).
_V1_KEY_RENAMES = [
    ("crystal_encoder.sp_emb.", "crystal_encoder.species_embedding."),
    ("crystal_encoder.init_fc.", "crystal_encoder.init_node_fc."),
    ("crystal_encoder.agg_fc.", "crystal_encoder.aggregate_fc."),
    ("crystal_decoder.fc_nd.", "crystal_decoder.fc_nodes."),
    ("crystal_decoder.fc_sd.", "crystal_decoder.fc_species_decoded."),
    ("crystal_decoder.fc_sf.", "crystal_decoder.fc_species_final."),
    ("crystal_decoder.fc_crd.", "crystal_decoder.fc_coords."),
    ("egnn1.phi_x.weight", "egnn1.phi_x.0.weight"),
    ("egnn1.phi_x.bias", "egnn1.phi_x.0.bias"),
    ("egnn2.phi_x.weight", "egnn2.phi_x.0.weight"),
    ("egnn2.phi_x.bias", "egnn2.phi_x.0.bias"),
    ("crystal_decoder.fc_coords.weight", "crystal_decoder.fc_coords.0.weight"),
    ("crystal_decoder.fc_coords.bias", "crystal_decoder.fc_coords.0.bias"),
]


@dataclass
class LoadedModel:
    model: DualAutoencoderModel
    stats: PropertyStats
    model_config: dict
    family: str | None = None
    family_variant_hint: str | None = None
    decoder_coordinate_input: str = "data"
    meta: dict = field(default_factory=dict)
    path: str = ""
    legacy: bool = False

    @property
    def device(self):
        return next(self.model.parameters()).device


def _remap_v1(sd: dict) -> dict:
    out = {}
    for k, v in sd.items():
        for a, b in _V1_KEY_RENAMES:
            k = k.replace(a, b)
        out[k] = v
    return out


def build_model(n_properties: int, model_cfg: dict, max_sites: int) -> DualAutoencoderModel:
    return DualAutoencoderModel(
        n_properties=n_properties, max_sites=max_sites,
        latent_dim=model_cfg.get("latent_dim", 128), node_hidden_dim=model_cfg.get("node_hidden_dim", 128),
        species_embedding_dim=model_cfg.get("species_embedding_dim", 64), edge_dim=model_cfg.get("edge_dim", 64),
        property_hidden_dim=model_cfg.get("property_hidden_dim", 128),
        periodic_encoder=bool(model_cfg.get("periodic_encoder", False)),
        element_features=model_cfg.get("element_features", "onehot"),
    )


def save_checkpoint(path: str, model: DualAutoencoderModel, stats: PropertyStats, model_cfg: dict,
                    max_sites: int, family: str | None, extra: dict | None = None) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload = {
        "format": "meidnet-2",
        "meidnet_version": __version__,
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "model_state_dict": model.state_dict(),
        "model_config": dict(model_cfg),
        "max_sites": max_sites,
        "properties": stats.to_dict(),
        "family": family,
    }
    payload.update(extra or {})
    tmp = path + ".tmp"
    torch.save(payload, tmp)
    os.replace(tmp, path)


def load_checkpoint(path: str, device: str | torch.device = "cpu") -> LoadedModel:
    if not os.path.exists(path):
        raise FileNotFoundError(f"No model at {path}. Train one with `meidnet train` or point model_path to a checkpoint.")
    raw = torch.load(path, map_location=device, weights_only=False)
    if isinstance(raw, dict) and raw.get("format") == "meidnet-2":
        stats = PropertyStats.from_dict(raw["properties"])
        cfg = raw["model_config"]
        model = build_model(len(stats.columns), cfg, raw["max_sites"])
        # A D1 checkpoint carries the symmetry head, which is an added module rather than part of build_model, so it has
        # to be attached before the weights load.  Its shapes are read back from the saved tensors instead of from
        # today's constants, so the load stays strict and a later change to MAX_ORBITS cannot orphan this checkpoint.
        sd = raw["model_state_dict"]
        if "crystal_decoder.sym_trunk.0.weight" in sd:
            hidden, latent = sd["crystal_decoder.sym_trunk.0.weight"].shape
            model.crystal_decoder.add_symmetry_head(
                n_spacegroups=sd["crystal_decoder.fc_spacegroup.weight"].shape[0],
                max_orbits=sd["crystal_decoder.fc_orbit.0.weight"].shape[0] // 64,
                latent_dim=int(latent), hidden=int(hidden))
            if "crystal_decoder.fc_orbit_coord_bins.weight" in sd:
                model.crystal_decoder.add_coordinate_bins(
                    sd["crystal_decoder.fc_orbit_coord_bins.weight"].shape[0] // 3)
        model.load_state_dict(sd, strict=True)
        meta = {k: v for k, v in raw.items() if k not in ("model_state_dict",)}
        lm = LoadedModel(model.to(device).eval(), stats, cfg, raw.get("family"), None,
                         cfg.get("decoder_coordinate_input", "data"), meta, path, legacy=False)
        return lm

    # ── MEIDNet v1 checkpoint ────────────────────────────────────────────────
    sd = raw["model_state_dict"] if isinstance(raw, dict) and "model_state_dict" in raw else raw
    sd = _remap_v1(sd)
    max_sites = int(raw.get("max_sites", 20)) if isinstance(raw, dict) else 20
    stats = PropertyStats.from_dict(V1_PROPERTIES)
    cfg = {"latent_dim": 128, "node_hidden_dim": 128, "species_embedding_dim": 64, "edge_dim": 64,
           "property_hidden_dim": 128, "decoder_coordinate_input": "data"}
    model = build_model(2, cfg, max_sites)
    missing, unexpected = model.load_state_dict(sd, strict=False)
    critical = [k for k in missing if not k.startswith("crystal_encoder")]
    if critical or unexpected:
        raise RuntimeError(
            f"{os.path.basename(path)} is not a MEIDNet checkpoint I understand "
            f"(missing: {critical[:5]}, unexpected: {list(unexpected)[:5]})."
        )
    meta = {"format": "meidnet-1", "source": os.path.basename(path),
            "note": "Published MEIDNet v1 model trained on Perov-5 (CDVAE split); properties are not normalised."}
    return LoadedModel(model.to(device).eval(), stats, cfg, "perovskite_abx3", None, "data", meta, path, legacy=True)


def describe(lm: LoadedModel) -> str:
    props = ", ".join(f"{lab} [{u}]" if u else lab for lab, u in zip(lm.stats.labels, lm.stats.units))
    n_params = sum(p.numel() for p in lm.model.parameters())
    lines = [
        f"model file      : {lm.path}",
        f"format          : {'MEIDNet v1 (published)' if lm.legacy else 'MEIDNet 2'}",
        f"properties      : {props}",
        f"family          : {lm.family or 'not recorded'}",
        f"max atoms/cell  : {lm.model.max_sites}",
        f"latent size     : {lm.model.latent_dim}",
        f"parameters      : {n_params:,}",
    ]
    hist = lm.meta.get("history")
    if hist and hist.get("val"):
        last = hist["val"][-1]
        lines.append("validation MAE  : " + ", ".join(f"{k} {v:.3g}" for k, v in last.get("mae", {}).items()))
    return "\n".join(lines)


def property_ranges(lm: LoadedModel) -> dict[str, tuple[float, float]]:
    """Training-data range of each property (if recorded) - used to flag extrapolation."""
    out = {}
    if lm.stats.minimum is not None:
        for i, c in enumerate(lm.stats.columns):
            out[c] = (float(lm.stats.minimum[i]), float(lm.stats.maximum[i]))
    elif lm.legacy:
        # Perov-5 training split ranges (data/perov5/train.csv)
        out = {"heat_all": (-0.64, 5.16), "dir_gap": (0.0, 7.9)}
    return out


def to_numpy(t: torch.Tensor) -> np.ndarray:
    return t.detach().cpu().numpy()
