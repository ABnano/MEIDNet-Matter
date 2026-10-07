"""The staged pipeline: the ten blocks, their metrics and bands, and the source of every component (read-only)."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from matter.api.errors import ApiError
from matter.services.pipeline_blocks import blocks_payload, component_list, component_source

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/blocks", summary="The ten blocks with their metrics, bands and components")
def blocks() -> dict:
    return blocks_payload()


@router.get("/blocks/{block_id}", summary="One block")
def block(block_id: str) -> dict:
    bid = (block_id or "").upper()
    for b in blocks_payload()["blocks"]:
        if b["id"] == bid:
            return b
    raise ApiError("not_found", f"no block {block_id!r}", status=404)


@router.get("/components", summary="Every component with its size, checksum and where it can run")
def components() -> list[dict]:
    return component_list()


@router.get("/components/{name}", summary="The source of one component, as plain text", response_class=PlainTextResponse)
def component(name: str):
    text, meta = component_source(name)
    return PlainTextResponse(text, headers={"X-Matter-Sha256": meta["sha256"], "Cache-Control": "no-cache",
                                            "Content-Disposition": f'inline; filename="{name}"'})
