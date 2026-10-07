"""The staged pipeline as data: the ten blocks with their metrics and bands, and the source of every component.

Everything comes from `meidnet_eval.stages`, the single definition the research pipeline itself is graded by, so the
page and the grading can never disagree.  Component sources are served read-only from the installed `meidnet_eval`
package through an allowlist of plain file names; nothing outside that package is reachable.
"""
from __future__ import annotations

import hashlib
import importlib.resources as ir
import re
from functools import lru_cache

from matter.api.errors import ApiError

SAFE_NAME = re.compile(r"^[a-z0-9_]+\.py$")


@lru_cache(maxsize=1)
def blocks_payload() -> dict:
    from meidnet_eval import COMPONENTS, stages
    payload = stages.export_blocks()
    for block in payload["blocks"]:
        comps = []
        for note in block["components"]:
            file = note.split(" ")[0].strip()
            info = COMPONENTS.get(file, {})
            comps.append({"file": file, "note": note, "viewable": file in component_files(),
                          "runnable": info.get("runnable", "local"), "needs": info.get("needs", [])})
        block["components"] = comps
    return payload


@lru_cache(maxsize=1)
def component_files() -> dict:
    """Plain file name -> (bytes, sha256) for every component of the installed package."""
    out = {}
    root = ir.files("meidnet_eval")
    for entry in root.iterdir():
        if entry.is_file() and SAFE_NAME.match(entry.name) and entry.name != "__init__.py":
            data = entry.read_bytes()
            out[entry.name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return out


def component_list() -> list[dict]:
    from meidnet_eval import COMPONENTS
    blocks = {}
    for block in blocks_payload()["blocks"]:
        for c in block["components"]:
            blocks.setdefault(c["file"], []).append(block["id"])
    rows = []
    for name, meta in sorted(component_files().items()):
        info = COMPONENTS.get(name, {})
        rows.append({"file": name, **meta, "blocks": blocks.get(name, []), "runnable": info.get("runnable", "local"),
                     "needs": info.get("needs", [])})
    return rows


def component_source(name: str) -> tuple[str, dict]:
    """The text of one component, by its plain file name; anything else is not found."""
    if not SAFE_NAME.match(name or "") or name not in component_files():
        raise ApiError("not_found", f"no component named {name!r}", status=404)
    text = (ir.files("meidnet_eval") / name).read_text(encoding="utf-8")
    return text, component_files()[name]
