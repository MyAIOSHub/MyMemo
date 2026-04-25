"""Tests for scripts/import_sayso.py — pure-logic only (no HTTP / SQLite).

The HTTP path through HubClient is exercised end-to-end in dry-run mode by the
operator; here we just guard the data-shape converters that determine what gets
sent to EverCore.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest


# Load the script as a module — it isn't a package member.
# Register it in sys.modules *before* executing so @dataclass can resolve
# `sys.modules[cls.__module__]` while the class body runs.
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "import_sayso", ROOT / "scripts" / "import_sayso.py"
)
assert spec and spec.loader
import_sayso = importlib.util.module_from_spec(spec)
sys.modules["import_sayso"] = import_sayso
spec.loader.exec_module(import_sayso)


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


def test_truncate_short_text_unchanged():
    assert import_sayso._truncate("hello") == "hello"


def test_truncate_strips_whitespace():
    assert import_sayso._truncate("  hi  ") == "hi"


def test_truncate_long_text_marked():
    long = "x" * (import_sayso.MAX_CONTENT_CHARS + 100)
    out = import_sayso._truncate(long)
    assert out.startswith("x" * 100)
    assert "[...truncated, 100 chars]" in out


def test_truncate_handles_none():
    assert import_sayso._truncate(None) == ""


# ---------------------------------------------------------------------------
# _meeting_to_messages
# ---------------------------------------------------------------------------


def _meeting_row(**overrides):
    base = {
        "id": "mt_1",
        "title": "Product sync",
        "participants": json.dumps(["alice", "bob"]),
        "agenda": json.dumps(["Item A", "Item B"]),
        "briefing": "{}",
        "summary": "We agreed on X",
        "transcript": "alice: hello\nbob: hi",
        "state": "ended",
        "created_at": 1_700_000_000_000,
        "updated_at": 1_700_000_001_000,
        "ended_at": 1_700_000_002_000,
        "user_id": 1,
        "messages": [],
    }
    base.update(overrides)
    return base


def test_meeting_header_includes_participants_and_agenda():
    msgs = import_sayso._meeting_to_messages(_meeting_row(), user_id="mymemo_user")
    header = msgs[0]
    assert header["role"] == "user"
    assert "Product sync" in header["content"]
    assert "alice, bob" in header["content"]
    assert "Item A; Item B" in header["content"]
    assert header["sender_id"] == "mymemo_user"


def test_meeting_falls_back_to_transcript_when_no_messages():
    msgs = import_sayso._meeting_to_messages(_meeting_row(), user_id="u")
    contents = [m["content"] for m in msgs]
    assert any("alice: hello" in c for c in contents)
    assert any("We agreed on X" in c for c in contents)


def test_meeting_uses_message_rows_when_present():
    meeting = _meeting_row(
        messages=[
            {"id": "m1", "role": "user", "content": "What is the plan?", "metadata": None, "created_at": 1_700_000_000_500},
            {"id": "m2", "role": "advice", "content": "Focus on Q2 launch", "metadata": None, "created_at": 1_700_000_000_600},
        ]
    )
    msgs = import_sayso._meeting_to_messages(meeting, user_id="u")
    assert len(msgs) == 3  # header + 2 messages
    assert msgs[1]["role"] == "user"
    # 'advice' role is mapped to 'assistant' so EverCore accepts it.
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["sender_name"] == "say-so-advice"


def test_meeting_skips_empty_message_content():
    meeting = _meeting_row(
        messages=[
            {"id": "m1", "role": "user", "content": "", "metadata": None, "created_at": 1},
            {"id": "m2", "role": "assistant", "content": "  ", "metadata": None, "created_at": 2},
        ]
    )
    msgs = import_sayso._meeting_to_messages(meeting, user_id="u")
    # Only the header should remain (transcript fallback also fires; both kept).
    assert all(m["content"] for m in msgs)


def test_meeting_handles_corrupt_participants_json():
    meeting = _meeting_row(participants="NOT_JSON", agenda="ALSO_NOT_JSON")
    msgs = import_sayso._meeting_to_messages(meeting, user_id="u")
    # Should not raise; header still emits the title.
    assert "Product sync" in msgs[0]["content"]


# ---------------------------------------------------------------------------
# _audio_to_message
# ---------------------------------------------------------------------------


def test_audio_converts_seconds_to_ms():
    audio = {"id": "a1", "session_id": "s1", "created_at": 1_700_000_000, "content": "hello world"}
    msg = import_sayso._audio_to_message(audio, user_id="u")
    assert msg["timestamp"] == 1_700_000_000_000
    assert msg["role"] == "user"
    assert msg["sender_name"] == "say-so-transcript"
    assert msg["message_id"] == "sayso-audio-a1"


# ---------------------------------------------------------------------------
# Watermark persistence
# ---------------------------------------------------------------------------


def test_watermark_roundtrip(tmp_path: Path):
    state = tmp_path / "state.json"
    wm = import_sayso.Watermark(meetings_max_updated_at_ms=10, audios_max_created_at_s=20)
    wm.save(state)
    loaded = import_sayso.Watermark.load(state)
    assert loaded.meetings_max_updated_at_ms == 10
    assert loaded.audios_max_created_at_s == 20


def test_watermark_missing_file_returns_zero(tmp_path: Path):
    wm = import_sayso.Watermark.load(tmp_path / "nope.json")
    assert wm.meetings_max_updated_at_ms == 0
    assert wm.audios_max_created_at_s == 0


def test_watermark_corrupt_file_resets(tmp_path: Path):
    f = tmp_path / "bad.json"
    f.write_text("{not json")
    wm = import_sayso.Watermark.load(f)
    assert wm.meetings_max_updated_at_ms == 0


# ---------------------------------------------------------------------------
# Read-only SQLite open + fetch_new_audios filter
# ---------------------------------------------------------------------------


def _make_test_db(tmp_path: Path) -> Path:
    """Build a minimal sayso-shaped SQLite DB for reader tests."""
    db = tmp_path / "sayso.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE assistant_meetings (
            id TEXT PRIMARY KEY,
            title TEXT,
            participants TEXT,
            agenda TEXT,
            briefing TEXT,
            summary TEXT,
            transcript TEXT,
            state TEXT,
            created_at INTEGER,
            updated_at INTEGER,
            ended_at INTEGER,
            user_id INTEGER
        );
        CREATE TABLE assistant_messages (
            id TEXT PRIMARY KEY,
            meeting_id TEXT,
            role TEXT,
            content TEXT,
            metadata TEXT,
            created_at INTEGER
        );
        CREATE TABLE audios (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            user_id INTEGER,
            created_at INTEGER,
            filename TEXT,
            content TEXT,
            duration REAL,
            mode TEXT,
            hotkey TEXT,
            version TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO audios VALUES ('a1','s1',1,1000,'f.wav','hello',1.0,'m','h','v')"
    )
    conn.execute(
        "INSERT INTO audios VALUES ('a2','s1',1,2000,'f2.wav','',1.0,'m','h','v')"
    )  # blank — skipped
    conn.execute(
        "INSERT INTO audios VALUES ('a3','s2',1,3000,'f3.wav','later',1.0,'m','h','v')"
    )
    conn.commit()
    conn.close()
    return db


def test_open_ro_rejects_writes(tmp_path: Path):
    db = _make_test_db(tmp_path)
    conn = import_sayso._open_ro(db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO audios VALUES ('z','s',1,9,'x','y',0,'m','h','v')")
    conn.close()


def test_fetch_new_audios_drops_blank_and_old(tmp_path: Path):
    db = _make_test_db(tmp_path)
    conn = import_sayso._open_ro(db)
    rows = import_sayso.fetch_new_audios(conn, since_s=1500)
    conn.close()
    ids = [r["id"] for r in rows]
    assert ids == ["a3"]  # a1 too old, a2 blank


def test_open_ro_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        import_sayso._open_ro(tmp_path / "nope.sqlite3")
