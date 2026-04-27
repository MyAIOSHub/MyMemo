"""Personalization endpoints — condensed user-profile hints for downstream apps."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.personalization_summary_service import (
    DEFAULT_MAX_CHARS,
    get_personalization_summary,
)

router = APIRouter(prefix="/v1/personalization")


@router.get("/summary")
async def personalization_summary(
    user_id: Optional[str] = Query(default=None, description="EverCore user_id"),
    max_chars: int = Query(default=DEFAULT_MAX_CHARS, ge=20, le=500),
    no_cache: bool = Query(default=False),
) -> Dict[str, Any]:
    """Return condensed personalization summary derived from profile memories."""
    try:
        return await get_personalization_summary(
            user_id=user_id,
            max_chars=max_chars,
            use_cache=not no_cache,
        )
    except Exception as e:
        logger.exception("personalization summary failed")
        raise HTTPException(status_code=502, detail=f"summary failed: {e}")
