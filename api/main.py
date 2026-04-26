# Load environment variables
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.auth import PasswordAuthMiddleware
from open_notebook.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ExternalServiceError,
    InvalidInputError,
    NetworkError,
    NotFoundError,
    OpenNotebookError,
    RateLimitError,
)
from api.routers import (
    auth,
    config,
    credentials,
    embedding_rebuild,
    memories,
    models,
    settings,
    sources,
)
from api.routers import commands as commands_router
from open_notebook.database.async_migrate import AsyncMigrationManager
from open_notebook.utils.encryption import get_secret_from_env

# Import commands to register them in the API process
try:
    logger.info("Commands imported in API process")
except Exception as e:
    logger.error(f"Failed to import commands in API process: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for the FastAPI application.
    Runs database migrations automatically on startup.
    """
    import os

    # Startup: Security checks
    logger.info("Starting API initialization...")

    # Security check: Encryption key (MYMEMO_ENCRYPTION_KEY with legacy fallback).
    if not (
        get_secret_from_env("MYMEMO_ENCRYPTION_KEY")
        or get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY")
    ):
        logger.warning(
            "Neither MYMEMO_ENCRYPTION_KEY nor OPEN_NOTEBOOK_ENCRYPTION_KEY is set. "
            "API key encryption will fail until one is configured. "
            "Set MYMEMO_ENCRYPTION_KEY to any secret string."
        )

    # Surface the resolved SurrealDB namespace + database. .env files copied
    # from older forks may still pin SURREAL_NAMESPACE=open_notebook while
    # docker-compose.yml uses mymemo, which silently splits data between the
    # two paths. Logging the value lets operators catch the drift.
    logger.info(
        "SurrealDB target: namespace={ns} database={db}",
        ns=os.environ.get("SURREAL_NAMESPACE", "<default>"),
        db=os.environ.get("SURREAL_DATABASE", "<default>"),
    )

    # Run database migrations

    try:
        migration_manager = AsyncMigrationManager()
        current_version = await migration_manager.get_current_version()
        logger.info(f"Current database version: {current_version}")

        if await migration_manager.needs_migration():
            logger.warning("Database migrations are pending. Running migrations...")
            await migration_manager.run_migration_up()
            new_version = await migration_manager.get_current_version()
            logger.success(
                f"Migrations completed successfully. Database is now at version {new_version}"
            )
        else:
            logger.info(
                "Database is already at the latest version. No migrations needed."
            )
    except Exception as e:
        logger.error(f"CRITICAL: Database migration failed: {str(e)}")
        logger.exception(e)
        # Fail fast - don't start the API with an outdated database schema
        raise RuntimeError(f"Failed to run database migrations: {str(e)}") from e

    logger.success("API initialization completed successfully")

    # Yield control to the application
    yield

    # Shutdown: cleanup resources
    from api.memory_service import memory_service

    await memory_service.close()
    logger.info("API shutdown complete")


app = FastAPI(
    title="MyMemo API",
    description="REST API for MyMemo — memory + agent infrastructure",
    lifespan=lifespan,
)


def _allowed_origins() -> list[str]:
    """Configured CORS origins. Supports `MYMEMO_CORS_ORIGINS=foo,bar`.

    Default: localhost dev origins (http://localhost:3000 / 127.0.0.1).
    Set `MYMEMO_CORS_ORIGINS=*` only if explicitly intended (NOT recommended
    with credentials).
    """
    raw = os.environ.get("MYMEMO_CORS_ORIGINS", "").strip()
    if not raw:
        return [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5055",
            "http://127.0.0.1:5055",
        ]
    return [o.strip() for o in raw.split(",") if o.strip()]


_CORS_ORIGINS = _allowed_origins()
_CORS_WILDCARD = _CORS_ORIGINS == ["*"]


def _is_debug_mode() -> bool:
    return os.environ.get("MYMEMO_DEBUG", "").lower() in ("1", "true", "yes")


# Password auth middleware. /docs and /openapi.json are gated unless MYMEMO_DEBUG is set.
_excluded = ["/", "/health", "/api/auth/status", "/api/config"]
if _is_debug_mode():
    _excluded.extend(["/docs", "/openapi.json", "/redoc"])

app.add_middleware(
    PasswordAuthMiddleware,
    excluded_paths=_excluded,
)

# CORS — explicit allowlist by default. `allow_credentials=True` is incompatible
# with `allow_origins=['*']` per the spec; we keep credentials but require an
# explicit origin set unless the operator opted into wildcard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=not _CORS_WILDCARD,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _safe_origin(request: Request) -> Optional[str]:
    origin = request.headers.get("origin")
    if not origin:
        return None
    if _CORS_WILDCARD:
        return "*"
    return origin if origin in _CORS_ORIGINS else None


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Ensure CORS headers on error responses, but only for allowed origins."""
    origin = _safe_origin(request)
    headers = dict(exc.headers or {})
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        if not _CORS_WILDCARD:
            headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


def _cors_headers(request: Request) -> dict[str, str]:
    origin = _safe_origin(request)
    if not origin:
        return {}
    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }
    if not _CORS_WILDCARD:
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(InvalidInputError)
async def invalid_input_error_handler(request: Request, exc: InvalidInputError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=401,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(RateLimitError)
async def rate_limit_error_handler(request: Request, exc: RateLimitError):
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(request: Request, exc: ConfigurationError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(NetworkError)
async def network_error_handler(request: Request, exc: NetworkError):
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(ExternalServiceError)
async def external_service_error_handler(request: Request, exc: ExternalServiceError):
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


@app.exception_handler(OpenNotebookError)
async def open_notebook_error_handler(request: Request, exc: OpenNotebookError):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers=_cors_headers(request),
    )


# Include routers
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(
    embedding_rebuild.router, prefix="/api/embeddings", tags=["embeddings"]
)
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(sources.router, prefix="/api", tags=["sources"])
app.include_router(commands_router.router, prefix="/api", tags=["commands"])
app.include_router(credentials.router, prefix="/api", tags=["credentials"])
app.include_router(memories.router, prefix="/api", tags=["memories"])


@app.get("/")
async def root():
    return {"message": "MyMemo API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
