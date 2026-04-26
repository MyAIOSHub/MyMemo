"""
Unit tests for api.memory_service.MemoryService (EverCore v1 API).

All external HTTP calls are mocked via httpx.AsyncClient patches.
No real Memory Hub or network access is required.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from api.memory_service import MemoryService


# ============================================================================
# Helpers
# ============================================================================


def _make_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Build a fake httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("POST", "http://test"),
    )


def _attach_mock_client(svc: MemoryService, *, get=None, post=None) -> None:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.is_closed = False
    if get is not None:
        mock.get = AsyncMock(return_value=get) if not isinstance(get, AsyncMock) else get
    if post is not None:
        mock.post = AsyncMock(return_value=post) if not isinstance(post, AsyncMock) else post
    svc._client = mock


# ============================================================================
# TEST SUITE 1: check_status
# ============================================================================


class TestCheckStatus:
    @pytest.mark.asyncio
    async def test_connected_when_health_ok(self):
        svc = MemoryService()
        _attach_mock_client(svc, get=_make_response(200, {}))
        result = await svc.check_status()
        assert result["connected"] is True
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_connected_false_on_500(self):
        svc = MemoryService()
        _attach_mock_client(svc, get=_make_response(500, {}))
        result = await svc.check_status()
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_connected_false_on_exception(self):
        svc = MemoryService()
        mock = AsyncMock(spec=httpx.AsyncClient)
        mock.is_closed = False
        mock.get = AsyncMock(side_effect=ConnectionError("refused"))
        svc._client = mock
        result = await svc.check_status()
        assert result["connected"] is False
        assert "error" in result


# ============================================================================
# TEST SUITE 2: browse_memories  (POST /api/v1/memories/get)
# ============================================================================


class TestBrowseMemories:
    @pytest.mark.asyncio
    async def test_normal_return(self):
        svc = MemoryService()
        _attach_mock_client(
            svc,
            post=_make_response(
                200,
                {
                    "data": {
                        "episodes": [
                            {"id": "mem1", "subject": "Subj", "summary": "Sum"},
                        ],
                        "profiles": [],
                        "agent_cases": [],
                        "agent_skills": [],
                        "total_count": 1,
                        "count": 1,
                    }
                },
            ),
        )
        result = await svc.browse_memories(memory_type="episodic_memory")
        assert len(result["memories"]) == 1
        assert result["memories"][0]["id"] == "mem1"
        assert result["total_count"] == 1
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_empty_result(self):
        svc = MemoryService()
        _attach_mock_client(
            svc,
            post=_make_response(
                200,
                {
                    "data": {
                        "episodes": [],
                        "profiles": [],
                        "agent_cases": [],
                        "agent_skills": [],
                        "total_count": 0,
                        "count": 0,
                    }
                },
            ),
        )
        result = await svc.browse_memories()
        assert result["memories"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_pagination_has_more(self):
        svc = MemoryService()
        _attach_mock_client(
            svc,
            post=_make_response(
                200,
                {
                    "data": {
                        "episodes": [{"id": f"e{i}", "summary": "x"} for i in range(5)],
                        "profiles": [],
                        "agent_cases": [],
                        "agent_skills": [],
                        "total_count": 50,
                        "count": 5,
                    }
                },
            ),
        )
        result = await svc.browse_memories(limit=5, offset=0)
        assert result["total_count"] == 50
        assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_has_more_uses_raw_count_not_filtered(self):
        """Items dropped by `_memory_to_item` (no id) must not skew has_more."""
        svc = MemoryService()
        _attach_mock_client(
            svc,
            post=_make_response(
                200,
                {
                    "data": {
                        # 5 raw items but 2 have no id → filtered out by normalization
                        "episodes": [
                            {"id": "e1", "summary": "a"},
                            {"summary": "no-id"},
                            {"id": "e2", "summary": "b"},
                            {"summary": "no-id-2"},
                            {"id": "e3", "summary": "c"},
                        ],
                        "profiles": [],
                        "agent_cases": [],
                        "agent_skills": [],
                        "total_count": 5,
                        # server returned all 5 raw items in this single page
                        "count": 5,
                    }
                },
            ),
        )
        result = await svc.browse_memories(limit=10, offset=0)
        # 3 normalized items, but has_more must still reflect raw page coverage
        assert len(result["memories"]) == 3
        assert result["has_more"] is False, "raw count of 5 covers total of 5"

    @pytest.mark.asyncio
    async def test_http_error_raises(self):
        svc = MemoryService()
        _attach_mock_client(svc, post=_make_response(502, {"error": "bad gateway"}))
        with pytest.raises(httpx.HTTPStatusError):
            await svc.browse_memories()

    @pytest.mark.asyncio
    async def test_profile_bucket(self):
        svc = MemoryService()
        _attach_mock_client(
            svc,
            post=_make_response(
                200,
                {
                    "data": {
                        "episodes": [],
                        "profiles": [{"id": "p1", "subject": "User profile"}],
                        "agent_cases": [],
                        "agent_skills": [],
                        "total_count": 1,
                        "count": 1,
                    }
                },
            ),
        )
        result = await svc.browse_memories(memory_type="profile")
        assert len(result["memories"]) == 1
        assert result["memories"][0]["id"] == "p1"
        assert result["memories"][0]["memory_type"] == "profile"


# ============================================================================
# TEST SUITE 3: search_memories  (POST /api/v1/memories/search)
# ============================================================================


class TestSearchMemories:
    @pytest.mark.asyncio
    async def test_search_returns_inline_score(self):
        svc = MemoryService()
        _attach_mock_client(
            svc,
            post=_make_response(
                200,
                {
                    "data": {
                        "episodes": [
                            {"id": "e1", "summary": "Episode one", "score": 0.95},
                        ],
                        "profiles": [],
                        "raw_messages": [],
                        "agent_memory": None,
                    }
                },
            ),
        )
        result = await svc.search_memories(query="test", retrieve_method="hybrid")
        assert len(result["memories"]) == 1
        assert result["memories"][0]["id"] == "e1"
        assert result["memories"][0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_aggregates_buckets(self):
        svc = MemoryService()
        _attach_mock_client(
            svc,
            post=_make_response(
                200,
                {
                    "data": {
                        "episodes": [{"id": "e1", "summary": "ep"}],
                        "profiles": [{"id": "p1", "subject": "prof"}],
                        "raw_messages": [{"id": "r1", "content": "raw"}],
                        "agent_memory": None,
                    }
                },
            ),
        )
        result = await svc.search_memories(query="x")
        types = {m["memory_type"] for m in result["memories"]}
        assert types == {"episodic_memory", "profile", "raw_message"}

    @pytest.mark.asyncio
    async def test_search_http_error_raises(self):
        svc = MemoryService()
        _attach_mock_client(svc, post=_make_response(500, {"error": "server error"}))
        with pytest.raises(httpx.HTTPStatusError):
            await svc.search_memories(query="test")


# ============================================================================
# TEST SUITE 4: _memory_to_item per memory_type (v1 fields)
# ============================================================================


class TestMemoryToItem:
    def test_episodic_memory_prefers_subject_for_title(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "e1", "subject": "Subj", "summary": "Sum"},
            "episodic_memory",
        )
        assert item is not None
        assert item["title"] == "Subj"
        assert item["content"] == "Sum"

    def test_episodic_memory_falls_back_to_summary_then_episode(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "e2", "summary": "Sum line", "episode": "Ep details"},
            "episodic_memory",
        )
        assert item["title"].startswith("Sum line")
        assert item["content"] == "Sum line"

    def test_profile_type(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "p1", "subject": "Profile subj", "summary": "About user"},
            "profile",
        )
        assert item is not None
        assert item["memory_type"] == "profile"
        assert item["title"] == "Profile subj"
        assert item["content"] == "About user"

    def test_raw_message_type(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "r1", "content": "User said hi"},
            "raw_message",
        )
        assert item is not None
        assert item["content"] == "User said hi"
        assert item["title"] == "User said hi"

    def test_unknown_type_fallback(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "u1", "summary": "Generic"},
            "some_unknown_type",
        )
        assert item is not None
        assert item["content"] == "Generic"

    def test_no_id_returns_none(self):
        svc = MemoryService()
        assert svc._memory_to_item({"summary": "no id"}, "episodic_memory") is None

    def test_episode_id_used_as_fallback(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"episode_id": "ep99", "summary": "Test"},
            "episodic_memory",
        )
        assert item is not None
        assert item["id"] == "ep99"


# ============================================================================
# TEST SUITE 5: source_origin inference (unchanged from v0)
# ============================================================================


class TestSourceOriginInference:
    """Origin classification + blocklist behavior.

    Default config blocks `browser` and `claude_code`; for those, _memory_to_item
    must return None. Unblocked origins (evermemo, sayso) come through normally.
    """

    @pytest.mark.parametrize(
        "group_name,expected",
        [
            ("daily_review", "evermemo"),
            ("", "evermemo"),
            ("sayso-meeting", "sayso"),
            ("sayso-transcript", "sayso"),
        ],
    )
    def test_origin_unblocked(self, group_name, expected):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "x", "summary": "S", "group_name": group_name},
            "episodic_memory",
        )
        assert item is not None
        assert item["source_origin"] == expected

    @pytest.mark.parametrize(
        "group_name",
        [
            "MyBrowserTab",
            "MyMemo Session",
            "attention_capture",
            "Claude Session",
            "CC-session-1",
        ],
    )
    def test_origin_blocked_by_default(self, group_name):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "x", "summary": "S", "group_name": group_name},
            "episodic_memory",
        )
        assert item is None, f"expected blocked origin for group_name={group_name!r}"

    def test_blocklist_can_be_disabled(self, monkeypatch):
        """Patching MEMORY_BLOCKED_ORIGINS to empty re-enables those origins."""
        from api import memory_service as ms_mod

        monkeypatch.setattr(ms_mod, "MEMORY_BLOCKED_ORIGINS", frozenset())
        svc = ms_mod.MemoryService()
        item = svc._memory_to_item(
            {"id": "x", "summary": "S", "group_name": "MyBrowserTab"},
            "episodic_memory",
        )
        assert item is not None
        assert item["source_origin"] == "browser"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
