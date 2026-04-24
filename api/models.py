"""Pydantic schemas used by the MyMemo REST API.

Post memory-pivot, only the schemas actually imported by live routers
(models, credentials, embedding_rebuild, settings) remain. Notebook / Note /
Chat / Ask / Search / Transformation / Insight / Podcast / Source request
schemas were deleted with their endpoints.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ===========================================================================
# Models registry
# ===========================================================================


class ModelCreate(BaseModel):
    name: str = Field(..., description="Model name (e.g., gpt-5-mini, claude, gemini)")
    provider: str = Field(..., description="Provider name (openai, anthropic, etc.)")
    type: str = Field(
        ...,
        description="Model type (language, embedding, text_to_speech, speech_to_text)",
    )
    credential: Optional[str] = Field(
        None, description="Credential ID to link this model to"
    )


class ModelResponse(BaseModel):
    id: str
    name: str
    provider: str
    type: str
    credential: Optional[str] = None
    created: str
    updated: str


class DefaultModelsResponse(BaseModel):
    default_chat_model: Optional[str] = None
    default_transformation_model: Optional[str] = None
    large_context_model: Optional[str] = None
    default_text_to_speech_model: Optional[str] = None
    default_speech_to_text_model: Optional[str] = None
    default_embedding_model: Optional[str] = None
    default_tools_model: Optional[str] = None


class ProviderAvailabilityResponse(BaseModel):
    available: List[str] = Field(..., description="List of available providers")
    unavailable: List[str] = Field(..., description="List of unavailable providers")
    supported_types: Dict[str, List[str]] = Field(
        ..., description="Provider to supported model types mapping"
    )


# ===========================================================================
# Embedding rebuild
# ===========================================================================


class RebuildRequest(BaseModel):
    mode: Literal["existing", "all"] = Field(
        ...,
        description="'existing' re-embeds sources that already have embeddings; "
        "'all' embeds every source with text",
    )


class RebuildResponse(BaseModel):
    command_id: str = Field(..., description="Command ID to track progress")
    total_items: int = Field(..., description="Estimated number of items to process")
    message: str = Field(..., description="Status message")


class RebuildProgress(BaseModel):
    processed: int
    total: int
    percentage: float


class RebuildStats(BaseModel):
    sources: int = 0
    failed: int = 0


class RebuildStatusResponse(BaseModel):
    command_id: str
    status: str = Field(..., description="queued, running, completed, failed")
    progress: Optional[RebuildProgress] = None
    stats: Optional[RebuildStats] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


# ===========================================================================
# Settings
# ===========================================================================


class SettingsResponse(BaseModel):
    default_content_processing_engine_doc: Optional[str] = None
    default_content_processing_engine_url: Optional[str] = None
    default_embedding_option: Optional[str] = None
    auto_delete_files: Optional[str] = None
    youtube_preferred_languages: Optional[List[str]] = None


class SettingsUpdate(BaseModel):
    default_content_processing_engine_doc: Optional[str] = None
    default_content_processing_engine_url: Optional[str] = None
    default_embedding_option: Optional[str] = None
    auto_delete_files: Optional[str] = None
    youtube_preferred_languages: Optional[List[str]] = None


# ===========================================================================
# Credentials
# ===========================================================================


class CreateCredentialRequest(BaseModel):
    name: str = Field(..., description="Credential name")
    provider: str = Field(..., description="Provider name (openai, anthropic, etc.)")
    modalities: List[str] = Field(
        default_factory=list,
        description="Supported modalities (language, embedding, text_to_speech, speech_to_text)",
    )
    api_key: Optional[str] = Field(None, description="API key (stored encrypted)")
    base_url: Optional[str] = None
    endpoint: Optional[str] = Field(None, description="Endpoint URL (Azure)")
    api_version: Optional[str] = Field(None, description="API version (Azure)")
    endpoint_llm: Optional[str] = None
    endpoint_embedding: Optional[str] = None
    endpoint_stt: Optional[str] = None
    endpoint_tts: Optional[str] = None
    project: Optional[str] = Field(None, description="Project ID (Vertex)")
    location: Optional[str] = Field(None, description="Location (Vertex)")
    credentials_path: Optional[str] = Field(
        None, description="Credentials file path (Vertex)"
    )


class UpdateCredentialRequest(BaseModel):
    name: Optional[str] = None
    modalities: Optional[List[str]] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    endpoint: Optional[str] = None
    api_version: Optional[str] = None
    endpoint_llm: Optional[str] = None
    endpoint_embedding: Optional[str] = None
    endpoint_stt: Optional[str] = None
    endpoint_tts: Optional[str] = None
    project: Optional[str] = None
    location: Optional[str] = None
    credentials_path: Optional[str] = None


class CredentialResponse(BaseModel):
    """Response for a credential (never includes raw api_key)."""

    id: str
    name: str
    provider: str
    modalities: List[str]
    base_url: Optional[str] = None
    endpoint: Optional[str] = None
    api_version: Optional[str] = None
    endpoint_llm: Optional[str] = None
    endpoint_embedding: Optional[str] = None
    endpoint_stt: Optional[str] = None
    endpoint_tts: Optional[str] = None
    project: Optional[str] = None
    location: Optional[str] = None
    credentials_path: Optional[str] = None
    has_api_key: bool = False
    created: str
    updated: str
    model_count: int = 0


class CredentialDeleteResponse(BaseModel):
    message: str
    deleted_models: int = 0


class DiscoveredModelResponse(BaseModel):
    name: str
    provider: str
    model_type: Optional[str] = None
    description: Optional[str] = None


class DiscoverModelsResponse(BaseModel):
    credential_id: str
    provider: str
    discovered: List[DiscoveredModelResponse]


class RegisterModelData(BaseModel):
    name: str
    provider: str
    model_type: str


class RegisterModelsRequest(BaseModel):
    models: List[RegisterModelData]


class RegisterModelsResponse(BaseModel):
    created: int
    existing: int


# ===========================================================================
# Generic
# ===========================================================================


class ErrorResponse(BaseModel):
    error: str
    message: str
