"""Memory Materializer — converts EverCore episodes into topic-based .md files.

Fetches episodic memories and profiles from EverCore, classifies them by
project/topic using LLM, and writes structured .md files to `memory-docs/`.

Usage:
    python materializer.py                  # default output to ./memory-docs/
    python materializer.py --output /path   # custom output directory

Environment:
    MEMORY_HUB_URL       (default: http://localhost:1995)
    MEMORY_HUB_USER_ID   (default: mymemo_user)
    LLM_API_KEY          (required — DashScope Bailian key)
    LLM_BASE_URL         (default: https://dashscope.aliyuncs.com/compatible-mode/v1)
    LLM_MODEL            (default: qwen-long)
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config — read at call-time, not at import. Storing secrets in module globals
# (and patching them later via globals()[...]) was both fragile and exposed
# LLM_API_KEY to anyone who imported this module.
# ---------------------------------------------------------------------------


def _hub_url() -> str:
    return os.getenv("MEMORY_HUB_URL", "http://localhost:1995")


def _hub_user_id() -> str:
    return os.getenv("MEMORY_HUB_USER_ID", "mymemo_user")


def _llm_api_key() -> str:
    return os.getenv("LLM_API_KEY", "")


def _llm_base_url() -> str:
    return os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")


def _llm_model() -> str:
    return os.getenv("LLM_MODEL", "qwen-long")


# memory-hub-mcp ships as its own folder and isn't always on PYTHONPATH.
# When the parent project is importable, reuse the canonical origin helper;
# otherwise keep an in-file fallback that mirrors the same rules so the
# script still works standalone.
try:
    from open_notebook.utils.memory_origin import (
        blocked_origins_from_env as _blocked_origins,
        classify_origin,
    )

    def _episode_origin(ep: dict) -> str:
        return classify_origin(ep.get("group_name"))

except ImportError:  # pragma: no cover — exercised only outside the project venv
    def _blocked_origins() -> frozenset[str]:
        raw = os.getenv("MEMORY_BLOCKED_ORIGINS", "browser,claude_code")
        return frozenset(s.strip() for s in raw.split(",") if s.strip())

    def _episode_origin(ep: dict) -> str:
        gn = (ep.get("group_name") or "").lower()
        if "browser" in gn or "mymemo" in gn or "attention" in gn:
            return "browser"
        if "claude" in gn or "cc" in gn:
            return "claude_code"
        if "sayso" in gn:
            return "sayso"
        return "evermemo"


# Backwards-compat shims — old `from materializer import MEMORY_HUB_URL` etc.
# now resolve via getattr but force callers to read the *current* env value.
MEMORY_HUB_URL = _hub_url()
MEMORY_HUB_USER_ID = _hub_user_id()
LLM_BASE_URL = _llm_base_url()
LLM_MODEL = _llm_model()
MAX_TOKENS_PER_MD = 4000  # soft limit per .md file (chars, ~1000 tokens)
RECENT_DAYS = 3

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "memory-docs"


# ---------------------------------------------------------------------------
# Prompt-injection guard
# ---------------------------------------------------------------------------


def _sanitize_for_prompt(text: str, *, max_len: int = 200) -> str:
    """Strip control chars + structural tokens before feeding to an LLM.

    Memory subjects/summaries originate from untrusted inputs (Claude Code
    transcripts, browser-attention captures) and could contain role-hijacking
    sequences like ``\\nSYSTEM: ignore previous`` or JSON-breaking quotes that
    let an attacker pivot the classifier output (and therefore filenames /
    written content).
    """
    if not text:
        return ""
    out = text.replace("\r", " ").replace("\n", " ")
    out = "".join(ch for ch in out if ch.isprintable())
    # Drop characters that would let crafted memories close out the JSON shape.
    for token in ("```", "\\u", '"role"', "system:", "SYSTEM:"):
        out = out.replace(token, " ")
    return out[:max_len]


# ---------------------------------------------------------------------------
# EverCore client helpers
# ---------------------------------------------------------------------------

def _hub_post(path: str, payload: dict, timeout: float = 30.0) -> dict:
    with httpx.Client(base_url=_hub_url(), timeout=timeout) as c:
        r = c.post(path, json=payload)
        r.raise_for_status()
        return r.json()


def fetch_all_episodes(user_id: str, max_pages: int = 20) -> list[dict]:
    """Fetch all episodic memories from EverCore, paginated.

    Filters out episodes whose derived origin is in MEMORY_BLOCKED_ORIGINS
    (default: browser, claude_code) so the materialized .md output stays
    focused on signal-rich sources.
    """
    blocked = _blocked_origins()
    all_eps: list[dict] = []
    for page in range(1, max_pages + 1):
        result = _hub_post("/api/v1/memories/get", {
            "memory_type": "episodic_memory",
            "page": page,
            "page_size": 100,
            "rank_by": "timestamp",
            "rank_order": "desc",
            "filters": {"user_id": user_id},
        })
        episodes = result.get("data", {}).get("episodes", [])
        kept = [ep for ep in episodes if _episode_origin(ep) not in blocked]
        all_eps.extend(kept)
        if len(episodes) < 100:
            break
    return all_eps


def fetch_profile(user_id: str) -> list[dict]:
    """Fetch user profile from EverCore."""
    result = _hub_post("/api/v1/memories/get", {
        "memory_type": "profile",
        "page": 1,
        "page_size": 10,
        "filters": {"user_id": user_id},
    })
    return result.get("data", {}).get("profiles", [])


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _llm_call(system: str, user: str, max_tokens: int = 2000) -> str:
    """Call DashScope-compatible LLM and return assistant content."""
    api_key = _llm_api_key()
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set — cannot classify memories")
    with httpx.Client(timeout=60.0) as c:
        r = c.post(
            f"{_llm_base_url()}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _llm_model(),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.1,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def classify_episodes(episodes: list[dict]) -> dict[str, list[dict]]:
    """Use LLM to classify episodes into project/topic buckets.

    Returns: { "project-mymemo": [ep, ...], "project-myteam": [...], "misc": [...] }
    """
    if not episodes:
        return {}

    # Build subject list for batch classification.
    # Sanitize each subject before embedding into the LLM prompt — see
    # `_sanitize_for_prompt` for the threat model.
    subjects = []
    for i, ep in enumerate(episodes):
        raw = ep.get("subject") or ep.get("summary", "")[:100]
        subjects.append(f"{i}: {_sanitize_for_prompt(raw, max_len=120)}")

    subjects_text = "\n".join(subjects[:200])  # cap at 200 for prompt length

    system = (
        "You are a memory classifier. Given a list of memory episode subjects "
        "(numbered), extract the project name for each. "
        "Return a JSON object mapping index number to project name (lowercase, "
        "hyphenated). Use 'misc' for episodes that don't belong to any specific project. "
        "Use 'user-preferences' for episodes about personal preferences/habits. "
        "Example: {\"0\": \"myteam\", \"1\": \"mymemo\", \"2\": \"misc\"}"
    )

    try:
        raw = _llm_call(system, subjects_text, max_tokens=4000)
        # Extract JSON from response (may have markdown fences)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        mapping = json.loads(raw)
    except Exception as e:
        logger.warning(
            "LLM classification failed: %s, falling back to group_name", e
        )
        mapping = {}

    # Build buckets
    buckets: dict[str, list[dict]] = defaultdict(list)
    for i, ep in enumerate(episodes[:200]):
        project = mapping.get(str(i))
        if not project:
            # Fallback: derive from group_name
            gn = (ep.get("group_name") or "").lower()
            if "mymemo" in gn or "open-notebook" in gn or "notebook" in gn:
                project = "mymemo"
            elif "myteam" in gn or "multica" in gn:
                project = "myteam"
            else:
                project = "misc"
        buckets[f"project-{project}"].append(ep)

    # Remaining episodes beyond 200 go to misc
    for ep in episodes[200:]:
        buckets["project-misc"].append(ep)

    return dict(buckets)


def _build_source_index(episodes: list[dict]) -> str:
    """Build a source index section linking back to EverCore episodes."""
    if not episodes:
        return ""
    lines = ["\n---\n", "## Source Index\n",
             "| # | Episode ID | Session | Timestamp | Subject |",
             "|---|-----------|---------|-----------|---------|"]
    seen_ids: set[str] = set()
    for i, ep in enumerate(episodes):
        ep_id = ep.get("id", "")
        if not ep_id or ep_id in seen_ids:
            continue
        seen_ids.add(ep_id)
        session = ep.get("session_id", "")[:12]
        ts = (ep.get("timestamp") or "")[:19]
        subject = (ep.get("subject") or "")[:50].replace("|", "/")
        lines.append(f"| {i+1} | `{ep_id[:16]}` | `{session}` | {ts} | {subject} |")
    return "\n".join(lines) + "\n"


def summarize_for_md(project: str, episodes: list[dict]) -> str:
    """Use LLM to generate a coherent .md summary for a project's episodes."""
    # Build episode content. Sanitize subject + summary so untrusted memory
    # text can't smuggle role-hijacking sequences into the writer prompt.
    ep_texts = []
    for ep in episodes[:30]:  # cap to avoid prompt overflow
        subject = _sanitize_for_prompt(ep.get("subject", ""), max_len=200)
        summary = _sanitize_for_prompt(ep.get("summary", ""), max_len=300)
        ts = ep.get("timestamp", "")
        ep_id = ep.get("id", "")[:16]
        ep_texts.append(f"[{ts}] (ep:{ep_id}) {subject}\n{summary}")

    content = "\n---\n".join(ep_texts)

    system = (
        "You are a technical writer. Given episodic memories about a project, "
        "write a concise .md document summarizing the key knowledge. "
        "Include: project overview, recent decisions, technical details, "
        "current status. Use markdown headers. Keep under 3000 characters. "
        "Write in the same language as the input. "
        "IMPORTANT: When referencing specific information from an episode, "
        "include the episode reference tag (ep:xxxx) inline so readers can "
        "trace back to the source."
    )

    try:
        summary = _llm_call(system, f"Project: {project}\n\nMemories:\n{content}", max_tokens=4000)
    except Exception as e:
        # Fallback: raw concatenation
        lines = [f"# {project}\n"]
        for ep in episodes[:15]:
            ep_id = ep.get("id", "")[:16]
            lines.append(f"- **{ep.get('subject', 'Untitled')}** ({ep.get('timestamp', '')}) `ep:{ep_id}`")
            if ep.get("summary"):
                lines.append(f"  {ep['summary'][:200]}")
        summary = "\n".join(lines)

    # Append source index table
    summary += _build_source_index(episodes)
    return summary


