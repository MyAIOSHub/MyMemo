"""Minimal Sources router for memory-only MyMemo.

Exposes read + delete + status for Sources created by memory import.
File upload / URL ingest / notebook link / insight / transformation are gone
with the Open Notebook web surface. Responses are plain dicts (no response
model validation) — the web UI that consumed the strict schemas is removed.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from open_notebook.domain.notebook import Source

router = APIRouter()


def _source_dict(source: Source) -> Dict[str, Any]:
    asset: Any = None
    if source.asset:
        asset = {
            "file_path": source.asset.file_path,
            "url": source.asset.url,
        }
        if source.asset.memory_ref:
            asset["memory_ref"] = source.asset.memory_ref.model_dump()
    return {
        "id": source.id or "",
        "title": source.title,
        "topics": source.topics or [],
        "full_text": source.full_text,
        "asset": asset,
        "command": str(source.command) if source.command else None,
        "created": str(source.created) if source.created else None,
        "updated": str(source.updated) if source.updated else None,
    }


@router.get("/sources")
async def list_sources(
    memory_only: bool = Query(
        default=False,
        description="If true, only return sources imported from a memory",
    ),
):
    try:
        all_sources = await Source.get_all(order_by="updated desc")
    except Exception as e:
        logger.error(f"Error listing sources: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing sources: {e}")

    out = []
    for s in all_sources:
        if memory_only and not (s.asset and s.asset.memory_ref):
            continue
        out.append(_source_dict(s))
    return out


@router.get("/sources/{source_id}")
async def get_source(source_id: str):
    try:
        source = await Source.get(source_id)
    except Exception as e:
        logger.error(f"Error fetching source {source_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching source: {e}")
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return _source_dict(source)


@router.get("/sources/{source_id}/status")
async def get_source_status(source_id: str):
    try:
        source = await Source.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        status = await source.get_status()
        progress = await source.get_processing_progress()
        return {
            "id": source.id or "",
            "status": status or "unknown",
            "command_id": str(source.command) if source.command else None,
            "processing_info": progress,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching status for source {source_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching status: {e}")


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    """Delete local Source. Does NOT cascade to EverCore memories."""
    try:
        source = await Source.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        await source.delete()
        return {"message": "Source deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting source {source_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting source: {e}")
