"""
Granola Meeting Subagents — 4 phase-based agents wrapping skills extracted
from `prompts from granola.md`. Designed to plug into Claude Agent SDK's
`agents` parameter via AgentDefinition.

Phases:
  - prep        : @before a meeting — briefing, suggested topics, sales warm-up
  - live        : @during a meeting — backstory, smart contributions, decode jargon, recap
  - postprocess : @after a meeting  — TL;DR, follow-up email, todos, blind spots, coaching
  - cross       : @across meetings  — weekly recap, state-of-me, pipeline prep, decisions log

Each subagent loads every .md skill in its phase directory and concatenates
them into the system prompt. Skill .md files use YAML-ish frontmatter with
`trigger:` lists so the orchestrator can route slash commands to a subagent.

Usage:
    from granola_subagents import build_granola_agent_definitions, list_phase_skills

    agents = build_granola_agent_definitions()  # dict[name, AgentDefinition-shaped dict]
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parent / "skills" / "granola"

# ---------------------------------------------------------------------------
# Phase → subagent config
# ---------------------------------------------------------------------------

GRANOLA_SUBAGENTS: dict[str, dict[str, Any]] = {
    "granola-prep": {
        "phase": "prep",
        "phase_zh": "会前",
        "phase_en_label": "BEFORE the meeting",
        "description": (
            "【会前 / BEFORE】Pre-meeting prep specialist. "
            "中文场景：会议开始前的准备工作 —— 议程建议、参会人背景、最近一次相关会议回顾、"
            "销售场景下的破冰话术与发现式提问。"
            "EN: Activate ONLY when the meeting has not started yet. Generates briefing "
            "notes, suggested topics, prospect rapport lines, and discovery questions. "
            "Skills: suggest-topics, look-again, sales-affirm, sales-questions, joke. "
            "Do NOT use for live in-meeting requests, post-meeting artifacts, or cross-"
            "meeting synthesis."
        ),
        "model": "sonnet",
    },
    "granola-live": {
        "phase": "live",
        "phase_zh": "会中",
        "phase_en_label": "DURING the meeting",
        "description": (
            "【会中 / DURING】Live in-meeting copilot. "
            "中文场景：会议进行中的实时辅助 —— 给一段话题的来龙去脉、让我接得上话、"
            "建议追问、解释黑话、决策框架、生成 Linear 工单、收尾确认下一步。"
            "EN: Activate ONLY while the meeting is in progress. Provides 20-second "
            "backstory recaps, smart contributions, follow-up questions, jargon "
            "decoding, decision frameworks, Linear ticket links, and end-of-meeting "
            "wrap-ups. Skills: backstory, make-me-sound-smart, suggest-questions, "
            "what-does-that-mean, help-me-decide, create-linear-ticket, "
            "recap-next-steps. Do NOT use for prep, post-meeting artifacts, or "
            "cross-meeting work."
        ),
        "model": "sonnet",
    },
    "granola-postprocess": {
        "phase": "postprocess",
        "phase_zh": "会后",
        "phase_en_label": "AFTER the meeting",
        "description": (
            "【会后 / AFTER】Post-meeting processor (single-meeting artifacts). "
            "中文场景：单场会议结束后的产出 —— 三句话总结、跟进邮件、待办列表、"
            "盲点风险分析、帮助文档、内容生产计划、约下次会议的日历/邮件链接、"
            "Matt Mochary 风格的教练反馈、把痛点改写为 LinkedIn 设计简报、"
            "拉长或缩短笔记。"
            "EN: Activate AFTER a single meeting ends, when transforming that meeting's "
            "transcript or notes into shareable artifacts. Skills: write-tldr, "
            "write-followup-email, list-todos, blind-spots, create-help-doc, "
            "devrel-content, schedule-followup, coach-me-matt, pain-point-linkedin, "
            "notes-shorter, notes-longer. Do NOT use for prep, live moments, or "
            "synthesis across multiple meetings (use granola-cross for that)."
        ),
        "model": "sonnet",
    },
    "granola-cross": {
        "phase": "cross",
        "phase_zh": "跨会议",
        "phase_en_label": "ACROSS multiple meetings",
        "description": (
            "【跨会议 / ACROSS】Cross-meeting synthesizer (multi-meeting / time-window). "
            "中文场景：跨多场会议或一段时间窗的综合分析 —— 周报、向上汇报的 State of Me、"
            "销售管道复盘、在飞项目状态、关键决策列表、最近 N 天的待办、"
            "下次会议准备简报、谁还欠我没交、文件夹/主题汇总、本周近况。"
            "EN: Activate when synthesizing across MULTIPLE meetings or a time window "
            "(last 7 days, last 2 weeks, this week). Skills: list-recent-todos, "
            "weekly-recap, state-of-me, prep-next-meeting, catch-me-up, "
            "list-key-decisions, in-flight-projects, pipeline-prep, who-owes-me, "
            "summarize-folder. Do NOT use for prep of a single upcoming meeting, "
            "live moments, or single-meeting post-processing."
        ),
        "model": "sonnet",
    },
}


# ---------------------------------------------------------------------------
# Skill discovery + frontmatter parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_TRIGGER_LINE_RE = re.compile(r'^trigger:\s*\[(.+)\]\s*$', re.MULTILINE)


def _parse_skill(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {"name": path.stem, "triggers": [], "body": text, "path": path}
    fm, body = m.group(1), m.group(2)
    triggers: list[str] = []
    tm = _TRIGGER_LINE_RE.search(fm)
    if tm:
        triggers = [
            t.strip().strip('"').strip("'")
            for t in tm.group(1).split(",")
            if t.strip()
        ]
    name = path.stem
    name_match = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
    if name_match:
        name = name_match.group(1).strip().strip('"').strip("'")
    return {"name": name, "triggers": triggers, "body": body, "path": path}


def list_phase_skills(phase: str) -> list[dict[str, Any]]:
    """Discover every skill .md under `skills/granola/<phase>/`."""
    phase_dir = SKILLS_ROOT / phase
    if not phase_dir.is_dir():
        return []
    return [_parse_skill(p) for p in sorted(phase_dir.glob("*.md"))]


def all_skill_index() -> dict[str, dict[str, Any]]:
    """Build a lookup of every trigger → (subagent, skill) across all phases."""
    index: dict[str, dict[str, Any]] = {}
    for sub_name, cfg in GRANOLA_SUBAGENTS.items():
        for skill in list_phase_skills(cfg["phase"]):
            for trig in skill["triggers"]:
                index[trig.lower()] = {
                    "subagent": sub_name,
                    "phase": cfg["phase"],
                    "skill": skill["name"],
                    "path": str(skill["path"]),
                }
    return index


# Chinese phase-keyword fallbacks. Slash commands remain English (universal);
# this map only triggers when no English trigger matched. Each entry routes to
# a subagent based on Chinese phrasing patterns.
_ZH_PHASE_KEYWORDS: dict[str, str] = {
    # prep
    "会前": "granola-prep", "开会前": "granola-prep", "准备会议": "granola-prep",
    "会议准备": "granola-prep", "议程建议": "granola-prep", "话题建议": "granola-prep",
    "破冰": "granola-prep", "暖场": "granola-prep",
    # live
    "会中": "granola-live", "正在开会": "granola-live", "刚才说的": "granola-live",
    "背景信息": "granola-live", "什么意思": "granola-live", "解释一下": "granola-live",
    "追问": "granola-live", "提问": "granola-live", "总结下一步": "granola-live",
    "帮我决定": "granola-live", "做决定": "granola-live", "工单": "granola-live",
    "linear单": "granola-live",
    # postprocess
    "会后": "granola-postprocess", "纪要": "granola-postprocess",
    "tldr": "granola-postprocess", "三句话总结": "granola-postprocess",
    "三句话": "granola-postprocess", "总结这个会议": "granola-postprocess",
    "总结会议": "granola-postprocess", "总结这次会议": "granola-postprocess",
    "会议总结": "granola-postprocess",
    "跟进邮件": "granola-postprocess", "后续邮件": "granola-postprocess",
    "待办": "granola-postprocess", "任务清单": "granola-postprocess",
    "盲点": "granola-postprocess", "风险分析": "granola-postprocess",
    "帮助文档": "granola-postprocess", "教练我": "granola-postprocess",
    "缩短笔记": "granola-postprocess", "扩写笔记": "granola-postprocess",
    "约下次会议": "granola-postprocess", "安排下次": "granola-postprocess",
    # cross
    "跨会议": "granola-cross", "周报": "granola-cross", "每周回顾": "granola-cross",
    "本周总结": "granola-cross", "向上汇报": "granola-cross",
    "近期待办": "granola-cross", "最近的待办": "granola-cross",
    "决策列表": "granola-cross", "关键决策": "granola-cross",
    "在飞项目": "granola-cross", "进行中项目": "granola-cross",
    "管道复盘": "granola-cross", "销售管道": "granola-cross",
    "下次会议准备": "granola-cross", "下次会准备": "granola-cross",
    "近况": "granola-cross", "最近发生了什么": "granola-cross",
    "谁欠我": "granola-cross", "别人答应我的": "granola-cross",
    "总结这个文件夹": "granola-cross", "汇总文件夹": "granola-cross",
}


def route_command_to_subagent(command_or_text: str) -> str | None:
    """Match user input against skill triggers. Returns subagent name or None."""
    text = command_or_text.lower().strip()
    index = all_skill_index()

    # Exact slash command match first
    if text in index:
        return index[text]["subagent"]

    # Prefix match (e.g. "/recap-next-steps please" → "/recap-next-steps")
    for trigger, info in index.items():
        if text.startswith(trigger + " ") or text == trigger:
            return info["subagent"]

    # English natural-language substring match
    for trigger, info in index.items():
        if not trigger.startswith("/") and trigger in text:
            return info["subagent"]

    # Chinese phase-keyword fallback (lowercase already applied)
    for kw, subagent in _ZH_PHASE_KEYWORDS.items():
        if kw in text:
            return subagent

    return None


# ---------------------------------------------------------------------------
# System-prompt assembly
# ---------------------------------------------------------------------------

_PHASE_GUIDANCE: dict[str, str] = {
    "prep": (
        "You are operating BEFORE a meeting starts (会前). The user has limited "
        "time and wants to walk in oriented. Default to scannable bullets, "
        "suggested topics framed as possibilities (not directives), and human "
        "language with no jargon. Confirm context you used at the end. "
        "Boundary: do NOT generate post-meeting artifacts (TL;DR, follow-up "
        "email, todo list) here — those belong to the AFTER phase."
    ),
    "live": (
        "You are operating DURING a live meeting (会中). Optimize for speed "
        "and readability — the user has seconds, not minutes. Skip preamble. "
        "Default outputs: short bullets, first-person voice when contributing, "
        "no quotation marks. The user can read your reply in 20 seconds or "
        "less. Boundary: do NOT write polished emails or weekly recaps here — "
        "those belong to the AFTER or ACROSS phases."
    ),
    "postprocess": (
        "You are operating AFTER a meeting ends (会后), processing ONE "
        "meeting's transcript/notes into shareable artifacts: emails, TL;DRs, "
        "todo lists, risk analyses, help docs, calendar links. Match the "
        "exact output format demanded by each skill. Use placeholders like "
        "[Insert ARR] / [请填写ARR] when data is missing rather than "
        "inventing numbers. Boundary: do NOT synthesize across multiple "
        "meetings here — that belongs to the ACROSS phase."
    ),
    "cross": (
        "You are operating ACROSS multiple meetings (跨会议) or a time "
        "window (last 7 days, last 2 weeks, this week). Anchor to the user's "
        "stated 'today' (or the query date if none given). Synthesize themes; "
        "do not list every meeting. Group by day / project / person where "
        "useful. Be opinionated about what matters; cut filler. Boundary: do "
        "NOT generate single-meeting artifacts here — those belong to the "
        "AFTER phase."
    ),
}


def build_subagent_prompt(subagent_name: str) -> str:
    cfg = GRANOLA_SUBAGENTS.get(subagent_name)
    if not cfg:
        return ""
    phase = cfg["phase"]
    skills = list_phase_skills(phase)

    skill_index_lines = []
    skill_bodies = []
    for s in skills:
        triggers = ", ".join(f"`{t}`" for t in s["triggers"]) or "(no explicit triggers)"
        skill_index_lines.append(f"- **{s['name']}** — triggers: {triggers}")
        skill_bodies.append(f"## Skill: {s['name']}\n\n{s['body'].strip()}")

    skill_index = "\n".join(skill_index_lines) or "(no skills loaded)"
    skill_text = "\n\n---\n\n".join(skill_bodies) or "(no skill content)"

    # Truncate for safety on very long phases
    if len(skill_text) > 35000:
        skill_text = skill_text[:35000] + "\n\n... (truncated)"

    phase_zh = cfg.get("phase_zh", "")
    phase_label = cfg.get("phase_en_label", phase.upper())
    header = f"Granola Meeting Agent — **{phase_label}** subagent"
    if phase_zh:
        header += f" / **{phase_zh}** 子代理"

    return f"""You are MyMemo's {header}.

