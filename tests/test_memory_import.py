"""
Unit tests for api.memory_import_service.

All database and external service calls are mocked.
No real SurrealDB or Memory Hub required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from open_notebook.domain.notebook import Asset, MemoryRef, Source


# ============================================================================
# Fixtures & Helpers
# ============================================================================

SAMPLE_MEMORIES = [
    {
        "id": "mem-001",
        "memory_type": "episodic_memory",
        "title": "Meeting notes",
        "summary": "Discussed project roadmap",
        "content": "Discussed project roadmap",
        "timestamp": "2026-03-25T10:00:00",
        "source_origin": "browser",
        "group_id": "g1",
        "group_name": "MyBrowser",
        "participants": ["Alice", "Bob"],
        "keywords": ["roadmap", "Q2"],
    },
    {
        "id": "mem-002",
        "memory_type": "episodic_memory",
        "title": "Code review",
        "summary": "Reviewed PR #42",
        "content": "Reviewed PR #42",
        "timestamp": "2026-03-25T11:00:00",
        "source_origin": "claude_code",
        "group_id": "g2",
        "group_name": "Claude Session",
        "participants": None,
        "keywords": None,
    },
]


def _browse_result(memories=None):
    return {
        "memories": memories if memories is not None else SAMPLE_MEMORIES,
        "total_count": len(memories) if memories is not None else len(SAMPLE_MEMORIES),
        "has_more": False,
    }


# ============================================================================
# TEST SUITE 1: import_memories_as_sources - normal flow
# ============================================================================


class TestImportMemoriesNormal:
    """Tests for successful memory import."""

    @pytest.mark.asyncio
    @patch("api.memory_import_service._find_existing_source_by_memory_id", new_callable=AsyncMock, return_value=False)
    @patch("api.memory_import_service.repo_query", new_callable=AsyncMock)
    async def test_import_creates_source(self, mock_repo_query, mock_find_existing):
        """Normal import flow: Source is created and linked to notebook."""
        mock_source_instance = MagicMock(spec=Source)
        mock_source_instance.id = "source:new-1"
        mock_source_instance.title = "Meeting notes"
        mock_source_instance.save = AsyncMock()
        mock_source_instance.relate = AsyncMock()
        mock_source_instance.vectorize = AsyncMock()

        with (
            patch("api.memory_import_service.memory_service") as mock_mem_svc,
            patch("api.memory_import_service.Source", return_value=mock_source_instance) as MockSource,
            patch("api.memory_import_service.Asset") as MockAsset,
            patch("api.memory_import_service.MemoryRef") as MockMemRef,
            patch("open_notebook.database.repository.ensure_record_id", return_value="notebook:nb1"),
        ):
            mock_mem_svc.browse_memories = AsyncMock(return_value=_browse_result())

            from api.memory_import_service import import_memories_as_sources

            results = await import_memories_as_sources(
                memory_ids=["mem-001"],
                memory_type="episodic_memory",
                notebook_id="notebook:nb1",
                user_id="test_user",
            )

        assert len(results) == 1
        assert results[0]["status"] == "imported"
        assert results[0]["source_id"] == "source:new-1"
        mock_source_instance.save.assert_awaited_once()
        mock_source_instance.relate.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.memory_import_service._find_existing_source_by_memory_id", new_callable=AsyncMock, return_value=False)
    @patch("api.memory_import_service.repo_query", new_callable=AsyncMock)
    async def test_vectorize_failure_does_not_block(self, mock_repo_query, mock_find_existing):
        """Vectorize failure should not prevent source creation."""
        mock_source_instance = MagicMock(spec=Source)
        mock_source_instance.id = "source:new-2"
        mock_source_instance.title = "Code review"
        mock_source_instance.save = AsyncMock()
        mock_source_instance.relate = AsyncMock()
        mock_source_instance.vectorize = AsyncMock(side_effect=RuntimeError("embedding failed"))

        with (
            patch("api.memory_import_service.memory_service") as mock_mem_svc,
            patch("api.memory_import_service.Source", return_value=mock_source_instance),
            patch("api.memory_import_service.Asset"),
            patch("api.memory_import_service.MemoryRef"),
            patch("open_notebook.database.repository.ensure_record_id", return_value="notebook:nb1"),
        ):
            mock_mem_svc.browse_memories = AsyncMock(return_value=_browse_result())

            from api.memory_import_service import import_memories_as_sources

            results = await import_memories_as_sources(
                memory_ids=["mem-002"],
                memory_type="episodic_memory",
                notebook_id="notebook:nb1",
                user_id="test_user",
            )

        # Should still be imported even though vectorize failed
        assert len(results) == 1
        assert results[0]["status"] == "imported"


# ============================================================================
# TEST SUITE 2: Deduplication
# ============================================================================


class TestImportDeduplication:
    """Tests for dedup logic."""

    @pytest.mark.asyncio
    async def test_duplicate_skipped(self):
        """Already-imported memory returns status=duplicate."""
        with (
            patch("api.memory_import_service.memory_service") as mock_mem_svc,
            patch(
                "api.memory_import_service._find_existing_source_by_memory_id",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_mem_svc.browse_memories = AsyncMock(return_value=_browse_result())

            from api.memory_import_service import import_memories_as_sources

            results = await import_memories_as_sources(
                memory_ids=["mem-001"],
                memory_type="episodic_memory",
                notebook_id="notebook:nb1",
                user_id="test_user",
            )

        assert len(results) == 1
        assert results[0]["status"] == "duplicate"
        assert results[0]["memory_id"] == "mem-001"


# ============================================================================
# TEST SUITE 3: Not Found
# ============================================================================


class TestImportNotFound:
    """Tests for memories not found in browse results."""

    @pytest.mark.asyncio
    async def test_not_found_memory(self):
        """Memory ID not in browse result -> status=not_found."""
        with patch("api.memory_import_service.memory_service") as mock_mem_svc:
            mock_mem_svc.browse_memories = AsyncMock(return_value=_browse_result())

            from api.memory_import_service import import_memories_as_sources

            results = await import_memories_as_sources(
                memory_ids=["non-existent-id"],
                memory_type="episodic_memory",
                notebook_id="notebook:nb1",
                user_id="test_user",
            )

        assert len(results) == 1
        assert results[0]["status"] == "not_found"


# ============================================================================
# TEST SUITE 4: MemoryRef construction
# ============================================================================


class TestMemoryRefConstruction:
    """Tests for MemoryRef type correctness."""

    def test_memory_ref_fields(self):
        """MemoryRef builds correctly with all fields."""
        ref = MemoryRef(
            memory_id="mem-abc",
            memory_type="profile",
            user_id="user-1",
            source_origin="browser",
            group_id="g1",
            group_name="MyBrowser",
            original_timestamp="2026-03-25T10:00:00",
        )
        assert ref.memory_id == "mem-abc"
        assert ref.memory_type == "profile"
        assert ref.source_origin == "browser"
        assert ref.user_id == "user-1"
        assert ref.group_id == "g1"
        assert ref.group_name == "MyBrowser"
        assert ref.original_timestamp == "2026-03-25T10:00:00"

    def test_memory_ref_defaults(self):
        """MemoryRef defaults are correct."""
        ref = MemoryRef(memory_id="mem-def")
        assert ref.memory_type == "episodic_memory"
        assert ref.source_origin == "evermemo"

    def test_memory_ref_legacy_types_still_validate(self):
        """Legacy v0 memory types must remain readable for existing DB rows."""
        for legacy in ("event_log", "foresight"):
            ref = MemoryRef(memory_id="legacy", memory_type=legacy)
            assert ref.memory_type == legacy
        assert ref.user_id is None
        assert ref.group_id is None

    def test_asset_with_memory_ref(self):
        """Asset can hold a MemoryRef."""
        ref = MemoryRef(memory_id="mem-x")
        asset = Asset(memory_ref=ref)
        assert asset.memory_ref is not None
        assert asset.memory_ref.memory_id == "mem-x"
        assert asset.file_path is None
        assert asset.url is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
