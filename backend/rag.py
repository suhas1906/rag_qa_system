"""
RAG Pipeline
============
Chunking strategy
-----------------
Chunk size  : 500 tokens (~400 words)
Overlap     : 100 tokens (~80 words)

Rationale:
- The AWS Customer Agreement is dense legal prose with long paragraphs.
  500-token chunks keep each chunk semantically coherent (one clause /
  sub-section) while staying well within embedding model input limits.
- A 100-token overlap ensures that sentences that straddle a boundary are
  present in both adjacent chunks, preventing retrieval misses at edges.

Top-k choice: 4
- k=4 gives ~2 000 tokens of context, comfortably within the LLM's prompt
  budget while covering enough of the document to answer most multi-part
  questions.

Embedding model : all-MiniLM-L6-v2 (sentence-transformers)
LLM : Groq llama-3.3-70b-versatile (free)
"""

import os
import re
import time
from pathlib import Path

import chromadb
from groq import Groq
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_SIZE    = 500
CHUNK_OVERLAP = 100
TOP_K         = 4
COLLECTION    = "aws_agreement"
CHROMA_DIR    = str(Path(__file__).parent / "chroma_store")

NOT_FOUND_SIGNAL = "ANSWER_NOT_IN_DOCUMENT"

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_embedder = None
_chroma_client = None
_collection = None
_groq_client = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _get_collection():
    global _chroma_client, _collection
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    if _collection is None:
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


# ---------------------------------------------------------------------------
# PDF parsing & chunking
# ---------------------------------------------------------------------------

def _extract_text_from_pdf(pdf_path: str) -> list[tuple[str, int]]:
    """Return a list of (page_text, page_number) tuples."""
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            pages.append((text, i))
    return pages


def _word_tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer."""
    return text.split()


def _chunk_text(pages: list[tuple[str, int]]) -> list[dict]:
    """
    Slide a window of CHUNK_SIZE words with CHUNK_OVERLAP across
    the full document.
    """
    word_page_pairs: list[tuple[str, int]] = []
    for text, page_num in pages:
        for word in _word_tokenize(text):
            word_page_pairs.append((word, page_num))

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(word_page_pairs):
        end = min(start + CHUNK_SIZE, len(word_page_pairs))
        window = word_page_pairs[start:end]
        chunk_words = [w for w, _ in window]
        chunk_page  = window[0][1]

        chunks.append({
            "text":        " ".join(chunk_words),
            "page":        chunk_page,
            "chunk_index": chunk_index,
        })

        chunk_index += 1
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest_pdf(pdf_path: str) -> int:
    """Parse, chunk, embed, and store the PDF."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass

    global _collection
    _collection = None

    pages  = _extract_text_from_pdf(pdf_path)
    chunks = _chunk_text(pages)

    embedder   = _get_embedder()
    collection = _get_collection()

    texts      = [c["text"] for c in chunks]
    embeddings = embedder.encode(texts, show_progress_bar=True).tolist()

    ids        = [f"chunk_{c['chunk_index']}" for c in chunks]
    metadatas  = [{"page": c["page"], "chunk_index": c["chunk_index"]} for c in chunks]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    return len(chunks)


# ---------------------------------------------------------------------------
# Query / retrieval
# ---------------------------------------------------------------------------

def _retrieve(query: str) -> list[dict]:
    """Embed the query and return top-k chunks from ChromaDB."""
    embedder   = _get_embedder()
    collection = _get_collection()

    if collection.count() == 0:
        raise RuntimeError("No document ingested yet. Call POST /ingest first.")

    query_embedding = embedder.encode([query]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(TOP_K, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text":        doc,
            "page":        meta.get("page"),
            "chunk_index": meta.get("chunk_index"),
            "distance":    dist,
        })

    return chunks


def _build_prompt(query: str, context_chunks: list[dict]) -> str:
    """Construct the RAG prompt sent to the LLM."""
    context_sections = []
    for i, chunk in enumerate(context_chunks, start=1):
        context_sections.append(
            f"[Source {i} — Page {chunk['page']}]\n{chunk['text']}"
        )
    context_text = "\n\n---\n\n".join(context_sections)

    return f"""You are a precise assistant that answers questions ONLY using the provided document excerpts from the AWS Customer Agreement.

DOCUMENT EXCERPTS:
{context_text}

---

INSTRUCTIONS:
- Answer the question using ONLY the information in the excerpts above.
- If the answer cannot be found in the excerpts, respond with exactly: {NOT_FOUND_SIGNAL}
- Do not add external knowledge or make up information.
- Be concise and cite the relevant section where possible.

QUESTION: {query}

ANSWER:"""


def answer_query(query: str) -> dict:
    """Full RAG pipeline: retrieve → prompt → LLM → parse."""
    t0 = time.perf_counter()

    chunks = _retrieve(query)
    prompt = _build_prompt(query, chunks)

    client = _get_groq()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )

    raw_answer = response.choices[0].message.content.strip()
    answer_found = NOT_FOUND_SIGNAL not in raw_answer

    if not answer_found:
        answer = "The answer to your question was not found in the AWS Customer Agreement."
    else:
        answer = raw_answer

    latency_ms = (time.perf_counter() - t0) * 1000

    sources = [
        {
            "text":        c["text"],
            "page":        c["page"],
            "chunk_index": c["chunk_index"],
        }
        for c in chunks
    ]

    return {
        "answer":       answer,
        "sources":      sources if answer_found else [],
        "answer_found": answer_found,
        "latency_ms":   round(latency_ms, 2),
    }