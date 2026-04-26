from fastapi import APIRouter, HTTPException
from loguru import logger
from surreal_commands import get_command_status

from api.command_service import CommandService
from api.models import (
    RebuildProgress,
    RebuildRequest,
    RebuildResponse,
    RebuildStats,
    RebuildStatusResponse,
)
from open_notebook.database.repository import repo_query

router = APIRouter()


@router.post("/rebuild", response_model=RebuildResponse)
async def start_rebuild(request: RebuildRequest):
    """Start a background job to rebuild embeddings.

    - **mode**: ``existing`` re-embeds sources that already have embeddings;
      ``all`` embeds every source with text.

    Returns the command ID to track progress and an estimated source count.
    """
    try:
        logger.info(f"Starting rebuild request: mode={request.mode}")

        # Import commands so surreal-commands can resolve them locally.
        import commands.embedding_commands  # noqa: F401

        if request.mode == "existing":
            result = await repo_query(
                """
                SELECT VALUE count(array::distinct(
                    SELECT VALUE source.id
                    FROM source_embedding
                    WHERE embedding != none AND array::len(embedding) > 0
                )) as count FROM {}
                """
            )
        else:
            result = await repo_query(
                "SELECT VALUE count() as count FROM source WHERE full_text != none GROUP ALL"
            )

        total_estimate = 0
        if result and isinstance(result[0], dict):
            total_estimate = result[0].get("count", 0)
        elif result:
            total_estimate = result[0] if isinstance(result[0], int) else 0

        logger.info(f"Estimated {total_estimate} sources to process")

        command_id = await CommandService.submit_command_job(
            "open_notebook",
            "rebuild_embeddings",
            {"mode": request.mode},
        )

        logger.info(f"Submitted rebuild command: {command_id}")

        return RebuildResponse(
            command_id=command_id,
            total_items=total_estimate,
            message=f"Rebuild operation started. Estimated {total_estimate} sources to process.",
        )

    except Exception as e:
        logger.error(f"Failed to start rebuild: {e}")
        logger.exception(e)
        raise HTTPException(
            status_code=500, detail=f"Failed to start rebuild operation: {str(e)}"
        )


@router.get("/rebuild/{command_id}/status", response_model=RebuildStatusResponse)
async def get_rebuild_status(command_id: str):
    """Get the status of a rebuild operation.

    Returns:
    - **status**: queued, running, completed, failed
    - **progress**: processed count, total count, percentage
    - **stats**: sources submitted + failed
    - **timestamps**: started_at, completed_at
    """
    try:
        status = await get_command_status(command_id)

        if not status:
            raise HTTPException(status_code=404, detail="Rebuild command not found")

        response = RebuildStatusResponse(
            command_id=command_id,
            status=status.status,
        )

        if status.result and isinstance(status.result, dict):
            result = status.result

            if "total_items" in result and "jobs_submitted" in result:
                total = result["total_items"]
                submitted = result["jobs_submitted"]
                response.progress = RebuildProgress(
                    processed=submitted,
                    total=total,
                    percentage=round((submitted / total * 100) if total > 0 else 0, 2),
                )

            response.stats = RebuildStats(
                sources=result.get("jobs_submitted", 0),
                failed=result.get("failed_submissions", 0),
            )

        if hasattr(status, "created") and status.created:
            response.started_at = str(status.created)
        if hasattr(status, "updated") and status.updated:
            response.completed_at = str(status.updated)

        if (
            status.status == "failed"
            and status.result
            and isinstance(status.result, dict)
        ):
            response.error_message = status.result.get("error_message", "Unknown error")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rebuild status: {e}")
        logger.exception(e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get rebuild status: {str(e)}"
        )
