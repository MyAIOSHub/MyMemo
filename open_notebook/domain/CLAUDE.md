# Domain Module

Data models with async SurrealDB persistence. Post memory-pivot the domain is minimal: memory snapshots + embeddings + credentials.

## Files

- **`base.py`** — `ObjectModel` (auto-id records) + `RecordModel` (singletons). `save`/`delete`/`relate`/`get` + auto-embedding hook (only used by `Source` now).
- **`notebook.py`** — **misnamed but retained** to avoid an import ripple. Contains: `MemoryRef`, `Asset`, `Source`, `SourceEmbedding`. Notebook/Note/ChatSession/SourceInsight/text_search/vector_search were removed.
- **`credential.py`** — `Credential` records, one per API key. Fernet-encrypted `api_key` (SecretStr). `to_esperanto_config()` for AIFactory.
- **`provider_config.py`** — legacy, retained only so migrations from old ProviderConfig records can still read them.
- **`models.py`** — `Model` records (registry of provisioned models).
- **`content_settings.py`** — `ContentSettings` singleton (file-deletion policy, etc).

## Source (post-pivot)

```python
class Source(ObjectModel):
    asset: Optional[Asset]       # file_path / url / memory_ref
    title: Optional[str]
    topics: Optional[List[str]]
    full_text: Optional[str]
    command: Optional[RecordID]  # link to embed_source job

    async def vectorize() -> str            # submit embed_source command
    async def get_status() -> Optional[str] # poll command
    async def get_processing_progress() -> Optional[Dict]
    async def get_context(size) -> Dict     # short/long, no insight bundling
    async def delete() -> bool               # cascades to source_embedding rows
```

Removed methods: `add_to_notebook`, `add_insight`, `get_insights`. The `asset.memory_ref` field is the only provenance carried now.

## MemoryRef

Pydantic model for EverCore memory metadata on an imported Source:

```python
class MemoryRef(BaseModel):
    memory_id: str
    memory_type: Literal[
        "episodic_memory", "profile", "raw_message",
        "event_log", "foresight",  # legacy v0
    ] = "episodic_memory"
    user_id: Optional[str]
    source_origin: Literal["browser", "claude_code", "evermemo"] = "evermemo"
    group_id: Optional[str]
    group_name: Optional[str]
    original_timestamp: Optional[str]
```

`api/memory_import_service.py` populates this; de-dup check queries `WHERE asset.memory_ref.memory_id = $id`.

## Patterns

- **Async/await** throughout
- **Polymorphic `get()`** on ObjectModel resolves subclass from `table:id` prefix — currently only `Source` and `Credential` use it
- **Fire-and-forget embedding**: `Source.vectorize()` submits a surreal command
- **Timestamps**: `created` / `updated` auto-managed ISO strings

## Quirks

- **`notebook.py` file name is legacy** — no Notebook class in it. Rename when refactoring imports project-wide.
- **`Source.command` field** — stored as RecordID, parsed from strings via field_validator
- **Auto-embedding**: `Source.save()` does NOT auto-submit; caller must call `vectorize()` explicitly
- **Search functions gone**: `text_search` / `vector_search` removed; if needed again, point at the EverCore search endpoint at :1995 instead of re-wiring SurrealDB
