"""Service for importing EverMemOS memories as Open Notebook Sources."""

from typing import Any, Dict, List

from loguru import logger

from api.memory_service import memory_service
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import Asset, MemoryRef, Source


async def _find_existing_source_by_memory_id(memory_id: str) -> bool:
    """Check if a memory has already been imported as a Source (dedup)."""
    try:
        results = await repo_query(
            """
            SELECT id FROM source
            WHERE asset.memory_ref.memory_id = $memory_id
            LIMIT 1
            """,
            {"memory_id": memory_id},
        )
        return bool(results)
    except Exception as e:
        logger.warning(f"Dedup check failed for memory {memory_id}, treating as new: {e}")
        return False


async def import_memories_as_sources(
    memory_ids: List[str],
    memory_type: str,
    notebook_id: str,
    user_id: str,
) -> List[Dict[str, Any]]:
    """Import selected EverCore memories as Open Notebook Sources.

    Features:
    - Deduplication: skips memories already imported as Sources
    - Pages through `browse_memories` until every requested ID is found or
      the server runs out of memories. v1's GetMemRequest is page-based, so
      a single fetch can only see one page; for users with >500 memories of
      the same type we keep paging.

    Args:
        memory_ids: List of EverCore memory IDs to import.
        memory_type: Type of memory (episodic_memory, profile).
        notebook_id: Target notebook to link sources to.
        user_id: EverCore user ID for fetching memories.

    Returns:
        List of created source info dicts with id, title, status.
    """
    PAGE_SIZE = 100
    MAX_PAGES = 50  # hard ceiling: 50 * 100 = 5000 memories per import session
    wanted = set(memory_ids)
    all_memories: Dict[str, Dict[str, Any]] = {}
    offset = 0
    for _ in range(MAX_PAGES):
        page = await memory_service.browse_memories(
            user_id=user_id,
            memory_type=memory_type,
            limit=PAGE_SIZE,
            offset=offset,
        )
        for m in page.get("memories", []):
            mid = m.get("id")
            if mid:
                all_memories[mid] = m
        # Stop early once every requested ID has been located.
        if wanted.issubset(all_memories.keys()):
            break
        if not page.get("has_more"):
            break
        offset += PAGE_SIZE
    if not wanted.issubset(all_memories.keys()):
        missing = wanted - all_memories.keys()
        logger.warning(
            "import_memories: %d of %d requested IDs not found after paging "
            "(possibly beyond MAX_PAGES=%d window): %s",
            len(missing),
            len(wanted),
            MAX_PAGES,
            sorted(missing)[:5],
        )

    created_sources = []

    for mem_id in memory_ids:
        mem = all_memories.get(mem_id)
        if not mem:
            logger.warning(f"Memory {mem_id} not found, skipping")
            created_sources.append({
                "memory_id": mem_id,
                "status": "not_found",
            })
            continue

        # Dedup check: skip if already imported
        if await _find_existing_source_by_memory_id(mem_id):
            logger.info(f"Memory {mem_id} already imported, skipping")
            created_sources.append({
                "memory_id": mem_id,
                "status": "duplicate",
            })
            continue

        try:
            source = await _create_source_from_memory(mem, notebook_id)
            created_sources.append({
                "memory_id": mem_id,
                "source_id": source.id,
                "title": source.title,
                "status": "imported",
            })
        except Exception as e:
            logger.error(f"Failed to import memory {mem_id}: {e}")
            created_sources.append({
                "memory_id": mem_id,
                "status": "error",
                "error": str(e),
            })

    return created_sources


async def _create_source_from_memory(
    memory: Dict[str, Any],
    notebook_id: str,
) -> Source:
    """Create a Source from a normalized MemoryItem dict (v1 EverOS shape)."""
    title = memory.get("title") or memory.get("subject") or "Untitled Memory"
    content = memory.get("content", "")

    # Build full text from v1 fields: subject -> summary -> episode -> content.
    full_text_parts: List[str] = []
    seen: set[str] = set()
    for key in ("subject", "summary", "episode", "content"):
        value = memory.get(key)
        if value and value not in seen:
            full_text_parts.append(value)
            seen.add(value)
    if memory.get("keywords"):
        full_text_parts.append("Key events: " + ", ".join(memory["keywords"]))

    full_text = "\n\n".join(full_text_parts) or content or title

    # Build typed memory reference
    memory_ref = MemoryRef(
        memory_id=memory["id"],
        memory_type=memory.get("memory_type", "episodic_memory"),
        user_id=memory.get("user_id"),
        source_origin=memory.get("source_origin", "evermemo"),
        group_id=memory.get("group_id"),
        group_name=memory.get("group_name"),
        original_timestamp=memory.get("timestamp"),
    )

    asset = Asset(memory_ref=memory_ref)
    topics = memory.get("keywords") or []

    source = Source(
        title=title,
        full_text=full_text,
        asset=asset,
        topics=topics,
    )
    await source.save()

    # Link to notebook
    await source.relate("reference", ensure_record_id(notebook_id))

    # Submit vectorization job (fire-and-forget)
    try:
        await source.vectorize()
    except Exception as e:
        logger.warning(f"Vectorization submission failed for source {source.id}: {e}")

    logger.info(
        f"Imported memory {memory['id']} as source {source.id} "
        f"(origin: {memory.get('source_origin', 'unknown')})"
    )
    return source
