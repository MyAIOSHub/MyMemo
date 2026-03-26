"""
Unit tests for api.memory_service.MemoryService.

All external HTTP calls are mocked via httpx.AsyncClient patches.
No real Memory Hub or network access is required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.memory_service import MemoryService


# ============================================================================
# Helpers
# ============================================================================


def _make_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Build a fake httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "http://test"),
    )
    return resp


# ============================================================================
# TEST SUITE 1: check_status
# ============================================================================


class TestCheckStatus:
    """Tests for MemoryService.check_status."""

    @pytest.mark.asyncio
    async def test_connected_when_health_ok(self):
        """Health endpoint returns 200 -> connected=True."""
        svc = MemoryService()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_make_response(200, {}))
        svc._client = mock_client

        result = await svc.check_status()
        assert result["connected"] is True
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_connected_false_on_500(self):
        """Health endpoint returns 500 -> connected=False."""
        svc = MemoryService()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(return_value=_make_response(500, {}))
        svc._client = mock_client

        result = await svc.check_status()
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_connected_false_on_exception(self):
        """Network error -> connected=False with error message."""
        svc = MemoryService()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        svc._client = mock_client

        result = await svc.check_status()
        assert result["connected"] is False
        assert "error" in result


# ============================================================================
# TEST SUITE 2: browse_memories
# ============================================================================


class TestBrowseMemories:
    """Tests for MemoryService.browse_memories."""

    @pytest.mark.asyncio
    async def test_normal_return(self):
        """Successful browse returns normalized memories."""
        svc = MemoryService()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(
            return_value=_make_response(
                200,
                {
                    "result": {
                        "memories": [
                            {"id": "mem1", "summary": "Test summary", "title": "Title1"},
                        ],
                        "total_count": 1,
                        "has_more": False,
                    }
                },
            )
        )
        svc._client = mock_client

        result = await svc.browse_memories(memory_type="episodic_memory")
        assert len(result["memories"]) == 1
        assert result["memories"][0]["id"] == "mem1"
        assert result["total_count"] == 1
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_empty_result(self):
        """Browse with no memories returns empty list."""
        svc = MemoryService()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(
            return_value=_make_response(
                200,
                {"result": {"memories": [], "total_count": 0, "has_more": False}},
            )
        )
        svc._client = mock_client

        result = await svc.browse_memories()
        assert result["memories"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_http_error_raises(self):
        """HTTP 502 from upstream -> raises HTTPError."""
        svc = MemoryService()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        resp = _make_response(502, {"error": "bad gateway"})
        mock_client.get = AsyncMock(return_value=resp)
        svc._client = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await svc.browse_memories()


# ============================================================================
# TEST SUITE 3: search_memories
# ============================================================================


class TestSearchMemories:
    """Tests for MemoryService.search_memories."""

    @pytest.mark.asyncio
    async def test_hybrid_search_with_scores(self):
        """Search returns memories with scores correctly attached."""
        svc = MemoryService()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get = AsyncMock(
            return_value=_make_response(
                200,
                {
                    "result": {
                        "memories": [
                            {
                                "episodic_memory": [
                                    {"id": "e1", "summary": "Episode one"},
                                ]
                            }
                        ],
                        "scores": [
                            {"episodic_memory": [0.95]},
                        ],
                        "total_count": 1,
                        "has_more": False,
                    }
                },
            )
        )
        svc._client = mock_client

        result = await svc.search_memories(query="test", retrieve_method="hybrid")
        assert len(result["memories"]) == 1
        assert result["memories"][0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_http_error_raises(self):
        """HTTP error in search -> raises."""
        svc = MemoryService()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        resp = _make_response(500, {"error": "server error"})
        mock_client.get = AsyncMock(return_value=resp)
        svc._client = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await svc.search_memories(query="test")


# ============================================================================
# TEST SUITE 4: _normalize_fetch_memories
# ============================================================================


class TestNormalizeFetchMemories:
    """Tests for MemoryService._normalize_fetch_memories."""

    def test_empty_list(self):
        svc = MemoryService()
        assert svc._normalize_fetch_memories([], "episodic_memory") == []

    def test_non_dict_elements_skipped(self):
        svc = MemoryService()
        result = svc._normalize_fetch_memories(
            ["not_a_dict", 42, None], "episodic_memory"
        )
        assert result == []

    def test_missing_id_skipped(self):
        svc = MemoryService()
        result = svc._normalize_fetch_memories(
            [{"summary": "no id here"}], "episodic_memory"
        )
        assert result == []

    def test_valid_memory_normalized(self):
        svc = MemoryService()
        result = svc._normalize_fetch_memories(
            [{"id": "m1", "summary": "Hello"}], "episodic_memory"
        )
        assert len(result) == 1
        assert result[0]["id"] == "m1"
        assert result[0]["content"] == "Hello"


# ============================================================================
# TEST SUITE 5: _memory_to_item per memory_type
# ============================================================================


class TestMemoryToItem:
    """Tests for MemoryService._memory_to_item across memory types."""

    def test_episodic_memory(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "e1", "summary": "Sum", "title": "Ep Title"},
            "episodic_memory",
        )
        assert item is not None
        assert item["content"] == "Sum"
        assert item["title"] == "Ep Title"

    def test_episodic_memory_falls_back_to_subject(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "e2", "summary": "Sum", "subject": "Subject line"},
            "episodic_memory",
        )
        assert item["title"] == "Subject line"

    def test_event_log(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "ev1", "atomic_fact": "User clicked button"},
            "event_log",
        )
        assert item is not None
        assert item["content"] == "User clicked button"
        assert item["title"] == "User clicked button"

    def test_foresight(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "f1", "content": "Predicted outcome"},
            "foresight",
        )
        assert item is not None
        assert item["content"] == "Predicted outcome"

    def test_unknown_type_fallback(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "u1", "content": "Generic content"},
            "some_unknown_type",
        )
        assert item is not None
        assert item["content"] == "Generic content"

    def test_no_id_returns_none(self):
        svc = MemoryService()
        item = svc._memory_to_item({"summary": "no id"}, "episodic_memory")
        assert item is None

    def test_episode_id_used_as_fallback(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"episode_id": "ep99", "summary": "Test"},
            "episodic_memory",
        )
        assert item is not None
        assert item["id"] == "ep99"


# ============================================================================
# TEST SUITE 6: source_origin inference
# ============================================================================


class TestSourceOriginInference:
    """Tests for source_origin field based on group_name."""

    def test_browser_origin(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "b1", "summary": "S", "group_name": "MyBrowserTab"},
            "episodic_memory",
        )
        assert item["source_origin"] == "browser"

    def test_mymemo_origin(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "b2", "summary": "S", "group_name": "MyMemo Session"},
            "episodic_memory",
        )
        assert item["source_origin"] == "browser"

    def test_attention_origin(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "b3", "summary": "S", "group_name": "attention_capture"},
            "episodic_memory",
        )
        assert item["source_origin"] == "browser"

    def test_claude_origin(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "c1", "summary": "S", "group_name": "Claude Session"},
            "episodic_memory",
        )
        assert item["source_origin"] == "claude_code"

    def test_cc_origin(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "c2", "summary": "S", "group_name": "CC-session-1"},
            "episodic_memory",
        )
        assert item["source_origin"] == "claude_code"

    def test_default_evermemo_origin(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "d1", "summary": "S", "group_name": "daily_review"},
            "episodic_memory",
        )
        assert item["source_origin"] == "evermemo"

    def test_empty_group_name_defaults_evermemo(self):
        svc = MemoryService()
        item = svc._memory_to_item(
            {"id": "d2", "summary": "S"},
            "episodic_memory",
        )
        assert item["source_origin"] == "evermemo"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
