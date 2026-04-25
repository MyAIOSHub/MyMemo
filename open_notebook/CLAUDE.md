# open_notebook/ — Backend Core

Historical package name (kept to avoid cascading import churn). Contains the reduced surface needed for memory + agent ops.

## Subpackages

| Dir | Purpose |
|-----|---------|
| `domain/` | `Source`, `Asset`, `MemoryRef`, `SourceEmbedding`, `ObjectModel` base, `Credential`. Notebook/Note/ChatSession/SourceInsight + Transformation deleted in the memory pivot. |
| `ai/` | ModelManager + Esperanto integration. Multi-provider LLM/embedding/TTS provisioning. |
| `database/` | SurrealDB async driver wrapper, repository helpers, migrations. |
| `utils/` | Chunking (langchain-text-splitters), embedding (Esperanto), encryption (Fernet), token/text helpers. Context builder deleted. |

## Not present anymore

- `graphs/` — LangGraph workflows (chat, ask, source_chat, transformation, source, prompt, tools). All deleted.
- `podcasts/` — podcast-creator integration. Deleted.
- `utils/context_builder.py` — notebook context assembly. Deleted.
- `domain/notebook.py` — was `Notebook`, `Note`, `ChatSession`, `SourceInsight`, `text_search`, `vector_search`. Now holds only `Source`, `Asset`, `MemoryRef`, `SourceEmbedding`.
- `domain/transformation.py` — deleted.

## Architecture highlights

### 1. Async-first

All DB + AI calls are async. SurrealDB async driver with connection pool.

### 2. Multi-provider AI via Esperanto

Unified interface to 8+ providers. Credentials are stored per-provider in SurrealDB (Fernet encrypted). `ModelManager` factory resolves credentials DB-first, env-var fallback.

### 3. Database schema

Automatic migrations on API startup. Graph DB + built-in vector search. Relevant tables post-pivot: `source`, `source_embedding`, `credential`, `model`, `settings`.

### 4. Error handling

Exception hierarchy in `exceptions.py` rooted at `OpenNotebookError`. `utils/error_classifier.classify_error()` maps raw provider exceptions to typed errors for FastAPI handlers.

## Component references

- **[domain/CLAUDE.md](domain/CLAUDE.md)**: Source lifecycle + memory_ref
- **[ai/CLAUDE.md](ai/CLAUDE.md)**: ModelManager, Esperanto, credentials resolution
- **[database/CLAUDE.md](database/CLAUDE.md)**: SurrealDB ops, migrations
- **[utils/CLAUDE.md](utils/CLAUDE.md)**: Chunking, embedding, encryption utils

## Quirks

- **Migrations auto-run** on every API startup.
- **SurrealDB must be reachable** or API fails startup.
- **`Source.vectorize()` is fire-and-forget** — returns command_id, actual work happens via the `embed_source` surreal command.
- **No LangGraph workflows** — pure function calls or surreal-commands jobs only. `ai/provision.py` still uses `langchain_core` types for Esperanto's interface.

## Support

- Issues: https://github.com/MyAIOSHub/MyMemo/issues
