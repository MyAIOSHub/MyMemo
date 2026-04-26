# MyMemo — Root CLAUDE.md

Architectural guidance for contributors.

## Project Overview

**MyMemo** = self-hosted memory + agent infrastructure for AI coding tools. Collects context (browser attention, Claude Code sessions, manual input), processes via LLM into searchable episodic memories, serves unified HTTP API for any agent.

Originated as a fork of lfnovo/open-notebook. The Open Notebook web surface (notebooks, chat, podcasts, transformations, notes) has been ripped out. What remains: memory ingestion + agent system + MCP server + materializer.

**Key values**: Privacy-first, local-only by default, agent-native, multi-provider AI.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Agent Consumption Layer                  │
│                                                             │
│  Claude Code hooks   MCP server (stdio)   MemoDesktop       │
│  Materializer .md    HTTP API clients     (external)        │
└──────────────┬──────────────────────────────┬──────────────┘
               │                              │
               │ HTTP                         │ HTTP :5055
               │                              │
┌──────────────▼─────────┐     ┌─────────────▼──────────────┐
│ Memory Hub gateway     │     │  MyMemo API (FastAPI)      │
│ nginx @ :1995          │     │  api/ + open_notebook/     │
├────────────────────────┤     ├────────────────────────────┤
│ /api/v1/* → EverCore   │     │ /api/memories   (proxy)    │
│ /local-store/* → MyAtt │     │ /api/sources    (snapshot) │
│ /cc/* → cchistory      │     │ /api/credentials           │
│                        │     │ /api/models /api/settings  │
│ MongoDB + Milvus + ES  │     │ /api/embeddings/rebuild    │
│ + Redis + DashScope    │     └──────────────┬─────────────┘
└────────────┬───────────┘                    │ SurrealQL
             │ vendored in EverMemOS/         │
             │                   ┌────────────▼──────────────┐
             │                   │ SurrealDB @ :8000         │
             │                   │ Source (with memory_ref), │
             └───── referenced ──┤ SourceEmbedding,          │
                                 │ Credential                │
                                 └───────────────────────────┘
```

**Three discrete stacks**:

1. **Memory Hub** (`docker-compose.memory-hub.yml` + `EverMemOS/`): nginx + EverCore + MyAttention + cchistory + Mongo + Milvus + ES + Redis. Port 1995. **Do not touch** without understanding the EverCore vendored patches.

2. **MyMemo API** (`api/` + `open_notebook/` + `commands/`): FastAPI on port 5055. Proxies memory ops to 1995, stores imported memories as local `Source` records (+ vector chunks) in SurrealDB.

3. **Agent system** (`agent/` + `memory-hub-mcp/`): Claude Agent SDK based agent + skills, MCP server for external agents, materializer that turns episodic memories into topic `.md` files.

---

## Tech Stack

- **Language**: Python 3.11+
- **API framework**: FastAPI 0.104+
- **Database**: SurrealDB (graph DB + vectors; hosts Source + Credential snapshots only)
- **AI providers**: Esperanto (8+ providers)
- **Job queue**: Surreal-Commands (embed_source, rebuild_embeddings)
- **Chunking**: langchain-text-splitters
- **Logging**: Loguru
- **Validation**: Pydantic v2

Memory Hub stack runs separately (vendored EverMemOS + DashScope patches).

---

## Discrete Components

- **[api/CLAUDE.md](api/CLAUDE.md)**: FastAPI routers, services, memory proxy
- **[open_notebook/CLAUDE.md](open_notebook/CLAUDE.md)**: Domain models (Source, Asset, MemoryRef), AI provisioning, database
- **[open_notebook/domain/CLAUDE.md](open_notebook/domain/CLAUDE.md)**: Source + MemoryRef lifecycle
- **[open_notebook/ai/CLAUDE.md](open_notebook/ai/CLAUDE.md)**: ModelManager, Esperanto
- **[open_notebook/database/CLAUDE.md](open_notebook/database/CLAUDE.md)**: SurrealDB ops
- **[commands/CLAUDE.md](commands/CLAUDE.md)**: Surreal-commands (embed_source, rebuild_embeddings)
- **[agent/](agent/)**: Agent system, skills, meeting mode
- **[memory-hub-mcp/README.md](memory-hub-mcp/README.md)**: MCP server + materializer
- **[scripts/import_sayso.py](scripts/import_sayso.py)**: Pull meetings + voice transcripts from `~/.config/ai.sayso.app/db.sqlite3` into EverCore as `sayso-meeting` / `sayso-transcript` group memories. Idempotent watermark in `data/sayso-import.state`.

---

## Port Map

| Port | Service | Owner |
|------|---------|-------|
| 1995 | Memory Hub nginx gateway | `docker-compose.memory-hub.yml` (separate stack) |
| 5055 | MyMemo REST API | `api/main.py` |
| 8000 | SurrealDB | `docker-compose.yml` |

Port 1995 must stay reachable for the API proxy + MCP server + materializer. Changes to the MyMemo API must not break it.

---

## Removed (legacy Open Notebook)

These features were in the upstream fork. Removed in the memory-only pivot:

- Notebook / Note / ChatSession domain models
- Chat, ask, transformation, source_chat, insight LangGraph workflows
- Podcast generation (podcast-creator library)
- File upload / URL ingest routers
- Web frontend (Next.js) + desktop shell (Electron)
- Streamlit legacy pages

Memory imports still create `Source` records, but as **memory snapshots with `memory_ref` provenance**, not manually-uploaded research content.

---

## Common Tasks

### Run locally

```bash
# 1. Memory Hub (separate terminal)
docker compose -f docker-compose.memory-hub.yml --env-file memory-hub.env up

# 2. SurrealDB + API + worker
make start-all
```

### Import memories into the local Source store

```bash
curl -X POST http://localhost:5055/api/memories/import \
  -H 'Content-Type: application/json' \
  -d '{"memory_ids":["ep_123"],"memory_type":"episodic_memory","notebook_id":"default"}'
```

The `notebook_id` field is retained for legacy compatibility but is treated as an opaque grouping string — Notebook records no longer exist in the schema.

### Add a new API endpoint

1. Router in `api/routers/feature.py`
2. Register in `api/main.py`
3. Hit http://localhost:5055/docs

### Add a DB migration

1. `open_notebook/database/migrations/XXX_description.surql`
2. Optional `XXX_description_down.surql`
3. Auto-runs on API startup

---

## Quirks & Gotchas

- **Migrations auto-run** on API startup via `AsyncMigrationManager`.
- **Memory Hub can be offline** — API degrades gracefully. `/memories/status` returns `connected: false`.
- **`TENANT_SINGLE_TENANT_ID=t_mymemo`** on the Memory Hub side; all records namespaced under that tenant in Mongo/Milvus/ES.
- **Source.vectorize() is fire-and-forget** — returns command_id immediately; `/commands/{id}` endpoint polls status.
- **DashScope is patched** into EverMemOS locally (`EverMemOS/src/agentic_layer/vectorize_dashscope.py` + `rerank_dashscope.py`). Upstream sync must re-apply.
- **No web UI** — all consumption is via HTTP, MCP, or agent. External clients like MemoDesktop connect to port 1995 directly.

---

## Support

- **Issues**: https://github.com/MyAIOSHub/MyMemo/issues
- **License**: MIT
