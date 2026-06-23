"""
FastAPI application entry point.

Endpoints
---------
POST /ingest      – parse & embed the AWS Customer Agreement PDF
POST /ask         – RAG Q&A with SQL logging
GET  /analytics   – SQL-backed usage analytics
GET  /health      – simple liveness probe
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from database import get_analytics, init_db, log_query
from models import AnalyticsResponse, AskRequest, AskResponse, IngestResponse, SourceChunk
from rag import answer_query, ingest_pdf

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RAG Document Q&A",
    description="Retrieval-Augmented Generation over the AWS Customer Agreement",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise the SQLite schema on startup
init_db()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PDF_PATH = Path(__file__).parent.parent / "data" / "aws_agreement.pdf"


def _require_pdf() -> str:
    if not PDF_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PDF not found at {PDF_PATH}. Place the AWS Customer Agreement PDF at data/aws_agreement.pdf.",
        )
    return str(PDF_PATH)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_200_OK)
def ingest():
    """
    Parse, chunk, embed, and store the AWS Customer Agreement PDF.
    Safe to call multiple times — re-ingestion replaces existing data.
    """
    pdf_path = _require_pdf()
    try:
        chunks_created = ingest_pdf(pdf_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        )
    return IngestResponse(
        message="PDF ingested successfully.",
        chunks_created=chunks_created,
        document="aws_agreement.pdf",
    )


@app.post("/ask", response_model=AskResponse, status_code=status.HTTP_200_OK)
def ask(request: AskRequest):
    """
    Answer a question using the RAG pipeline and log the interaction.
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    try:
        result = answer_query(query)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG pipeline error: {exc}",
        )

    log_query(
        query=query,
        answer=result["answer"],
        answer_found=result["answer_found"],
        latency_ms=result["latency_ms"],
        num_sources=len(result["sources"]),
    )

    sources = [
        SourceChunk(
            text=s["text"],
            page=s.get("page"),
            chunk_index=s["chunk_index"],
        )
        for s in result["sources"]
    ]

    return AskResponse(
        query=query,
        answer=result["answer"],
        sources=sources,
        latency_ms=result["latency_ms"],
        answer_found=result["answer_found"],
    )


@app.get("/analytics", response_model=AnalyticsResponse, status_code=status.HTTP_200_OK)
def analytics():
    """
    Return SQL-backed usage analytics (GROUP BY / COUNT / AVG).
    """
    try:
        data = get_analytics()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analytics query failed: {exc}",
        )
    return AnalyticsResponse(**data)