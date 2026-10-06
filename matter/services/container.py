"""The services the API works with, built once when the application starts."""
from __future__ import annotations

import os
from dataclasses import dataclass

from matter.settings import Settings


@dataclass
class Services:
    settings: Settings
    artefacts: object = None            # DemoArtefacts
    registry: object = None             # ModelRegistry
    dataset_index: object = None        # DatasetIndex
    startup_error: str | None = None

    @classmethod
    def build(cls, settings: Settings) -> "Services":
        os.makedirs(settings.run_root, exist_ok=True)
        if settings.torch_threads:
            try:
                import torch
                torch.set_num_threads(settings.torch_threads)
            except Exception:           # torch missing or blocked: the API still answers /health
                pass
        s = cls(settings=settings)
        try:
            from matter.services.artefacts import DemoArtefacts
            from matter.services.novelty import DatasetIndex
            from matter.services.registry import ModelRegistry
            s.artefacts = DemoArtefacts(settings.demo_dir)
            s.registry = ModelRegistry(settings, s.artefacts)
            s.dataset_index = DatasetIndex(s.artefacts.materials, s.artefacts.dataset.get("title", "the dataset"))
            default = s.artefacts.project["default_model"]
            if s.registry.available(default):
                try:
                    s.registry.load(default)
                except Exception as e:              # reported by /health; routes that need the model say why
                    s.startup_error = str(e)
        except Exception as e:                      # no artefacts: /health still answers, the rest is 503
            s.startup_error = str(e)
        return s

    @property
    def model_loaded(self) -> bool:
        return bool(self.registry and self.artefacts and self.registry.loaded(self.artefacts.project["default_model"]))

    def close(self) -> None:
        pass