# ---------------------------------------------------------------------------
# File generators
# ---------------------------------------------------------------------------

def generate_user_preferences(profiles: list[dict]) -> str:
    """Generate user-preferences.md from EverCore profile data."""
    if not profiles:
        return "# User Preferences\n\nNo profile data available yet.\n"

    lines = ["# User Preferences\n"]
    for p in profiles:
        p_id = p.get("id", "")[:16]
        summary = p.get("summary") or ""
        subject = p.get("subject") or ""
        if subject:
            lines.append(f"## {subject}")
        if p_id:
            lines.append(f"> Source: `profile:{p_id}`\n")
        if summary:
            lines.append(f"{summary}\n")
    return "\n".join(lines) if len(lines) > 1 else "# User Preferences\n\nProfile data is still being built.\n"


def generate_recent_focus(episodes: list[dict]) -> str:
    """Generate recent-focus.md from the most recent episodes."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    recent = []
    for ep in episodes:
        ts_str = ep.get("timestamp", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if ts >= cutoff:
                recent.append(ep)
        except (ValueError, TypeError):
            continue

    if not recent:
        return f"# Recent Focus (last {RECENT_DAYS} days)\n\nNo recent activity.\n"

    # Dedup by episode ID
    seen: set[str] = set()
    deduped: list[dict] = []
    for ep in recent:
        ep_id = ep.get("id", "")
        if ep_id and ep_id not in seen:
            seen.add(ep_id)
            deduped.append(ep)

    lines = [f"# Recent Focus (last {RECENT_DAYS} days)\n"]
    for ep in deduped[:20]:
        ep_id = ep.get("id", "")[:16]
        session_id = ep.get("session_id", "")[:12]
        subject = ep.get("subject", "Untitled")
        summary = (ep.get("summary") or "")[:200]
        ts = ep.get("timestamp", "")
        lines.append(f"## [{ts[:10]}] {subject}")
        lines.append(f"> Source: `ep:{ep_id}` | session:`{session_id}` | {ts}\n")
        if summary:
            lines.append(f"{summary}\n")

    lines.append(_build_source_index(deduped))
    return "\n".join(lines)


def generate_index(output_dir: Path) -> str:
    """Generate INDEX.md listing all .md files with one-line summaries."""
    lines = ["# Memory Documents Index\n",
             f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    for md_file in sorted(output_dir.glob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        # Read first non-empty, non-header line as summary
        summary = ""
        for line in md_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("Last updated"):
                summary = stripped[:120]
                break
        lines.append(f"- **[{md_file.name}]({md_file.name})** — {summary}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def materialize(output_dir: Path, user_id: str | None = None) -> dict[str, Any]:
    """Run full materialization: fetch → classify → write .md files.

    Logs progress via `logger.info` instead of `print` because this function
    is also reachable from the MCP server, where stdout is the JSON-RPC wire
    protocol. CLI users can configure the root logger to mirror logs to
    stdout if desired.
    """
    uid = user_id or _hub_user_id()
    output_dir.mkdir(parents=True, exist_ok=True)
    stats: dict[str, Any] = {"files_written": 0, "episodes_processed": 0}

    logger.info("Fetching episodes from %s for user=%s...", _hub_url(), uid)
    episodes = fetch_all_episodes(uid)
    stats["episodes_processed"] = len(episodes)
    logger.info("  Got %d episodes", len(episodes))

    profiles = fetch_profile(uid)
    logger.info("  Got %d profiles", len(profiles))

    # 1. User preferences (from profiles)
    prefs_content = generate_user_preferences(profiles)
    (output_dir / "user-preferences.md").write_text(prefs_content, encoding="utf-8")
    stats["files_written"] += 1
    logger.info("  Wrote user-preferences.md")

    # 2. Recent focus (from recent episodes)
    recent_content = generate_recent_focus(episodes)
    (output_dir / "recent-focus.md").write_text(recent_content, encoding="utf-8")
    stats["files_written"] += 1
    logger.info("  Wrote recent-focus.md")

    # 3. Project files (LLM classification)
    if episodes:
        logger.info("  Classifying %d episodes by project...", len(episodes))
        buckets = classify_episodes(episodes)
        for project_key, eps in buckets.items():
            if not eps:
                continue
            filename = f"{project_key}.md"
            logger.info("  Summarizing %s (%d episodes)...", project_key, len(eps))
            content = summarize_for_md(project_key, eps)
            (output_dir / filename).write_text(content, encoding="utf-8")
            stats["files_written"] += 1
            logger.info("  Wrote %s", filename)

    # 4. INDEX.md
    index_content = generate_index(output_dir)
    (output_dir / "INDEX.md").write_text(index_content, encoding="utf-8")
    logger.info("  Wrote INDEX.md")

    # 5. Write timestamp marker for freshness check
    (output_dir / ".last_materialized").write_text(
        datetime.now(timezone.utc).isoformat(), encoding="utf-8"
    )

    logger.info(
        "Done: %d files, %d episodes",
        stats["files_written"],
        stats["episodes_processed"],
    )
    return stats


def is_fresh(output_dir: Path, max_age_minutes: int = 30) -> bool:
    """Check if materialized .md files are still fresh."""
    marker = output_dir / ".last_materialized"
    if not marker.exists():
        return False
    try:
        ts = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
        age = datetime.now(timezone.utc) - ts
        return age < timedelta(minutes=max_age_minutes)
    except (ValueError, OSError):
        return False


if __name__ == "__main__":
    # CLI mode: surface progress to stdout so users see what's happening.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Materialize EverCore memories to .md files")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--user-id", type=str, default=None, help="EverCore user ID")
    args = parser.parse_args()

    # Reuse the shared env-file loader. After this, every call-site reads via
    # `_llm_api_key()` etc., so module globals don't need patching.
    try:
        from agent._shared import load_hub_env
    except ImportError:
        # If memory-hub-mcp is run without the agent package on PYTHONPATH,
        # fall back to inline parsing.
        def load_hub_env(env_file: Path | None = None) -> None:
            env_file = env_file or Path(__file__).resolve().parent.parent / "memory-hub.env"
            if not env_file.exists():
                return
            for raw in env_file.read_text().splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    load_hub_env()

    materialize(args.output, args.user_id)
