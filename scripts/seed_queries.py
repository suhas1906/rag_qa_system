"""
Seed script — fires 30+ test queries at the /ask endpoint so the
analytics dashboard has realistic data to display.

Usage:
    python scripts/seed_queries.py

Make sure the FastAPI server is running and the PDF has been ingested first.
"""

import time
import requests

API_BASE = "http://localhost:8000"

QUERIES = [
    # --- Answerable ---
    "What are the payment terms in the AWS Customer Agreement?",
    "How can I terminate my AWS account?",
    "What is the governing law for the AWS Customer Agreement?",
    "Does AWS provide any service level agreements?",
    "What are AWS's responsibilities regarding data privacy?",
    "What happens to my data if I terminate my account?",
    "Can AWS suspend my account? Under what conditions?",
    "What is the dispute resolution process?",
    "Are there any restrictions on how I can use AWS services?",
    "What intellectual property rights does AWS retain?",
    "How does AWS handle confidential information?",
    "What are the limitations of liability in the agreement?",
    "What indemnification obligations do I have?",
    "Can I transfer my AWS account to another party?",
    "How are fees calculated for AWS services?",
    "What notice period is required to terminate the agreement?",
    "Does the agreement cover third-party services?",
    "What are the acceptable use policies?",
    "What security obligations does AWS have?",
    "How does AWS handle changes to the agreement?",
    "What warranties does AWS provide?",
    "Are there any export control restrictions?",
    "What happens during an account suspension?",
    "How can I dispute a charge on my AWS bill?",
    "What is the difference between AWS content and my content?",

    # --- Out of scope ---
    "What is the capital of France?",
    "Who won the FIFA World Cup in 2022?",
    "How do I bake chocolate chip cookies?",
    "What is the meaning of life?",
    "Tell me about quantum computing research in 2025.",
]

REPEAT_QUERIES = [
    "What are the payment terms in the AWS Customer Agreement?",
    "Can AWS suspend my account? Under what conditions?",
    "How can I terminate my AWS account?",
    "What are the limitations of liability in the agreement?",
    "What is the capital of France?",
]

ALL_QUERIES = QUERIES + REPEAT_QUERIES


def main():
    print(f"Sending {len(ALL_QUERIES)} queries to {API_BASE}/ask ...\n")
    for i, query in enumerate(ALL_QUERIES, 1):
        try:
            resp = requests.post(
                f"{API_BASE}/ask",
                json={"query": query},
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                status = "✅" if data["answer_found"] else "❌"
                print(f"[{i:02d}] {status} ({data['latency_ms']:.0f}ms) {query[:70]}")
            else:
                print(f"[{i:02d}] ERROR {resp.status_code}: {resp.text[:80]}")
        except Exception as exc:
            print(f"[{i:02d}] EXCEPTION: {exc}")
        time.sleep(0.5)

    print("\nDone! Check the analytics dashboard.")


if __name__ == "__main__":
    main()