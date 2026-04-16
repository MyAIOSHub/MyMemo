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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MEMORY_HUB_URL = os.getenv("MEMORY_HUB_URL", "http://localhost:1995")
MEMORY_HUB_USER_ID = os.getenv("MEMORY_HUB_USER_ID", "mymemo_user")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-long")
MAX_TOKENS_PER_MD = 4000  # soft limit per .md file (chars, ~1000 tokens)
RECENT_DAYS = 3

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "memory-docs"


# ---------------------------------------------------------------------------
# EverCore client helpers
# ---------------------------------------------------------------------------

def _hub_post(path: str, payload: dict, timeout: float = 30.0) -> dict:
    with httpx.Client(base_url=MEMORY_HUB_URL, timeout=timeout) as c:
        r = c.post(path, json=payload)
        r.raise_for_status()
        return r.json()


def fetch_all_episodes(user_id: str, max_pages: int = 20) -> list[dict]:
    """Fetch all episodic memories from EverCore, paginated."""
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
        all_eps.extend(episodes)
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
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY not set — cannot classify memories")
    with httpx.Client(timeout=60.0) as c:
        r = c.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
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

    # Build subject list for batch classification
    subjects = []
    for i, ep in enumerate(episodes):
        subj = ep.get("subject") or ep.get("summary", "")[:100]
        subjects.append(f"{i}: {subj}")

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
        print(f"  LLM classification failed: {e}, falling back to group_name")
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


def summarize_for_md(project: str, episodes: list[dict]) -> str:
    """Use LLM to generate a coherent .md summary for a project's episodes."""
    # Build episode content
    ep_texts = []
    for ep in episodes[:30]:  # cap to avoid prompt overflow
        subject = ep.get("subject", "")
        summary = ep.get("summary", "")
        ts = ep.get("timestamp", "")
        ep_texts.append(f"[{ts}] {subject}\n{summary[:300]}")

    content = "\n---\n".join(ep_texts)

    system = (
        "You are a technical writer. Given episodic memories about a project, "
        "write a concise .md document summarizing the key knowledge. "
        "Include: project overview, recent decisions, technical details, "
        "current status. Use markdown headers. Keep under 3000 characters. "
        "Write in the same language as the input."
    )

    try:
        return _llm_call(system, f"Project: {project}\n\nMemories:\n{content}", max_tokens=4000)
    except Exception as e:
        # Fallback: raw concatenation
        lines = [f"# {project}\n"]
        for ep in episodes[:15]:
            lines.append(f"- **{ep.get('subject', 'Untitled')}** ({ep.get('timestamp', '')})")
            if ep.get("summary"):
                lines.append(f"  {ep['summary'][:200]}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# File generators
# ---------------------------------------------------------------------------

def generate_user_preferences(profiles: list[dict]) -> str:
    """Generate user-preferences.md from EverCore profile data."""
    if not profiles:
        return "# User Preferences\n\nNo profile data available yet.\n"

    lines = ["# User Preferences\n"]
    for p in profiles:
        summary = p.get("summary") or ""
        subject = p.get("subject") or ""
        if subject:
            lines.append(f"## {subject}\n")
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

    lines = [f"# Recent Focus (last {RECENT_DAYS} days)\n"]
    for ep in recent[:20]:
        subject = ep.get("subject", "Untitled")
        summary = (ep.get("summary") or "")[:200]
        ts = ep.get("timestamp", "")
        lines.append(f"## [{ts[:10]}] {subject}\n")
        if summary:
            lines.append(f"{summary}\n")
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
    """Run full materialization: fetch → classify → write .md files."""
    uid = user_id or MEMORY_HUB_USER_ID
    output_dir.mkdir(parents=True, exist_ok=True)
    stats: dict[str, Any] = {"files_written": 0, "episodes_processed": 0}

    print(f"Fetching episodes from {MEMORY_HUB_URL} for user={uid}...")
    episodes = fetch_all_episodes(uid)
    stats["episodes_processed"] = len(episodes)
    print(f"  Got {len(episodes)} episodes")

    profiles = fetch_profile(uid)
    print(f"  Got {len(profiles)} profiles")

    # 1. User preferences (from profiles)
    prefs_content = generate_user_preferences(profiles)
    (output_dir / "user-preferences.md").write_text(prefs_content, encoding="utf-8")
    stats["files_written"] += 1
    print(f"  Wrote user-preferences.md")

    # 2. Recent focus (from recent episodes)
    recent_content = generate_recent_focus(episodes)
    (output_dir / "recent-focus.md").write_text(recent_content, encoding="utf-8")
    stats["files_written"] += 1
    print(f"  Wrote recent-focus.md")

    # 3. Project files (LLM classification)
    if episodes:
        print(f"  Classifying {len(episodes)} episodes by project...")
        buckets = classify_episodes(episodes)
        for project_key, eps in buckets.items():
            if not eps:
                continue
            filename = f"{project_key}.md"
            print(f"  Summarizing {project_key} ({len(eps)} episodes)...")
            content = summarize_for_md(project_key, eps)
            (output_dir / filename).write_text(content, encoding="utf-8")
            stats["files_written"] += 1
            print(f"  Wrote {filename}")

    # 4. INDEX.md
    index_content = generate_index(output_dir)
    (output_dir / "INDEX.md").write_text(index_content, encoding="utf-8")
    print(f"  Wrote INDEX.md")

    # 5. Write timestamp marker for freshness check
    (output_dir / ".last_materialized").write_text(
        datetime.now(timezone.utc).isoformat(), encoding="utf-8"
    )

    print(f"\nDone: {stats['files_written']} files, {stats['episodes_processed']} episodes")
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
    parser = argparse.ArgumentParser(description="Materialize EverCore memories to .md files")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--user-id", type=str, default=None, help="EverCore user ID")
    args = parser.parse_args()

    # Load env from memory-hub.env if present
    env_file = Path(__file__).resolve().parent.parent / "memory-hub.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
        # Re-read after loading
        globals()["LLM_API_KEY"] = os.getenv("LLM_API_KEY", "")
        globals()["LLM_BASE_URL"] = os.getenv("LLM_BASE_URL", LLM_BASE_URL)
        globals()["LLM_MODEL"] = os.getenv("LLM_MODEL", LLM_MODEL)

    materialize(args.output, args.user_id)
