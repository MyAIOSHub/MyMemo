# Utils Module

Small helpers used across the memory-only backend.

## Modules

- **`chunking.py`** — `chunk_text`, `detect_content_type` (HTML / Markdown / plain). Content-type aware splitters via `langchain-text-splitters`. Default 1500-char chunks, 225-char overlap.
- **`embedding.py`** — `generate_embedding` (single) / `generate_embeddings` (batched, default 50). Uses Esperanto embedding model. Handles content larger than chunk size via mean pooling for single-shot case.
- **`encryption.py`** — Fernet encryption helpers (`encrypt_value`, `decrypt_value`). Requires `OPEN_NOTEBOOK_ENCRYPTION_KEY` env var. Derives a stable Fernet key via SHA-256 so callers can use a simple passphrase.
- **`text_utils.py`** — `clean_thinking_content`, `parse_thinking_content`, `remove_non_ascii`, `remove_non_printable`.
- **`token_utils.py`** — `token_count`, `token_cost` via tiktoken.
- **`version_utils.py`** — `compare_versions`, `get_installed_version`, `get_version_from_github`.
- **`error_classifier.py`** — `classify_error()` maps raw LLM provider exceptions to typed `OpenNotebookError` subclasses.
- **`graph_utils.py`** — small `langchain_core.runnables` helpers (relic, kept for model provisioning).

## Removed

- `context_builder.py` — notebook context assembly (sources + notes + insights with token budgeting). Gone with the Notebook/Note domain.

## Quirks

- **No circular imports** — utils never imports from `domain/` (domain imports utils).
- **Token count estimate** — `token_count()` returns an estimate; callers must tolerate slight drift from provider-reported tokens.
- **TIKTOKEN_CACHE_DIR** — set to `/app/tiktoken-cache` in Docker so the encoding is available offline.
