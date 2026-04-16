"""
MyMemo Agent — Claude Agent SDK based assistant with skills + memory.

Invocation:
    python agent.py "your prompt here"
    python agent.py --skill code-reviewer "review this code"
    python agent.py --skill meeting-decision --memory  "should we use Kafka or SQS?"
    echo "prompt" | python agent.py --stdin

Output: NDJSON to stdout
    {"type":"thinking","text":"..."}     — reasoning trace
    {"type":"text","text":"..."}         — partial response
    {"type":"skill","name":"..."}        — skill activated
    {"type":"memory","files":["..."]}    — memory docs loaded
    {"type":"done","text":"..."}         — final complete response
    {"type":"error","message":"..."}     — failure

Environment:
    ANTHROPIC_BASE_URL  (default: https://dashscope.aliyuncs.com/apps/anthropic)
    ANTHROPIC_API_KEY   (required)
    ANTHROPIC_MODEL     (default: qwen3-coder-plus)
    MEMORY_HUB_URL      (default: http://localhost:1995)
    MEMORY_HUB_USER_ID  (default: mymemo_user)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

AGENT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = AGENT_DIR / "skills"
PROJECT_ROOT = AGENT_DIR.parent
MEMORY_DOCS_DIR = PROJECT_ROOT / "memory-docs"


def load_env():
    """Load memory-hub.env if present and map keys for Claude Agent SDK."""
    env_file = PROJECT_ROOT / "memory-hub.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    # Map LLM_API_KEY → ANTHROPIC_API_KEY if not already set
    # (memory-hub.env uses LLM_API_KEY, Claude Agent SDK needs ANTHROPIC_API_KEY)
    if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("LLM_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = os.environ["LLM_API_KEY"]


def get_config() -> dict[str, str]:
    # Use AGENT_* env vars first (MyMemo-specific), then fall back to general ones.
    # IMPORTANT: do NOT inherit ANTHROPIC_BASE_URL from parent process (Claude Code
    # sets it to api.anthropic.com which won't accept DashScope keys).
    return {
        "base_url": os.environ.get("AGENT_BASE_URL", "https://dashscope.aliyuncs.com/apps/anthropic"),
        "api_key": os.environ.get("AGENT_API_KEY") or os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("AGENT_MODEL", "qwen3-coder-plus"),
        "memory_hub_url": os.environ.get("MEMORY_HUB_URL", "http://localhost:1995"),
        "memory_hub_user_id": os.environ.get("MEMORY_HUB_USER_ID", "mymemo_user"),
    }


# ---------------------------------------------------------------------------
# NDJSON output
# ---------------------------------------------------------------------------

def emit(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


# ---------------------------------------------------------------------------
# Skill loader
# ---------------------------------------------------------------------------

def list_skills() -> dict[str, Path]:
    """Discover all .md skill files recursively."""
    skills: dict[str, Path] = {}
    if not SKILLS_DIR.exists():
        return skills
    for md in SKILLS_DIR.rglob("*.md"):
        name = md.stem  # e.g., "code-reviewer", "meeting-decision"
        skills[name] = md
    return skills


def load_skill(name: str) -> str | None:
    """Load a skill's .md content by name."""
    skills = list_skills()
    path = skills.get(name)
    if path and path.exists():
        return path.read_text(encoding="utf-8")
    return None


# ---------------------------------------------------------------------------
# Memory loader (from materialized .md files)
# ---------------------------------------------------------------------------

def load_memory_index() -> str | None:
    """Read INDEX.md to know available memory docs."""
    index_path = MEMORY_DOCS_DIR / "INDEX.md"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return None


def load_memory_doc(filename: str) -> str | None:
    """Read a specific memory .md file."""
    path = MEMORY_DOCS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def search_memories_http(query: str, cfg: dict[str, str]) -> list[dict[str, Any]]:
    """Direct HTTP search to EverCore (for when materialized docs aren't enough)."""
    import httpx
    try:
        with httpx.Client(base_url=cfg["memory_hub_url"], timeout=10.0) as c:
            r = c.post("/api/v1/memories/search", json={
                "query": query,
                "method": "hybrid",
                "memory_types": ["episodic_memory"],
                "top_k": 5,
                "filters": {"user_id": cfg["memory_hub_user_id"]},
            })
            r.raise_for_status()
            return r.json().get("data", {}).get("episodes", [])
    except Exception:
        return []


