# Memory Hub

Powered by [EverMind-AI/EverOS](https://github.com/EverMind-AI/EverOS) (the project previously known as EverMemOS; the memory engine is now called **EverCore**). The hub bundles EverCore with MyAttention local-store and CCHistory behind a single nginx gateway on `:1995`.

## Start

1. Export the model keys you actually use, or copy values from [memory-hub.env.example](./memory-hub.env.example).
2. The default memory stack uses DashScope for `LLM`, `embedding`, and `rerank`. In the common setup, `LLM_API_KEY`, `VECTORIZE_API_KEY`, and `RERANK_API_KEY` can all use the same Bailian key.
3. `VECTORIZE_BASE_URL` defaults to `https://dashscope.aliyuncs.com/compatible-mode/v1` with `text-embedding-v4`.
4. `RERANK_BASE_URL` defaults to `https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank` with `qwen3-rerank`.
5. `TENANT_SINGLE_TENANT_ID` defaults to `t_mymemo` (single-tenant mode — required by EverCore v1).
6. Run `docker compose -f docker-compose.memory-hub.yml --env-file memory-hub.env up --build`.
7. Open `http://127.0.0.1:1995/cc/` for Claude Code history, or `http://127.0.0.1:1995/docs` for EverCore.

## Endpoints

- `http://127.0.0.1:1995/api/v1/*` → EverCore (v1 API)
- `http://127.0.0.1:1995/local-store/*` → MyAttention-local-store
- `http://127.0.0.1:1995/cc/*` → cchistory

### EverCore v1 highlights

All memory reads/writes are now `POST` with JSON body (v0 `GET` querystring routes are gone):

- `POST /api/v1/memories` — store messages (personal scene)
- `POST /api/v1/memories/get` — browse memories (body: `memory_type`, `page`, `page_size`, `filters`)
- `POST /api/v1/memories/search` — search (body: `query`, `method`, `memory_types`, `top_k`, `filters`)
- `PUT /api/v1/settings` — **required** before the first write to init the tenant settings
- `POST /api/v1/memories/delete` — soft delete (currently not invoked by Open Notebook — see note below)

### Tenant context

EverCore v1 enforces strict tenant isolation. The docker-compose wires `TENANT_SINGLE_TENANT_ID` (default `t_mymemo`); change it only if you run multiple independent memory spaces on the same machine. All data is namespaced under that id in MongoDB / Milvus / Elasticsearch.

### Delete policy

Deleting a memory-sourced `Source` inside Open Notebook **does not** cascade to EverCore. The underlying memory stays in EverCore; only the local `source` record is removed. This is deliberate to prevent accidental loss of primary memories.

## Claude Code Sync

- `cchistory` scans `${HOME}/.claude/projects` automatically after startup.
- Manual sync: `POST /cc/api/sync/run`
- Import one session: `POST /cc/api/session/{session_id}/import`
- Status: `GET /cc/api/sync/status`

## MCP

The bundled MCP server lives at [memory-hub-mcp/memory_hub_mcp.py](./memory-hub-mcp/memory_hub_mcp.py). It exposes `search_memories`, `recent_memories`, and a `materialize` tool (which calls into [memory-hub-mcp/materializer.py](./memory-hub-mcp/materializer.py) to render `user-preferences.md`, `recent-focus.md`, and `project-*.md`). Wire it into any MCP-aware client over stdio — see [memory-hub-mcp/README.md](./memory-hub-mcp/README.md) for the connection snippet.

## Upgrading the vendored EverCore source

The `EverMemOS/` directory is a vendored snapshot of `EverMind-AI/EverOS` → `methods/evermemos/`, with one local patch: **DashScope provider support** in [EverMemOS/src/agentic_layer/vectorize_dashscope.py](../EverMemOS/src/agentic_layer/vectorize_dashscope.py) and [EverMemOS/src/agentic_layer/rerank_dashscope.py](../EverMemOS/src/agentic_layer/rerank_dashscope.py). Upstream does not ship DashScope — if you re-sync, re-apply these two files plus the `elif provider.lower() == "dashscope":` branches in `vectorize_service.py` and `rerank_service.py`.
