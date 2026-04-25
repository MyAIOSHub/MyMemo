"""MCP server for EverCore (EverOS) Memory Hub.

Exposes three tools over stdio transport:
  - search_memories: semantic/keyword/hybrid search
  - browse_memories: paginated listing by memory type
  - store_memory:    save a message as a new memory

Configuration via environment variables:
  MEMORY_HUB_URL      (default: http://localhost:1995)
  MEMORY_HUB_USER_ID  (default: mymemo_user)
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

MEMORY_HUB_URL = os.getenv("MEMORY_HUB_URL", "http://localhost:1995")
MEMORY_HUB_USER_ID = os.getenv("MEMORY_HUB_USER_ID", "mymemo_user")

mcp = FastMCP(
    "memory-hub",
    instructions=(
        "EverCore Memory Hub — long-term memory for AI agents. "
        "Use search_memories to find relevant past context, "
        "browse_memories to list memories by type, "
        "and store_memory to save new information."
    ),
)


def _post(path: str, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    """POST to EverCore v1 API and return parsed JSON."""
    with httpx.Client(base_url=MEMORY_HUB_URL, timeout=timeout) as client:
        resp = client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_memories(
    query: str,
    method: str = "hybrid",
    memory_types: list[str] | None = None,
    top_k: int = 10,
    user_id: str | None = None,
) -> str:
    """Search memories from EverCore Memory Hub.

    Returns the most relevant episodic memories, profiles, and raw messages
    matching the query. Use this when you need context from past sessions,
    decisions, or conversations.

    Args:
        query: Natural-language search query.
        method: Retrieval strategy — keyword, vector, hybrid (default), or agentic.
        memory_types: Memory types to search (default: ["episodic_memory"]).
        top_k: Maximum number of results to return.
        user_id: Override user ID (default from MEMORY_HUB_USER_ID env).
    """
    payload = {
        "query": query,
        "method": method,
        "memory_types": memory_types or ["episodic_memory"],
        "top_k": top_k,
        "filters": {"user_id": user_id or MEMORY_HUB_USER_ID},
    }
    result = _post("/api/v1/memories/search", payload)
    data = result.get("data") or {}

    # Format results as readable text for the LLM.
    lines: list[str] = []
    for bucket, label in (("episodes", "Episodic"), ("profiles", "Profile"), ("raw_messages", "Raw")):
        items = data.get(bucket) or []
        for item in items:
            score = item.get("score")
            subject = item.get("subject") or ""
            summary = item.get("summary") or item.get("episode") or item.get("content") or ""
            ts = item.get("timestamp") or ""
            score_str = f" (score: {score:.2f})" if score is not None else ""
            title = f"{subject}: {summary}" if subject else summary
            lines.append(f"[{label}]{score_str} {title}  [{ts}]")

    if not lines:
        return f'No memories found for query: "{query}"'
    return f"Found {len(lines)} memories:\n\n" + "\n".join(lines)


@mcp.tool()
def browse_memories(
    memory_type: str = "episodic_memory",
    page: int = 1,
    page_size: int = 20,
    user_id: str | None = None,
) -> str:
    """Browse memories from EverCore Memory Hub with pagination.

    Use this to list recent memories by type. Supports episodic_memory,
    profile, agent_case, agent_skill.

    Args:
        memory_type: Type of memories to browse.
        page: Page number (1-based).
        page_size: Number of items per page (max 100).
        user_id: Override user ID (default from MEMORY_HUB_USER_ID env).
    """
    payload = {
        "memory_type": memory_type,
        "page": page,
        "page_size": min(page_size, 100),
        "rank_by": "timestamp",
        "rank_order": "desc",
        "filters": {"user_id": user_id or MEMORY_HUB_USER_ID},
    }
    result = _post("/api/v1/memories/get", payload)
    data = result.get("data") or {}

    total = data.get("total_count", 0)
    count = data.get("count", 0)

    # Pull items from the matching bucket.
    bucket_map = {
        "episodic_memory": "episodes",
        "profile": "profiles",
        "agent_case": "agent_cases",
        "agent_skill": "agent_skills",
    }
    items = data.get(bucket_map.get(memory_type, "episodes")) or []

    lines: list[str] = []
    for item in items:
        subject = item.get("subject") or ""
        summary = item.get("summary") or item.get("episode") or ""
        ts = item.get("timestamp") or ""
        title = f"{subject}: {summary[:100]}" if subject else (summary[:120] or "(empty)")
        lines.append(f"  - [{ts}] {title}")

    header = f"Page {page} of {memory_type} ({count}/{total} total):"
    if not lines:
        return f"{header}\n  (no memories found)"
    return f"{header}\n" + "\n".join(lines)


@mcp.tool()
def store_memory(
    content: str,
    role: str = "user",
    user_id: str | None = None,
) -> str:
    """Store a message as a new memory in EverCore Memory Hub.

    The memory will be processed by EverCore's extraction pipeline
    (boundary detection, episode clustering, profile extraction) and
    become searchable once processing completes.

    Args:
        content: The message content to store as a memory.
        role: Message role — 'user' or 'assistant'.
        user_id: Override user ID (default from MEMORY_HUB_USER_ID env).
    """
    uid = user_id or MEMORY_HUB_USER_ID
    ts = int(time.time() * 1000)
    msg_id = "mcp_" + hashlib.sha256(f"{ts}:{role}:{content}".encode()).hexdigest()[:24]

    payload = {
        "user_id": uid,
        "messages": [
            {
                "message_id": msg_id,
                "sender_id": uid,
                "sender_name": uid if role == "user" else "assistant",
                "role": role,
                "timestamp": ts,
                "content": content,
            }
        ],
    }
    result = _post("/api/v1/memories", payload, timeout=90.0)
    data = result.get("data") or {}
    status = data.get("status", "unknown")
    count = data.get("message_count", 0)
    return f"Stored {count} message(s). Status: {status}"


@mcp.tool()
def refresh_memory_docs(output_dir: str | None = None) -> str:
    """Materialize EverCore memories into topic-based .md files.

    Fetches all episodic memories and profiles, classifies them by project
    using LLM, and writes structured .md files to the memory-docs/ directory.
    Call this to refresh the local .md cache when memories have changed.

    Args:
        output_dir: Override output directory. Must resolve INSIDE the
            allowlist (default `../memory-docs/`, or any path under
            `$MYMEMO_MATERIALIZE_ROOT` when that env var is set). Absolute
            traversal outside the allowlist is rejected.
    """
    import os
    from pathlib import Path
    from materializer import materialize, DEFAULT_OUTPUT

    if output_dir is None:
        target = DEFAULT_OUTPUT
    else:
        # Path-traversal guard: resolve, then assert the result is within
        # the allowlist. Default allowlist is the parent directory of
        # DEFAULT_OUTPUT (so siblings like project-foo.md can be written).
        allow_root_str = os.environ.get(
            "MYMEMO_MATERIALIZE_ROOT", str(DEFAULT_OUTPUT.parent)
        )
        allow_root = Path(allow_root_str).resolve()
        candidate = Path(output_dir).expanduser().resolve()
        try:
            candidate.relative_to(allow_root)
        except ValueError:
            return (
                f"output_dir {candidate} is outside allowed root {allow_root}; "
                "set MYMEMO_MATERIALIZE_ROOT to widen the allowlist."
            )
        target = candidate

    try:
        stats = materialize(target)
        return (
            f"Materialized {stats['episodes_processed']} episodes into "
            f"{stats['files_written']} .md files at {target}"
        )
    except Exception as e:
        return f"Materialization failed: {e}"


@mcp.tool()
def check_hub_status() -> str:
    """Check if Memory Hub is reachable and healthy."""
    try:
        with httpx.Client(base_url=MEMORY_HUB_URL, timeout=5.0) as client:
            resp = client.get("/health")
            if resp.status_code < 400:
                body = resp.json()
                return f"Memory Hub is healthy at {MEMORY_HUB_URL} — {body.get('message', 'OK')}"
            return f"Memory Hub returned HTTP {resp.status_code}"
    except Exception as e:
        return f"Memory Hub not reachable at {MEMORY_HUB_URL}: {e}"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
