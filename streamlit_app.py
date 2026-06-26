"""Streamlit channel — chat UI over the shared RAG + memory + guardrails pipeline.

Run locally:  streamlit run streamlit_app.py
"""
import os
import tempfile

import streamlit as st

from app import config, llm, pipeline
from app.memory import ConversationMemory
from app.rag import get_store

st.set_page_config(
    page_title="Oakridge Handbook Assistant",
    page_icon="📖",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── theme: dark glassmorphism + warm amber ─────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* layered dark background with soft amber + cool glows for glass to refract */
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(1100px 620px at 88% -12%, rgba(245,158,11,0.16), transparent 60%),
            radial-gradient(900px 520px at 2% 112%, rgba(56,120,200,0.12), transparent 55%),
            linear-gradient(180deg, #0a0f1c 0%, #080c16 100%);
        color: #e7ecf3;
    }
    html, body, [class*="css"], button, input, textarea { font-family: 'Inter', sans-serif; }

    /* hide Streamlit chrome for a standalone-app feel */
    #MainMenu, header[data-testid="stHeader"], footer,
    [data-testid="stToolbar"], [data-testid="stDecoration"],
    [data-testid="stStatusWidget"] { display: none !important; }

    /* glass chat bubbles */
    [data-testid="stChatMessage"] {
        background: rgba(255,255,255,0.055);
        backdrop-filter: blur(14px) saturate(140%);
        -webkit-backdrop-filter: blur(14px) saturate(140%);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 18px;
        padding: 0.35rem 0.95rem;
        margin-bottom: 0.55rem;
        box-shadow: 0 10px 34px rgba(0,0,0,0.28);
    }

    /* glass sidebar */
    [data-testid="stSidebar"] > div:first-child {
        background: rgba(255,255,255,0.045);
        backdrop-filter: blur(16px) saturate(140%);
        -webkit-backdrop-filter: blur(16px) saturate(140%);
        border-right: 1px solid rgba(255,255,255,0.08);
    }

    /* amber glass buttons + example chips */
    .stButton > button {
        background: rgba(245,158,11,0.10);
        color: #fde9c8;
        border: 1px solid rgba(245,158,11,0.35);
        border-radius: 14px;
        padding: 0.6rem 0.95rem;
        font-weight: 500;
        line-height: 1.25;
        backdrop-filter: blur(8px);
        transition: all .18s ease;
    }
    .stButton > button:hover {
        background: rgba(245,158,11,0.20);
        border-color: rgba(245,158,11,0.65);
        transform: translateY(-1px);
        box-shadow: 0 8px 22px rgba(245,158,11,0.20);
    }

    /* glass chat input + file uploader */
    [data-testid="stChatInput"] {
        background: rgba(255,255,255,0.06);
        backdrop-filter: blur(14px);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 16px;
    }
    [data-testid="stChatInput"] textarea { color: #e7ecf3; }
    [data-testid="stFileUploaderDropzone"] {
        background: rgba(255,255,255,0.04);
        border: 1px dashed rgba(255,255,255,0.18);
        border-radius: 14px;
    }

    /* header + welcome card */
    .app-header h1 {
        font-weight: 700; letter-spacing: -0.025em;
        font-size: 1.9rem; margin: 0.2rem 0 0.15rem 0;
    }
    .app-sub { color: #95a3ba; font-size: 0.93rem; margin-bottom: 1.1rem; }
    .welcome-card {
        background: rgba(255,255,255,0.05);
        backdrop-filter: blur(14px) saturate(140%);
        -webkit-backdrop-filter: blur(14px) saturate(140%);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 18px;
        padding: 1.15rem 1.35rem;
        margin-bottom: 0.85rem;
        box-shadow: 0 10px 34px rgba(0,0,0,0.28);
    }
    .welcome-card h3 { margin: 0 0 0.35rem 0; font-weight: 600; }
    .welcome-card p { color: #95a3ba; margin: 0; font-size: 0.93rem; line-height: 1.5; }
    .chips-label {
        color: #8b98ae; font-size: 0.74rem; text-transform: uppercase;
        letter-spacing: 0.10em; margin: 0.5rem 0 0.35rem 2px;
    }

    /* accents */
    [data-testid="stMetricValue"] { color: #fbbf24; }
    a, a:visited { color: #fbbf24; }
    ::selection { background: rgba(245,158,11,0.30); }
    ::-webkit-scrollbar { width: 9px; height: 9px; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.14); border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

EXAMPLES = [
    "What's the dress code on Fridays?",
    "When is a student placed on academic probation?",
    "How many unexcused absences void course credit?",
    "What happens if I'm caught cheating?",
]
ASSISTANT_AVATAR = "📖"
USER_AVATAR = "🧑‍🎓"

# ── session state ──────────────────────────────────────────────────────────────
if "store" not in st.session_state:
    st.session_state.store = get_store()
if "memory" not in st.session_state:
    st.session_state.memory = ConversationMemory(summarize_fn=llm.summarize)
if "messages" not in st.session_state:
    st.session_state.messages = []
store = st.session_state.store

# ── sidebar: knowledge base + PDF upload ───────────────────────────────────────
with st.sidebar:
    st.markdown("### 📚 Knowledge base")
    st.metric("Indexed chunks", store.count())
    if store.sources():
        st.caption("Sources: " + ", ".join(store.sources()))
    if config.LLM_PROVIDER != "gemini":
        st.warning("Running in **mock** mode — set `GEMINI_API_KEY` for real answers.")

    st.divider()
    uploads = st.file_uploader("Add PDF(s) to the knowledge base", type="pdf",
                               accept_multiple_files=True)
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
st.markdown(
    '<div class="app-header"><h1>Oakridge Handbook Assistant</h1>'
    '<div class="app-sub">Answers drawn straight from the student handbook — '
    'with the source and page cited.</div></div>',
    unsafe_allow_html=True,
)

# ── resolve the prompt: typed input OR a clicked example chip ───────────────────
typed = st.chat_input("Ask about the handbook…")
prompt = typed or st.session_state.pop("pending", None)

# ── welcome + example chips (only on an empty conversation) ─────────────────────
if not st.session_state.messages and not prompt:
    st.markdown(
        '<div class="welcome-card"><h3>Welcome 👋</h3>'
        "<p>Ask about academics, attendance, conduct, dress code, or campus policies. "
        "I only answer from the handbook, and I'll tell you plainly if something isn't "
        "covered.</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="chips-label">Try asking</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, q in enumerate(EXAMPLES):
        if cols[i % 2].button(q, key=f"ex_{i}", use_container_width=True):
            st.session_state.pending = q
            st.rerun()

# ── conversation history ──────────────────────────────────────────────────────
for m in st.session_state.messages:
    avatar = ASSISTANT_AVATAR if m["role"] == "assistant" else USER_AVATAR
    with st.chat_message(m["role"], avatar=avatar):
        st.markdown(m["content"])

# ── handle a new prompt ────────────────────────────────────────────────────────
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        stream = pipeline.answer_stream(prompt, st.session_state.memory, store, channel="streamlit")
        full = st.write_stream(stream)
    st.session_state.messages.append({"role": "assistant", "content": full})
