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
    backend: object = None              # DesignBackend (MEIDNetBackend)
    jobs: object = None                 # JobManager
    runs: object = None                 # RunStore
    catalog: object = None              # CheckpointCatalog (the checkpoints the studies refer to)
    judge: object = None                # MegnetJudge (the independent band-gap judge)
    studies: object = None              # Studies (static research artefacts)
    reference: object = None            # Reference (known formulas, reference AMD set)
    generations: object = None          # GenerationStore
    startup_error: str | None = None
    generation_error: str | None = None
    default_note: str | None = None     # set when the demo's default model file is missing and another one stands in

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
        from matter.backends.meidnet_backend import MEIDNetBackend
        from matter.services.jobs import JobManager
        from matter.services.runs import RunStore
        s.backend = MEIDNetBackend()
        s.jobs = JobManager(settings.public)
        s.runs = RunStore(settings.run_root, settings.public)
        try:
            from matter.services.artefacts import DemoArtefacts
            from matter.services.novelty import DatasetIndex
            from matter.services.registry import ModelRegistry
            s.artefacts = DemoArtefacts(settings.demo_dir)
            s.registry = ModelRegistry(settings, s.artefacts)
            s.dataset_index = DatasetIndex(s.artefacts.materials, s.artefacts.dataset.get("title", "the dataset"))
            default = s.artefacts.project["default_model"]
            if not s.registry.available(default):
                # a checkpoints folder from before 0.8.0 holds only the published model: the demo runs on a model whose
                # file is present, and /health says so, rather than failing at the first search
                present = [m for m in s.registry.ids() if s.registry.available(m)]
                if present:
                    s.default_note = (f"the model file of {default} is not present, so the demo uses {present[0]}; "
                                      "python scripts/fetch_assets.py fetches every model")
                    default = s.artefacts.project["default_model"] = present[0]
                    if isinstance(s.artefacts.project.get("default_goal"), dict):
                        s.artefacts.project["default_goal"]["model_id"] = default
            if s.registry.available(default):
                try:
                    s.registry.load(default)
                except Exception as e:              # reported by /health; routes that need the model say why
                    s.startup_error = str(e)
        except Exception as e:                      # no artefacts: /health still answers, the rest is 503
            s.startup_error = str(e)
        try:
            from matter.services.checkpoints import CheckpointCatalog
            from matter.services.generation import GenerationStore, Reference
            from matter.services.judge import MegnetJudge
            from matter.services.studies import Studies
            s.catalog = CheckpointCatalog(settings)
            s.judge = MegnetJudge(settings)
            s.studies = Studies(settings.research_dir)
            s.reference = Reference(settings.research_dir)
            s.generations = GenerationStore(os.path.join(settings.run_root, "generate"), settings.public)
            if settings.warm_start:
                import threading
                threading.Thread(target=s.warm, daemon=True, name="warm-start").start()
        except Exception as e:                      # the research routes say why; the demo project is unaffected
            s.generation_error = str(e)
        return s

    def warm(self) -> None:
        """Load the generation model and the judge before the first visitor asks (public hosts)."""
        try:
            for cid in self.catalog.ids():
                e = self.catalog.entry(cid)
                if e.get("role") == "generation" and self.catalog.available(cid):
                    self.catalog.load(cid)
            self.judge.ready()
        except Exception as e:
            self.generation_error = str(e)

    @property
    def generation_ready(self) -> bool:
        if not self.catalog:
            return False
        return any(self.catalog.loaded(c) for c in self.catalog.ids() if self.catalog.entry(c).get("role") == "generation")

    @property
    def model_loaded(self) -> bool:
        return bool(self.registry and self.artefacts and self.registry.loaded(self.artefacts.project["default_model"]))

    def close(self) -> None:
        pass
