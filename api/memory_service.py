"""Service for communicating with EverOS / EverCore Memory Hub (v1 API)."""

import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from open_notebook.config import (
    MEMORY_BLOCKED_ORIGINS,
    MEMORY_HUB_URL,
    MEMORY_HUB_USER_ID,
)
from open_notebook.utils.memory_origin import classify_origin


def _safe_host(url: str) -> str:
    """Return the hostname only, dropping scheme + path + creds."""
    try:
        parsed = urlparse(url)
        return parsed.hostname or "memory-hub"
    except Exception:
        return "memory-hub"


class MemoryService:
    """HTTP client for EverOS / EverCore (v1) Memory Hub API.

    Uses a shared httpx.AsyncClient for connection pooling.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self):
        self.base_url = MEMORY_HUB_URL
        self.default_user_id = MEMORY_HUB_USER_ID
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create shared HTTP client with connection pooling."""
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=30.0,
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                )
            return self._client

    async def close(self) -> None:
        """Close the HTTP client. Called from FastAPI lifespan shutdown."""
        async with self._lock:
            if self._client and not self._client.is_closed:
                await self._client.aclose()
                self._client = None

    async def check_status(self) -> Dict[str, Any]:
        """Check Memory Hub connectivity.

        Treats only 2xx/3xx as connected. A 4xx (e.g. 404 from a wrong URL,
        401 from misconfigured auth) means the hub is reachable but the
        endpoint is unusable, which the UI should surface as disconnected.
        """
        try:
            client = await self._get_client()
            resp = await client.get("/health", timeout=5.0)
            return {
                "connected": resp.status_code < 400,
                "status_code": resp.status_code,
                "url": _safe_host(self.base_url),
            }
        except Exception as e:
            # Log host only — full URL may carry creds or internal topology.
            safe_host = _safe_host(self.base_url)
            logger.warning(
                "Memory Hub not reachable at host {host}: {err}",
                host=safe_host,
                err=e,
            )
            # Same reasoning applies to the JSON response — never leak the
            # raw base_url to API clients (it may embed http://user:pass@…).
            return {
                "connected": False,
                "error": str(e),
                "url": safe_host,
            }

    async def browse_memories(
        self,
        user_id: Optional[str] = None,
        memory_type: str = "episodic_memory",
        limit: int = 20,
        offset: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Browse memories from EverOS with pagination.

        Proxies to POST /api/v1/memories/get (GetMemRequest).

        v1 uses page/page_size instead of limit/offset; we map by clamping
        offset down to the nearest page boundary. Callers should keep offset
        as an exact multiple of `limit` to avoid lossy rounding.
        """
        page_size = max(1, min(limit, 100))
        if offset and offset % page_size != 0:
            logger.warning(
                "browse_memories: offset=%s is not a multiple of limit=%s; "
                "rounding down to the nearest page boundary",
                offset,
                page_size,
            )
        page = (offset // page_size) + 1

        filters: Dict[str, Any] = {"user_id": user_id or self.default_user_id}
        if start_time or end_time:
            ts_filter: Dict[str, Any] = {}
            if start_time:
                ts_filter["gte"] = start_time
            if end_time:
                ts_filter["lte"] = end_time
            filters["timestamp"] = ts_filter

        payload: Dict[str, Any] = {
            "memory_type": memory_type,
            "page": page,
            "page_size": page_size,
            "rank_by": "timestamp",
            "rank_order": "desc",
            "filters": filters,
        }

        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/memories/get", json=payload)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data") or {}

            raw = self._extract_items(data, memory_type)
            memories = [m for m in (self._memory_to_item(r, memory_type) for r in raw) if m]

            # has_more must be derived from the RAW page count returned by the
            # server, not the post-normalization count, otherwise items dropped
            # by `_memory_to_item` (missing id, etc.) would skew pagination.
            raw_count = data.get("count", len(raw))
            total = data.get("total_count", raw_count)
            return {
                "memories": memories,
                "total_count": total,
                "has_more": (offset + raw_count) < total,
            }
        except httpx.HTTPError as e:
            logger.error("Failed to browse memories: {}", e)
            raise

    async def search_memories(
        self,
        query: str,
        user_id: Optional[str] = None,
        memory_types: Optional[List[str]] = None,
        retrieve_method: str = "hybrid",
        top_k: int = 20,
    ) -> Dict[str, Any]:
        """Search memories from EverOS.

        Proxies to POST /api/v1/memories/search (SearchMemoriesRequest).
        """
        if memory_types is None:
            memory_types = ["episodic_memory"]

        payload: Dict[str, Any] = {
            "query": query,
            "method": retrieve_method,
            "memory_types": memory_types,
            "top_k": top_k,
            "filters": {"user_id": user_id or self.default_user_id},
        }

        try:
            client = await self._get_client()
            resp = await client.post("/api/v1/memories/search", json=payload)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data") or {}

            memories: List[Dict[str, Any]] = []
            # Search response buckets each memory type in its own key.
            for bucket, mem_type in (
                ("episodes", "episodic_memory"),
                ("profiles", "profile"),
                ("raw_messages", "raw_message"),
            ):
                for raw in data.get(bucket) or []:
                    item = self._memory_to_item(raw, mem_type)
                    if item:
                        memories.append(item)

            return {
                "memories": memories,
                "total_count": len(memories),
                "has_more": False,
            }
        except httpx.HTTPError as e:
            logger.error("Failed to search memories: {}", e)
            raise

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_items(data: Dict[str, Any], memory_type: str) -> List[Dict[str, Any]]:
        """Pull the relevant list out of a GetMem response payload."""
        bucket_map = {
            "episodic_memory": "episodes",
            "profile": "profiles",
            "agent_case": "agent_cases",
            "agent_skill": "agent_skills",
        }
        bucket = bucket_map.get(memory_type, "episodes")
        items = data.get(bucket) or []
        return [m for m in items if isinstance(m, dict)]

    def _memory_to_item(
        self, mem: Dict[str, Any], memory_type: str
    ) -> Optional[Dict[str, Any]]:
        """Convert a single v1 memory payload to the flat MemoryItem the frontend expects."""
        mem_id = mem.get("id") or mem.get("episode_id") or mem.get("memory_id")
        if not mem_id:
            return None

        subject = mem.get("subject") or ""
        summary = mem.get("summary") or ""
        episode = mem.get("episode") or ""

        if memory_type == "episodic_memory":
            content = summary or episode
            title = subject or summary[:100] or episode[:100] or "Episodic Memory"
        elif memory_type == "profile":
            content = summary or mem.get("content", "")
            title = subject or content[:100] or "Profile"
        elif memory_type == "raw_message":
            content = mem.get("content") or episode
            title = content[:100] if content else "Raw Message"
        else:
            content = summary or mem.get("content", "") or episode
            title = subject or content[:100] or memory_type

        # Derive source origin from group_name + drop blocked origins.
        # Both rules live in open_notebook.utils.memory_origin so the
        # materializer (separate sub-package) can re-use the same logic.
        group_name = mem.get("group_name") or ""
        source_origin = classify_origin(group_name)
        if source_origin in MEMORY_BLOCKED_ORIGINS:
            return None

        # Score is inlined in the item under v1 (not in a separate scores[] array).
        score = mem.get("score")

        timestamp_raw = mem.get("timestamp") or mem.get("event_time")
        timestamp = str(timestamp_raw) if timestamp_raw else None

        return {
            "id": str(mem_id),
            "memory_type": memory_type,
            "title": title,
            "subject": subject or None,
            "summary": summary or None,
            "episode": episode or None,
            "content": content,
            "timestamp": timestamp,
            "source_origin": source_origin,
            "group_id": mem.get("group_id"),
            "group_name": group_name or None,
            "participants": mem.get("participants"),
            "keywords": mem.get("key_events") or mem.get("keywords"),
            "score": score,
        }


# Singleton instance
memory_service = MemoryService()
