"""Shared helpers used by agent.py + meeting.py.

Single source of truth for:
- NDJSON `emit()` (was duplicated in agent.py and meeting.py)
- `load_hub_env()` env-file parsing (was duplicated in agent.py + meeting.py
  + memory-hub-mcp/materializer.py)
- `EverCoreClient`, a thin sync httpx client (was open-coded in three places)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


# ---------------------------------------------------------------------------
# NDJSON emit (was agent.py:79 + meeting.py:477)
# ---------------------------------------------------------------------------


def emit(event: Dict[str, Any]) -> None:
    """Write a single NDJSON event to stdout. Used as agent IPC protocol."""
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Env-file loader (was load_env / _load_env / __main__ block in materializer)
# ---------------------------------------------------------------------------


def load_hub_env(env_file: Optional[Path] = None) -> None:
    """Read `memory-hub.env` (or any KEY=VAL file) and call `os.environ.setdefault`.

    Walks `KEY=VAL` lines, ignores comments + blanks. Idempotent —
    `setdefault` keeps already-exported values.
    """
    if env_file is None:
        # default: <project_root>/memory-hub.env
        env_file = Path(__file__).resolve().parent.parent / "memory-hub.env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


# ---------------------------------------------------------------------------
# EverCore Memory Hub client — sync, used outside FastAPI's async loop.
# ---------------------------------------------------------------------------


class EverCoreClient:
    """Thin sync httpx wrapper for EverCore v1 + the local-store / cc proxies.

    All three previous open-coded sites (memory-hub-mcp, materializer, agent)
    used the same path / payload shape. Centralizing here means auth-header
    or base-URL changes happen in one place.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        user_id: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url or os.environ.get(
            "MEMORY_HUB_URL", "http://localhost:1995"
        )
        self.user_id = user_id or os.environ.get("MEMORY_HUB_USER_ID", "mymemo_user")
        self.timeout = timeout

    def post(self, path: str, payload: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=timeout or self.timeout) as c:
            r = c.post(path, json=payload)
            r.raise_for_status()
            return r.json()

    def search(
        self,
        query: str,
        method: str = "hybrid",
        memory_types: Optional[list] = None,
        top_k: int = 5,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.post(
            "/api/v1/memories/search",
            {
                "query": query,
                "method": method,
                "memory_types": memory_types or ["episodic_memory"],
                "top_k": top_k,
                "filters": {"user_id": user_id or self.user_id},
            },
        )

    def get_memories(
        self,
        memory_type: str = "episodic_memory",
        page: int = 1,
        page_size: int = 100,
        user_id: Optional[str] = None,
        rank_by: str = "timestamp",
        rank_order: str = "desc",
    ) -> Dict[str, Any]:
        return self.post(
            "/api/v1/memories/get",
            {
                "memory_type": memory_type,
                "page": page,
                "page_size": page_size,
                "rank_by": rank_by,
                "rank_order": rank_order,
                "filters": {"user_id": user_id or self.user_id},
            },
        )

    def store(
        self,
        messages: list,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.post(
            "/api/v1/memories",
            {
                "user_id": user_id or self.user_id,
                "messages": messages,
            },
        )

    def health(self) -> int:
        with httpx.Client(base_url=self.base_url, timeout=5.0) as c:
            r = c.get("/health")
            return r.status_code
