"""
Unit tests for api.routers.memories (FastAPI endpoints).

Uses httpx.AsyncClient against the FastAPI app with mocked services.
No real Memory Hub or database required.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from api.main import app


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing FastAPI app."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ============================================================================
# TEST SUITE 1: GET /api/memories/status
# ============================================================================


class TestMemoryStatus:
    """Tests for the /api/memories/status endpoint."""

    @pytest.mark.asyncio
    async def test_status_connected(self, client):
        """Returns connected=True when hub is reachable."""
        with patch(
            "api.routers.memories.memory_service"
        ) as mock_svc:
            mock_svc.check_status = AsyncMock(
                return_value={"connected": True, "status_code": 200, "url": "http://localhost:1995"}
            )
            resp = await client.get("/api/memories/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True

    @pytest.mark.asyncio
    async def test_status_disconnected(self, client):
        """Returns connected=False when hub is unreachable."""
        with patch(
            "api.routers.memories.memory_service"
        ) as mock_svc:
            mock_svc.check_status = AsyncMock(
                return_value={"connected": False, "error": "refused", "url": "http://localhost:1995"}
            )
            resp = await client.get("/api/memories/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False


# ============================================================================
# TEST SUITE 2: GET /api/memories/browse
# ============================================================================


class TestBrowseEndpoint:
    """Tests for the /api/memories/browse endpoint."""

    @pytest.mark.asyncio
    async def test_browse_with_params(self, client):
        """Browse with memory_type and limit returns data."""
        with patch(
            "api.routers.memories.memory_service"
        ) as mock_svc:
            mock_svc.browse_memories = AsyncMock(
                return_value={
                    "memories": [{"id": "m1", "title": "Test", "content": "c"}],
                    "total_count": 1,
                    "has_more": False,
                }
            )
            resp = await client.get(
                "/api/memories/browse",
                params={"memory_type": "episodic_memory", "limit": 10},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["memories"]) == 1
        assert data["total_count"] == 1

    @pytest.mark.asyncio
    async def test_browse_hub_error_returns_502(self, client):
        """When Memory Hub is unreachable, returns 502."""
        with patch(
            "api.routers.memories.memory_service"
        ) as mock_svc:
            mock_svc.browse_memories = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            resp = await client.get("/api/memories/browse")

        assert resp.status_code == 502


# ============================================================================
# TEST SUITE 3: GET /api/memories/search
# ============================================================================


class TestSearchEndpoint:
    """Tests for the /api/memories/search endpoint."""

    @pytest.mark.asyncio
    async def test_search_hybrid(self, client):
        """Search with retrieve_method=hybrid returns results."""
        with patch(
            "api.routers.memories.memory_service"
        ) as mock_svc:
            mock_svc.search_memories = AsyncMock(
                return_value={
                    "memories": [{"id": "s1", "title": "Found", "score": 0.9}],
                    "total_count": 1,
                    "has_more": False,
                }
            )
            resp = await client.get(
                "/api/memories/search",
                params={"query": "test", "retrieve_method": "hybrid"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["memories"]) == 1

    @pytest.mark.asyncio
    async def test_search_hub_error_returns_502(self, client):
        """When Memory Hub search fails, returns 502."""
        with patch(
            "api.routers.memories.memory_service"
        ) as mock_svc:
            mock_svc.search_memories = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            resp = await client.get(
                "/api/memories/search",
                params={"query": "test"},
            )

        assert resp.status_code == 502


# ============================================================================
# TEST SUITE 4: POST /api/memories/import
# ============================================================================


class TestImportEndpoint:
    """Tests for the /api/memories/import endpoint."""

    @pytest.mark.asyncio
    async def test_import_success(self, client):
        """Successful import returns MemoryImportResponse."""
        with patch(
            "api.routers.memories.import_memories_as_sources",
            new_callable=AsyncMock,
            return_value=[
                {
                    "memory_id": "mem-1",
                    "source_id": "source:s1",
                    "title": "Imported memory",
                    "status": "imported",
                },
            ],
        ):
            resp = await client.post(
                "/api/memories/import",
                json={
                    "memory_ids": ["mem-1"],
                    "memory_type": "episodic_memory",
                    "notebook_id": "notebook:nb1",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["success_count"] == 1
        assert data["imported"][0]["status"] == "imported"

    @pytest.mark.asyncio
    async def test_import_mixed_results(self, client):
        """Import with mixed statuses correctly counts successes."""
        with patch(
            "api.routers.memories.import_memories_as_sources",
            new_callable=AsyncMock,
            return_value=[
                {"memory_id": "m1", "source_id": "source:s1", "title": "T1", "status": "imported"},
                {"memory_id": "m2", "status": "duplicate"},
                {"memory_id": "m3", "status": "not_found"},
            ],
        ):
            resp = await client.post(
                "/api/memories/import",
                json={
                    "memory_ids": ["m1", "m2", "m3"],
                    "memory_type": "episodic_memory",
                    "notebook_id": "notebook:nb1",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["success_count"] == 1

    @pytest.mark.asyncio
    async def test_import_service_error_returns_500(self, client):
        """Internal error during import returns 500."""
        with patch(
            "api.routers.memories.import_memories_as_sources",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB down"),
        ):
            resp = await client.post(
                "/api/memories/import",
                json={
                    "memory_ids": ["mem-1"],
                    "memory_type": "episodic_memory",
                    "notebook_id": "notebook:nb1",
                },
            )

        assert resp.status_code == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
