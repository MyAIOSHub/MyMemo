"""Service for communicating with EverMemOS Memory Hub."""

import asyncio
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from open_notebook.config import MEMORY_HUB_URL, MEMORY_HUB_USER_ID


class MemoryService:
    """HTTP client for EverMemOS Memory Hub API.

    Uses a shared httpx.AsyncClient for connection pooling.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self):
        self.base_url = MEMORY_HUB_URL
        self.default_user_id = MEMORY_HUB_USER_ID
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create shared HTTP client with connection pooling.

        Uses asyncio.Lock to prevent race conditions under concurrent requests.
        """
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
        """Check Memory Hub connectivity."""
        try:
            client = await self._get_client()
            resp = await client.get("/health", timeout=5.0)
            return {
                "connected": resp.status_code < 500,
                "status_code": resp.status_code,
                "url": self.base_url,
            }
        except Exception as e:
            logger.warning(f"Memory Hub not reachable at {self.base_url}: {e}")
            return {
                "connected": False,
                "error": str(e),
                "url": self.base_url,
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
        """Browse memories from EverMemOS with pagination.

        Proxies to GET /api/v1/memories (FetchMemRequest).
        """
        params: Dict[str, Any] = {
            "user_id": user_id or self.default_user_id,
            "memory_type": memory_type,
            "limit": limit,
            "offset": offset,
        }
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        try:
            client = await self._get_client()
            resp = await client.get("/api/v1/memories", params=params)
            resp.raise_for_status()
            data = resp.json()

            result = data.get("result", {})
            raw_memories = result.get("memories", [])
            memories = self._normalize_fetch_memories(raw_memories, memory_type)

            return {
                "memories": memories,
                "total_count": result.get("total_count", len(memories)),
                "has_more": result.get("has_more", False),
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to browse memories: {e}")
            raise

    async def search_memories(
        self,
        query: str,
        user_id: Optional[str] = None,
        memory_types: Optional[List[str]] = None,
        retrieve_method: str = "hybrid",
        top_k: int = 20,
    ) -> Dict[str, Any]:
        """Search memories from EverMemOS.

        Proxies to GET /api/v1/memories/search (RetrieveMemRequest).
        """
        if memory_types is None:
            memory_types = ["episodic_memory", "event_log"]

        params: Dict[str, Any] = {
            "user_id": user_id or self.default_user_id,
            "query": query,
            "retrieve_method": retrieve_method,
            "top_k": top_k,
            "memory_types": memory_types,
        }

        try:
            client = await self._get_client()
            resp = await client.get("/api/v1/memories/search", params=params)
            resp.raise_for_status()
            data = resp.json()

            result = data.get("result", {})
            raw_memories = result.get("memories", [])
            scores = result.get("scores", [])
            memories = self._normalize_search_memories(raw_memories, scores)

            return {
                "memories": memories,
                "total_count": result.get("total_count", len(memories)),
                "has_more": result.get("has_more", False),
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to search memories: {e}")
            raise

    def _normalize_fetch_memories(
        self, raw_memories: List[Any], memory_type: str
    ) -> List[Dict[str, Any]]:
        """Normalize EverMemOS FetchMemResponse memories to flat MemoryItem list."""
        items = []
        for mem in raw_memories:
            if not isinstance(mem, dict):
                continue
            item = self._memory_to_item(mem, memory_type)
            if item:
                items.append(item)
        return items

    def _normalize_search_memories(
        self,
        raw_memories: List[Any],
        scores: List[Any],
    ) -> List[Dict[str, Any]]:
        """Normalize EverMemOS RetrieveMemResponse memories.

        Search response format: memories is List[Dict[str, List[BaseMemory]]]
        e.g., [{"episodic_memory": [...], "event_log": [...]}, ...]
        """
        items = []
        for group_idx, group in enumerate(raw_memories):
            if not isinstance(group, dict):
                continue
            for mem_type, mem_list in group.items():
                if not isinstance(mem_list, list):
                    continue
                for mem_idx, mem in enumerate(mem_list):
                    if not isinstance(mem, dict):
                        continue
                    item = self._memory_to_item(mem, mem_type)
                    if item:
                        # Attach score if available
                        try:
                            score_group = scores[group_idx] if group_idx < len(scores) else {}
                            score_list = score_group.get(mem_type, [])
                            if mem_idx < len(score_list):
                                item["score"] = score_list[mem_idx]
                        except (IndexError, KeyError, TypeError):
                            pass
                        items.append(item)
        return items

    def _memory_to_item(
        self, mem: Dict[str, Any], memory_type: str
    ) -> Optional[Dict[str, Any]]:
        """Convert a single EverMemOS memory dict to normalized MemoryItem."""
        mem_id = mem.get("id") or mem.get("episode_id")
        if not mem_id:
            return None

        # Determine content based on memory type
        if memory_type == "episodic_memory":
            content = mem.get("summary", "")
            title = mem.get("title") or mem.get("subject") or content[:100]
        elif memory_type == "event_log":
            content = mem.get("atomic_fact", "")
            title = content[:100] if content else "Event Log"
        elif memory_type == "foresight":
            content = mem.get("content", "")
            title = content[:100] if content else "Foresight"
        else:
            content = mem.get("content") or mem.get("summary", "")
            title = mem.get("title") or content[:100]

        # Determine source origin from metadata/group
        source_origin = "evermemo"
        group_name = mem.get("group_name", "")
        if group_name:
            gn_lower = group_name.lower()
            if "browser" in gn_lower or "mymemo" in gn_lower or "attention" in gn_lower:
                source_origin = "browser"
            elif "claude" in gn_lower or "cc" in gn_lower:
                source_origin = "claude_code"

        return {
            "id": str(mem_id),
            "memory_type": memory_type,
            "title": title,
            "summary": mem.get("summary"),
            "content": content,
            "timestamp": str(mem.get("timestamp", "")) if mem.get("timestamp") else None,
            "source_origin": source_origin,
            "group_id": mem.get("group_id"),
            "group_name": mem.get("group_name"),
            "participants": mem.get("participants"),
            "keywords": mem.get("key_events"),
        }


# Singleton instance
memory_service = MemoryService()
