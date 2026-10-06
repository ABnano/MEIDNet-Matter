"""The services the API works with, built once when the application starts."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from matter.settings import Settings


@dataclass
class Services:
    settings: Settings
    model_loaded: bool = False
    started: dict = field(default_factory=dict)

    @classmethod
    def build(cls, settings: Settings) -> "Services":
        os.makedirs(settings.run_root, exist_ok=True)
        if settings.torch_threads:
            try:
                import torch
                torch.set_num_threads(settings.torch_threads)
            except Exception:           # torch missing or blocked: the API still answers /health
                pass
        return cls(settings=settings)

    def close(self) -> None:
        pass
