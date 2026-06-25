"""RAG: PDF ingestion, recursive chunking, in-memory vector store, MMR retrieval.

A lightweight numpy store is used instead of ChromaDB to keep the Docker image well under
500MB (no onnxruntime / torch). The corpus here is small (a handbook + a few uploads), so
exact cosine similarity is plenty fast. Retrieval semantics — cosine similarity + Maximal
Marginal Relevance, k=3 — mirror the Week 3 lab.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass

import numpy as np
from pypdf import PdfReader

from app import config
from app.llm import Embeddings


# ── Recursive character splitter (faithful to LangChain's RecursiveCharacterTextSplitter) ──
def recursive_split(text: str, chunk_size: int, overlap: int,
                    separators: list[str] | None = None) -> list[str]:
    separators = separators if separators is not None else ["\n\n", "\n", ". ", " ", ""]
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    sep = next((s for s in separators if s and s in text), "")
    if sep == "":  # last resort: hard character split
        step = max(1, chunk_size - overlap)
        return [text[i:i + chunk_size] for i in range(0, len(text), step)]

    chunks: list[str] = []
    current = ""
    for piece in text.split(sep):
        candidate = (current + sep + piece) if current else piece
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(piece) > chunk_size:
                chunks.extend(recursive_split(piece, chunk_size, overlap, separators[1:]))
                current = ""
            else:
                current = piece
    if current:
        chunks.append(current)

    # sliding-window overlap between consecutive chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for prev, nxt in zip(chunks, chunks[1:]):
            overlapped.append((prev[-overlap:] + " " + nxt).strip())
        chunks = overlapped
    return [c for c in chunks if c.strip()]


def load_pdf_chunks(path: str, source: str) -> list[dict]:
    reader = PdfReader(path)
    chunks: list[dict] = []
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        for piece in recursive_split(page_text, config.CHUNK_SIZE, config.CHUNK_OVERLAP):
            chunks.append({"text": piece, "source": source, "page": page_num})
    return chunks


@dataclass
class Hit:
    text: str
    source: str
    page: int
    score: float


class VectorStore:
    def __init__(self):
        self._emb = Embeddings()
        self._vectors: np.ndarray | None = None   # (N, D)
        self._meta: list[dict] = []               # [{"text", "source", "page"}]
        self._lock = threading.Lock()

    def count(self) -> int:
        return len(self._meta)

    def sources(self) -> list[str]:
        return sorted({m["source"] for m in self._meta})

    def add_chunks(self, chunks: list[dict]) -> int:
        if not chunks:
            return 0
        vecs = np.array(self._emb.embed_documents([c["text"] for c in chunks]), dtype=np.float32)
        with self._lock:
            self._vectors = vecs if self._vectors is None else np.vstack([self._vectors, vecs])
            self._meta.extend(chunks)
        return len(chunks)

    def add_pdf(self, path: str, source: str) -> int:
        return self.add_chunks(load_pdf_chunks(path, source))

    def _normalized(self) -> tuple[np.ndarray, np.ndarray]:
        mat = self._vectors
        return mat, mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)

    def mmr_search(self, query: str, k: int | None = None, fetch_k: int | None = None,
                   lambda_mult: float | None = None) -> list[Hit]:
        if self._vectors is None or not self._meta:
            return []
        k = k or config.RETRIEVAL_K
        fetch_k = fetch_k or config.FETCH_K
        lambda_mult = config.MMR_LAMBDA if lambda_mult is None else lambda_mult

        q = np.array(self._emb.embed_query(query), dtype=np.float32)
        qn = q / (np.linalg.norm(q) + 1e-8)
        _, normed = self._normalized()
        sims = normed @ qn  # cosine similarity (N,)

        n = len(self._meta)
        fetch_k, k = min(fetch_k, n), min(k, n)
        candidates = list(np.argsort(-sims)[:fetch_k])

        selected: list[int] = []
        while candidates and len(selected) < k:
            if not selected:
                best = candidates[0]
            else:
                best, best_score = candidates[0], -1e9
                for idx in candidates:
                    diversity = max(float(normed[idx] @ normed[s]) for s in selected)
                    mmr = lambda_mult * float(sims[idx]) - (1 - lambda_mult) * diversity
                    if mmr > best_score:
                        best_score, best = mmr, idx
            selected.append(best)
            candidates.remove(best)

        return [
            Hit(self._meta[i]["text"], self._meta[i]["source"], self._meta[i]["page"], float(sims[i]))
            for i in selected
        ]


# ── process-wide singleton, seeded with the handbook on first use ──────────────────
_STORE: VectorStore | None = None
_STORE_LOCK = threading.Lock()


def get_store() -> VectorStore:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                store = VectorStore()
                if os.path.exists(config.SEED_PDF):
                    store.add_pdf(config.SEED_PDF, source="school_handbook.pdf")
                _STORE = store
    return _STORE
