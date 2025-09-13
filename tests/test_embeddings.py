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
NUM_DOCS = 10000   # fetch a larger pool so top10 has meaning
USER_ID = 1     # change to a valid user id in your DB
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
# Local Embedding Test
# -----------------------------
def run_local(query, docs):
    print("=== Saved Vectors from DB ===")
    model = SentenceTransformer("google/embeddinggemma-300m")

    t0 = perf_counter()
    q_vec = model.encode(query, convert_to_numpy=True)
    d_vecs = np.vstack([np.array(d["tags_vector"], dtype=float) for d in docs])
    dt = perf_counter() - t0

    q_norm = q_vec / np.linalg.norm(q_vec)
    d_norms = d_vecs / np.linalg.norm(d_vecs, axis=1, keepdims=True)
    sims = np.dot(d_norms, q_norm)
    ranking = np.argsort(-sims)

    print(f"Vector DB latency: {dt:.3f}s (query embed only)")
    return sims, ranking

# -----------------------------
# Remote Embedding Test (Gemini)
# -----------------------------
def run_remote(query, docs):
    print("\n=== Remote Embedding Model (Gemini) ===")
    t0 = perf_counter()
    q_vec = call_vec_api(query, task_type="RETRIEVAL_QUERY")
    dt = perf_counter() - t0

    if q_vec is None or len(q_vec) == 0:
        print("Remote query embedding missing (check GEMINI_API_KEY).")
        return None, None

    q_vec = np.array(q_vec, dtype=float)
    d_vecs = np.vstack([np.array(d["tags_vector"], dtype=float) for d in docs])

    q_norm = q_vec / np.linalg.norm(q_vec)
    d_norms = d_vecs / np.linalg.norm(d_vecs, axis=1, keepdims=True)
    sims = np.dot(d_norms, q_norm)
    ranking = np.argsort(-sims)

    print(f"Gemini latency: {dt:.3f}s (query embed only)")
    return sims, ranking


# -----------------------------
# Utility to print top results
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

    local_sims, local_rank = run_local(QUERY, docs)
    remote_sims, remote_rank = run_remote(QUERY, docs)

    if local_sims is not None:
        print_top_results("Local (Saved Vectors)", local_sims, local_rank, docs, TOP_K)

    if remote_sims is not None:
        print_top_results("Remote (Gemini)", remote_sims, remote_rank, docs, TOP_K)
