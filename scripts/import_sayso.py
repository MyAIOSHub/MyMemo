#!/usr/bin/env python3
"""Import say-so-desktop SQLite data into EverCore as raw_message memories.

Reads two tables from the say-so-desktop app:
  - assistant_meetings + assistant_messages → group_add as `sayso-meeting`
  - audios                                   → group_add as `sayso-transcript`

Pushes via POST /api/v1/memories/group, then triggers
POST /api/v1/memories/group/flush so EverCore extracts episodes immediately.

Watermarks live in `data/sayso-import.state` so the script is idempotent and
incremental — re-running picks up only new rows since the last successful pass.

Usage:
    python scripts/import_sayso.py
    python scripts/import_sayso.py --db ~/.config/ai.sayso.app/db.sqlite3
    python scripts/import_sayso.py --hub-url http://localhost:1995 --dry-run

Env (overridable by CLI flags):
    SAYSO_DB_PATH        default: ~/.config/ai.sayso.app/db.sqlite3
    MEMORY_HUB_URL       default: http://localhost:1995
    MEMORY_HUB_USER_ID   default: mymemo_user
    SAYSO_STATE_PATH     default: ./data/sayso-import.state
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx

logger = logging.getLogger("import_sayso")

DEFAULT_DB = Path("~/.config/ai.sayso.app/db.sqlite3").expanduser()
DEFAULT_STATE = Path("data/sayso-import.state")
DEFAULT_HUB = "http://localhost:1995"
DEFAULT_USER = "mymemo_user"

# Cap per-message body to keep request payload + LLM extraction sane.
MAX_CONTENT_CHARS = 8000
# Cap messages per group_add call (server limit is 500).
MAX_BATCH_MESSAGES = 200
HTTP_TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# State (watermark) persistence
# ---------------------------------------------------------------------------


@dataclass
class Watermark:
    """High-water marks per source table. Stored as plain JSON."""

    meetings_max_updated_at_ms: int = 0
    audios_max_created_at_s: int = 0

    @classmethod
    def load(cls, path: Path) -> "Watermark":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                meetings_max_updated_at_ms=int(data.get("meetings_max_updated_at_ms", 0)),
                audios_max_created_at_s=int(data.get("audios_max_created_at_s", 0)),
            )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("State file corrupt (%s); resetting watermark.", e)
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "meetings_max_updated_at_ms": self.meetings_max_updated_at_ms,
                    "audios_max_created_at_s": self.audios_max_created_at_s,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(path)


# ---------------------------------------------------------------------------
# SQLite reader (read-only, won't lock the running app)
# ---------------------------------------------------------------------------


class SaysoDBUnavailable(RuntimeError):
    """Raised when the say-so SQLite file cannot be opened for reading."""


def _open_ro(db_path: Path) -> sqlite3.Connection:
    """Open SQLite read-only via URI; tolerates concurrent writers.

    If the say-so app is mid-checkpoint and holds the WAL exclusive lock,
    sqlite3.connect raises OperationalError. Re-raise as SaysoDBUnavailable
    so main() can exit cleanly instead of crashing with a stack trace.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"say-so DB not found at {db_path}")
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    except sqlite3.OperationalError as e:
        raise SaysoDBUnavailable(
            f"could not open {db_path} read-only ({e}); "
            "is the say-so app holding an exclusive WAL checkpoint?"
        ) from e
    conn.row_factory = sqlite3.Row
    return conn


def _truncate(text: str | None, limit: int = MAX_CONTENT_CHARS) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[...truncated, {len(text) - limit} chars]"


def fetch_new_meetings(
    conn: sqlite3.Connection, since_ms: int
) -> list[dict[str, Any]]:
    """Return meetings updated after watermark, plus their messages."""
    rows = conn.execute(
        """
        SELECT id, title, participants, agenda, briefing, summary, transcript,
               state, created_at, updated_at, ended_at, user_id
        FROM assistant_meetings
        WHERE updated_at > ?
        ORDER BY updated_at ASC
        """,
        (since_ms,),
    ).fetchall()

    meetings: list[dict[str, Any]] = []
    for r in rows:
        meeting = dict(r)
        msg_rows = conn.execute(
            """
            SELECT id, role, content, metadata, created_at
            FROM assistant_messages
            WHERE meeting_id = ?
            ORDER BY created_at ASC
            """,
            (meeting["id"],),
        ).fetchall()
        meeting["messages"] = [dict(m) for m in msg_rows]
        meetings.append(meeting)
    return meetings


