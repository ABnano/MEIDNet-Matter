"""The checkpoint catalogue: every trained model the studies refer to, with its checksum, size, training configuration
and where to download it.  Files that are present on this server are verified by sha256 before they are loaded, exactly
as the demo model is; files that are not present are still listed with their download URLs.
"""
from __future__ import annotations

import json
import os
import threading

from matter.api.errors import ApiError
from matter.services.registry import sha256_file


class CheckpointCatalog:
    def __init__(self, settings):
        self.settings = settings
        self.manifest_path = settings.checkpoints_manifest
        self.dir = settings.checkpoints_dir
        self._loaded: dict[str, object] = {}
        self._lock = threading.Lock()
        self.manifest = {"schema": None, "release": None, "checkpoints": []}
        if self.manifest_path and os.path.isfile(self.manifest_path):
            with open(self.manifest_path, encoding="utf-8") as f:
                self.manifest = json.load(f)
        self._by_id = {c["id"]: c for c in self.manifest.get("checkpoints", [])}

    # ── listing ──
    def ids(self) -> list[str]:
        return list(self._by_id)

    def entry(self, cid: str) -> dict:
        if cid not in self._by_id:
            raise ApiError("not_found", f"no checkpoint {cid!r}", status=404)
        return self._by_id[cid]

    def path(self, cid: str) -> str | None:
        e = self.entry(cid)
        if "file" not in e:
            return None
        return os.path.join(self.dir, e["file"])

    def available(self, cid: str) -> bool:
        p = self.path(cid)
        return bool(p and os.path.isfile(p))

    def loaded(self, cid: str) -> bool:
        return cid in self._loaded

    def info(self, cid: str, with_config: bool = False) -> dict:
        e = dict(self.entry(cid))
        e["available"] = self.available(cid)
        e["loaded"] = self.loaded(cid)
        e["download_url"] = f"/api/checkpoints/{cid}/download" if e["available"] else None
        if with_config and e.get("config"):
            cfg = os.path.join(self.dir, e["config"])
            if os.path.isfile(cfg):
                with open(cfg, encoding="utf-8") as f:
                    e["config_text"] = f.read()
        return e

    def listing(self) -> dict:
        return {"schema": self.manifest.get("schema"), "release": self.manifest.get("release"),
                "checkpoints": [self.info(cid) for cid in self.ids()]}

    # ── loading ──
    def load(self, cid: str):
        """Load a model after verifying its checksum; cached.  503 model_unavailable when the file is absent or differs."""
        e = self.entry(cid)
        if cid in self._loaded:
            return self._loaded[cid]
        with self._lock:
            if cid in self._loaded:
                return self._loaded[cid]
            p = self.path(cid)
            if not e.get("loadable", True) or not p:
                raise ApiError("model_unavailable", f"{cid} is not a model this server can load", status=503)
            if not os.path.isfile(p):
                raise ApiError("model_unavailable", f"the model file {e['file']} is not present: run python scripts/fetch_assets.py "
                                                    f"--only {cid}", status=503)
            if e.get("sha256") and sha256_file(p) != e["sha256"]:
                raise ApiError("model_unavailable", f"the model file {e['file']} does not match the checksum in the manifest", status=503)
            from meidnet.checkpoint import load_checkpoint
            lm = load_checkpoint(p, device="cpu")
            self._loaded[cid] = lm
            return lm
