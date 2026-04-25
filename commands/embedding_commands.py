"""Embedding commands for MyMemo.

Post-Open-Notebook-rip, only Sources need embeddings. Notes, SourceInsights,
create_insight, rebuild_embeddings coordination over non-source types are
gone with the notebook UI.
"""

import time
from typing import Literal, Optional

from loguru import logger
from pydantic import BaseModel
from surreal_commands import CommandInput, CommandOutput, command, submit_command

from open_notebook.database.repository import ensure_record_id, repo_insert, repo_query
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import ConfigurationError
from open_notebook.utils.chunking import chunk_text, detect_content_type
from open_notebook.utils.embedding import generate_embeddings


def full_model_dump(model):
    if isinstance(model, BaseModel):
        return model.model_dump()
    if isinstance(model, dict):
        return {k: full_model_dump(v) for k, v in model.items()}
    if isinstance(model, list):
        return [full_model_dump(item) for item in model]
    return model


def get_command_id(input_data: CommandInput) -> str:
    if input_data.execution_context:
        return str(input_data.execution_context.command_id)
    return "unknown"


class EmbedSourceInput(CommandInput):
    source_id: str


class EmbedSourceOutput(CommandOutput):
    success: bool
    source_id: str
    chunks_created: int
    processing_time: float
    error_message: Optional[str] = None


class RebuildEmbeddingsInput(CommandInput):
    mode: Literal["existing", "all"] = "all"


class RebuildEmbeddingsOutput(CommandOutput):
    success: bool
    total_items: int
    jobs_submitted: int
    failed_submissions: int
    processing_time: float
    error_message: Optional[str] = None


@command(
    "embed_source",
    app="open_notebook",
    retry={
        "max_attempts": 5,
        "wait_strategy": "exponential_jitter",
        "wait_min": 1,
        "wait_max": 60,
        "stop_on": [ValueError, ConfigurationError],
        "retry_log_level": "debug",
    },
)
async def embed_source_command(input_data: EmbedSourceInput) -> EmbedSourceOutput:
    """Generate + store chunk embeddings for a Source."""
    start_time = time.time()
    try:
        logger.info(f"Starting embedding for source: {input_data.source_id}")

        source = await Source.get(input_data.source_id)
        if not source:
            raise ValueError(f"Source '{input_data.source_id}' not found")
        if not source.full_text or not source.full_text.strip():
            raise ValueError(f"Source '{input_data.source_id}' has no text to embed")

        await repo_query(
            "DELETE source_embedding WHERE source = $source_id",
            {"source_id": ensure_record_id(input_data.source_id)},
        )

        file_path = source.asset.file_path if source.asset else None
        content_type = detect_content_type(source.full_text, file_path)
        chunks = chunk_text(source.full_text, content_type=content_type)
        total_chunks = len(chunks)
        if total_chunks == 0:
            raise ValueError("No chunks created after splitting text")

        cmd_id = get_command_id(input_data)
        embeddings = await generate_embeddings(chunks, command_id=cmd_id)
        if len(embeddings) != len(chunks):
            raise ValueError(
                f"Embedding count mismatch: got {len(embeddings)} for {len(chunks)} chunks"
            )

        records = [
            {
                "source": ensure_record_id(input_data.source_id),
                "order": idx,
                "content": chunk,
                "embedding": embedding,
            }
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        await repo_insert("source_embedding", records)

        processing_time = time.time() - start_time
        logger.info(
            f"Embedded source {input_data.source_id}: "
            f"{total_chunks} chunks in {processing_time:.2f}s"
        )
        return EmbedSourceOutput(
            success=True,
            source_id=input_data.source_id,
            chunks_created=total_chunks,
            processing_time=processing_time,
        )
    except ValueError as e:
        processing_time = time.time() - start_time
        cmd_id = get_command_id(input_data)
        logger.error(
            f"Failed to embed source {input_data.source_id} (command: {cmd_id}): {e}"
        )
        return EmbedSourceOutput(
            success=False,
            source_id=input_data.source_id,
            chunks_created=0,
            processing_time=processing_time,
            error_message=str(e),
        )
    except Exception as e:
        cmd_id = get_command_id(input_data)
        logger.debug(
            f"Transient error embedding source {input_data.source_id} "
            f"(command: {cmd_id}): {e}"
        )
        raise


@command("rebuild_embeddings", app="open_notebook", retry=None)
async def rebuild_embeddings_command(
    input_data: RebuildEmbeddingsInput,
) -> RebuildEmbeddingsOutput:
    """Submit embed_source for every Source. No retry (coordinator only)."""
    start_time = time.time()
    try:
        if input_data.mode == "existing":
            result = await repo_query(
                """
                RETURN array::distinct(
                    SELECT VALUE source.id
                    FROM source_embedding
                    WHERE embedding != none AND array::len(embedding) > 0
                )
                """
            )
            source_ids = [str(s) for s in result] if result else []
        else:
            result = await repo_query(
                "SELECT id FROM source WHERE full_text != none "
                "AND string::trim(full_text) != ''"
            )
            source_ids = [str(r["id"]) for r in result] if result else []

        submitted = 0
        failed = 0
        for sid in source_ids:
            try:
                submit_command("open_notebook", "embed_source", {"source_id": sid})
                submitted += 1
            except Exception as e:
                failed += 1
                logger.error(f"Failed to submit embed_source for {sid}: {e}")

        processing_time = time.time() - start_time
        logger.info(
            f"rebuild_embeddings: {submitted} submitted, {failed} failed "
            f"(total {len(source_ids)}) in {processing_time:.2f}s"
        )
        return RebuildEmbeddingsOutput(
            success=failed == 0,
            total_items=len(source_ids),
            jobs_submitted=submitted,
            failed_submissions=failed,
            processing_time=processing_time,
            error_message=None if failed == 0 else f"{failed} submissions failed",
        )
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"rebuild_embeddings failed: {e}")
        return RebuildEmbeddingsOutput(
            success=False,
            total_items=0,
            jobs_submitted=0,
            failed_submissions=0,
            processing_time=processing_time,
            error_message=str(e),
        )
