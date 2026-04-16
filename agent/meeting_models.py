"""Meeting data models — mirrors MyIsland's MeetingModels.swift."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


# ---------------------------------------------------------------------------
# Config & Input
# ---------------------------------------------------------------------------

@dataclass
class MeetingConfig:
    topic: str
    participants: list[str] = field(default_factory=list)
    agenda: list[str] = field(default_factory=list)
    scheduled_at: str | None = None
    duration_minutes: int = 60


@dataclass
class TranscriptSegment:
    id: str
    text: str
    speaker: str | None = None
    timestamp_ms: int = 0


# ---------------------------------------------------------------------------
# Trigger System
# ---------------------------------------------------------------------------

@dataclass
class TriggerContext:
    """Aggregated signal counts from the last N transcript segments."""
    recent_segment_count: int = 0
    repeated_tail_count: int = 0
    owner_mention_count: int = 0
    action_cue_count: int = 0
    question_cue_count: int = 0
    problem_definition_count: int = 0
    decision_mention_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "recent_segment_count": self.recent_segment_count,
            "repeated_tail_count": self.repeated_tail_count,
            "owner_mention_count": self.owner_mention_count,
            "action_cue_count": self.action_cue_count,
            "question_cue_count": self.question_cue_count,
            "problem_definition_count": self.problem_definition_count,
            "decision_mention_count": self.decision_mention_count,
        }


@dataclass
class TriggerRule:
    id: str
    name: str
    description: str
    logic: dict[str, Any]
    cooldown_seconds: float = 90.0


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

@dataclass
class RouteDecision:
    theme: str
    subtask: str
    subagents: list[str]
    skill_ids: list[str]
    why: str


# ---------------------------------------------------------------------------
# Advice Cards
# ---------------------------------------------------------------------------

@dataclass
class AdviceCard:
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    title: str = ""
    body: str = ""
    card_type: str = "critical_thinking"  # critical_thinking / prompter / deep_probe
    trigger_rule_id: str | None = None
    skill_ids: list[str] = field(default_factory=list)
    subagents: list[str] = field(default_factory=list)
    core_judgment: str | None = None
    blind_spot: str | None = None
    next_step: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "card_type": self.card_type,
            "trigger_rule_id": self.trigger_rule_id,
            "skill_ids": self.skill_ids,
            "subagents": self.subagents,
            "core_judgment": self.core_judgment,
            "blind_spot": self.blind_spot,
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

@dataclass
class SummaryBundle:
    full_summary: str = ""
    chapters: list[dict[str, str]] = field(default_factory=list)
    action_items: list[dict[str, str]] = field(default_factory=list)
    decisions: list[dict[str, str]] = field(default_factory=list)
    speaker_viewpoints: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_summary": self.full_summary,
            "chapters": self.chapters,
            "action_items": self.action_items,
            "decisions": self.decisions,
            "speaker_viewpoints": self.speaker_viewpoints,
        }


# ---------------------------------------------------------------------------
# Meeting Record
# ---------------------------------------------------------------------------

@dataclass
class MeetingRecord:
    id: str = field(default_factory=lambda: str(uuid4())[:12])
    config: MeetingConfig = field(default_factory=lambda: MeetingConfig(topic=""))
    state: str = "draft"  # draft / recording / processing / completed
    transcript: list[TranscriptSegment] = field(default_factory=list)
    advice_cards: list[AdviceCard] = field(default_factory=list)
    post_advice_cards: list[AdviceCard] = field(default_factory=list)
    summary: SummaryBundle | None = None
    chat_history: list[dict[str, str]] = field(default_factory=list)
    memory_files_loaded: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_transcript_md(md_text: str) -> list[TranscriptSegment]:
    """Parse a meeting.md file into TranscriptSegments.

    Supports formats:
      [Speaker] text
      **Speaker**: text
      - text (no speaker)
    """
    segments: list[TranscriptSegment] = []
    for i, line in enumerate(md_text.splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        speaker = None
        text = line

        # [Speaker] text
        if line.startswith("[") and "]" in line:
            bracket_end = line.index("]")
            speaker = line[1:bracket_end].strip()
            text = line[bracket_end + 1:].strip()
        # **Speaker**: text
        elif line.startswith("**") and "**:" in line:
            star_end = line.index("**:", 2)
            speaker = line[2:star_end].strip()
            text = line[star_end + 3:].strip()
        # - text
        elif line.startswith("- "):
            text = line[2:].strip()

        if text:
            segments.append(TranscriptSegment(
                id=f"seg_{i}",
                text=text,
                speaker=speaker,
                timestamp_ms=i * 30000,  # approximate 30s per segment
            ))

    return segments
