"""The models of the project: their files, loaded on first use, and what the API says about them."""
from __future__ import annotations

import hashlib
import os
import threading

from matter.api.errors import ApiError
from matter.services.artefacts import DemoArtefacts
from matter.settings import Settings


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ModelRegistry:
    def __init__(self, settings: Settings, artefacts: DemoArtefacts):
        self.settings = settings
        self.artefacts = artefacts
        self._loaded: dict[str, object] = {}
        self._errors: dict[str, str] = {}
        self._lock = threading.Lock()

    def ids(self) -> list[str]:
        return list(self.artefacts.models)

    def entry(self, model_id: str) -> dict:
        try:
            return self.artefacts.models[model_id]
        except KeyError:
            raise ApiError("not_found", f"unknown model '{model_id}'; this project has {', '.join(self.ids())}", status=404) from None

    def path(self, model_id: str) -> str:
        return self.settings.model_file(self.entry(model_id)["file"])

    def available(self, model_id: str) -> bool:
        return os.path.exists(self.path(model_id))

    def load(self, model_id: str):
        """The meidnet LoadedModel, read once; a missing or altered file is a clear 503."""
        with self._lock:
            if model_id in self._loaded:
                return self._loaded[model_id]
            entry, path = self.entry(model_id), self.path(model_id)
            if not os.path.exists(path):
                raise ApiError("model_unavailable", f"the model file {entry['file']} is not present: run python scripts/fetch_assets.py "
                               f"(expected at {path})", status=503)
            if sha256_file(path) != entry["sha256"]:
                raise ApiError("model_unavailable", f"the model file {entry['file']} does not match the checksum the demo was built with",
                               status=503)
            try:
                from meidnet.checkpoint import load_checkpoint
                lm = load_checkpoint(path, device="cpu")
            except OSError as e:                     # torch blocked or broken on this machine
                raise ApiError("model_unavailable", f"the model cannot be loaded here: {e}", status=503) from None
            self._loaded[model_id] = lm
            return lm

    def loaded(self, model_id: str) -> bool:
        return model_id in self._loaded

    def info(self, model_id: str, with_evaluation: bool = True) -> dict:
        entry = dict(self.entry(model_id))
        entry["available"] = self.available(model_id)
        entry["loaded"] = self.loaded(model_id)
        r = self.artefacts.readiness.get(model_id, {})
        entry["caveats"] = r.get("caveats", [])
        entry["latents_available"] = self.artefacts.latents(model_id) is not None
        if with_evaluation:
            entry["evaluation"] = {"split": r.get("split"), "n": r.get("n"), "space": r.get("space"), **r.get("evaluation", {}),
                                   "recoverability": r.get("recoverability")}
        return entry