def fetch_new_audios(
    conn: sqlite3.Connection, since_s: int
) -> list[dict[str, Any]]:
    """Return audio transcripts created after watermark (skips empty)."""
    rows = conn.execute(
        """
        SELECT id, session_id, user_id, created_at, filename, content,
               duration, mode, hotkey, version
        FROM audios
        WHERE created_at > ?
          AND content IS NOT NULL
          AND TRIM(content) <> ''
        ORDER BY created_at ASC
        """,
        (since_s,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# EverCore HTTP client
# ---------------------------------------------------------------------------


class HubClient:
    def __init__(self, base_url: str, dry_run: bool = False):
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self._client = httpx.Client(base_url=self.base_url, timeout=HTTP_TIMEOUT)

    def __enter__(self) -> "HubClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self._client.close()

    def group_add(
        self,
        group_id: str,
        group_name: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
            "group_id": group_id,
            "group_meta": {"name": group_name},
            "messages": messages,
        }
        if self.dry_run:
            logger.info(
                "[dry-run] POST /api/v1/memories/group group_id=%s msgs=%d",
                group_id,
                len(messages),
            )
            return {"status": "dry_run"}
        r = self._client.post("/api/v1/memories/group", json=payload)
        r.raise_for_status()
        return r.json()

    def group_flush(self, group_id: str) -> dict[str, Any]:
        if self.dry_run:
            logger.info("[dry-run] POST /api/v1/memories/group/flush group_id=%s", group_id)
            return {"status": "dry_run"}
        r = self._client.post(
            "/api/v1/memories/group/flush", json={"group_id": group_id}
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Conversion: SQLite row → EverCore MessageItem
# ---------------------------------------------------------------------------


def _meeting_to_messages(meeting: dict[str, Any], user_id: str) -> list[dict[str, Any]]:
    """Convert one meeting (+ its assistant_messages) to MessageItem batch.

    Strategy:
      1. Header message summarizing meeting metadata (title, participants, agenda).
      2. Each assistant_message becomes one MessageItem.
      3. If transcript is present and there are no per-message rows, emit it as
         a single user message so EverCore still has the substance.
    """
    out: list[dict[str, Any]] = []
    base_ts = int(meeting.get("created_at") or int(time.time() * 1000))

    title = meeting.get("title") or "Untitled Meeting"
    participants_raw = meeting.get("participants") or "[]"
    agenda_raw = meeting.get("agenda") or "[]"
    try:
        participants = json.loads(participants_raw)
    except (json.JSONDecodeError, TypeError):
        participants = []
    try:
        agenda = json.loads(agenda_raw)
    except (json.JSONDecodeError, TypeError):
        agenda = []

    header_lines = [f"Meeting: {title}"]
    if participants:
        header_lines.append(f"Participants: {', '.join(str(p) for p in participants)}")
    if agenda:
        header_lines.append(f"Agenda: {'; '.join(str(a) for a in agenda)}")
    out.append(
        {
            "message_id": f"sayso-meeting-{meeting['id']}-header",
            "sender_id": user_id,
            "sender_name": "say-so-meeting",
            "role": "user",
            "timestamp": base_ts,
            "content": _truncate("\n".join(header_lines)),
        }
    )

    msg_rows = meeting.get("messages") or []
    if msg_rows:
        for m in msg_rows:
            content = _truncate(m.get("content") or "")
            if not content:
                continue
            # Map sayso roles to EverCore-accepted roles.
            raw_role = (m.get("role") or "user").lower()
            role = "assistant" if raw_role in ("assistant", "advice", "system") else "user"
            out.append(
                {
                    "message_id": f"sayso-meeting-msg-{m['id']}",
                    "sender_id": user_id,
                    "sender_name": f"say-so-{raw_role}",
                    "role": role,
                    "timestamp": int(m.get("created_at") or base_ts),
                    "content": content,
                }
            )
    else:
        transcript = _truncate(meeting.get("transcript") or "")
        summary_raw = meeting.get("summary") or ""
        if transcript:
            out.append(
                {
                    "message_id": f"sayso-meeting-{meeting['id']}-transcript",
                    "sender_id": user_id,
                    "sender_name": "say-so-meeting",
                    "role": "user",
                    "timestamp": base_ts,
                    "content": transcript,
                }
            )
        if summary_raw:
            out.append(
                {
                    "message_id": f"sayso-meeting-{meeting['id']}-summary",
                    "sender_id": user_id,
                    "sender_name": "say-so-meeting",
                    "role": "assistant",
                    "timestamp": base_ts + 1,
                    "content": _truncate(str(summary_raw)),
                }
            )

    return out


def _audio_to_message(audio: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Convert one transcript row to a single MessageItem (sayso 'audios' table).

    `audios.created_at` is in seconds; EverCore expects unix milliseconds.
    """
    ts_ms = int(audio["created_at"]) * 1000
    return {
        "message_id": f"sayso-audio-{audio['id']}",
        "sender_id": user_id,
        "sender_name": "say-so-transcript",
        "role": "user",
        "timestamp": ts_ms,
        "content": _truncate(audio.get("content") or ""),
    }


def _chunked(items: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ---------------------------------------------------------------------------
# Importers
# ---------------------------------------------------------------------------


def import_meetings(
    conn: sqlite3.Connection, hub: HubClient, user_id: str, watermark: Watermark
) -> int:
    """Import all meetings updated since the last watermark."""
    meetings = fetch_new_meetings(conn, watermark.meetings_max_updated_at_ms)
    if not meetings:
        logger.info("Meetings: no new rows since updated_at>%d", watermark.meetings_max_updated_at_ms)
        return 0

    imported = 0
    for meeting in meetings:
        messages = _meeting_to_messages(meeting, user_id)
        if not messages:
            continue
        group_id = f"sayso-meeting-{meeting['id']}"
        # Watermark only advances after BOTH add+flush succeed, so a crash
        # mid-batch leaves the meeting eligible on the next run.
        try:
            for batch in _chunked(messages, MAX_BATCH_MESSAGES):
                hub.group_add(group_id, "sayso-meeting", batch)
            hub.group_flush(group_id)
        except httpx.HTTPError as e:
            logger.error("Meeting %s failed (%s); skipping watermark advance.", meeting["id"], e)
            raise
        imported += 1
        watermark.meetings_max_updated_at_ms = max(
            watermark.meetings_max_updated_at_ms,
            int(meeting.get("updated_at") or 0),
        )
        logger.info("Imported meeting %s (%d msgs)", meeting["id"], len(messages))
    return imported


def import_audios(
    conn: sqlite3.Connection, hub: HubClient, user_id: str, watermark: Watermark
) -> int:
    """Import audio transcripts grouped by session_id since the last watermark."""
    audios = fetch_new_audios(conn, watermark.audios_max_created_at_s)
    if not audios:
        logger.info("Audios: no new rows since created_at>%d", watermark.audios_max_created_at_s)
        return 0

    # Group by session_id so a single recording session lands in one EverCore group,
    # which gives the LLM enough context to extract a coherent episode.
    by_session: dict[str, list[dict[str, Any]]] = {}
    for a in audios:
        by_session.setdefault(a.get("session_id") or f"solo-{a['id']}", []).append(a)

    imported = 0
    for session_id, rows in by_session.items():
        messages = [_audio_to_message(a, user_id) for a in rows]
        messages = [m for m in messages if m["content"]]
        if not messages:
            continue
        group_id = f"sayso-transcript-{session_id}"
        # Same ordering guarantee as meetings: only bump watermark when the
        # full session round-trip lands successfully.
        try:
            for batch in _chunked(messages, MAX_BATCH_MESSAGES):
                hub.group_add(group_id, "sayso-transcript", batch)
            hub.group_flush(group_id)
        except httpx.HTTPError as e:
            logger.error("Transcript session %s failed (%s); skipping watermark advance.", session_id, e)
            raise
        imported += len(rows)
        watermark.audios_max_created_at_s = max(
            watermark.audios_max_created_at_s,
            max(int(a["created_at"]) for a in rows),
        )
        logger.info(
            "Imported transcript session %s (%d rows, %d msgs)",
            session_id,
            len(rows),
            len(messages),
        )
    return imported


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("SAYSO_DB_PATH", str(DEFAULT_DB))).expanduser(),
        help="Path to say-so SQLite DB",
    )
    p.add_argument(
        "--hub-url",
        default=os.environ.get("MEMORY_HUB_URL", DEFAULT_HUB),
        help="EverCore base URL",
    )
    p.add_argument(
        "--user-id",
        default=os.environ.get("MEMORY_HUB_USER_ID", DEFAULT_USER),
        help="Owner user ID for ingested memories",
    )
    p.add_argument(
        "--state",
        type=Path,
        default=Path(os.environ.get("SAYSO_STATE_PATH", str(DEFAULT_STATE))),
        help="Watermark state file",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Ignore existing watermark and re-import everything",
    )
    p.add_argument("--dry-run", action="store_true", help="Print actions without calling EverCore")
    p.add_argument("--meetings-only", action="store_true")
    p.add_argument("--audios-only", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.db.exists():
        logger.error("DB not found: %s", args.db)
        return 1

    watermark = Watermark() if args.reset else Watermark.load(args.state)
    logger.info(
        "Watermark: meetings>%d ms, audios>%d s",
        watermark.meetings_max_updated_at_ms,
        watermark.audios_max_created_at_s,
    )

    try:
        conn = _open_ro(args.db)
    except SaysoDBUnavailable as e:
        logger.error(str(e))
        return 2

    with closing(conn), HubClient(args.hub_url, args.dry_run) as hub:
        meetings_n = 0 if args.audios_only else import_meetings(conn, hub, args.user_id, watermark)
        audios_n = 0 if args.meetings_only else import_audios(conn, hub, args.user_id, watermark)

    if not args.dry_run:
        watermark.save(args.state)

    logger.info("Done. meetings=%d audios=%d", meetings_n, audios_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
