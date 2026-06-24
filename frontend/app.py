"""
Streamlit frontend for the RAG Document Q&A system.
"""

import pandas as pd
import requests
import streamlit as st

API_BASE = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AWS Agreement Q&A",
    page_icon="📄",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📄 AWS Agreement Q&A")
    st.markdown("---")
    st.subheader("Setup")

    if st.button("📥 Ingest Document", use_container_width=True):
        with st.spinner("Ingesting PDF..."):
            try:
                resp = requests.post(f"{API_BASE}/ingest", timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(f"✅ Ingested! {data['chunks_created']} chunks created.")
                else:
                    st.error(f"Error {resp.status_code}: {resp.json().get('detail')}")
            except requests.ConnectionError:
                st.error("Cannot reach the FastAPI backend. Is it running?")

    st.markdown("---")
    st.caption("Built with FastAPI · ChromaDB · sentence-transformers · Claude")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_chat, tab_analytics = st.tabs(["💬 Chat", "📊 Analytics"])

# ===========================================================================
# Chat tab
# ===========================================================================

with tab_chat:
    st.header("Ask a question about the AWS Customer Agreement")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander("📚 Source chunks"):
                    for i, src in enumerate(msg["sources"], 1):
                        st.markdown(f"**Source {i} — Page {src.get('page', '?')}**")
                        st.text(src["text"][:600] + ("…" if len(src["text"]) > 600 else ""))

    if prompt := st.chat_input("E.g. What are the payment terms in the AWS agreement?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    resp = requests.post(
                        f"{API_BASE}/ask",
                        json={"query": prompt},
                        timeout=60,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        answer  = data["answer"]
                        sources = data["sources"]
                        latency = data["latency_ms"]
                        found   = data["answer_found"]

                        st.markdown(answer)
                        st.caption(f"⏱ {latency:.0f} ms  |  {'✅ Answer found' if found else '❌ Not in document'}")

                        if sources:
                            with st.expander("📚 Source chunks"):
                                for i, src in enumerate(sources, 1):
                                    st.markdown(f"**Source {i} — Page {src.get('page', '?')}**")
                                    st.text(src["text"][:600] + ("…" if len(src["text"]) > 600 else ""))

                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "sources": sources,
                        })
                    elif resp.status_code == 409:
                        st.warning("Document not ingested yet. Click 'Ingest Document' in the sidebar first.")
                    else:
                        detail = resp.json().get("detail", "Unknown error")
                        st.error(f"Error {resp.status_code}: {detail}")
                except requests.ConnectionError:
                    st.error("Cannot reach the FastAPI backend. Is it running on port 8000?")

# ===========================================================================
# Analytics tab
# ===========================================================================

with tab_analytics:
    st.header("📊 Usage Analytics")

    if st.button("🔄 Refresh", key="refresh_analytics"):
        st.rerun()

    try:
        resp = requests.get(f"{API_BASE}/analytics", timeout=15)
        if resp.status_code != 200:
            st.error(f"Analytics endpoint error: {resp.status_code}")
        else:
            data = resp.json()

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Queries",      data["total_queries"])
            col2.metric("Avg Latency (ms)",   f"{data['avg_latency_ms']:.0f}")
            col3.metric("Unanswered Queries", data["unanswered_queries"])
            col4.metric("Unanswered Rate",    f"{data['unanswered_rate_pct']:.1f}%")

            st.markdown("---")

            col_left, col_right = st.columns(2)

            with col_left:
                st.subheader("🔝 Most Frequently Asked Questions")
                if data["top_questions"]:
                    df_top = pd.DataFrame(data["top_questions"])
                    df_top.columns = ["Question", "Count"]
                    st.dataframe(df_top, use_container_width=True, hide_index=True)
                else:
                    st.info("No data yet.")

            with col_right:
                st.subheader("❌ Unanswered Questions")
                if data["unanswered_questions"]:
                    df_un = pd.DataFrame(data["unanswered_questions"])
                    df_un.columns = ["Question", "Count"]
                    st.dataframe(df_un, use_container_width=True, hide_index=True)
                else:
                    st.success("All questions answered so far!")

            st.markdown("---")
            st.subheader("📅 Queries Over Time")
            if data["queries_over_time"]:
                df_time = pd.DataFrame(data["queries_over_time"])
                df_time.columns = ["Day", "Queries"]
                df_time = df_time.set_index("Day")
                st.bar_chart(df_time)
            else:
                st.info("No data yet.")

    except requests.ConnectionError:
        st.error("Cannot reach the FastAPI backend. Is it running on port 8000?")