\# RAG Document Q\&A System



A Retrieval-Augmented Generation (RAG) system that answers questions about the AWS Customer Agreement, with a FastAPI backend, SQLite analytics logging, and a Streamlit frontend.



\---



\## Architecture Overview
┌─────────────────────────────────────────────────────┐



│                   Streamlit UI                      │



│   (Chat Interface + Analytics Dashboard)            │



└──────────────────────┬──────────────────────────────┘



│ HTTP (requests)



▼



┌─────────────────────────────────────────────────────┐



│                FastAPI Backend                      │



│  POST /ingest   POST /ask   GET /analytics          │



│                                                     │



│  ┌────────────────────┐  ┌──────────────────────┐   │



│  │    RAG Pipeline    │  │   SQLite Logging     │   │



│  │  pypdf (parse)     │  │  query\_logs table    │   │



│  │  sentence-trans.   │  │  GROUP BY / AVG /    │   │



│  │  (embed chunks)    │  │  COUNT analytics     │   │



│  │  ChromaDB          │  └──────────────────────┘   │



│  │  (vector store)    │                             │



│  │  Groq Llama 3.3    │                             │



│  │  (LLM answer)      │                             │



│  └────────────────────┘                             │



└─────────────────────────────────────────────────────┘

---



\## Key Design Decisions



\### Chunking Strategy

| Parameter | Value | Rationale |

|-----------|-------|-----------|

| Chunk size | 500 words | Keeps each chunk semantically coherent (one clause/sub-section) while staying within embedding model limits |

| Overlap | 100 words | Prevents retrieval misses at chunk boundaries; sentences that straddle a split appear in both adjacent chunks |



\### Top-k = 4

Four chunks provide around 2000 words of context — enough to answer most multi-part legal questions while staying within the LLM prompt window.



\### Embedding Model: `all-MiniLM-L6-v2`

\- Runs entirely offline (no API cost)

\- Fast inference on CPU

\- Strong performance on semantic similarity with short passages



\### Vector Store: ChromaDB (persistent)

\- No server to host; persists to disk (backend/chroma\_store/)

\- Native cosine similarity

\- Safe to re-ingest (collection is deleted and recreated)



\### LLM: Groq Llama 3.3 70B (Free)

\- Completely free, no credit card required

\- Very fast response times

\- Excellent quality for legal Q\&A tasks



\### SQL Schema

```sql

CREATE TABLE query\_logs (

&#x20;   id           INTEGER PRIMARY KEY AUTOINCREMENT,

&#x20;   query        TEXT    NOT NULL,

&#x20;   answer       TEXT    NOT NULL,

&#x20;   answer\_found INTEGER NOT NULL DEFAULT 1,

&#x20;   latency\_ms   REAL    NOT NULL,

&#x20;   num\_sources  INTEGER NOT NULL DEFAULT 0,

&#x20;   created\_at   TEXT    NOT NULL

);

```

`answer\_found` as an integer flag makes `SUM(CASE WHEN ...)` and filtering straightforward in SQL.



\---



\## Project Structure
rag\_qa\_system/



├── backend/



│   ├── main.py          # FastAPI app (endpoints)



│   ├── rag.py           # RAG pipeline (parse, chunk, embed, retrieve, answer)



│   ├── database.py      # SQLite init, logging, analytics queries



│   ├── models.py        # Pydantic request/response models



│   └── requirements.txt



├── frontend/



│   ├── app.py           # Streamlit UI



│   └── requirements.txt



├── data/



│   └── aws\_agreement.pdf



├── scripts/



│   └── seed\_queries.py  # fires 35 test queries for demo analytics



└── README.md

---



\## Setup and Run Instructions



\### Prerequisites

\- Python 3.11

\- A Groq API key (free at https://console.groq.com)



\### 1. Clone the repo

```bash

git clone https://github.com/suhas1906/rag\_qa\_system.git

cd rag\_qa\_system

```



\### 2. Place the PDF

Copy the AWS Customer Agreement PDF to:data/aws\_agreement.pdf

### 3. Install backend dependencies

```bash

cd backend

python -m venv venv

source venv/Scripts/activate

pip install -r requirements.txt

pip install groq

```



\### 4. Set your Groq API key

```bash

export GROQ\_API\_KEY="your-groq-key-here"

```



\### 5. Start the FastAPI server

```bash

uvicorn main:app --reload --port 8000

```

API docs available at http://localhost:8000/docs



\### 6. Ingest the document

```bash

curl -X POST http://localhost:8000/ingest

```



\### 7. Install frontend dependencies (new terminal)

```bash

cd frontend

python -m venv venv\_frontend

source venv\_frontend/Scripts/activate

pip install -r requirements.txt

```



\### 8. Start the Streamlit app

```bash

streamlit run app.py --server.port 8501

```

Open http://localhost:8501 in your browser.



\### 9. Seed test queries (optional - populates analytics)

```bash

cd ..

python scripts/seed\_queries.py

```



\---



\## API Reference



| Method | Endpoint | Description |

|--------|----------|-------------|

| `POST` | `/ingest` | Parse, chunk, embed, and store the PDF |

| `POST` | `/ask` | Ask a question; returns answer + sources + logs interaction |

| `GET`  | `/analytics` | SQL-backed usage analytics |

| `GET`  | `/health` | Liveness probe |



\### POST /ask Example

```bash

curl -X POST http://localhost:8000/ask \\

&#x20; -H "Content-Type: application/json" \\

&#x20; -d '{"query": "What are the payment terms?"}'

```



Response:

```json

{

&#x20; "query": "What are the payment terms?",

&#x20; "answer": "According to Section 3...",

&#x20; "sources": \[{"text": "...", "page": 3, "chunk\_index": 12}],

&#x20; "latency\_ms": 1243.5,

&#x20; "answer\_found": true

}

```



\---



\## Assumptions

1\. The PDF is machine-readable (not a scanned image)

2\. A single ChromaDB collection holds all chunks

3\. Streamlit and FastAPI run as separate processes on the same machine

4\. GROQ\_API\_KEY is available as an environment variable at server startup

