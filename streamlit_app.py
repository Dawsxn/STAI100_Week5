"""Streamlit channel — chat UI over the shared RAG + memory + guardrails pipeline.

Run locally:  streamlit run streamlit_app.py
"""
import os
import tempfile

import streamlit as st

from app import config, llm, pipeline
from app.memory import ConversationMemory
from app.rag import get_store

st.set_page_config(page_title="Oakridge Support Bot", page_icon="🎓", layout="centered")

# ── session state ────────────────────────────────────────────────────────────
if "store" not in st.session_state:
    st.session_state.store = get_store()
if "memory" not in st.session_state:
    st.session_state.memory = ConversationMemory(summarize_fn=llm.summarize)
if "messages" not in st.session_state:
    st.session_state.messages = []

store = st.session_state.store

# ── sidebar: knowledge base + PDF upload ───────────────────────────────────────
with st.sidebar:
    st.header("📚 Knowledge Base")
    st.metric("Indexed chunks", store.count())
    if store.sources():
        st.caption("Sources: " + ", ".join(store.sources()))
    if config.LLM_PROVIDER != "gemini":
        st.warning("Running in **MOCK** mode — set `GEMINI_API_KEY` for real answers.")

    st.divider()
    uploads = st.file_uploader(
        "Add PDF(s) to the knowledge base", type="pdf", accept_multiple_files=True
    )
    if uploads and st.button("Index uploaded PDF(s)", use_container_width=True):
        added = 0
        with st.spinner("Embedding and indexing…"):
            for up in uploads:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(up.getbuffer())
                    tmp_path = tmp.name
                try:
                    added += store.add_pdf(tmp_path, source=up.name)
                finally:
                    os.unlink(tmp_path)
        st.success(f"Added {added} chunks from {len(uploads)} file(s).")
        st.rerun()

    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.memory = ConversationMemory(summarize_fn=llm.summarize)
        st.rerun()

# ── header ──────────────────────────────────────────────────────────────────
st.title("🎓 Oakridge Academy Support Bot")
st.caption("RAG + conversation memory + 3-layer guardrails · Week 5 dual-channel demo")

# ── render history ────────────────────────────────────────────────────────────
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ── input + streamed response ──────────────────────────────────────────────────
if prompt := st.chat_input("Ask about the handbook (academics, conduct, dress code…)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        stream = pipeline.answer_stream(
            prompt, st.session_state.memory, store, channel="streamlit"
        )
        full = st.write_stream(stream)
    st.session_state.messages.append({"role": "assistant", "content": full})
