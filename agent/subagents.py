"""
MyMemo Subagent Definitions — maps 167 skills into 7 scene-based subagents
for use with Claude Agent SDK's `agents` parameter.

Usage:
    from subagents import SUBAGENT_DEFINITIONS, load_subagent_skills

    # Get AgentDefinition-ready dicts
    agents = SUBAGENT_DEFINITIONS

    # Load all skill .md contents for a specific subagent
    skills_text = load_subagent_skills("code-dev")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# ---------------------------------------------------------------------------
# Subagent → skill category mapping
# ---------------------------------------------------------------------------

SUBAGENT_SKILLS: dict[str, dict[str, Any]] = {
    # === 开发场景 ===
    "code-dev": {
        "description": "Software development expert — code review, debugging, testing, architecture, DevOps, frontend/backend/mobile engineering",
        "categories": ["coding", "engineering", "dev-tools", "commands", "references"],
        "model": "sonnet",
    },

    # === 会议场景 ===
    "meeting-advisor": {
        "description": "Meeting analyst — decision making, Socratic questioning, risk analysis, retrospectives, brainstorming facilitation, meeting synthesis, tradeoff evaluation",
        "categories": ["meeting"],
        "model": "sonnet",
    },

    # === 项目管理场景 ===
    "project-manager": {
        "description": "Project management coordinator — planning, task breakdown, sprint management, git workflow, CI/CD, shipping, spec writing, code review process, branch management",
        "categories": ["workflow", "commands"],
        "model": "sonnet",
    },

    # === 商业讨论场景 ===
    "business-strategist": {
        "description": "Business strategy and marketing expert — market sizing, competitive analysis, product R&D planning, unit economics, JTBD analysis, consultant-style planning, moat evaluation",
        "categories": ["marketing", "diagnosis"],
        "model": "sonnet",
    },

    # === 深度思考场景 ===
    "deep-thinker": {
        "description": "Deep reasoning and analytical thinking — first principles, five whys, roundtable debate, pattern analysis, analogies, investment analysis, writing frameworks",
        "categories": ["thinking"],
        "model": "sonnet",
    },

    # === 内容创作场景 ===
    "content-creator": {
        "description": "Content creation specialist — articles, social media, WeChat publishing, copywriting, video scripts, newsletters, novels, multimedia content",
        "categories": ["content", "wechat"],
        "model": "sonnet",
    },

    # === 记忆管理场景 ===
    "memory-manager": {
        "description": "Long-term memory specialist — store, recall, search, organize, connect dots, generate insights, and maintain personal knowledge across sessions",
        "categories": ["memory", "clawiser", "insight"],
        "model": "sonnet",
    },

    # === 学习研究场景 ===
    "learning-researcher": {
        "description": "Learning and research assistant — study notes, flashcards, literature review, paper analysis, prerequisite mapping, knowledge gap identification",
        "categories": ["learning"],
        "model": "sonnet",
    },
}


def list_subagent_skills(subagent_name: str) -> list[str]:
    """List all skill names belonging to a subagent."""
    config = SUBAGENT_SKILLS.get(subagent_name)
    if not config:
        return []
    skills: list[str] = []
    for cat in config["categories"]:
        cat_dir = SKILLS_DIR / cat
        if cat_dir.is_dir():
            for md in sorted(cat_dir.glob("*.md")):
                skills.append(md.stem)
    return skills


def load_subagent_skills(subagent_name: str) -> str:
    """Load and concatenate all skill .md contents for a subagent."""
    config = SUBAGENT_SKILLS.get(subagent_name)
    if not config:
        return ""
    parts: list[str] = []
    for cat in config["categories"]:
        cat_dir = SKILLS_DIR / cat
        if not cat_dir.is_dir():
            continue
        for md in sorted(cat_dir.glob("*.md")):
            content = md.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"## Skill: {md.stem}\n\n{content}")
    return "\n\n---\n\n".join(parts)


def get_subagent_prompt(subagent_name: str) -> str:
    """Build a complete system prompt for a subagent, including its skills."""
    config = SUBAGENT_SKILLS.get(subagent_name)
    if not config:
        return ""

    skill_names = list_subagent_skills(subagent_name)
    skills_text = load_subagent_skills(subagent_name)

    # Truncate if too long (keep under ~30k chars to fit model context)
    if len(skills_text) > 30000:
        skills_text = skills_text[:30000] + "\n\n... (truncated)"

    return f"""You are MyMemo's {config['description']}.

You have access to {len(skill_names)} specialized skills:
{chr(10).join(f'  - {s}' for s in skill_names)}

When the user's request matches a skill, apply that skill's methodology.
When no skill matches directly, use your general expertise.

# Skills Reference

{skills_text}
"""


def build_agent_definitions() -> dict[str, dict[str, Any]]:
    """Build Claude Agent SDK AgentDefinition-compatible dicts for all subagents."""
    definitions: dict[str, dict[str, Any]] = {}
    for name, config in SUBAGENT_SKILLS.items():
        skill_names = list_subagent_skills(name)
        definitions[name] = {
            "description": f"{config['description']} ({len(skill_names)} skills)",
            "prompt": get_subagent_prompt(name),
            "model": config.get("model", "sonnet"),
        }
    return definitions


# Quick summary for CLI
if __name__ == "__main__":
    import json
    for name, config in SUBAGENT_SKILLS.items():
        skills = list_subagent_skills(name)
        cats = config["categories"]
        print(f"\n[{name}] — {config['description']}")
        print(f"  Categories: {', '.join(cats)}")
        print(f"  Skills ({len(skills)}): {', '.join(skills[:8])}{'...' if len(skills) > 8 else ''}")
