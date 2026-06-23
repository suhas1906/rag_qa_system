"""
Pydantic models for request and response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional


class AskRequest(BaseModel):
    """Request model for the /ask endpoint."""
    query: str = Field(..., min_length=1, max_length=1000, description="The question to ask")


class SourceChunk(BaseModel):
    """A source chunk returned with the answer."""
    text: str
    page: Optional[int] = None
    chunk_index: int


class AskResponse(BaseModel):
    """Response model for the /ask endpoint."""
    query: str
    answer: str
    sources: list[SourceChunk]
    latency_ms: float
    answer_found: bool


class IngestResponse(BaseModel):
    """Response model for the /ingest endpoint."""
    message: str
    chunks_created: int
    document: str


class AnalyticsResponse(BaseModel):
    """Response model for the /analytics endpoint."""
    total_queries: int
    avg_latency_ms: float
    unanswered_queries: int
    unanswered_rate_pct: float
    top_questions: list[dict]
    unanswered_questions: list[dict]
    queries_over_time: list[dict]