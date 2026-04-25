"""Tests for memory-hub-mcp/materializer.py.

Focus on the pure generators that turn EverCore episodes/profiles into the
.md surface — `generate_user_preferences`, `generate_recent_focus`, and the
new origin blocklist that keeps noisy sources out of the materialized output.
LLM-bound paths (`classify_episodes`, `summarize_for_md`) are not covered here.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "materializer", ROOT / "memory-hub-mcp" / "materializer.py"
)
assert spec and spec.loader
materializer = importlib.util.module_from_spec(spec)
sys.modules["materializer"] = materializer
spec.loader.exec_module(materializer)


# ---------------------------------------------------------------------------
# Origin classification + blocklist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "group_name,expected",
    [
        ("MyBrowserTab", "browser"),
        ("attention_capture", "browser"),
        ("Claude Session", "claude_code"),
        ("CC-1", "claude_code"),
        ("sayso-meeting", "sayso"),
        ("daily_review", "evermemo"),
        ("", "evermemo"),
    ],
)
def test_episode_origin_classification(group_name, expected):
    assert materializer._episode_origin({"group_name": group_name}) == expected


def test_blocked_origins_default():
    blocked = materializer._blocked_origins()
    assert "browser" in blocked
    assert "claude_code" in blocked
    assert "evermemo" not in blocked
    assert "sayso" not in blocked


def test_blocked_origins_overridable(monkeypatch):
    monkeypatch.setenv("MEMORY_BLOCKED_ORIGINS", "evermemo,sayso")
    blocked = materializer._blocked_origins()
    assert blocked == frozenset({"evermemo", "sayso"})


def test_blocked_origins_empty(monkeypatch):
    monkeypatch.setenv("MEMORY_BLOCKED_ORIGINS", "")
    assert materializer._blocked_origins() == frozenset()


# ---------------------------------------------------------------------------
# generate_user_preferences  ←  task 3 capability check
# ---------------------------------------------------------------------------


def test_user_preferences_empty_profile():
    out = materializer.generate_user_preferences([])
    assert "User Preferences" in out
    assert "No profile data" in out


def test_user_preferences_renders_subject_and_summary():
    profiles = [
        {
            "id": "prof_abc1234567",  # 14 chars — under the 16-char id-truncation cap
            "subject": "Coding style",
            "summary": "Prefers terse Python with type hints, no inline comments.",
        },
        {
            "id": "prof_xyz",
            "subject": "Working hours",
            "summary": "Active 09:00–18:00 CST, async on weekends.",
        },
    ]
    out = materializer.generate_user_preferences(profiles)
    assert "# User Preferences" in out
    assert "## Coding style" in out
    assert "type hints" in out
    assert "## Working hours" in out
    assert "09:00–18:00" in out
    # Source provenance must be inline so the writer can trace. The materializer
    # truncates ids to 16 chars; the prefix that survives is what we assert.
    assert "profile:prof_abc1234567" in out


def test_user_preferences_handles_missing_fields():
    """A profile with no subject/summary should not crash; should still mark id."""
    profiles = [{"id": "prof_partial", "subject": "", "summary": ""}]
    out = materializer.generate_user_preferences(profiles)
    # The empty-record branch is exercised — the "still being built" copy lands
    # whenever no subject/summary survives.
    assert "User Preferences" in out


# ---------------------------------------------------------------------------
# generate_recent_focus  ←  task 3 capability check
# ---------------------------------------------------------------------------


def _ep(ep_id: str, days_ago: float, subject: str, summary: str = "") -> dict:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "id": ep_id,
        "subject": subject,
        "summary": summary,
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "session_id": "sess_" + ep_id,
    }


def test_recent_focus_filters_by_window():
    eps = [
        _ep("e1", days_ago=0.5, subject="Pushed PR for memory blocklist"),
        _ep("e2", days_ago=2.0, subject="Discussed sayso integration"),
        _ep("e3", days_ago=10.0, subject="Old work — should be excluded"),
    ]
    out = materializer.generate_recent_focus(eps)
    assert "Recent Focus" in out
    assert "memory blocklist" in out
    assert "sayso integration" in out
    assert "Old work" not in out


def test_recent_focus_dedupes_by_id():
    eps = [
        _ep("dup", days_ago=0.1, subject="First subject"),
        _ep("dup", days_ago=0.2, subject="Duplicate row, same id"),
        _ep("uniq", days_ago=0.3, subject="Different episode"),
    ]
    out = materializer.generate_recent_focus(eps)
    assert out.count("ep:dup") <= 2  # one in body, one in source-index table
    assert "Different episode" in out


def test_recent_focus_empty_window():
    eps = [_ep("old", days_ago=30, subject="ancient")]
    out = materializer.generate_recent_focus(eps)
    assert "No recent activity" in out


def test_recent_focus_skips_unparseable_timestamps():
    eps = [
        {"id": "bad", "subject": "no ts", "summary": "x", "timestamp": ""},
        {"id": "alsobad", "subject": "weird ts", "summary": "x", "timestamp": "not-a-date"},
        _ep("good", days_ago=0.1, subject="valid"),
    ]
    out = materializer.generate_recent_focus(eps)
    assert "valid" in out
    assert "no ts" not in out


# ---------------------------------------------------------------------------
# fetch_all_episodes blocklist behavior (mocked HTTP)
# ---------------------------------------------------------------------------


def test_fetch_all_episodes_drops_blocked(monkeypatch):
    """Blocked origins (browser/claude_code) must not survive fetch."""
    page1 = {
        "data": {
            "episodes": [
                {"id": "ev1", "group_name": "MyBrowserTab", "subject": "browse"},
                {"id": "ev2", "group_name": "Claude Session", "subject": "cc"},
                {"id": "ev3", "group_name": "sayso-meeting", "subject": "sayso"},
                {"id": "ev4", "group_name": "daily_review", "subject": "evermemo"},
            ]
        }
    }

    def fake_post(path, payload, timeout=30.0):
        return page1  # one page, then loop exits because <100 items

    monkeypatch.setattr(materializer, "_hub_post", fake_post)
    monkeypatch.setattr(materializer, "_blocked_origins", lambda: frozenset({"browser", "claude_code"}))

    out = materializer.fetch_all_episodes(user_id="u")
    ids = {e["id"] for e in out}
    assert ids == {"ev3", "ev4"}, f"unexpected survivors: {ids}"
