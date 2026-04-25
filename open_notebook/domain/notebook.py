import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional, Union

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator
from surreal_commands import submit_command
from surrealdb import RecordID

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.base import ObjectModel
from open_notebook.exceptions import DatabaseOperationError, InvalidInputError


class MemoryRef(BaseModel):
    """Reference to an EverCore (EverOS) memory imported as a Source."""

    memory_id: str
    memory_type: Literal[
        "episodic_memory",
        "profile",
        "raw_message",
        "event_log",
        "foresight",
    ] = "episodic_memory"
    user_id: Optional[str] = None
    source_origin: Literal["browser", "claude_code", "evermemo", "sayso"] = "evermemo"
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    original_timestamp: Optional[str] = None


class Asset(BaseModel):
    file_path: Optional[str] = None
    url: Optional[str] = None
    memory_ref: Optional[MemoryRef] = None


class SourceEmbedding(ObjectModel):
    table_name: ClassVar[str] = "source_embedding"
    content: str

    async def get_source(self) -> "Source":
        try:
            src = await repo_query(
                "select source.* from $id fetch source",
                {"id": ensure_record_id(self.id)},
            )
            return Source(**src[0]["source"])
        except Exception as e:
            logger.error(f"Error fetching source for embedding {self.id}: {str(e)}")
            raise DatabaseOperationError(e)


class Source(ObjectModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    table_name: ClassVar[str] = "source"
    asset: Optional[Asset] = None
    title: Optional[str] = None
    topics: Optional[List[str]] = Field(default_factory=list)
    full_text: Optional[str] = None
    command: Optional[Union[str, RecordID]] = Field(
        default=None, description="Link to surreal-commands processing job"
    )

    @field_validator("command", mode="before")
    @classmethod
    def parse_command(cls, value):
        if isinstance(value, str) and value:
            return ensure_record_id(value)
        return value

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, value):
        if value is None:
            return None
        if isinstance(value, RecordID):
            return str(value)
        return str(value) if value else None

    async def get_status(self) -> Optional[str]:
        if not self.command:
            return None
        try:
            from surreal_commands import get_command_status

            status = await get_command_status(str(self.command))
            return status.status if status else "unknown"
        except Exception as e:
            logger.warning(f"Failed to get command status for {self.command}: {e}")
            return "unknown"

    async def get_processing_progress(self) -> Optional[Dict[str, Any]]:
        if not self.command:
            return None
        try:
            from surreal_commands import get_command_status

            status_result = await get_command_status(str(self.command))
            if not status_result:
                return None
            result = getattr(status_result, "result", None)
            execution_metadata = (
                result.get("execution_metadata", {}) if isinstance(result, dict) else {}
            )
            return {
                "status": status_result.status,
                "started_at": execution_metadata.get("started_at"),
                "completed_at": execution_metadata.get("completed_at"),
                "error": getattr(status_result, "error_message", None),
                "result": result,
            }
        except Exception as e:
            logger.warning(f"Failed to get command progress for {self.command}: {e}")
            return None

    async def get_context(
        self, context_size: Literal["short", "long"] = "short"
    ) -> Dict[str, Any]:
        if context_size == "long":
            return dict(id=self.id, title=self.title, full_text=self.full_text)
        return dict(id=self.id, title=self.title)

    async def get_embedded_chunks(self) -> int:
        try:
            result = await repo_query(
                "select count() as chunks from source_embedding where source=$id GROUP ALL",
                {"id": ensure_record_id(self.id)},
            )
            if not result:
                return 0
            return result[0]["chunks"]
        except Exception as e:
            logger.error(f"Error fetching chunks count for source {self.id}: {str(e)}")
            raise DatabaseOperationError(f"Failed to count chunks for source: {str(e)}")

    async def vectorize(self) -> str:
        """Submit vectorization as background job via the embed_source command."""
        logger.info(f"Submitting embed_source job for source {self.id}")
        try:
            if not self.full_text or not self.full_text.strip():
                raise ValueError(f"Source {self.id} has no text to vectorize")
            command_id = submit_command(
                "open_notebook",
                "embed_source",
                {"source_id": str(self.id)},
            )
            command_id_str = str(command_id)
            logger.info(
                f"Embed source job submitted for source {self.id}: "
                f"command_id={command_id_str}"
            )
            return command_id_str
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to submit embed_source job for source {self.id}: {e}")
            raise DatabaseOperationError(e)

    def _prepare_save_data(self) -> dict:
        data = super()._prepare_save_data()
        if data.get("command") is not None:
            data["command"] = ensure_record_id(data["command"])
        return data

    async def delete(self) -> bool:
        """Delete source and clean up associated file + embeddings."""
        if self.asset and self.asset.file_path:
            file_path = Path(self.asset.file_path)
            if file_path.exists():
                try:
                    os.unlink(file_path)
                    logger.info(f"Deleted file for source {self.id}: {file_path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to delete file {file_path} for source {self.id}: {e}"
                    )
        try:
            source_id = ensure_record_id(self.id)
            await repo_query(
                "DELETE source_embedding WHERE source = $source_id",
                {"source_id": source_id},
            )
        except Exception as e:
            logger.warning(f"Failed to delete embeddings for source {self.id}: {e}")
        return await super().delete()
