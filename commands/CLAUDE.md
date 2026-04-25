# Commands Module

Async command handlers for long-running work via `surreal-commands` job queue. Post memory-pivot there are exactly two real commands + two test fixtures.

## Commands

- **`embed_source_command`**: Chunk a Source's `full_text` (content-type aware splitters — HTML / Markdown / plain), generate chunk embeddings in batches via Esperanto, bulk-insert into `source_embedding` table. Retry: 5 attempts, exponential jitter 1–60s, `stop_on=[ValueError, ConfigurationError]`.
- **`rebuild_embeddings_command`**: Coordinator — submits one `embed_source` per existing Source. No retry (coordinator only). Modes: `existing` (only sources that already have embeddings) / `all` (every source with text).
- **`process_text_command`** (example): Test fixture (uppercase/lowercase/reverse/word_count).
- **`analyze_data_command`** (example): Test fixture for numeric aggregations.

## Removed

- `embed_note_command`, `embed_insight_command`, `create_insight_command` — `Note` + `SourceInsight` classes deleted
- `process_source_command`, `run_transformation_command` — source graph + transformation domain deleted
- `generate_podcast_command` — podcast-creator integration deleted

## Patterns

- **Pydantic I/O**: `CommandInput` / `CommandOutput` subclasses for type safety.
- **Error policy**: `ValueError` / `ConfigurationError` = permanent (no retry); everything else retries with exponential jitter.
- **Fire-and-forget**: `Source.vectorize()` submits `embed_source` via `submit_command()` without waiting.
- **Content-type aware chunking**: `embed_source` uses `chunk_text()` with detection from file extension + heuristics. Default 1500-char chunks, 225-char overlap.
- **Batch embedding**: `generate_embeddings()` auto-batches (default 50) with per-batch retry.

## Dependencies

External: `surreal_commands`, `loguru`, `pydantic`
Internal: `open_notebook.domain.notebook` (Source), `open_notebook.utils.chunking`, `open_notebook.utils.embedding`, `open_notebook.database.repository`

## Edge cases

- Empty / whitespace-only `full_text` → `ValueError` (not retried)
- Chunk / embedding count mismatch → `ValueError` (not retried)
- Existing `source_embedding` rows are deleted before re-embedding (idempotent)

## Example

```python
@command(
    "embed_source",
    app="open_notebook",
    retry={
        "max_attempts": 5,
        "wait_strategy": "exponential_jitter",
        "stop_on": [ValueError, ConfigurationError],
    },
)
async def embed_source_command(input_data: EmbedSourceInput) -> EmbedSourceOutput:
    ...
```
