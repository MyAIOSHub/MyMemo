"""Single source of truth for memory origin classification + blocklist.

Both `api/memory_service.py` and `memory-hub-mcp/materializer.py` need to:
  1. Map an EverCore episode's `group_name` → an origin label
     ("browser" / "claude_code" / "sayso" / "evermemo").
  2. Honour MEMORY_BLOCKED_ORIGINS so noisy sources can be hidden.

Keeping the rules here means a future tweak (new ingestion source, renamed
group prefix) lands in one place and both consumers stay consistent.

The materializer is shipped as a separate sub-package under `memory-hub-mcp/`
and isn't on PYTHONPATH for end-users invoking the script directly. To stay
copy-paste-free, the materializer imports this module via a `sys.path` shim
(see materializer.py) when available, with a local fallback that mirrors the
same rules.
"""

from __future__ import annotations

import os
from typing import Mapping

# Default blocklist: high-volume sources that drown out signal in the
# materialized .md output and the /api/memories browse/search responses.
DEFAULT_BLOCKED = "browser,claude_code"


def parse_blocked_origins(raw: str | None) -> frozenset[str]:
    """Turn a comma-separated env value into a frozenset of origin labels."""
    if raw is None:
        raw = DEFAULT_BLOCKED
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def blocked_origins_from_env(env: Mapping[str, str] | None = None) -> frozenset[str]:
    """Read MEMORY_BLOCKED_ORIGINS from `env` (defaults to os.environ)."""
    src = env if env is not None else os.environ
    return parse_blocked_origins(src.get("MEMORY_BLOCKED_ORIGINS"))


def classify_origin(group_name: str | None) -> str:
    """Map an EverCore memory's group_name to a coarse origin label.

    The matching is substring-based so legacy group names (e.g.
    "MyBrowserTab", "CC-session-1") still resolve correctly. Returns
    "evermemo" for anything that doesn't match a known prefix.
    """
    if not group_name:
        return "evermemo"
    gn = group_name.lower()
    if "browser" in gn or "mymemo" in gn or "attention" in gn:
        return "browser"
    if "claude" in gn or "cc" in gn:
        return "claude_code"
    if "sayso" in gn:
        return "sayso"
    return "evermemo"
