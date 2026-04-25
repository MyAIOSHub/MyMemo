"""Authentication router. Reports whether the API is password-protected."""

from fastapi import APIRouter

from api.auth import _get_api_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status")
async def get_auth_status():
    """Check if authentication is enabled.

    Reports `MYMEMO_PASSWORD` (or legacy `OPEN_NOTEBOOK_PASSWORD`) presence.
    Both `_FILE` variants are honored.
    """
    auth_enabled = bool(_get_api_password())
    return {
        "auth_enabled": auth_enabled,
        "message": "Authentication is required"
        if auth_enabled
        else "Authentication is disabled",
    }
