"""The executed studies: static artefacts built by scripts/build_studies.py and served read-only.

    <research_dir>/studies/index.json            the studies in reading order
    <research_dir>/studies/<id>/study.json       facts, block verdicts, target following, candidates, checkpoints
    <research_dir>/studies/<id>/files/<name>     the tables and CIFs a study links to (only names listed in study.json)
"""
from __future__ import annotations

import json
import os
import re

from matter.api.errors import ApiError

SAFE_ID = re.compile(r"^[a-z0-9-]+$")


class Studies:
    def __init__(self, research_dir: str):
        self.dir = research_dir
        self._index = None
        self._cache: dict[str, dict] = {}

    @property
    def available(self) -> bool:
        return os.path.isfile(os.path.join(self.dir, "studies", "index.json"))

    def index(self) -> dict:
        if self._index is None:
            path = os.path.join(self.dir, "studies", "index.json")
            if not os.path.isfile(path):
                raise ApiError("not_found", "the research artefacts are not present on this server", status=404)
            with open(path, encoding="utf-8") as f:
                self._index = json.load(f)
        return self._index

    def get(self, study_id: str) -> dict:
        if not SAFE_ID.match(study_id or ""):
            raise ApiError("not_found", f"no study {study_id!r}", status=404)
        if study_id not in self._cache:
            path = os.path.join(self.dir, "studies", study_id, "study.json")
            if not os.path.isfile(path):
                raise ApiError("not_found", f"no study {study_id!r}", status=404)
            with open(path, encoding="utf-8") as f:
                self._cache[study_id] = json.load(f)
        return self._cache[study_id]

    def file_path(self, study_id: str, name: str) -> tuple[str, str]:
        """The on-disk path and media type of a file a study lists; a name the study does not list is not found."""
        study = self.get(study_id)
        files = study.get("files") or {}
        if name not in files or ".." in name or name.startswith("/"):
            raise ApiError("not_found", f"study {study_id} has no file {name!r}", status=404)
        path = os.path.join(self.dir, "studies", study_id, "files", *name.split("/"))
        if not os.path.isfile(path):
            raise ApiError("not_found", f"study {study_id} has no file {name!r}", status=404)
        return path, files[name].get("media") or "application/octet-stream"

    def pipeline_blocks_file(self) -> str | None:
        path = os.path.join(self.dir, "pipeline", "blocks.json")
        return path if os.path.isfile(path) else None
