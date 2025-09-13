# tests/test_embedding_comparison.py

import ast
import numpy as np
from time import perf_counter
from sqlalchemy import text
from sentence_transformers import SentenceTransformer

from core.ai.ai import call_vec_api
from core.database.database import get_db_session

# -----------------------------
# Config
# -----------------------------
QUERY = "cars"
NUM_DOCS = 150   # fetch 500 for re-embed test
USER_ID = 1
TOP_K = 10

# -----------------------------
# DB Fetch
# -----------------------------
def fetch_documents(user_id: int, limit: int = NUM_DOCS):
    session = get_db_session()
    try:
        sql = text("""
            SELECT id, file_path, tags, tags_vector
            FROM data
            WHERE user_id = :uid
              AND tags IS NOT NULL
              AND tags_vector IS NOT NULL
            ORDER BY RANDOM()
            LIMIT :lim
        """)
        rows = session.execute(sql, {"uid": user_id, "lim": limit}).fetchall()
        return [
            {
                "id": r[0],
                "file_path": r[1],
                "tags": r[2],
                "tags_vector": (
                    r[3] if isinstance(r[3], (list, np.ndarray))
                    else ast.literal_eval(r[3])
                )
            }
            for r in rows
        ]
    finally:
        session.close()

# -----------------------------
# Remote query vs DB embeddings
# -----------------------------
def run_remote(query, docs):
    print("\n=== Remote Query vs Saved DB Embeddings ===")
    t0 = perf_counter()
    q_vec = call_vec_api(query, task_type="RETRIEVAL_QUERY")
    dt = perf_counter() - t0

    if not q_vec:
        print("Remote query embedding missing (check GEMINI_API_KEY).")
        return None, None

    q_vec = np.array(q_vec, dtype=float)
    d_vecs = np.vstack([np.array(d["tags_vector"], dtype=float) for d in docs])

    q_norm = q_vec / np.linalg.norm(q_vec)
    d_norms = d_vecs / np.linalg.norm(d_vecs, axis=1, keepdims=True)
    sims = np.dot(d_norms, q_norm)
    ranking = np.argsort(-sims)

    print(f"Remote query latency: {dt:.3f}s")
    return sims, ranking

# -----------------------------
# Re-embed rows locally
# -----------------------------
def reembed_docs(docs):
    model = SentenceTransformer("google/embeddinggemma-300m")
    print(f"Re-embedding {len(docs)} docs locally...")
    t0 = perf_counter()
    new_vecs = model.encode([d["tags"] for d in docs], convert_to_numpy=True, batch_size=4, show_progress_bar=True)
    dt = perf_counter() - t0
    print(f"Re-embedding latency: {dt:.3f}s")
    for d, vec in zip(docs, new_vecs):
        d["tags_vector_re"] = vec
    return docs, model

# -----------------------------
# Local query vs re-embedded docs
# -----------------------------
def run_local_re(query, docs, model):
    print("\n=== Local Query vs Locally Re-embedded Docs ===")
    q_vec = model.encode(query, convert_to_numpy=True)
    d_vecs = np.vstack([np.array(d["tags_vector_re"], dtype=float) for d in docs])

    q_norm = q_vec / np.linalg.norm(q_vec)
    d_norms = d_vecs / np.linalg.norm(d_vecs, axis=1, keepdims=True)
    sims = np.dot(d_norms, q_norm)
    ranking = np.argsort(-sims)
    return sims, ranking

# -----------------------------
# Utility
# -----------------------------
def print_top_results(name, sims, ranking, docs, k=TOP_K):
    print(f"\n=== Top {k} Results: {name} ===")
    for i in range(min(k, len(docs))):
        idx = ranking[i]
        sim = sims[idx]
        doc = docs[idx]
        print(f"{i+1:02d}. {doc['file_path']} | sim={sim:.3f} | {doc['tags'][:100]}...")

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    docs = fetch_documents(USER_ID, NUM_DOCS)
    if not docs:
        print("No docs found for this user.")
        exit()
    print(f"Fetched {len(docs)} documents from DB")

    # Step 1: Remote query vs existing DB embeddings
    remote_sims, remote_rank = run_remote(QUERY, docs)
    if remote_sims is not None:
        print_top_results("Remote Query vs DB Embeddings", remote_sims, remote_rank, docs, TOP_K)

    # Step 2: Re-embed same docs locally
    re_docs, model = reembed_docs(docs)

    # Step 3: Local query vs locally re-embedded docs
    re_sims, re_rank = run_local_re(QUERY, re_docs, model)
    if re_sims is not None:
        print_top_results("Local Query vs Local Re-embeddings", re_sims, re_rank, re_docs, TOP_K)
