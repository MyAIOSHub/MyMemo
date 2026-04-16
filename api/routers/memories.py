"""Memory Hub proxy endpoints.

Provides browse, search, and import of EverMemOS memories.
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

VALID_MEMORY_TYPES = Literal["episodic_memory", "profile", "raw_message"]

from api.memory_service import memory_service
from api.memory_import_service import import_memories_as_sources
from open_notebook.config import MEMORY_HUB_USER_ID

router = APIRouter(prefix="/memories")


# --- Request/Response Models ---


class MemoryImportRequest(BaseModel):
    memory_ids: List[str] = Field(..., description="EverMemOS memory IDs to import")
    memory_type: VALID_MEMORY_TYPES = Field(
        default="episodic_memory",
        description="Memory type: episodic_memory, profile, raw_message",
    )
    notebook_id: str = Field(..., description="Target notebook ID")
    user_id: Optional[str] = Field(
        default=None, description="EverMemOS user ID (defaults to config)"
    )


class MemoryImportResult(BaseModel):
    memory_id: str
    source_id: Optional[str] = None
    title: Optional[str] = None
    status: str
    error: Optional[str] = None


class MemoryImportResponse(BaseModel):
    imported: List[MemoryImportResult]
    total: int
    success_count: int


# --- Endpoints ---


@router.get("/status")
async def memory_hub_status():
    """Check Memory Hub connectivity."""
    status = await memory_service.check_status()
    return status


@router.get("/browse")
async def browse_memories(
    user_id: Optional[str] = Query(default=None),
    memory_type: VALID_MEMORY_TYPES = Query(default="episodic_memory"),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
):
    """Browse memories from EverMemOS with pagination."""
    try:
        result = await memory_service.browse_memories(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
            start_time=start_time,
            end_time=end_time,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to browse memories: {e}")
        raise HTTPException(status_code=502, detail="Memory Hub is unavailable. Please check that it is running.")


@router.get("/search")
async def search_memories(
    query: str = Query(..., description="Search query"),
    user_id: Optional[str] = Query(default=None),
    memory_types: Optional[str] = Query(
        default=None,
        description="Comma-separated memory types",
    ),
    retrieve_method: str = Query(default="hybrid"),
    top_k: int = Query(default=20, ge=1, le=100),
):
    """Search memories from EverMemOS."""
    types_list = None
    if memory_types:
        types_list = [t.strip() for t in memory_types.split(",") if t.strip()]

    try:
        result = await memory_service.search_memories(
            query=query,
            user_id=user_id,
            memory_types=types_list,
            retrieve_method=retrieve_method,
            top_k=top_k,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        raise HTTPException(status_code=502, detail="Memory Hub is unavailable. Please check that it is running.")


@router.post("/import", response_model=MemoryImportResponse)
async def import_memories(request: MemoryImportRequest):
    """Import selected EverMemOS memories as notebook Sources."""
    user_id = request.user_id or MEMORY_HUB_USER_ID

    try:
        results = await import_memories_as_sources(
            memory_ids=request.memory_ids,
            memory_type=request.memory_type,
            notebook_id=request.notebook_id,
            user_id=user_id,
        )

        success_count = sum(1 for r in results if r.get("status") == "imported")

        return MemoryImportResponse(
            imported=[MemoryImportResult(**r) for r in results],
            total=len(results),
            success_count=success_count,
        )
    except Exception as e:
        logger.error(f"Failed to import memories: {e}")
        raise HTTPException(status_code=500, detail="Failed to import memories. Check server logs for details.")
