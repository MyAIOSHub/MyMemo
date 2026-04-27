"""
Granola Meeting Agent — Claude Agent SDK orchestrator wrapping 4 phase-based
subagents (prep, live, postprocess, cross). Inspired by Granola's recipe
catalogue (`prompts from granola.md`).

Invocation:
    python granola_agent.py /suggest-topics --topic "Platform sync" --participants "Sam,Jane"
    python granola_agent.py /backstory --transcript meeting.md
    python granola_agent.py /write-tldr --transcript meeting.md
    python granola_agent.py /catch-me-up --memory
    echo "Help me decide between Kafka and SQS" | python granola_agent.py --stdin --phase live

Output: NDJSON to stdout (same envelope as agent.py)
    {"type":"granola_subagent","name":"...","phase":"..."}
    {"type":"skill_routed","trigger":"/...","skill":"..."}
    {"type":"text","text":"..."}
    {"type":"done","text":"..."}
    {"type":"error","message":"..."}
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parent
MEMORY_DOCS_DIR = PROJECT_ROOT / "memory-docs"

# Make this module runnable both as a script (`python agent/granola_agent.py`)
# and as a package member (`python -m agent.granola_agent`) from project root.
for _p in (str(AGENT_DIR), str(PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from agent._shared import EverCoreClient, emit, load_hub_env  # type: ignore
except ImportError:
    from _shared import EverCoreClient, emit, load_hub_env  # type: ignore

try:
    from agent.granola_subagents import (  # type: ignore
        GRANOLA_SUBAGENTS,
        all_skill_index,
        build_granola_agent_definitions,
        list_phase_skills,
        route_command_to_subagent,
    )
except ImportError:
    from granola_subagents import (  # type: ignore
        GRANOLA_SUBAGENTS,
        all_skill_index,
        build_granola_agent_definitions,
        list_phase_skills,
        route_command_to_subagent,
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_env():
    load_hub_env(PROJECT_ROOT / "memory-hub.env")
    if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("LLM_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = os.environ["LLM_API_KEY"]


_CJK_RE = __import__("re").compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def detect_language(text: str, threshold: float = 0.10) -> str:
    """Return 'zh' if CJK char ratio >= threshold of non-space chars, else 'en'.

    Uses character-ratio not absolute count — handles short slash commands
    mixed with Chinese context, and avoids false-positive on a single emoji-
    range glyph in otherwise English text.
    """
    if not text:
        return "en"
    stripped = "".join(text.split())
    if not stripped:
        return "en"
    cjk = len(_CJK_RE.findall(stripped))
    return "zh" if (cjk / len(stripped)) >= threshold else "en"


_LANG_DIRECTIVE: dict[str, str] = {
    "zh": (
        "## 语言规则（强制）\n\n"
        "用户输入为中文。**整段回复必须使用中文**，包括标题、列表项、字段名、"
        "占位符（如 `[请填写公司名称]`，不要保留英文 `[Insert company name]`）、"
        "邮件正文、表格表头。\n\n"
        "保留不翻译：\n"
        "- 代码块、命令、URL、文件路径、变量名、API 字段名\n"
        "- 专有产品名（Linear / Granola / Gmail / Google Calendar 等）\n"
        "- 技术缩写（PRD / TL;DR / RAPID / OKR / KPI / DRI 等）\n\n"
        "Skill 模板里的英文标题（如 `Pain point:` / `Target audience:`）翻译为中文"
        "（`痛点：` / `目标受众：`），但保持原有结构和顺序。Markdown 链接的可见文本"
        "翻译为中文，URL 部分保持原样。"
    ),
    "en": (
        "## Language Rule (mandatory)\n\n"
        "User input is in English. **Reply entirely in English**, matching the "
        "exact field labels, section headings, and placeholders defined by each "
        "skill template. Do not translate skill-defined labels."
    ),
}


def get_config() -> dict[str, str]:
    return {
        "base_url": os.environ.get(
            "AGENT_BASE_URL",
            "https://dashscope.aliyuncs.com/apps/anthropic",
        ),
        "api_key": os.environ.get("AGENT_API_KEY") or os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("AGENT_MODEL", "qwen3-coder-plus"),
        "memory_hub_url": os.environ.get("MEMORY_HUB_URL", "http://localhost:1995"),
        "memory_hub_user_id": os.environ.get("MEMORY_HUB_USER_ID", "mymemo_user"),
    }


# ---------------------------------------------------------------------------
# Context loading (transcript + memory)
# ---------------------------------------------------------------------------

def load_transcript(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        emit({"type": "warning", "message": f"transcript not found: {path}"})
        return ""
    return p.read_text(encoding="utf-8")


def load_memory_context(prompt: str, cfg: dict[str, str], max_episodes: int = 5) -> str:
    """Pull recent relevant episodes from EverCore via search."""
    try:
        client = EverCoreClient(
            base_url=cfg["memory_hub_url"],
            user_id=cfg["memory_hub_user_id"],
            timeout=10.0,
        )
        episodes = client.search(prompt, top_k=max_episodes).get("data", {}).get("episodes", [])
    except Exception:
        return ""

    if not episodes:
        return ""

    lines = []
    for ep in episodes[:max_episodes]:
        ts = ep.get("timestamp", "")
        subj = ep.get("subject", "")
        summ = (ep.get("summary") or "")[:300]
        lines.append(f"- [{ts}] **{subj}** — {summ}")
    return "## Memory Context (recent episodes)\n\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Subagent dispatch
# ---------------------------------------------------------------------------

def select_subagent(
    explicit_phase: str | None,
    explicit_subagent: str | None,
    user_text: str,
) -> tuple[str, str]:
    """Return (subagent_name, reason)."""
    if explicit_subagent:
        if explicit_subagent in GRANOLA_SUBAGENTS:
            return explicit_subagent, "explicit-subagent-flag"
        # Allow short form: prep/live/postprocess/cross → granola-<phase>
        candidate = f"granola-{explicit_subagent}"
        if candidate in GRANOLA_SUBAGENTS:
            return candidate, "explicit-subagent-flag"

    if explicit_phase:
        for name, cfg in GRANOLA_SUBAGENTS.items():
            if cfg["phase"] == explicit_phase:
                return name, "explicit-phase-flag"

    routed = route_command_to_subagent(user_text)
    if routed:
        return routed, "trigger-match"

    # Default fallback: live (most common in-context use)
    return "granola-live", "default-fallback"


def build_user_prompt(
    raw_prompt: str,
    transcript: str,
    memory_context: str,
    extra_context: dict[str, str] | None = None,
) -> str:
    parts: list[str] = []
    if extra_context:
        meta_lines = [f"- {k}: {v}" for k, v in extra_context.items() if v]
        if meta_lines:
            parts.append("## Meeting Metadata\n\n" + "\n".join(meta_lines))
    if transcript:
        parts.append("## Transcript / Notes\n\n" + transcript[:25000])
    if memory_context:
        parts.append(memory_context)
    parts.append("## User Request\n\n" + raw_prompt)
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# SDK runner
# ---------------------------------------------------------------------------

async def run_granola_agent(
    user_prompt: str,
    subagent_name: str,
    transcript: str,
    memory_enabled: bool,
    extra_context: dict[str, str] | None = None,
    max_turns: int = 1,
    lang: str = "auto",
) -> int:
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition
    except ImportError:
        emit({"type": "error", "message": "claude-agent-sdk not installed. Run: pip install claude-agent-sdk"})
        return 2

    cfg = get_config()
    if not cfg["api_key"]:
        emit({"type": "error", "message": "AGENT_API_KEY or LLM_API_KEY not set"})
        return 3

    # Build all 4 subagent definitions so the SDK can also delegate via Task tool
    agent_defs_raw = build_granola_agent_definitions()
    agents_dict: dict[str, AgentDefinition] = {
        name: AgentDefinition(
            description=d["description"],
            prompt=d["prompt"],
            model=d["model"],
        )
        for name, d in agent_defs_raw.items()
    }

    # Active subagent's prompt becomes the system prompt for the main loop
    active = agent_defs_raw[subagent_name]

    # Language detection — input language drives output language
    if lang == "auto":
        # Detect from the strongest signal: transcript first (longer, more
        # representative), then user prompt as fallback.
        sample = (transcript[:2000] + " " + user_prompt) if transcript else user_prompt
        detected = detect_language(sample)
    else:
        detected = lang if lang in _LANG_DIRECTIVE else "en"

    emit({"type": "language", "detected": detected, "mode": lang})

    system_prompt = active["prompt"] + "\n\n" + _LANG_DIRECTIVE[detected]

    emit({
        "type": "granola_subagent",
        "name": subagent_name,
        "phase": GRANOLA_SUBAGENTS[subagent_name]["phase"],
    })

    # Memory context
    memory_block = ""
    if memory_enabled:
        memory_block = load_memory_context(user_prompt, cfg)
        if memory_block:
            emit({"type": "memory", "files": ["(EverCore search)"]})

    full_prompt = build_user_prompt(user_prompt, transcript, memory_block, extra_context)

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
        async for message in query(prompt=full_prompt, options=options):
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

def cmd_list_subagents():
    for name, cfg in GRANOLA_SUBAGENTS.items():
        skills = list_phase_skills(cfg["phase"])
        emit({
            "type": "granola_subagent_info",
            "name": name,
            "phase": cfg["phase"],
            "description": cfg["description"],
            "skill_count": len(skills),
            "skills": [s["name"] for s in skills],
        })


def cmd_list_triggers():
    for trigger, info in sorted(all_skill_index().items()):
        emit({"type": "trigger_info", "trigger": trigger, **info})


def main():
    load_env()

    parser = argparse.ArgumentParser(
        description="Granola Meeting Agent — 4 phase-based subagents (prep/live/postprocess/cross)"
    )
    parser.add_argument("prompt", nargs="*", help="User prompt or slash command")
    parser.add_argument("--stdin", action="store_true", help="Read prompt from stdin")
    parser.add_argument("--phase", choices=["prep", "live", "postprocess", "cross"],
                        help="Force a specific phase subagent")
    parser.add_argument("--subagent", "-a", help="Specific subagent (granola-prep|live|postprocess|cross)")
    parser.add_argument("--max-turns", type=int, default=1)
    parser.add_argument("--memory", "-m", action="store_true", default=True)
    parser.add_argument("--no-memory", action="store_true")

    # Meeting context
    parser.add_argument("--topic", help="Meeting topic / title")
    parser.add_argument("--participants", help="Comma-separated names")
    parser.add_argument("--scheduled-at", dest="scheduled_at", help="Meeting scheduled time")
    parser.add_argument("--transcript", help="Path to transcript .md / .txt file")
    parser.add_argument("--today", help="Override 'today' anchor for cross-meeting skills (YYYY-MM-DD)")
    parser.add_argument("--lang", choices=["auto", "zh", "en"], default="auto",
                        help="Output language. 'auto' (default) follows input language.")

    # Inspection
    parser.add_argument("--list-subagents", action="store_true")
    parser.add_argument("--list-triggers", action="store_true",
                        help="Show every slash command → subagent mapping")

    args = parser.parse_args()

    if args.list_subagents:
        cmd_list_subagents()
        return
    if args.list_triggers:
        cmd_list_triggers()
        return

    if args.stdin:
        user_prompt = sys.stdin.read().strip()
    else:
        user_prompt = " ".join(args.prompt).strip()

    if not user_prompt:
        emit({"type": "error", "message": "empty prompt"})
        sys.exit(3)

    subagent_name, reason = select_subagent(args.phase, args.subagent, user_prompt)
    emit({"type": "subagent_selected", "name": subagent_name, "reason": reason})

    transcript = load_transcript(args.transcript)
    extra_context = {
        "topic": args.topic or "",
        "participants": args.participants or "",
        "scheduled_at": args.scheduled_at or "",
        "today": args.today or "",
    }

    memory_enabled = args.memory and not args.no_memory
    exit_code = asyncio.run(run_granola_agent(
        user_prompt=user_prompt,
        subagent_name=subagent_name,
        transcript=transcript,
        memory_enabled=memory_enabled,
        extra_context=extra_context,
        max_turns=args.max_turns,
        lang=args.lang,
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
