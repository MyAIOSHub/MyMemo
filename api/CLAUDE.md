# API Module

FastAPI backend for MyMemo. Exposes memory proxy + source snapshot store + credentials + model registry on port 5055.

## Purpose

Three layers:
1. **Routers** (`routers/*`): HTTP endpoints
2. **Services** (`memory_service.py`, `memory_import_service.py`, `credentials_service.py`, `command_service.py`): business logic
3. **Schemas** (`models.py`): Pydantic request/response (largely dormant — web UI that validated them is gone; kept where routers still use them)

**Not present anymore** (removed in the memory-only pivot): chat, notebooks, notes, podcasts, source-chat, transformations, insights, search, episode-profiles, speaker-profiles, languages routers + their services + the LangGraph workflows they invoked.

## Startup flow

- Load `.env`
- CORS + `PasswordAuthMiddleware`
- `AsyncMigrationManager` runs on lifespan startup
- Register routers

## Routers (current)

| Router | File | Path | Purpose |
|--------|------|------|---------|
| auth | `routers/auth.py` | `/api/auth` | Password-based login |
| config | `routers/config.py` | `/api/config` | Runtime config for clients |
| credentials | `routers/credentials.py` | `/api/credentials` | CRUD encrypted API keys (Fernet) |
| models | `routers/models.py` | `/api/models` | Model registry (Esperanto) |
| settings | `routers/settings.py` | `/api/settings` | App settings |
| sources | `routers/sources.py` | `/api/sources` | Read/list/delete Source records (memory snapshots) |
| commands | `routers/commands.py` | `/api/commands` | Poll surreal-commands job status |
| embedding_rebuild | `routers/embedding_rebuild.py` | `/api/embeddings/rebuild` | Re-embed all sources |
| memories | `routers/memories.py` | `/api/memories` | Proxy to Memory Hub (:1995) + import-to-Source |

## Key services

- **`memory_service.py`**: httpx.AsyncClient to EverCore v1 API on :1995. Connection pool (max 10), `check_status` / `browse_memories` / `search_memories`.
- **`memory_import_service.py`**: imports memories as `Source` records with `memory_ref` metadata, de-dup by `asset.memory_ref.memory_id`, fire-and-forget vectorization via `source.vectorize()`.
- **`credentials_service.py`**: Fernet-encrypted credential storage, URL validation (SSRF protection allowing localhost for self-hosted), migration helpers from env / ProviderConfig.
- **`command_service.py`**: thin wrapper around `surreal-commands` job submission.

## Common patterns

- Async/await throughout
- Routers import services directly (no DI)
- Auth middleware global — all routes protected; `/docs`, `/health`, `/openapi.json` excluded
- Custom exception hierarchy (`open_notebook.exceptions.OpenNotebookError` + subclasses) mapped to HTTP codes in `main.py`
- LangGraph error classifier (`classify_error`) retained for LLM provider errors even though workflows are gone — `provision_langchain_model` raises through it

## Credential management

Unchanged from upstream. 13 providers, Fernet encryption, URL SSRF protection, test + discover + migrate endpoints. See `credentials_service.py` + `credential.py` domain model.

## Error handling

Global exception handlers in `main.py`:

| Exception | HTTP |
|-----------|------|
| `NotFoundError` | 404 |
| `InvalidInputError` | 400 |
| `AuthenticationError` | 401 |
| `RateLimitError` | 429 |
| `ConfigurationError` | 422 |
| `NetworkError` / `ExternalServiceError` | 502 |
| `OpenNotebookError` (fallback) | 500 |

## Quirks & gotchas

- **Migration auto-run**: `AsyncMigrationManager` fires on FastAPI lifespan startup.
- **`PasswordAuthMiddleware` is dev-grade**: plain shared-secret bearer token. Replace with OAuth/JWT for production.
- **CORS is wide open**: `allow_origins=['*']` + `allow_credentials=True`. Tighten before exposing beyond localhost.
- **Source router is read-mostly**: no file upload, no URL ingest, no notebook link, no insights, no update endpoint. Memory import is the only write path that produces Sources (via the memories router → `memory_import_service`).
- **`api/models.py` has dead Pydantic classes** (InsightResponse, NoteResponse, ChatRequest, PodcastRequest, etc.). Kept to avoid a ripple of imports; trim opportunistically.

## How to add an endpoint

1. Router in `routers/feature.py`
2. Register in `main.py`
3. If it triggers long-running work, submit a surreal command via `command_service`
4. Test at http://localhost:5055/docs

## Testing

- Interactive: http://localhost:5055/docs
- Direct: `uv run pytest tests/test_memory_*`
