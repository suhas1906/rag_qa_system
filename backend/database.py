"""
SQLite database for logging queries and analytics.

Schema design rationale:
- query_logs is the central table; each row = one /ask call
- answer_found flag lets us easily GROUP BY answered vs unanswered
- latency_ms stored as REAL so AVG() works directly
- created_at stored as TEXT in ISO-8601 for easy strftime() grouping
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "logs.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection with row_factory set for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist yet."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                query       TEXT    NOT NULL,
                answer      TEXT    NOT NULL,
                answer_found INTEGER NOT NULL DEFAULT 1,
                latency_ms  REAL    NOT NULL,
                num_sources INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.commit()


def log_query(
    query: str,
    answer: str,
    answer_found: bool,
    latency_ms: float,
    num_sources: int,
) -> None:
    """Insert one query log row."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO query_logs (query, answer, answer_found, latency_ms, num_sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                query,
                answer,
                1 if answer_found else 0,
                latency_ms,
                num_sources,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def get_analytics() -> dict:
    """
    Run all analytics SQL queries and return a single dict.
    Uses GROUP BY / COUNT / AVG as required by the assignment.
    """
    with get_connection() as conn:

        totals = conn.execute("""
            SELECT
                COUNT(*)                                AS total_queries,
                ROUND(AVG(latency_ms), 2)               AS avg_latency_ms,
                SUM(CASE WHEN answer_found=0 THEN 1 ELSE 0 END) AS unanswered_queries
            FROM query_logs
        """).fetchone()

        total_queries    = totals["total_queries"] or 0
        avg_latency_ms   = totals["avg_latency_ms"] or 0.0
        unanswered_count = totals["unanswered_queries"] or 0
        unanswered_rate  = round((unanswered_count / total_queries * 100), 1) if total_queries else 0.0

        top_questions = conn.execute("""
            SELECT query, COUNT(*) AS ask_count
            FROM query_logs
            GROUP BY query
            ORDER BY ask_count DESC
            LIMIT 10
        """).fetchall()

        unanswered = conn.execute("""
            SELECT query, COUNT(*) AS ask_count
            FROM query_logs
            WHERE answer_found = 0
            GROUP BY query
            ORDER BY ask_count DESC
            LIMIT 10
        """).fetchall()

        over_time = conn.execute("""
            SELECT
                strftime('%Y-%m-%d', created_at) AS day,
                COUNT(*) AS query_count
            FROM query_logs
            GROUP BY day
            ORDER BY day
        """).fetchall()

    return {
        "total_queries":       total_queries,
        "avg_latency_ms":      avg_latency_ms,
        "unanswered_queries":  unanswered_count,
        "unanswered_rate_pct": unanswered_rate,
        "top_questions":       [dict(r) for r in top_questions],
        "unanswered_questions":[dict(r) for r in unanswered],
        "queries_over_time":   [dict(r) for r in over_time],
    }