{cfg['description']}

## Phase Guidance

{_PHASE_GUIDANCE[phase]}

## Available Skills ({len(skills)})

{skill_index}

## Routing Rule

When the user's input matches a skill's trigger (slash command or natural phrasing), apply that skill's methodology *exactly* as written — formats, headings, constraints, output templates. When no skill matches directly, use the closest skill in this phase or fall back to general meeting expertise consistent with the phase guidance above.

## Skill Contents

{skill_text}
"""


def build_granola_agent_definitions() -> dict[str, dict[str, Any]]:
    """Return AgentDefinition-shaped dicts for all 4 granola subagents.

    Caller should wrap each into claude_agent_sdk.AgentDefinition before passing
    to ClaudeAgentOptions(agents=...).
    """
    out: dict[str, dict[str, Any]] = {}
    for name, cfg in GRANOLA_SUBAGENTS.items():
        skills = list_phase_skills(cfg["phase"])
        out[name] = {
            "description": f"{cfg['description']} ({len(skills)} skills loaded)",
            "prompt": build_subagent_prompt(name),
            "model": cfg.get("model", "sonnet"),
        }
    return out


# ---------------------------------------------------------------------------
# CLI summary
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for name, cfg in GRANOLA_SUBAGENTS.items():
        skills = list_phase_skills(cfg["phase"])
        print(f"\n[{name}] phase={cfg['phase']} model={cfg['model']}")
        for s in skills:
            trig = ", ".join(s["triggers"][:3]) or "(no triggers)"
            print(f"  - {s['name']:<28} {trig}")
    print("\nTotal triggers indexed:", len(all_skill_index()))
