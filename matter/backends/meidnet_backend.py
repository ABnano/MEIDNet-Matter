"""MEIDNet as a design backend: thin calls into the meidnet package; the science stays in the services."""
from __future__ import annotations

from typing import Any

from matter.backends.base import DesignBackend, ModelHandle, SearchHooks


class MEIDNetBackend(DesignBackend):
    name = "meidnet"

    def load_model(self, handle: ModelHandle):
        from meidnet.checkpoint import load_checkpoint
        return load_checkpoint(handle.path, device="cpu")

    def describe_model(self, model) -> dict:
        from meidnet.checkpoint import property_ranges
        return {"properties": model.stats.to_dict(), "max_sites": model.model.max_sites, "latent_dim": model.model.latent_dim,
                "legacy": model.legacy, "family": model.family, "property_ranges": {c: list(v) for c, v in property_ranges(model).items()}}

    def assess_readiness(self, validated, services) -> dict:
        from matter.services.readiness import assess
        return assess(validated, services)

    def search(self, model, config, family, out_dir: str, hooks: SearchHooks):
        from meidnet.checkpoint import property_ranges
        from meidnet.generate import Designer
        from meidnet.train import pick_device
        designer = Designer(model, family, config.generation, device=pick_device("cpu"), log=hooks.log, on_saved=hooks.on_candidate,
                            on_step=hooks.on_step, should_stop=hooks.should_stop)
        return designer.run(out_dir, ranges=property_ranges(model))

    def score_candidates(self, raw: list[dict], context) -> list[dict]:
        from matter.services.enrichment import enrich
        return [enrich(r, context, i + 1) for i, r in enumerate(raw)]

    def export(self, run: dict, fmt: str, services) -> bytes:
        from matter.services import export
        if fmt == "csv":
            return export.candidates_csv(run).encode("utf-8")
        if fmt == "bundle":
            return export.bundle_zip(run, services)
        raise ValueError(f"unknown export format {fmt}")

    def encode_composition(self, model, family, elements: dict[str, str]):
        """Projection-space structure latent and encoder-side predictions of a composition placed on the prototype."""
        import dataclasses
        import numpy as np
        import torch
        from meidnet.constraints import build_candidate
        from meidnet.data import featurize
        fam = dataclasses.replace(family, refine_symmetry=False)
        cand = build_candidate(fam, elements)
        x = torch.tensor(featurize(cand.raw, model.model.max_sites), dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            zc, _ = model.model.encode_crystal(x)
            pred = model.stats.denormalize_tensor(model.model.property_decoder(zc))
        return zc[0].numpy().astype(np.float32), {c: float(v) for c, v in zip(model.stats.columns, pred[0].numpy())}, cand.raw