def intent_select_memory(prompt: str, index_content: str, cfg: dict[str, str]) -> list[str]:
    """Use LLM to select which memory .md files to load for this prompt."""
    import httpx
    llm_base = os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    llm_key = os.environ.get("LLM_API_KEY") or cfg["api_key"]
    llm_model = os.environ.get("LLM_MODEL", "qwen-long")

    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.post(f"{llm_base}/chat/completions", headers={
                "Authorization": f"Bearer {llm_key}",
                "Content-Type": "application/json",
            }, json={
                "model": llm_model,
                "messages": [
                    {"role": "system", "content": (
                        "You are a memory router. Select 0-3 files relevant to the user's prompt. "
                        "Return JSON: {\"files\": [\"file1.md\"]}"
                    )},
                    {"role": "user", "content": f"Files:\n{index_content}\n\nPrompt: {prompt}"},
                ],
                "max_tokens": 150,
                "temperature": 0,
            })
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text).get("files", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Build system prompt
# ---------------------------------------------------------------------------

def build_system_prompt(
    skill_name: str | None,
    memory_enabled: bool,
    prompt: str,
    cfg: dict[str, str],
) -> tuple[str, list[str]]:
    """Build the system prompt from skill + memory context.

    Returns (system_prompt, list_of_loaded_memory_files).
    """
    parts: list[str] = []
    loaded_files: list[str] = []

    # Base identity
    parts.append(
        "You are MyMemo Agent, a personal AI assistant with long-term memory "
        "and specialized skills. You help with coding, meeting analysis, "
        "project planning, and memory recall."
    )

    # Skill injection
    if skill_name:
        skill_content = load_skill(skill_name)
        if skill_content:
            emit({"type": "skill", "name": skill_name})
            parts.append(f"\n## Active Skill: {skill_name}\n\n{skill_content}")

    # Memory injection (intent-routed)
    if memory_enabled:
        index = load_memory_index()
        if index:
            selected = intent_select_memory(prompt, index, cfg)
            if selected:
                emit({"type": "memory", "files": selected})
                for filename in selected[:3]:
                    content = load_memory_doc(filename)
                    if content:
                        parts.append(f"\n## Memory: {filename}\n\n{content}")
                        loaded_files.append(filename)

        # If no materialized docs matched, fall back to search
        if not loaded_files:
            episodes = search_memories_http(prompt, cfg)
            if episodes:
                memory_text = "\n".join(
                    f"- [{ep.get('timestamp', '')}] {ep.get('subject', '')}: {(ep.get('summary') or '')[:200]}"
                    for ep in episodes[:5]
                )
                parts.append(f"\n## Memory (search results)\n\n{memory_text}")
                loaded_files.append("(search fallback)")
                emit({"type": "memory", "files": ["(search fallback)"]})

    return "\n\n".join(parts), loaded_files


# ---------------------------------------------------------------------------
# Run agent via Claude Agent SDK
# ---------------------------------------------------------------------------

async def run_agent(
    prompt: str,
    skill_name: str | None,
    memory_enabled: bool,
    subagent: str | None = None,
    max_turns: int = 1,
) -> int:
    """Main agent execution with optional subagent dispatch."""
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition
    except ImportError:
        emit({"type": "error", "message": "claude-agent-sdk not installed. Run: pip install claude-agent-sdk"})
        return 2

    cfg = get_config()
    if not cfg["api_key"]:
        emit({"type": "error", "message": "AGENT_API_KEY or LLM_API_KEY not set"})
        return 3

    system_prompt, loaded_files = build_system_prompt(skill_name, memory_enabled, prompt, cfg)

    # Build SDK-native subagent definitions
    agents_dict: dict[str, AgentDefinition] | None = None
    try:
        from subagents import SUBAGENT_SKILLS, get_subagent_prompt, list_subagent_skills
        agents_dict = {}
        for name, sa_cfg in SUBAGENT_SKILLS.items():
            sa_skills = list_subagent_skills(name)
            agents_dict[name] = AgentDefinition(
                description=f"{sa_cfg['description']} ({len(sa_skills)} skills)",
                prompt=get_subagent_prompt(name),
                model=sa_cfg.get("model"),
            )
        emit({"type": "subagents", "names": list(agents_dict.keys())})
    except ImportError:
        pass

    # If a specific subagent was requested, use its prompt as main system prompt
    if subagent:
        try:
            from subagents import get_subagent_prompt as gsp, SUBAGENT_SKILLS as SA
            if subagent in SA:
                system_prompt = gsp(subagent) + "\n\n" + system_prompt
                emit({"type": "subagent_active", "name": subagent})
        except ImportError:
            pass

    env = {
        "ANTHROPIC_BASE_URL": cfg["base_url"],
        "ANTHROPIC_API_KEY": cfg["api_key"],
    }

    options = ClaudeAgentOptions(
        model=cfg["model"],
        system_prompt=system_prompt,
        max_turns=max_turns,
        env=env,
        agents=agents_dict,
        permission_mode="bypassPermissions",
    )

    try:
        reply = ""
        async for message in query(prompt=prompt, options=options):
            if hasattr(message, "content"):
                blocks = message.content if isinstance(message.content, list) else [message.content]
                for block in blocks:
                    if hasattr(block, "text"):
                        reply += block.text
                        emit({"type": "text", "text": block.text})
                    elif isinstance(block, str):
                        reply += block
                        emit({"type": "text", "text": block})
            elif hasattr(message, "result") and hasattr(message.result, "text"):
                reply += message.result.text
                emit({"type": "text", "text": message.result.text})

        if not reply:
            emit({"type": "error", "message": "agent returned empty reply"})
            return 1

        emit({"type": "done", "text": reply})
        return 0

    except Exception as e:
        emit({"type": "error", "message": str(e)})
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    load_env()

    parser = argparse.ArgumentParser(description="MyMemo Agent — Claude Agent SDK assistant")
    parser.add_argument("prompt", nargs="*", help="User prompt")
    parser.add_argument("--stdin", action="store_true", help="Read prompt from stdin")
    parser.add_argument("--skill", "-s", type=str, default=None, help="Activate a skill by name")
    parser.add_argument("--subagent", "-a", type=str, default=None,
                        help="Route to a specific subagent (code-dev, meeting-advisor, project-manager, business-strategist, deep-thinker, content-creator, memory-manager, learning-researcher)")
    parser.add_argument("--max-turns", type=int, default=1, help="Max conversation turns (default: 1)")
    parser.add_argument("--memory", "-m", action="store_true", default=True, help="Enable memory context (default: on)")
    parser.add_argument("--no-memory", action="store_true", help="Disable memory context")
    parser.add_argument("--list-skills", action="store_true", help="List available skills and exit")
    parser.add_argument("--list-subagents", action="store_true", help="List available subagents and exit")

    # Meeting mode
    parser.add_argument("--meeting", type=str, default=None,
                        choices=["brief", "think", "chat", "summary", "writeback"],
                        help="Meeting mode: brief (pre), think (during), chat (during), summary (post), writeback (post)")
    parser.add_argument("--topic", type=str, default=None, help="Meeting topic")
    parser.add_argument("--participants", type=str, default=None, help="Comma-separated participant names")
    parser.add_argument("--agenda", type=str, default=None, help="Comma-separated agenda items")
    parser.add_argument("--scheduled-at", type=str, default=None, help="Meeting scheduled time")
    parser.add_argument("--transcript", type=str, default=None, help="Path to meeting transcript .md file")
    parser.add_argument("--auto-rules", action="store_true", help="Enable automatic trigger rule evaluation")
    parser.add_argument("--question", type=str, default=None, help="Question for meeting chat mode")
    parser.add_argument("--output", type=str, default=None, help="Output file path for summary")

    args = parser.parse_args()

    if args.list_skills:
        skills = list_skills()
        if skills:
            for name, path in sorted(skills.items()):
                category = path.parent.name
                emit({"type": "skill_info", "name": name, "category": category, "path": str(path)})
        else:
            emit({"type": "error", "message": "No skills found"})
        return

    if args.list_subagents:
        try:
            from subagents import SUBAGENT_SKILLS, list_subagent_skills
            for name, cfg in SUBAGENT_SKILLS.items():
                skills = list_subagent_skills(name)
                emit({
                    "type": "subagent_info",
                    "name": name,
                    "description": cfg["description"],
                    "categories": cfg["categories"],
                    "skill_count": len(skills),
                    "skills": skills[:10],
                })
        except ImportError:
            emit({"type": "error", "message": "subagents.py not found"})
        return

    # Meeting mode dispatch
    if args.meeting:
        from meeting import run_meeting_command
        sys.exit(run_meeting_command(args))

    if args.stdin:
        prompt = sys.stdin.read().strip()
    else:
        prompt = " ".join(args.prompt).strip()

    if not prompt:
        emit({"type": "error", "message": "empty prompt"})
        sys.exit(3)

    memory_enabled = args.memory and not args.no_memory
    exit_code = asyncio.run(run_agent(
        prompt, args.skill, memory_enabled,
        subagent=args.subagent,
        max_turns=args.max_turns,
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
