"""Meeting Orchestrator — 会前/会中/会后全闭环。

Ported from MyIsland's MeetingAdviceEngine + MeetingCoordinator architecture.
Uses direct LLM HTTP calls (not Claude Agent SDK) for speed in meeting context.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from meeting_models import (
    AdviceCard,
    MeetingConfig,
    MeetingRecord,
    RouteDecision,
    SummaryBundle,
    TranscriptSegment,
    TriggerContext,
    TriggerRule,
    parse_transcript_md,
)
from meeting_prompts import (
    BRIEFING_PROMPT,
    CHAT_PROMPT,
    ROUTE_PROMPT,
    SUMMARY_PROMPT,
    THINKING_PROMPT,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DOCS_DIR = PROJECT_ROOT / "memory-docs"
SKILLS_DIR = Path(__file__).resolve().parent / "skills" / "meeting"


from agent._shared import EverCoreClient, emit as _shared_emit, load_hub_env


def _load_env():
    """Thin wrapper kept for backward compatibility — delegates to load_hub_env."""
    load_hub_env(PROJECT_ROOT / "memory-hub.env")


def _get_llm_config() -> dict[str, str]:
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", "qwen-long"),
    }


def _get_memory_hub_config() -> dict[str, str]:
    return {
        "url": os.environ.get("MEMORY_HUB_URL", "http://localhost:1995"),
        "user_id": os.environ.get("MEMORY_HUB_USER_ID", "mymemo_user"),
    }


# ---------------------------------------------------------------------------
# LLM Call
# ---------------------------------------------------------------------------

def _llm_call(prompt: str, system: str = "", max_tokens: int = 4000) -> str:
    cfg = _get_llm_config()
    if not cfg["api_key"]:
        raise RuntimeError("LLM_API_KEY not set")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    with httpx.Client(timeout=90.0) as c:
        r = c.post(f"{cfg['base_url']}/chat/completions", headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        }, json={
            "model": cfg["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        })
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def _parse_json_from_llm(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Memory Integration
# ---------------------------------------------------------------------------

def _load_memory_for_topic(topic: str) -> tuple[str, list[str]]:
    """Use intent router to select relevant memory .md files."""
    index_path = MEMORY_DOCS_DIR / "INDEX.md"
    if not index_path.exists():
        return "", []

    index = index_path.read_text(encoding="utf-8")
    try:
        result = _llm_call(
            f"Files:\n{index}\n\nTopic: {topic}",
            system=(
                "You are a memory router. Select 0-3 files relevant to the meeting topic. "
                "Return JSON: {\"files\": [\"file1.md\"]}"
            ),
            max_tokens=150,
        )
        files = _parse_json_from_llm(result).get("files", [])
    except Exception:
        files = ["recent-focus.md"]

    parts: list[str] = []
    loaded: list[str] = []
    for fname in files[:3]:
        fp = MEMORY_DOCS_DIR / fname
        if fp.exists():
            parts.append(fp.read_text(encoding="utf-8"))
            loaded.append(fname)

    return "\n\n---\n\n".join(parts), loaded


# ---------------------------------------------------------------------------
# Subagent & Skill Routing (ported from MyIsland)
# ---------------------------------------------------------------------------

MEETING_SUBAGENTS: dict[str, list[str]] = {
    "socratic": ["meeting-socratic", "meeting-jtbd"],
    "first_principles": ["meeting-first-principles", "meeting-five-whys"],
    "critic": ["meeting-critic", "meeting-tradeoff"],
    "debate": ["meeting-tradeoff", "meeting-roundtable"],
    "roundtable": ["meeting-roundtable", "meeting-divergence"],
    "decision": ["meeting-decision", "meeting-tradeoff"],
    "execution": ["meeting-execution", "meeting-pattern"],
    "risk": ["meeting-risk", "meeting-antipattern"],
    "business": ["meeting-business", "meeting-unit-economics", "meeting-moat"],
    "retrospective": ["meeting-retrospective", "meeting-pattern"],
}

ROUTE_MAP: dict[tuple[str, str], list[str]] = {
    ("requirements_clarification", "define_problem"): ["socratic", "first_principles", "critic"],
    ("requirements_clarification", "test_premise"): ["first_principles", "critic", "socratic"],
    ("solution_review", "compare_options"): ["critic", "debate", "roundtable"],
    ("solution_review", "test_premise"): ["first_principles", "critic", "debate"],
    ("decision_commit", "force_decision"): ["decision", "risk", "debate"],
    ("decision_commit", "compare_options"): ["decision", "critic", "roundtable"],
    ("execution_alignment", "unblock_execution"): ["execution", "socratic", "decision"],
    ("execution_alignment", "force_decision"): ["execution", "decision", "risk"],
    ("brainstorming", "prompt_next"): ["roundtable", "first_principles", "business"],
    ("brainstorming", "define_problem"): ["socratic", "roundtable", "first_principles"],
    ("risk_retro", "extract_lessons"): ["risk", "retrospective", "critic"],
    ("risk_retro", "test_premise"): ["risk", "first_principles", "critic"],
    ("business_evaluation", "assess_business"): ["business", "critic", "first_principles"],
    ("business_evaluation", "compare_options"): ["business", "debate", "roundtable"],
    ("retrospective", "extract_lessons"): ["retrospective", "socratic", "first_principles"],
    ("retrospective", "define_problem"): ["retrospective", "socratic", "critic"],
}

# Fallback
_DEFAULT_SUBAGENTS = ["socratic", "critic", "roundtable"]


def _load_skills(skill_ids: list[str]) -> str:
    """Load skill .md content."""
    parts = []
    for sid in skill_ids:
        path = SKILLS_DIR / f"{sid}.md"
        if path.exists():
            parts.append(f"## {sid}\n\n{path.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)


def route_decision(topic: str, recent_segments: list[TranscriptSegment]) -> RouteDecision:
    """Use LLM to determine meeting theme and subtask, then map to subagents."""
    recent_text = "\n".join(f"[{s.speaker or '?'}] {s.text}" for s in recent_segments[-12:])

    try:
        result = _llm_call(ROUTE_PROMPT.format(topic=topic, recent_text=recent_text), max_tokens=200)
        parsed = _parse_json_from_llm(result)
        theme = parsed.get("theme", "brainstorming")
        subtask = parsed.get("subtask", "prompt_next")
        why = parsed.get("why", "")
    except Exception:
        theme, subtask, why = "brainstorming", "prompt_next", "fallback"

    subagents = ROUTE_MAP.get((theme, subtask), _DEFAULT_SUBAGENTS)
    skill_ids = []
    for sa in subagents:
        skill_ids.extend(MEETING_SUBAGENTS.get(sa, []))
    skill_ids = list(dict.fromkeys(skill_ids))  # dedup preserving order

    return RouteDecision(
        theme=theme, subtask=subtask,
        subagents=subagents, skill_ids=skill_ids, why=why,
    )


# ---------------------------------------------------------------------------
# Trigger Rules (JSON-Logic evaluator)
# ---------------------------------------------------------------------------

DEFAULT_RULES: list[TriggerRule] = [
    TriggerRule("repeated_debate", "重复争论", "话题反复拉扯没结论",
                {"and": [{">=": [{"var": "repeated_tail_count"}, 2]},
                         {"==": [{"var": "decision_mention_count"}, 0]}]}),
    TriggerRule("missing_owner", "缺少Owner", "有行动项但没负责人",
                {"and": [{">=": [{"var": "action_cue_count"}, 1]},
                         {"==": [{"var": "owner_mention_count"}, 0]}]}),
    TriggerRule("unclear_problem", "问题没定义清楚", "提问多但问题模糊",
                {"and": [{">=": [{"var": "question_cue_count"}, 2]},
                         {"<": [{"var": "problem_definition_count"}, 1]}]}),
    TriggerRule("no_convergence", "没有收敛", "讨论多但没结论",
                {"and": [{">=": [{"var": "recent_segment_count"}, 8]},
                         {"==": [{"var": "decision_mention_count"}, 0]},
                         {"<": [{"var": "owner_mention_count"}, 1]}]}),
]


def _eval_json_logic(logic: dict | list | str | int | float | bool, data: dict) -> Any:
    """Minimal JSON-Logic evaluator (var, and, or, ==, >=, >, <, <=)."""
    if isinstance(logic, (str, int, float, bool)):
        return logic
    if isinstance(logic, list):
        return [_eval_json_logic(item, data) for item in logic]
    if not isinstance(logic, dict) or not logic:
        return logic
    op = next(iter(logic))
    args = logic[op]
    if not isinstance(args, list):
        args = [args]

    if op == "var":
        return data.get(args[0], 0)
    if op == "and":
        return all(_eval_json_logic(a, data) for a in args)
    if op == "or":
        return any(_eval_json_logic(a, data) for a in args)

    # Comparison
    vals = [_eval_json_logic(a, data) for a in args]
    if len(vals) < 2:
        return False
    a, b = vals[0], vals[1]
    if op == "==":
        return a == b
    if op == ">=":
        return a >= b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    return False


_CUE_PATTERNS: dict[str, list[str]] = {
    "owner": ["负责人", "owner", "我来", "你来", "谁来"],
    "action": ["待办", "行动项", "follow up", "下一步", "安排", "action"],
    "question": ["为什么", "问题", "?", "？", "how", "why", "what"],
    "problem_def": ["目标", "问题定义", "success", "约束", "前提", "scope"],
    "decision": ["结论", "决定", "定了", "拍板", "方案确定", "敲定"],
}


def build_trigger_context(segments: list[TranscriptSegment]) -> TriggerContext:
    """Aggregate signal counts from recent transcript."""
    recent = segments[-12:]
    texts = [s.text.lower() for s in recent]
    full = " ".join(texts)

    # Repeated tail: how many of the last 3 segments have the same normalized text
    tails = [re.sub(r"\s+", "", t) for t in texts[-3:]] if len(texts) >= 3 else []
    repeated = len(tails) - len(set(tails)) if tails else 0

    def count_cues(patterns: list[str]) -> int:
        return sum(1 for p in patterns if p in full)

    return TriggerContext(
        recent_segment_count=len(recent),
        repeated_tail_count=repeated,
        owner_mention_count=count_cues(_CUE_PATTERNS["owner"]),
        action_cue_count=count_cues(_CUE_PATTERNS["action"]),
        question_cue_count=count_cues(_CUE_PATTERNS["question"]),
        problem_definition_count=count_cues(_CUE_PATTERNS["problem_def"]),
        decision_mention_count=count_cues(_CUE_PATTERNS["decision"]),
    )


def evaluate_rules(segments: list[TranscriptSegment]) -> list[TriggerRule]:
    """Evaluate default trigger rules, return fired ones."""
    ctx = build_trigger_context(segments)
    data = ctx.to_dict()
    return [r for r in DEFAULT_RULES if _eval_json_logic(r.logic, data)]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class MeetingOrchestrator:
    """Complete meeting lifecycle manager."""

    def __init__(self):
        _load_env()

    # === 会前 ===
    def generate_briefing(self, config: MeetingConfig) -> str:
        memory_ctx, loaded = _load_memory_for_topic(config.topic)
        prompt = BRIEFING_PROMPT.format(
            topic=config.topic,
            participants=", ".join(config.participants) or "未指定",
            agenda="\n".join(f"  {i+1}. {a}" for i, a in enumerate(config.agenda)) or "未指定",
            scheduled_at=config.scheduled_at or "未指定",
            memory_context=memory_ctx or "(无相关记忆)",
        )
        return _llm_call(prompt, max_tokens=2000)

    # === 会中:思考 ===
    def think(self, record: MeetingRecord, reason: str = "manual") -> list[AdviceCard]:
        route = route_decision(record.config.topic, record.transcript)
        skills_content = _load_skills(route.skill_ids)
        memory_ctx, loaded = _load_memory_for_topic(record.config.topic)
        recent = "\n".join(
            f"[{s.speaker or '?'}] {s.text}" for s in record.transcript[-12:]
        )

        prompt = THINKING_PROMPT.format(
            topic=record.config.topic,
            trigger_reason=reason,
            theme=route.theme,
            subtask=route.subtask,
            subagents=", ".join(route.subagents),
            route_why=route.why,
            recent_transcript=recent,
            skills_content=skills_content or "(无特定 skill)",
            memory_context=memory_ctx or "(无相关记忆)",
        )

        try:
            result = _llm_call(prompt, max_tokens=3000)
            cards_data = _parse_json_from_llm(result)
            if isinstance(cards_data, dict):
                cards_data = [cards_data]
        except Exception:
            return [AdviceCard(
                title="思考失败",
                body=f"LLM 未能生成建议。路由: {route.theme}/{route.subtask}",
                card_type="prompter",
            )]

        cards: list[AdviceCard] = []
        for cd in cards_data[:3]:
            cards.append(AdviceCard(
                title=cd.get("title", ""),
                body=cd.get("body", ""),
                card_type=cd.get("card_type", "critical_thinking"),
                skill_ids=route.skill_ids,
                subagents=route.subagents,
                core_judgment=cd.get("core_judgment"),
                blind_spot=cd.get("blind_spot"),
                next_step=cd.get("next_step"),
            ))
        return cards

    # === 会中:问答 ===
    def chat(self, record: MeetingRecord, question: str) -> str:
        memory_ctx, _ = _load_memory_for_topic(record.config.topic)
        transcript_text = "\n".join(
            f"[{s.speaker or '?'}] {s.text}" for s in record.transcript
        )
        chat_text = "\n".join(
            f"Q: {c.get('question','')}\nA: {c.get('answer','')}" for c in record.chat_history
        )

        prompt = CHAT_PROMPT.format(
            topic=record.config.topic,
            transcript=transcript_text[:15000],
            chat_history=chat_text or "(无)",
            memory_context=memory_ctx or "(无相关记忆)",
            question=question,
        )
        return _llm_call(prompt, max_tokens=2000)

    # === 会后:纪要 ===
    def generate_summary(self, record: MeetingRecord) -> SummaryBundle:
        transcript_text = "\n".join(
            f"[{s.speaker or '?'}] {s.text}" for s in record.transcript
        )
        chat_text = "\n".join(
            f"Q: {c.get('question','')}\nA: {c.get('answer','')}" for c in record.chat_history
        )
        cards_text = "\n".join(
            f"- [{c.card_type}] {c.title}: {c.body[:100]}" for c in record.advice_cards
        )

        prompt = SUMMARY_PROMPT.format(
            topic=record.config.topic,
            participants=", ".join(record.config.participants) or "未指定",
            duration=f"{record.config.duration_minutes} 分钟",
            transcript=transcript_text[:20000],
            chat_history=chat_text or "(无)",
            advice_cards=cards_text or "(无)",
        )

        try:
            result = _llm_call(prompt, max_tokens=4000)
            data = _parse_json_from_llm(result)
            return SummaryBundle(
                full_summary=data.get("full_summary", ""),
                chapters=data.get("chapters", []),
                action_items=data.get("action_items", []),
                decisions=data.get("decisions", []),
                speaker_viewpoints=data.get("speaker_viewpoints", []),
            )
        except Exception as e:
            return SummaryBundle(full_summary=f"纪要生成失败: {e}")

    # === 会后:记忆回写 ===
    def write_back_memory(self, record: MeetingRecord) -> bool:
        hub = _get_memory_hub_config()
        ts = int(time.time() * 1000)

        # Build messages from transcript
        messages = []
        for seg in record.transcript:
            msg_id = "mtg_" + hashlib.sha256(
                f"{record.id}:{seg.id}:{seg.text}".encode()
            ).hexdigest()[:24]
            messages.append({
                "message_id": msg_id,
                "sender_id": seg.speaker or hub["user_id"],
                "sender_name": seg.speaker or "Unknown",
                "role": "user",
                "timestamp": ts + seg.timestamp_ms,
                "content": seg.text,
            })

        if not messages:
            return False

        # Chunk into 500-message batches.
        # NOTE: this method is sync. Callers must NOT invoke it from inside an
        # async event loop — it would block the loop. The current caller
        # (`run_meeting_command`) runs from the CLI dispatch which is
        # synchronous, so this is safe.
        client = EverCoreClient(base_url=hub["url"], user_id=hub["user_id"], timeout=90.0)
        for i in range(0, len(messages), 500):
            chunk = messages[i:i + 500]
            try:
                client.store(chunk)
            except Exception:
                return False
        return True


# ---------------------------------------------------------------------------
# CLI entry (called from agent.py)
# ---------------------------------------------------------------------------

# `emit` is the shared NDJSON helper (was duplicated here previously).
emit = _shared_emit


def run_meeting_command(args) -> int:
    """Dispatch meeting subcommands."""
    orch = MeetingOrchestrator()
    cmd = args.meeting

    if cmd == "brief":
        config = MeetingConfig(
            topic=args.topic or "未知会议",
            participants=(args.participants or "").split(","),
            agenda=(args.agenda or "").split(",") if args.agenda else [],
            scheduled_at=args.scheduled_at,
        )
        emit({"type": "meeting_mode", "command": "brief"})
        briefing = orch.generate_briefing(config)
        emit({"type": "briefing", "content": briefing})
        return 0

    elif cmd in ("think", "chat", "summary", "writeback"):
        # All require --transcript
        if not args.transcript:
            emit({"type": "error", "message": "--transcript required for this command"})
            return 1

        tp = Path(args.transcript)
        if not tp.exists():
            emit({"type": "error", "message": f"File not found: {args.transcript}"})
            return 1

        md_text = tp.read_text(encoding="utf-8")
        segments = parse_transcript_md(md_text)

        record = MeetingRecord(
            config=MeetingConfig(
                topic=args.topic or tp.stem,
                participants=(args.participants or "").split(",") if args.participants else [],
            ),
            state="recording",
            transcript=segments,
        )

        if cmd == "think":
            emit({"type": "meeting_mode", "command": "think"})
            # Auto-rules check
            if getattr(args, "auto_rules", False):
                fired = evaluate_rules(segments)
                for r in fired:
                    emit({"type": "rule_fired", "rule": r.id, "name": r.name})

            cards = orch.think(record, reason="manual")
            for card in cards:
                emit({"type": "advice_card", "card": card.to_dict()})
            return 0

        elif cmd == "chat":
            question = args.question or ""
            if not question:
                emit({"type": "error", "message": "question required for chat"})
                return 1
            emit({"type": "meeting_mode", "command": "chat"})
            answer = orch.chat(record, question)
            emit({"type": "chat_response", "question": question, "answer": answer})
            return 0

        elif cmd == "summary":
            emit({"type": "meeting_mode", "command": "summary"})
            record.state = "processing"
            bundle = orch.generate_summary(record)
            emit({"type": "summary", "bundle": bundle.to_dict()})

            # Write to output file if specified
            if args.output:
                out = Path(args.output)
                out.write_text(bundle.full_summary, encoding="utf-8")
                emit({"type": "file_written", "path": str(out)})
            return 0

        elif cmd == "writeback":
            emit({"type": "meeting_mode", "command": "writeback"})
            ok = orch.write_back_memory(record)
            emit({"type": "writeback", "success": ok, "segments": len(segments)})
            return 0

    emit({"type": "error", "message": f"Unknown meeting command: {cmd}"})
    return 1
