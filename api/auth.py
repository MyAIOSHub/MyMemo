import hmac
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from open_notebook.utils.encryption import get_secret_from_env


def _get_api_password() -> Optional[str]:
    """Resolve the API password.

    Priority: `MYMEMO_PASSWORD` → `OPEN_NOTEBOOK_PASSWORD` (deprecated).
    Both `_FILE` variants are honored via `get_secret_from_env`. A deprecation
    warning is logged the first time a request falls back to the legacy name.
    """
    new = get_secret_from_env("MYMEMO_PASSWORD")
    if new:
        return new
    legacy = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
    if legacy:
        logger.warning(
            "OPEN_NOTEBOOK_PASSWORD is deprecated; switch to MYMEMO_PASSWORD."
        )
    return legacy


def _is_debug_mode() -> bool:
    """Whether to expose docs / openapi without auth."""
    return os.environ.get("MYMEMO_DEBUG", "").lower() in ("1", "true", "yes")


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """Bearer-token middleware. Compares with `hmac.compare_digest`."""

    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.password = _get_api_password()
        # In debug mode `/docs` and friends are reachable without auth so the
        # OpenAPI surface stays browseable. In production they require auth.
        always_excluded = ["/", "/health"]
        if _is_debug_mode():
            always_excluded.extend(["/docs", "/openapi.json", "/redoc"])
        self.excluded_paths = excluded_paths or always_excluded

    async def dispatch(self, request: Request, call_next):
        # Skip authentication if no password is set
        if not self.password:
            return await call_next(request)

        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Skip authentication for CORS preflight requests (OPTIONS)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Expected format: "Bearer {password}"
        try:
            scheme, credentials = auth_header.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid authentication scheme")
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header format"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Constant-time compare to prevent timing attacks
        if not hmac.compare_digest(credentials, self.password):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid password"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Password is correct, proceed with the request
        response = await call_next(request)
        return response


# Optional: HTTPBearer security scheme for OpenAPI documentation
security = HTTPBearer(auto_error=False)


def check_api_password(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> bool:
    """Dependency form of the password check used by individual routes."""
    password = _get_api_password()

    if not password:
        return True

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not hmac.compare_digest(credentials.credentials, password):
        raise HTTPException(
            status_code=401,
            detail="Invalid password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
